"""Tests for Orchestrator DAG resolution, capability matching, and preemption.
"""

import pytest
from shared.models import (
    ControlMode,
    NodeInfo,
    NodeStatus,
    Task,
    TaskAction,
    TaskActionType,
    TaskStatus,
)
from agentcorp_hub.orchestrator import Orchestrator
from agentcorp_hub.store import HubStore


@pytest.fixture
def store_and_orchestrator():
    store = HubStore()
    orchestrator = Orchestrator(store)
    return store, orchestrator


@pytest.mark.asyncio
async def test_goal_instantiation_from_template(store_and_orchestrator):
    store, orchestrator = store_and_orchestrator
    goal = await orchestrator.instantiate_goal_from_template("saas_mvp")

    assert goal is not None
    assert len(goal.task_ids) == 5

    tasks = await store.get_tasks_for_goal(goal.id)
    assert len(tasks) == 5

    # Check root task has no dependencies
    root_tasks = [t for t in tasks if not t.dependencies]
    assert len(root_tasks) == 1
    assert root_tasks[0].title == "System Architecture & API Specification"


@pytest.mark.asyncio
async def test_capability_matching_and_dependency_resolution(store_and_orchestrator):
    store, orchestrator = store_and_orchestrator

    # Register two nodes: one backend, one frontend
    node_dan = NodeInfo(
        node_id="node-dan",
        name="DevOps Dan",
        hostname="dan-box",
        capabilities=["backend", "shell"],
    )
    node_fiona = NodeInfo(
        node_id="node-fiona",
        name="Frontend Fiona",
        hostname="fiona-box",
        capabilities=["frontend", "shell"],
    )
    await store.register_node(node_dan)
    await store.register_node(node_fiona)

    goal = await orchestrator.instantiate_goal_from_template("saas_mvp")

    # First cycle of plan_and_schedule
    assignments = await orchestrator.plan_and_schedule()
    assert len(assignments) == 1

    assigned_task, assigned_node = assignments[0]
    # Root task requires ["backend", "shell"] -> should be assigned to node-dan
    assert assigned_task.title == "System Architecture & API Specification"
    assert assigned_node.node_id == "node-dan"
    assert assigned_task.status == TaskStatus.RUNNING

    # Mark the root task as COMPLETED
    await store.update_task(assigned_task.id, status=TaskStatus.COMPLETED)
    # Free up node-dan
    dan = await store.get_node("node-dan")
    dan.status = NodeStatus.ONLINE
    dan.current_task_id = None

    # Next scheduling cycle: both backend_api and frontend_ui should now be ready!
    assignments_2 = await orchestrator.plan_and_schedule()
    assert len(assignments_2) == 2
    assigned_node_ids = {n.node_id for _, n in assignments_2}
    assert assigned_node_ids == {"node-dan", "node-fiona"}


@pytest.mark.asyncio
async def test_orchestrator_handles_node_preemption(store_and_orchestrator):
    store, orchestrator = store_and_orchestrator

    node = NodeInfo(
        node_id="node-1",
        name="Worker 1",
        hostname="box1",
        capabilities=["shell"],
        status=NodeStatus.BUSY,
    )
    await store.register_node(node)

    task = Task(
        goal_id="g1",
        title="Active Shell Task",
        action=TaskAction(action_type=TaskActionType.SHELL, command="sleep 10"),
        status=TaskStatus.RUNNING,
        assigned_node_id="node-1",
    )
    await store.add_task(task)
    node.current_task_id = task.id

    # Simulate human preemption on node-1
    preempted_task = await orchestrator.handle_node_preemption("node-1", ControlMode.YIELDED_PASSIVE)
    assert preempted_task is not None
    assert preempted_task.status == TaskStatus.PREEMPTED
    assert node.status == NodeStatus.PREEMPTED

    # Simulate user releasing control
    resumed_task = await orchestrator.handle_node_preemption("node-1", ControlMode.FULL_CONTROL)
    assert resumed_task is not None
    assert resumed_task.status == TaskStatus.RUNNING
    assert node.status == NodeStatus.BUSY
