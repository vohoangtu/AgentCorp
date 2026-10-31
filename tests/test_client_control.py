"""Unit and integration tests for Agent Client Operation Control."""

import asyncio
import os
import pytest
from httpx import AsyncClient, ASGITransport

from shared.config import AgentClientConfig
from shared.events import AgentCorpMessage, EventType
from shared.models import (
    ControlMode,
    NodeInfo,
    NodeStatus,
    Task,
    TaskAction,
    TaskActionType,
    TaskStatus,
    WorkstationMode,
)
from agentcorp_hub.server import app, orchestrator, store
from agentcorp_node.daemon import AgentNodeDaemon
from agentcorp_node.executor import (
    PreemptionInterruptedError,
    TaskCancelledError,
    TaskExecutor,
)
from agentcorp_node.preemption import PreemptionMonitor


@pytest.mark.asyncio
async def test_executor_task_cancellation(tmp_path):
    """Test that TaskExecutor can abort a running long-running shell task."""
    monitor = PreemptionMonitor(node_id="test-node", workstation_mode=WorkstationMode.BACKGROUND)
    await monitor.start()
    executor = TaskExecutor(monitor=monitor, workspace_dir=str(tmp_path))

    # A long-running command (sleeps 5 seconds)
    task = Task(
        goal_id="g1",
        title="Long Sleep Task",
        action=TaskAction(
            action_type=TaskActionType.SHELL,
            command="sleep 5",
        ),
    )

    async def run_and_cancel():
        # Start task in background
        exec_future = asyncio.create_task(executor.execute_task(task))
        # Give it a fraction of a second to spawn the subprocess
        await asyncio.sleep(0.2)
        # Cancel task
        cancelled = executor.cancel_current_task(reason="Test abort")
        assert cancelled is True
        return await exec_future

    with pytest.raises(TaskCancelledError) as exc_info:
        await run_and_cancel()

    assert "Test abort" in str(exc_info.value) or "cancelled" in str(exc_info.value).lower()
    await monitor.stop()


@pytest.mark.asyncio
async def test_executor_adhoc_command(tmp_path):
    """Test that TaskExecutor can execute ad-hoc commands safely."""
    monitor = PreemptionMonitor(node_id="test-node")
    executor = TaskExecutor(monitor=monitor, workspace_dir=str(tmp_path))

    res = await executor.execute_adhoc_command("echo 'AgentCorp Client Control'")
    assert res["success"] is True
    assert res["exit_code"] == 0
    assert "AgentCorp Client Control" in res["stdout"]

    # Test dangerous command blocked by Conscience
    bad_res = await executor.execute_adhoc_command("rm -rf /")
    assert bad_res["success"] is False
    assert "Digital Conscience" in bad_res["stderr"]


@pytest.mark.asyncio
async def test_daemon_pause_and_resume():
    """Test that daemon handles CLIENT_PAUSE and CLIENT_RESUME events."""
    daemon = AgentNodeDaemon(
        node_id="test-daemon-1",
        name="TestDaemon",
        capabilities=["shell", "backend"],
    )

    assert daemon.is_drained is False

    # Send PAUSE
    pause_msg = AgentCorpMessage(
        event_type=EventType.CLIENT_PAUSE,
        source="hub",
        payload={"node_id": "test-daemon-1", "reason": "Maintenance"},
    )
    await daemon._handle_incoming_message(pause_msg)
    assert daemon.is_drained is True

    info = daemon.build_node_info()
    assert info.is_drained is True
    assert info.status == NodeStatus.IDLE

    # Send RESUME
    resume_msg = AgentCorpMessage(
        event_type=EventType.CLIENT_RESUME,
        source="hub",
        payload={"node_id": "test-daemon-1"},
    )
    await daemon._handle_incoming_message(resume_msg)
    assert daemon.is_drained is False

    info2 = daemon.build_node_info()
    assert info2.is_drained is False
    assert info2.status == NodeStatus.ONLINE


@pytest.mark.asyncio
async def test_daemon_dynamic_reconfig():
    """Test daemon handles CLIENT_RECONFIG to update parameters on the fly."""
    daemon = AgentNodeDaemon(
        node_id="test-daemon-reconfig",
        name="OrigName",
    )

    reconfig_msg = AgentCorpMessage(
        event_type=EventType.CLIENT_RECONFIG,
        source="hub",
        payload={
            "node_id": "test-daemon-reconfig",
            "config": {
                "inactivity_threshold_seconds": 25.0,
                "workstation_mode": "EXCLUSIVE",
                "name": "UpdatedName",
            },
        },
    )
    await daemon._handle_incoming_message(reconfig_msg)

    assert daemon.name == "UpdatedName"
    assert daemon.monitor.inactivity_threshold_seconds == 25.0
    assert daemon.monitor.workstation_mode == WorkstationMode.EXCLUSIVE


@pytest.mark.asyncio
async def test_hub_node_control_api_endpoints():
    """Test Hub REST endpoints for controlling nodes."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register a test node in store
        node = NodeInfo(
            node_id="test-api-node",
            name="APITestNode",
            hostname="test-host",
            capabilities=["shell", "devops"],
            status=NodeStatus.ONLINE,
            workstation_mode=WorkstationMode.BACKGROUND,
        )
        await store.register_node(node)

        # 1. Test Pause
        pause_res = await client.post("/api/nodes/test-api-node/pause", json={"reason": "Test pause"})
        assert pause_res.status_code == 200
        assert pause_res.json()["is_drained"] is True

        n_paused = await store.get_node("test-api-node")
        assert n_paused.is_drained is True

        # 2. Test Resume
        resume_res = await client.post("/api/nodes/test-api-node/resume", json={"reason": "Test resume"})
        assert resume_res.status_code == 200
        assert resume_res.json()["is_drained"] is False

        n_resumed = await store.get_node("test-api-node")
        assert n_resumed.is_drained is False

        # 3. Test Workstation Mode
        mode_res = await client.post("/api/nodes/test-api-node/workstation_mode", json={"workstation_mode": "EXCLUSIVE"})
        assert mode_res.status_code == 200
        n_mode = await store.get_node("test-api-node")
        assert n_mode.workstation_mode == WorkstationMode.EXCLUSIVE

        # 4. Test Config Get
        cfg_res = await client.get("/api/nodes/test-api-node/config")
        assert cfg_res.status_code == 200
        assert cfg_res.json()["node_id"] == "test-api-node"
