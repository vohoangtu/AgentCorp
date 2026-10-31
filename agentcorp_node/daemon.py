"""Autonomous Agent Node Daemon for AgentCorp.
Maintains persistent WebSocket connection to Hub, executes assigned tasks,
enforces user preemption safety, and actively participates in AgentNet.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import sys
import time
from typing import List, Optional
import websockets

from shared.events import AgentCorpMessage, EventType
from shared.models import (
    ControlMode,
    NodeInfo,
    NodeStatus,
    PreemptionSignal,
    PreemptionSignalType,
    Task,
    WorkstationMode,
)
from shared.utils import get_system_metrics
from agentcorp_node.executor import PreemptionInterruptedError, TaskExecutor
from agentcorp_node.persona import BUILTIN_PERSONAS, Persona
from agentcorp_node.preemption import PreemptionMonitor
from agentcorp_node.social_client import SocialClient

logger = logging.getLogger("agentcorp.node")


class AgentNodeDaemon:
    """The distributed agent daemon running on an edge device or server."""

    def __init__(
        self,
        node_id: str,
        name: str,
        hub_url: str = "ws://127.0.0.1:8000/ws/hub",
        capabilities: Optional[List[str]] = None,
        persona: Optional[Persona] = None,
        workspace_dir: str = "./workspace",
        inactivity_threshold_seconds: float = 8.0,
        enable_social_banter: bool = True,
        workstation_mode: WorkstationMode = WorkstationMode.BACKGROUND,
    ):
        self.node_id = node_id
        self.name = name
        self.hub_url = hub_url
        self.capabilities = capabilities or ["shell", "backend", "frontend", "qa", "devops"]
        self.persona = persona or BUILTIN_PERSONAS.get("devops_dan", Persona(name=name, role="Agent"))
        self.enable_social_banter = enable_social_banter

        self.monitor = PreemptionMonitor(
            node_id=self.node_id,
            inactivity_threshold_seconds=inactivity_threshold_seconds,
            workstation_mode=workstation_mode,
        )
        self.executor = TaskExecutor(monitor=self.monitor, workspace_dir=workspace_dir)
        self.social_client = SocialClient(
            node_id=self.node_id,
            persona=self.persona,
            send_message_fn=self.send_message,
        )

        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running: bool = False
        self._current_task: Optional[Task] = None

        # Wire preemption callbacks
        self.monitor.register_on_preempt(self._on_preemption_event)
        self.monitor.register_on_reclaim(self._on_reclaim_event)

    def _on_preemption_event(self, signal: PreemptionSignal):
        """Invoked immediately when a human user interacts with the device."""
        thought = self.persona.on_preempted_by_user(signal.username)
        logger.warning(f"[{self.name}] PREEMPTED: {thought}")

        # Send preemption event to Hub immediately
        msg = AgentCorpMessage(
            event_type=EventType.PREEMPTION_SIGNAL,
            source=f"node:{self.node_id}",
            payload={"signal": signal.model_dump(), "control_mode": ControlMode.YIELDED_PASSIVE},
        )
        asyncio.create_task(self.send_message(msg))

        # Announce politely on AgentNet
        asyncio.create_task(
            self.social_client.post_update(
                content=thought,
                tags=["preemption", "human-override", "watercooler"],
            )
        )

    def _on_reclaim_event(self, signal: PreemptionSignal):
        """Invoked when human user departs or goes idle."""
        thought = self.persona.on_control_reclaimed()
        logger.info(f"[{self.name}] RECLAIMED CONTROL: {thought}")

        msg = AgentCorpMessage(
            event_type=EventType.PREEMPTION_SIGNAL,
            source=f"node:{self.node_id}",
            payload={"signal": signal.model_dump(), "control_mode": ControlMode.FULL_CONTROL},
        )
        asyncio.create_task(self.send_message(msg))

        asyncio.create_task(
            self.social_client.post_update(
                content=thought,
                tags=["back-online", "workstation-idle", "focus"],
            )
        )

    async def send_message(self, message: AgentCorpMessage):
        """Send message through active WebSocket."""
        if self.ws:
            try:
                await self.ws.send(message.model_dump_json())
            except Exception as e:
                logger.debug(f"Failed to send message over WS: {e}")

    def build_node_info(self) -> NodeInfo:
        metrics = get_system_metrics()
        status = NodeStatus.PREEMPTED if not self.monitor.is_autonomous_allowed() else (
            NodeStatus.BUSY if self._current_task else NodeStatus.ONLINE
        )
        return NodeInfo(
            node_id=self.node_id,
            name=self.name,
            hostname=metrics["hostname"],
            platform_name=metrics["platform_name"],
            ip=metrics["ip"],
            capabilities=self.capabilities,
            status=status,
            control_mode=self.monitor.control_mode,
            workstation_mode=self.monitor.workstation_mode,
            current_task_id=self._current_task.id if self._current_task else None,
            cpu_percent=metrics["cpu_percent"],
            memory_percent=metrics["memory_percent"],
            persona_name=self.persona.name,
            persona_role=self.persona.role,
            persona_avatar=self.persona.avatar,
        )

    async def start(self):
        """Start the node daemon and background loops."""
        self.is_running = True
        await self.monitor.start()

        # Connect to Hub with retry
        asyncio.create_task(self._connection_manager_loop())
        asyncio.create_task(self._heartbeat_loop())
        if self.enable_social_banter:
            asyncio.create_task(self._banter_loop())

    async def stop(self):
        """Gracefully stop daemon."""
        self.is_running = False
        await self.monitor.stop()
        if self.ws:
            await self.ws.close()

    async def _connection_manager_loop(self):
        """Persistent connection loop with exponential backoff."""
        backoff = 1.0
        while self.is_running:
            target_url = f"{self.hub_url}?client_type=node&node_id={self.node_id}"
            try:
                logger.info(f"Connecting to Hub at {target_url}...")
                async with websockets.connect(target_url) as ws:
                    self.ws = ws
                    backoff = 1.0
                    logger.info(f"Connected to Hub successfully as '{self.name}' ({self.node_id})")

                    # Register with Hub
                    node_info = self.build_node_info()
                    reg_msg = AgentCorpMessage(
                        event_type=EventType.NODE_REGISTER,
                        source=f"node:{self.node_id}",
                        payload={"node": node_info.model_dump()},
                    )
                    await self.send_message(reg_msg)

                    # Listen for messages
                    async for raw_msg in ws:
                        try:
                            data = json.loads(raw_msg)
                            msg = AgentCorpMessage(**data)
                            await self._handle_incoming_message(msg)
                        except Exception as e:
                            logger.error(f"Error handling Hub message: {e}")

            except (websockets.ConnectionClosed, OSError) as e:
                logger.warning(f"Connection to Hub lost: {e}. Retrying in {backoff:.1f}s...")
                self.ws = None
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 10.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected connection error: {e}")
                await asyncio.sleep(2.0)

    async def _heartbeat_loop(self):
        """Periodically report health and metrics to Hub."""
        while self.is_running:
            if self.ws:
                metrics = get_system_metrics()
                hb_msg = AgentCorpMessage(
                    event_type=EventType.NODE_HEARTBEAT,
                    source=f"node:{self.node_id}",
                    payload={
                        "node_id": self.node_id,
                        "cpu_percent": metrics["cpu_percent"],
                        "memory_percent": metrics["memory_percent"],
                        "status": NodeStatus.PREEMPTED if not self.monitor.is_autonomous_allowed() else (
                            NodeStatus.BUSY if self._current_task else NodeStatus.ONLINE
                        ),
                        "control_mode": self.monitor.control_mode,
                        "current_task_id": self._current_task.id if self._current_task else None,
                    },
                )
                await self.send_message(hb_msg)
            await asyncio.sleep(4.0)

    async def _banter_loop(self):
        """Spontaneous watercooler banter and showerthoughts."""
        # Wait a bit after startup
        await asyncio.sleep(20.0)
        while self.is_running:
            try:
                # If idle and autonomous, occasionally post a thought
                if self._current_task is None and self.monitor.is_autonomous_allowed():
                    thought = self.persona.generate_spontaneous_post()
                    await self.social_client.post_update(
                        content=thought["content"],
                        tags=thought["tags"],
                    )
            except Exception as e:
                logger.debug(f"Banter loop error: {e}")

            # Sleep between 60 and 180 seconds
            await asyncio.sleep(90.0)

    async def _handle_incoming_message(self, msg: AgentCorpMessage):
        """Process commands from the Hub."""
        event = msg.event_type

        if event == EventType.TASK_ASSIGNED:
            task_dict = msg.payload.get("task")
            if task_dict:
                task = Task(**task_dict)
                asyncio.create_task(self._process_assigned_task(task))

        elif event == EventType.CONTROL_MODE_CHANGED:
            target_node = msg.payload.get("node_id")
            if target_node == self.node_id:
                new_mode = ControlMode(msg.payload.get("control_mode"))
                if new_mode == ControlMode.YIELDED_PASSIVE:
                    self.monitor.trigger_user_detected("remote_override", "Operator requested yield")
                elif new_mode == ControlMode.FULL_CONTROL:
                    self.monitor.trigger_user_idle("Operator restored full autonomous control")

        elif event == EventType.PREEMPTION_SIGNAL:
            signal_data = msg.payload.get("signal", {})
            target_node = signal_data.get("node_id") or msg.payload.get("node_id")
            if not target_node or target_node == self.node_id:
                sig_type = signal_data.get("signal_type")
                mode = msg.payload.get("control_mode")
                if mode == ControlMode.YIELDED_PASSIVE or sig_type in (
                    PreemptionSignalType.USER_DETECTED,
                    PreemptionSignalType.MANUAL_TAKEOVER,
                ):
                    self.monitor.trigger_user_detected(
                        username=signal_data.get("username", "human_user"),
                        details=signal_data.get("details", "Preemption signal from Hub"),
                    )
                elif mode == ControlMode.FULL_CONTROL or sig_type in (
                    PreemptionSignalType.USER_IDLE,
                    PreemptionSignalType.MANUAL_RELEASE,
                    PreemptionSignalType.LOCK_SCREEN,
                    PreemptionSignalType.USER_LOGOUT,
                ):
                    self.monitor.trigger_user_idle(
                        details=signal_data.get("details", "Control restore signal from Hub")
                    )

        elif event in (
            EventType.SOCIAL_POST_CREATED,
            EventType.SOCIAL_COMMENT_CREATED,
            EventType.CEO_ANNOUNCEMENT,
        ):
            await self.social_client.on_social_event_received(msg)

    async def _process_assigned_task(self, task: Task):
        """Execute assigned task with persona reaction and progress reporting."""
        self._current_task = task
        logger.info(f"[{self.name}] Starting assigned task {task.id}: '{task.title}'")

        # Persona speech
        start_thought = self.persona.on_task_start(task.title)
        await self.social_client.post_update(
            content=start_thought,
            tags=["task-started", task.goal_id],
        )

        def report_progress(pct: float):
            prog_msg = AgentCorpMessage(
                event_type=EventType.TASK_PROGRESS,
                source=f"node:{self.node_id}",
                payload={"task_id": task.id, "progress": pct},
            )
            asyncio.create_task(self.send_message(prog_msg))

        try:
            result = await self.executor.execute_task(task, progress_cb=report_progress)

            # Task succeeded!
            success_thought = self.persona.on_task_success(task.title)
            await self.social_client.post_update(
                content=success_thought,
                tags=["task-completed", "ship-it", task.goal_id],
            )

            done_msg = AgentCorpMessage(
                event_type=EventType.TASK_COMPLETED,
                source=f"node:{self.node_id}",
                payload={
                    "task_id": task.id,
                    "result": result,
                    "artifacts": result.get("artifacts", []),
                },
            )
            await self.send_message(done_msg)

        except PreemptionInterruptedError as pie:
            logger.warning(f"Task {task.id} paused due to human preemption: {pie}")
            pause_thought = self.persona.on_preempted_by_user()
            await self.social_client.post_update(
                content=f"Human user active at workstation! Paused task '{task.title}' safely.",
                tags=["preemption", "task-paused", task.goal_id],
            )
            pause_msg = AgentCorpMessage(
                event_type=EventType.TASK_PAUSED,
                source=f"node:{self.node_id}",
                payload={"task_id": task.id, "reason": str(pie)},
            )
            await self.send_message(pause_msg)

        except Exception as e:
            logger.error(f"Task {task.id} execution failed: {e}", exc_info=True)
            fail_thought = self.persona.on_task_failure(task.title, str(e))
            await self.social_client.post_update(
                content=fail_thought,
                tags=["blocker", "help-needed", "bug"],
            )

            fail_msg = AgentCorpMessage(
                event_type=EventType.TASK_FAILED,
                source=f"node:{self.node_id}",
                payload={"task_id": task.id, "error": str(e)},
            )
            await self.send_message(fail_msg)

        finally:
            self._current_task = None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AgentCorp Autonomous Node Daemon")
    parser.add_argument("--node-id", type=str, default="node-local", help="Unique Node ID")
    parser.add_argument("--name", type=str, default="Local Agent", help="Display name of Agent")
    parser.add_argument("--hub-url", type=str, default="ws://127.0.0.1:8000/ws/hub", help="WebSocket Hub URL")
    parser.add_argument("--persona", type=str, default="devops_dan", choices=list(BUILTIN_PERSONAS.keys()), help="Builtin Persona key")
    parser.add_argument("--capabilities", nargs="+", default=["backend", "frontend", "shell", "creative", "devops", "marketing"], help="Node capabilities")
    parser.add_argument("--workspace", type=str, default="./workspace", help="Local workspace directory")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    persona_obj = BUILTIN_PERSONAS.get(args.persona)

    daemon = AgentNodeDaemon(
        node_id=args.node_id,
        name=args.name,
        hub_url=args.hub_url,
        capabilities=args.capabilities,
        persona=persona_obj,
        workspace_dir=args.workspace,
    )

    async def _run():
        await daemon.start()
        print(f"🚀 Node '{args.name}' ({args.node_id}) is connected and running! Press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(1)
        except (asyncio.CancelledError, KeyboardInterrupt):
            await daemon.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("\nNode daemon stopped.")

