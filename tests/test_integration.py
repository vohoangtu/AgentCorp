"""Integration test: Hub, Node Daemon, Task DAG execution, and Preemption flow.
"""

import asyncio
import tempfile
import pytest
import uvicorn
import httpx

import pytest_asyncio
from shared.models import TaskStatus, NodeStatus, ControlMode
from agentcorp_hub.server import app, store
from agentcorp_node.daemon import AgentNodeDaemon
from agentcorp_node.persona import BUILTIN_PERSONAS


@pytest_asyncio.fixture
async def live_hub_and_node():
    # Run uvicorn server in background
    config = uvicorn.Config(app=app, host="127.0.0.1", port=8001, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.8)

    tmp_workspace = tempfile.mkdtemp(prefix="agentcorp_it_")

    node = AgentNodeDaemon(
        node_id="test-dan",
        name="DevOps Dan",
        hub_url="ws://127.0.0.1:8001/ws/hub",
        capabilities=["backend", "shell", "qa", "devops"],
        persona=BUILTIN_PERSONAS["devops_dan"],
        workspace_dir=tmp_workspace,
        inactivity_threshold_seconds=1.0,
        enable_social_banter=False,
    )
    await node.start()
    await asyncio.sleep(0.8)

    yield "http://127.0.0.1:8001", node

    # Teardown
    await node.stop()
    server.should_exit = True
    await server_task


@pytest.mark.asyncio
async def test_full_pipeline_and_preemption(live_hub_and_node):
    base_url, node = live_hub_and_node

    async with httpx.AsyncClient(base_url=base_url) as client:
        # 1. Verify node registered
        res = await client.get("/api/nodes")
        assert res.status_code == 200
        nodes = res.json()
        assert any(n["node_id"] == "test-dan" for n in nodes)

        # 2. Launch SaaS MVP goal
        res = await client.post("/api/goals", json={"template_id": "saas_mvp"})
        assert res.status_code == 200
        goal = res.json()
        assert len(goal["task_ids"]) == 5

        # 3. Allow orchestrator loop to schedule and node to execute first task
        await asyncio.sleep(2.5)

        # Check tasks status
        res = await client.get("/api/tasks")
        tasks = res.json()
        completed_tasks = [t for t in tasks if t["status"] == "COMPLETED"]
        assert len(completed_tasks) >= 1

        # 4. Trigger simulated human preemption
        res = await client.post(
            "/api/preemption/simulate",
            json={
                "node_id": "test-dan",
                "signal_type": "USER_DETECTED",
                "username": "human_tester",
            },
        )
        assert res.status_code == 200

        # Wait a moment for preemption to propagate
        await asyncio.sleep(0.5)

        # Verify node is preempted both in Hub and on the node daemon itself
        node_data = (await client.get("/api/nodes/test-dan")).json()
        assert node_data["control_mode"] == "YIELDED_PASSIVE"
        assert node_data["status"] == "PREEMPTED"
        assert node.monitor.control_mode == ControlMode.YIELDED_PASSIVE

        # 5. Check AgentNet feed has post about preemption authored by this node
        res = await client.get("/api/feed")
        feed = res.json()
        assert any(p["author_id"] == "test-dan" for p in feed)

        # 6. Release preemption
        res = await client.post(
            "/api/preemption/simulate",
            json={
                "node_id": "test-dan",
                "signal_type": "USER_IDLE",
                "username": "human_tester",
            },
        )
        assert res.status_code == 200
        await asyncio.sleep(0.5)

        node_data = (await client.get("/api/nodes/test-dan")).json()
        assert node_data["control_mode"] == "FULL_CONTROL"
        assert node.monitor.control_mode == ControlMode.FULL_CONTROL
