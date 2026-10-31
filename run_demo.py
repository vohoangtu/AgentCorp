"""One-click demonstration script for AgentCorp.
Starts the Hub master server, spawns 3 distributed autonomous agent nodes (Dan, Fiona, Gary),
dispatches a collaborative goal DAG, and demonstrates autonomous device execution and human preemption.
"""

from __future__ import annotations

import asyncio
import logging
import uvicorn
import httpx

from shared.models import ControlMode
from agentcorp_hub.server import app
from agentcorp_node.daemon import AgentNodeDaemon
from agentcorp_node.persona import BUILTIN_PERSONAS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("agentcorp.demo")


async def run_server(server: uvicorn.Server):
    await server.serve()


async def main():
    print("""
    ===================================================================
      ⚡ AgentCorp Distributed Autonomous Multi-Agent System & AgentNet ⚡
    ===================================================================
    """)

    # 1. Start Hub Server on port 8000
    config = uvicorn.Config(app=app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(run_server(server))

    # Give server 1.5 seconds to start up
    await asyncio.sleep(1.5)
    logger.info("AgentCorp Hub is live at http://127.0.0.1:8000/")

    # 2. Instantiate 3 autonomous agents
    dan = AgentNodeDaemon(
        node_id="node-dan",
        name="DevOps Dan",
        hub_url="ws://127.0.0.1:8000/ws/hub",
        capabilities=["backend", "devops", "qa", "shell"],
        persona=BUILTIN_PERSONAS["devops_dan"],
        workspace_dir="./workspace/dan",
        inactivity_threshold_seconds=5.0,
    )

    fiona = AgentNodeDaemon(
        node_id="node-fiona",
        name="Frontend Fiona",
        hub_url="ws://127.0.0.1:8000/ws/hub",
        capabilities=["frontend", "ui", "creative", "shell"],
        persona=BUILTIN_PERSONAS["frontend_fiona"],
        workspace_dir="./workspace/fiona",
        inactivity_threshold_seconds=5.0,
    )

    gary = AgentNodeDaemon(
        node_id="node-gary",
        name="Growth Gary",
        hub_url="ws://127.0.0.1:8000/ws/hub",
        capabilities=["copywriter", "marketing", "research", "creative", "shell"],
        persona=BUILTIN_PERSONAS["growth_gary"],
        workspace_dir="./workspace/gary",
        inactivity_threshold_seconds=5.0,
    )

    # Start the agent daemons
    await dan.start()
    await fiona.start()
    await gary.start()

    logger.info("All 3 agent nodes launched and connected to Hub.")
    await asyncio.sleep(2.0)

    # 3. Launch an autonomous goal: "saas_mvp"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://127.0.0.1:8000/api/goals",
            json={"template_id": "saas_mvp", "title": "Production SaaS MVP Launch (Autonomous)"},
        )
        goal_data = resp.json()
        logger.info(f"Launched Goal DAG: {goal_data.get('id')} - {goal_data.get('title')}")

    # 4. Allow agents to execute tasks and interact on AgentNet
    logger.info("Nodes are collaborating on tasks and posting updates to AgentNet...")
    await asyncio.sleep(6.0)

    # 5. Simulate a Human Preemption Event on Fiona's machine
    logger.info("\n--- [SIMULATION] Human user sits down at Fiona's workstation and types on keyboard ---")
    fiona.monitor.trigger_user_detected(username="sarah_designer", details="Typing in Figma and terminal")

    await asyncio.sleep(4.0)

    # 6. Human leaves workstation; Fiona reclaims control
    logger.info("\n--- [SIMULATION] Human user leaves workstation; inactivity threshold reached ---")
    fiona.monitor.trigger_user_idle(details="Workstation idle for > 5 seconds")

    # Let workflow continue
    await asyncio.sleep(6.0)

    # Keep server running if user wants to browse the UI
    logger.info("\nDemo pipeline executed! Web Dashboard available at http://127.0.0.1:8000/")
    logger.info("Press Ctrl+C to terminate demo server.")

    try:
        while True:
            await asyncio.sleep(1.0)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await dan.stop()
        await fiona.stop()
        await gary.stop()
        server.should_exit = True
        await server_task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDemo shutdown completed.")
