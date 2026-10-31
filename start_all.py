"""Persistent Cluster Launcher for AgentCorp.
Starts the Central Hub Server and automatically launches 3 distributed agent nodes (Dan, Fiona, Gary)
running concurrently on this machine. They stay online indefinitely until you press Ctrl+C.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import uvicorn

from agentcorp_hub.server import app
from agentcorp_node.daemon import AgentNodeDaemon
from agentcorp_node.persona import BUILTIN_PERSONAS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agentcorp.cluster")


async def main():
    print("""
    ===================================================================
      🏢 AgentCorp Persistent Multi-Agent Cluster & AgentNet Live 🏢
    ===================================================================
      Hub Dashboard : http://127.0.0.1:8000
      WebSocket Hub : ws://127.0.0.1:8000/ws/hub
    -------------------------------------------------------------------
      Spawning 3 Autonomous Agents:
        ☕ DevOps Dan    (Capabilities: backend, devops, qa, shell)
        🎨 Frontend Fiona (Capabilities: frontend, ui, creative, shell)
        📈 Growth Gary   (Capabilities: marketing, copywriter, research, creative)
    ===================================================================
    """)

    # 1. Start Hub Server on port 8000
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # Wait for server to bind port
    await asyncio.sleep(1.5)
    logger.info("Hub Server is active and listening on http://0.0.0.0:8000")

    # 2. Instantiate and connect 3 autonomous agent nodes
    dan = AgentNodeDaemon(
        node_id="node-dan",
        name="DevOps Dan",
        hub_url="ws://127.0.0.1:8000/ws/hub",
        capabilities=["backend", "devops", "qa", "shell"],
        persona=BUILTIN_PERSONAS["devops_dan"],
        workspace_dir="./workspace/dan",
        inactivity_threshold_seconds=8.0,
    )

    fiona = AgentNodeDaemon(
        node_id="node-fiona",
        name="Frontend Fiona",
        hub_url="ws://127.0.0.1:8000/ws/hub",
        capabilities=["frontend", "ui", "creative", "shell"],
        persona=BUILTIN_PERSONAS["frontend_fiona"],
        workspace_dir="./workspace/fiona",
        inactivity_threshold_seconds=8.0,
    )

    gary = AgentNodeDaemon(
        node_id="node-gary",
        name="Growth Gary",
        hub_url="ws://127.0.0.1:8000/ws/hub",
        capabilities=["copywriter", "marketing", "research", "creative", "shell"],
        persona=BUILTIN_PERSONAS["growth_gary"],
        workspace_dir="./workspace/gary",
        inactivity_threshold_seconds=8.0,
    )

    nodes = [dan, fiona, gary]
    for node in nodes:
        await node.start()

    logger.info("All 3 agent nodes are ONLINE and registered with Hub.")
    print("\n👉 Open your browser at: http://localhost:8000")
    print("👉 Press Ctrl+C at any time to shut down the cluster.\n")

    # Keep cluster running indefinitely
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
        logger.info("Shutting down agent nodes...")
        for node in nodes:
            await node.stop()
        server.should_exit = True
        await server_task
        logger.info("AgentCorp Cluster stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
