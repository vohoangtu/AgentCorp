"""CLI entrypoint for running an autonomous peer node in the Tailscale Mesh.
Usage:
    python3 -m agentcorp_mesh
    python3 -m agentcorp_mesh --name "Luna Designer" --persona frontend_fiona
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from agentcorp_node.persona import BUILTIN_PERSONAS
from agentcorp_mesh.mesh_node import MeshAgentNode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agentcorp.mesh")


async def main():
    parser = argparse.ArgumentParser(description="AgentCorp Decentralized P2P Mesh over Tailscale")
    parser.add_argument("--name", type=str, default=None, help="Display name of Agent")
    parser.add_argument("--node-id", type=str, default=None, help="Unique node identifier")
    parser.add_argument(
        "--persona",
        type=str,
        default="devops_dan",
        choices=list(BUILTIN_PERSONAS.keys()),
        help="Builtin agent persona",
    )
    parser.add_argument("--port", type=int, default=8000, help="Port to serve Hub on if elected leader")
    parser.add_argument(
        "--preferred-leader",
        nargs="*",
        default=["vultr", "server", "srv", "hub"],
        help="Hostnames preferred as Orchestrator leader",
    )
    parser.add_argument(
        "--workstation-mode",
        type=str,
        default="BACKGROUND",
        choices=["BACKGROUND", "EXCLUSIVE"],
        help="BACKGROUND: run quietly in background while user works; EXCLUSIVE: yield immediately when user is present",
    )
    args = parser.parse_args()

    persona_obj = BUILTIN_PERSONAS.get(args.persona)

    node = MeshAgentNode(
        name=args.name,
        node_id=args.node_id,
        persona=persona_obj,
        port=args.port,
        preferred_leaders=args.preferred_leader,
        workstation_mode=args.workstation_mode,
    )
        port=args.port,
        preferred_leaders=args.preferred_leader,
    )

    print("""
    ===================================================================
      🕸️  AgentCorp Decentralized P2P Mesh over Tailscale 🕸️
    ===================================================================
      No fixed server required! Nodes discover each other via Tailscale.
      Leader is automatically elected among online peers.
      If the leader disconnects or is preempted by human, a new leader takes over.
    ===================================================================
    """)

    await node.start()

    print(f"👉 Local Tailscale IP: {node.self_tailscale.ip}")
    print(f"👉 Current Elected Leader: {node.election.current_leader.hostname} ({node.election.current_leader.ip})")
    print(f"👉 Web Dashboard available at: http://{node.election.current_leader.ip}:{node.port}/")
    print("👉 Press Ctrl+C to disconnect from the mesh.\n")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        logger.info("Stopping mesh node...")
        await node.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
