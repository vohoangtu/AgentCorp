"""Tests for Task Executor and device control interlocks.
"""

import os
import shutil
import tempfile
import pytest
from shared.models import ControlMode, Task, TaskAction, TaskActionType
from agentcorp_node.executor import PreemptionInterruptedError, TaskExecutor
from agentcorp_node.preemption import PreemptionMonitor


@pytest.fixture
def workspace_and_executor():
    tmp_dir = tempfile.mkdtemp(prefix="agentcorp_test_")
    monitor = PreemptionMonitor(node_id="exec-node", inactivity_threshold_seconds=1.0)
    executor = TaskExecutor(monitor=monitor, workspace_dir=tmp_dir)
    yield tmp_dir, monitor, executor
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_shell_execution_success(workspace_and_executor):
    tmp_dir, monitor, executor = workspace_and_executor

    task = Task(
        goal_id="g1",
        title="Echo Test",
        action=TaskAction(
            action_type=TaskActionType.SHELL,
            command="echo 'AgentCorp Shell Test'",
        ),
    )

    res = await executor.execute_task(task)
    assert res["exit_code"] == 0
    assert "AgentCorp Shell Test" in res["stdout"]


@pytest.mark.asyncio
async def test_file_write_and_read(workspace_and_executor):
    tmp_dir, monitor, executor = workspace_and_executor

    write_task = Task(
        goal_id="g1",
        title="Write Code",
        action=TaskAction(
            action_type=TaskActionType.FILE_WRITE,
            params={"path": "src/hello.py", "content": "print('hello world')"},
        ),
    )

    w_res = await executor.execute_task(write_task)
    assert "artifacts" in w_res
    written_path = os.path.join(tmp_dir, "src/hello.py")
    assert os.path.exists(written_path)

    # Read back
    read_task = Task(
        goal_id="g1",
        title="Read Code",
        action=TaskAction(
            action_type=TaskActionType.FILE_READ,
            params={"path": "src/hello.py"},
        ),
    )
    r_res = await executor.execute_task(read_task)
    assert r_res["content"] == "print('hello world')"


@pytest.mark.asyncio
async def test_gui_interlock_blocked_when_preempted(workspace_and_executor):
    tmp_dir, monitor, executor = workspace_and_executor

    # Preempt device control
    monitor.trigger_user_detected("human_operator")
    assert monitor.is_autonomous_allowed() is False

    gui_task = Task(
        goal_id="g1",
        title="Click Button",
        action=TaskAction(
            action_type=TaskActionType.GUI,
            params={"steps": [{"action": "click", "x": 50, "y": 50}]},
        ),
    )

    with pytest.raises(PreemptionInterruptedError):
        await executor.execute_task(gui_task)
