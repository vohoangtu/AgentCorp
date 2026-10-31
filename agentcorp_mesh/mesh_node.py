"""Unified Peer-to-Peer Mesh Agent Node.
Dynamically transitions between Leader (Orchestrator + Worker) and Follower (Worker),
discovering peers automatically via Tailscale.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional
import uvicorn

from shared.models import WorkstationMode
from agentcorp_hub.server import app as hub_app
from agentcorp_node.daemon import AgentNodeDaemon
from agentcorp_node.persona import BUILTIN_PERSONAS, Persona
from agentcorp_mesh.election import MeshElectionManager
from agentcorp_mesh.tailscale_discovery import TailscaleDiscovery, TailscaleNode

logger = logging.getLogger("agentcorp.mesh.node")


class MeshAgentNode:
    """A self-configuring P2P node in the Tailscale network."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        persona: Optional[Persona] = None,
        capabilities: Optional[List[str]] = None,
        port: int = 8000,
        poll_interval: float = 6.0,
        preferred_leaders: Optional[List[str]] = None,
        workstation_mode: WorkstationMode = WorkstationMode.BACKGROUND,
    ):
        self.port = port
        self.poll_interval = poll_interval
        self.workstation_mode = WorkstationMode(workstation_mode)

        # Tailscale Discovery & Election
        self.discovery = TailscaleDiscovery(port=port)
        self.self_tailscale = self.discovery.get_self_node()

        self.node_id = node_id or f"node-{self.self_tailscale.hostname.lower()}"
        self.name = name or f"Agent-{self.self_tailscale.hostname}"
        self.persona = persona or BUILTIN_PERSONAS.get("devops_dan")
        self.capabilities = capabilities or ["shell", "backend", "frontend", "qa", "devops", "marketing"]

        self.election = MeshElectionManager(
            self_node=self.self_tailscale,
            preferred_leaders=preferred_leaders,
        )

        # Runtime instances
        self.hub_server: Optional[uvicorn.Server] = None
        self.hub_task: Optional[asyncio.Task] = None
        self.worker_daemon: Optional[AgentNodeDaemon] = None

        self.is_running: bool = False
        self._watchdog_task: Optional[asyncio.Task] = None
        self._active_leader_ip: Optional[str] = None

    async def start(self):
        """Start the mesh agent node."""
        self.is_running = True
        logger.info(
            f"🌐 [MESH] Starting Peer Node '{self.name}' on {self.self_tailscale.hostname} (Tailscale IP: {self.self_tailscale.ip})"
        )

        # Initial election round
        await self._evaluate_mesh_role()

        # Start background watchdog loop to monitor tailnet peers
        self._watchdog_task = asyncio.create_task(self._mesh_watchdog_loop())

    async def stop(self):
        """Gracefully stop mesh node and any running services."""
        self.is_running = False
        if self._watchdog_task:
            self._watchdog_task.cancel()

        if self.worker_daemon:
            await self.worker_daemon.stop()

        await self._stop_hub()
        logger.info(f"🌐 [MESH] Peer Node '{self.name}' stopped.")

    async def _start_hub(self):
        """Start local Hub server when elected leader."""
        if self.hub_server:
            return  # Already running

        logger.info(f"👑 [LEADER] Node '{self.name}' elected LEADER! Bootstrapping Central Hub on port {self.port}...")
        config = uvicorn.Config(
            app=hub_app,
            host="0.0.0.0",
            port=self.port,
            log_level="warning",
        )
        self.hub_server = uvicorn.Server(config)
        self.hub_task = asyncio.create_task(self.hub_server.serve())
        await asyncio.sleep(1.0)  # Wait for socket bind

    async def _stop_hub(self):
        """Stop local Hub server when stepping down."""
        if self.hub_server:
            logger.info("👋 [LEADER STEP-DOWN] Stopping local Hub server, stepping down to follower.")
            self.hub_server.should_exit = True
            if self.hub_task:
                try:
                    await self.hub_task
                except asyncio.CancelledError:
                    pass
            self.hub_server = None
            self.hub_task = None

    async def _evaluate_mesh_role(self):
        """Discover peers, calculate election, and adjust role."""
        try:
            peers = self.discovery.get_online_peers(include_self=True)
            leader = self.election.elect_leader(peers)

            if self.election.is_self_leader():
                # We are the Leader
                await self._start_hub()
                target_hub_url = f"ws://127.0.0.1:{self.port}/ws/hub"
            else:
                # We are Follower
                await self._stop_hub()
                target_hub_url = f"ws://{leader.ip}:{self.port}/ws/hub"

            # Check if leader changed or worker needs restart
            if leader.ip != self._active_leader_ip or not self.worker_daemon:
                logger.info(f"🔄 Connecting worker daemon to Hub at: {target_hub_url}")
                if self.worker_daemon:
                    await self.worker_daemon.stop()

                self._active_leader_ip = leader.ip
                self.worker_daemon = AgentNodeDaemon(
                    node_id=self.node_id,
                    name=self.name,
                    hub_url=target_hub_url,
                    capabilities=self.capabilities,
                    persona=self.persona,
                    workspace_dir=f"./workspace/{self.node_id}",
                    workstation_mode=self.workstation_mode,
                )

                # Link preemption monitor to election: if human touches this PC, notify election to yield leadership
                def on_preempt(sig):
                    self.election.set_node_preempted(self.self_tailscale.ip, True)
                    logger.warning(f"🚨 Workstation active with human user. Yielding election priority.")

                def on_reclaim(sig):
                    self.election.set_node_preempted(self.self_tailscale.ip, False)

                self.worker_daemon.monitor.register_on_preempt(on_preempt)
                self.worker_daemon.monitor.register_on_reclaim(on_reclaim)

                await self.worker_daemon.start()

        except Exception as e:
            logger.error(f"Error evaluating mesh role: {e}", exc_info=True)

    async def _mesh_watchdog_loop(self):
        """Regularly checks peer health and triggers re-election if topology changes."""
        while self.is_running:
            try:
                await asyncio.sleep(self.poll_interval)
                await self._evaluate_mesh_role()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Mesh watchdog error: {e}")
