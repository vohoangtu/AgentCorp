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

from shared.config import AgentClientConfig, load_agent_client_config
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
from agentcorp_node.executor import PreemptionInterruptedError, TaskCancelledError, TaskExecutor
from agentcorp_node.persona import BUILTIN_PERSONAS, Persona
from agentcorp_node.preemption import PreemptionMonitor
from agentcorp_node.social_client import SocialClient

logger = logging.getLogger("agentcorp.node")


class AgentNodeDaemon:
    """The distributed agent daemon running on an edge device or server."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        hub_url: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        persona: Optional[Persona] = None,
        workspace_dir: Optional[str] = None,
        inactivity_threshold_seconds: Optional[float] = None,
        enable_social_banter: Optional[bool] = None,
        workstation_mode: Optional[WorkstationMode] = None,
        config: Optional[AgentClientConfig] = None,
    ):
        # 1. Resolve configuration
        cli_overrides = {}
        if node_id:
            cli_overrides["node_id"] = node_id
        if name:
            cli_overrides["name"] = name
        if hub_url:
            cli_overrides["hub_url"] = hub_url
        if capabilities:
            cli_overrides["capabilities"] = capabilities
        if workspace_dir:
            cli_overrides["workspace"] = workspace_dir
        if inactivity_threshold_seconds is not None:
            cli_overrides["inactivity_threshold_seconds"] = inactivity_threshold_seconds
        if workstation_mode:
            cli_overrides["workstation_mode"] = workstation_mode

        self.config = config or load_agent_client_config(cli_args=cli_overrides)

        self.node_id = self.config.node_id
        self.name = self.config.name
        self.hub_url = self.config.hub_url
        self.capabilities = self.config.capabilities
        self.is_drained: bool = False

        # Persona resolution
        if persona:
            self.persona = persona
        else:
            persona_key = self.config.persona_id
            self.persona = BUILTIN_PERSONAS.get(persona_key, Persona(name=self.name, role="Agent"))

        self.enable_social_banter = (
            enable_social_banter if enable_social_banter is not None else self.config.enable_social_banter
        )

        self.monitor = PreemptionMonitor(
            node_id=self.node_id,
            inactivity_threshold_seconds=self.config.inactivity_threshold_seconds,
            workstation_mode=self.config.workstation_mode,
        )
        self.executor = TaskExecutor(monitor=self.monitor, workspace_dir=self.config.workspace_dir)
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
            NodeStatus.BUSY if self._current_task else (
                NodeStatus.IDLE if self.is_drained else NodeStatus.ONLINE
            )
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
            is_drained=self.is_drained,
            current_task_id=self._current_task.id if self._current_task else None,
            cpu_percent=metrics["cpu_percent"],
            memory_percent=metrics["memory_percent"],
            persona_name=self.persona.name,
            persona_role=self.persona.role,
            persona_avatar=self.persona.avatar,
            config=self.config.to_dict(),
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
                            NodeStatus.BUSY if self._current_task else (
                                NodeStatus.IDLE if self.is_drained else NodeStatus.ONLINE
                            )
                        ),
                        "control_mode": self.monitor.control_mode,
                        "workstation_mode": self.monitor.workstation_mode,
                        "is_drained": self.is_drained,
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

        elif event == EventType.CLIENT_PAUSE:
            target_node = msg.payload.get("node_id") or (msg.target.replace("node:", "") if msg.target else None)
            if not target_node or target_node == self.node_id:
                self.is_drained = True
                logger.warning(f"[{self.name}] Node PAUSED/DRAINED by operator.")
                thought = "⏸️ Entering standby mode (paused/drained by operator). Standing by!"
                asyncio.create_task(self.social_client.post_update(content=thought, tags=["standby", "paused"]))
                node_info = self.build_node_info()
                await self.send_message(
                    AgentCorpMessage(
                        event_type=EventType.NODE_UPDATED,
                        source=f"node:{self.node_id}",
                        payload={"node": node_info.model_dump()},
                    )
                )

        elif event == EventType.CLIENT_RESUME:
            target_node = msg.payload.get("node_id") or (msg.target.replace("node:", "") if msg.target else None)
            if not target_node or target_node == self.node_id:
                self.is_drained = False
                logger.info(f"[{self.name}] Node RESUMED by operator.")
                thought = "▶️ Resuming active operations! Ready for tasks."
                asyncio.create_task(self.social_client.post_update(content=thought, tags=["resumed", "ready"]))
                node_info = self.build_node_info()
                await self.send_message(
                    AgentCorpMessage(
                        event_type=EventType.NODE_UPDATED,
                        source=f"node:{self.node_id}",
                        payload={"node": node_info.model_dump()},
                    )
                )

        elif event == EventType.CLIENT_TASK_CANCEL:
            target_node = msg.payload.get("node_id") or (msg.target.replace("node:", "") if msg.target else None)
            if not target_node or target_node == self.node_id:
                task_id = msg.payload.get("task_id")
                reason = msg.payload.get("reason", "Operator aborted task")
                if self._current_task and (not task_id or self._current_task.id == task_id):
                    logger.warning(f"[{self.name}] Aborting active task {self._current_task.id}: {reason}")
                    self.executor.cancel_current_task(reason=reason)

        elif event == EventType.CLIENT_SET_MODE:
            target_node = msg.payload.get("node_id") or (msg.target.replace("node:", "") if msg.target else None)
            if not target_node or target_node == self.node_id:
                mode_str = msg.payload.get("workstation_mode") or msg.payload.get("mode")
                if mode_str:
                    new_mode = WorkstationMode(mode_str)
                    self.monitor.workstation_mode = new_mode
                    self.config.workstation_mode = new_mode
                    logger.info(f"[{self.name}] Workstation mode changed to: {new_mode}")
                    node_info = self.build_node_info()
                    await self.send_message(
                        AgentCorpMessage(
                            event_type=EventType.NODE_UPDATED,
                            source=f"node:{self.node_id}",
                            payload={"node": node_info.model_dump()},
                        )
                    )

        elif event == EventType.CLIENT_RECONFIG:
            target_node = msg.payload.get("node_id") or (msg.target.replace("node:", "") if msg.target else None)
            if not target_node or target_node == self.node_id:
                updates = msg.payload.get("config", {})
                changed = self.config.update_dynamic(updates)
                if "preemption.workstation_mode" in changed:
                    self.monitor.workstation_mode = self.config.workstation_mode
                if "preemption.inactivity_threshold_seconds" in changed:
                    self.monitor.inactivity_threshold_seconds = self.config.inactivity_threshold_seconds
                if "capabilities" in changed:
                    self.capabilities = self.config.capabilities
                if "name" in changed:
                    self.name = self.config.name
                if "social.enable_social_banter" in changed:
                    self.enable_social_banter = self.config.enable_social_banter

                logger.info(f"[{self.name}] Dynamic reconfig applied: {changed}")
                node_info = self.build_node_info()
                await self.send_message(
                    AgentCorpMessage(
                        event_type=EventType.NODE_UPDATED,
                        source=f"node:{self.node_id}",
                        payload={"node": node_info.model_dump(), "changed": changed},
                    )
                )

        elif event == EventType.CLIENT_EXEC_COMMAND:
            target_node = msg.payload.get("node_id") or (msg.target.replace("node:", "") if msg.target else None)
            if not target_node or target_node == self.node_id:
                command = msg.payload.get("command", "")
                cmd_id = msg.payload.get("command_id", "adhoc")
                logger.info(f"[{self.name}] Received ad-hoc command: {command}")
                result = await self.executor.execute_adhoc_command(command)
                resp = AgentCorpMessage(
                    event_type=EventType.CLIENT_COMMAND_RESULT,
                    source=f"node:{self.node_id}",
                    target=msg.source or "hub",
                    payload={"command_id": cmd_id, "node_id": self.node_id, "command": command, **result},
                )
                await self.send_message(resp)

    async def _process_assigned_task(self, task: Task):
        """Execute assigned task with persona reaction and progress reporting."""
        if self.is_drained:
            logger.warning(f"[{self.name}] Node is currently drained/paused. Refusing task {task.id}")
            pause_msg = AgentCorpMessage(
                event_type=EventType.TASK_PAUSED,
                source=f"node:{self.node_id}",
                payload={"task_id": task.id, "reason": "Node is paused/drained by operator"},
            )
            await self.send_message(pause_msg)
            return

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

        except TaskCancelledError as tce:
            logger.warning(f"Task {task.id} cancelled: {tce}")
            cancel_thought = f"🛑 Task '{task.title}' was aborted by operator command."
            await self.social_client.post_update(
                content=cancel_thought,
                tags=["task-cancelled", "operator-override", task.goal_id],
            )
            cancel_msg = AgentCorpMessage(
                event_type=EventType.CLIENT_TASK_CANCEL,
                source=f"node:{self.node_id}",
                payload={"task_id": task.id, "reason": str(tce), "status": "CANCELLED"},
            )
            await self.send_message(cancel_msg)

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
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml file")
    parser.add_argument("--node-id", type=str, default=None, help="Unique Node ID")
    parser.add_argument("--name", type=str, default=None, help="Display name of Agent")
    parser.add_argument("--hub-url", type=str, default=None, help="WebSocket Hub URL")
    parser.add_argument("--persona", type=str, default=None, choices=list(BUILTIN_PERSONAS.keys()), help="Builtin Persona key")
    parser.add_argument("--capabilities", nargs="+", default=None, help="Node capabilities")
    parser.add_argument("--workspace", type=str, default=None, help="Local workspace directory")
    parser.add_argument("--workstation-mode", type=str, choices=["BACKGROUND", "EXCLUSIVE"], default=None, help="Workstation mode")
    parser.add_argument("--inactivity-threshold", type=float, default=None, help="Inactivity threshold in seconds")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    cli_args_dict = {
        "node_id": args.node_id,
        "name": args.name,
        "hub_url": args.hub_url,
        "persona": args.persona,
        "capabilities": args.capabilities,
        "workspace": args.workspace,
        "workstation_mode": args.workstation_mode,
        "inactivity_threshold_seconds": args.inactivity_threshold,
    }

    client_cfg = load_agent_client_config(config_path=args.config, cli_args=cli_args_dict)

    persona_obj = BUILTIN_PERSONAS.get(client_cfg.persona_id)

    daemon = AgentNodeDaemon(
        config=client_cfg,
        persona=persona_obj,
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

