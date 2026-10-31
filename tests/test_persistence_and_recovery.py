"""Tests for SQLite persistence, node failure recovery, and preemption task pausing.
"""

import os
import tempfile
import pytest
from shared.models import (
    AgentMood,
    ControlMode,
    Goal,
    GoalStatus,
    NodeInfo,
    NodeStatus,
    PreemptionSignal,
    PreemptionSignalType,
    SocialComment,
    SocialPost,
    Task,
    TaskAction,
    TaskActionType,
    TaskStatus,
)
from agentcorp_hub.orchestrator import Orchestrator
from agentcorp_hub.store import HubStore
from agentcorp_node.daemon import AgentNodeDaemon
from agentcorp_node.executor import PreemptionInterruptedError
from agentcorp_node.persona import BUILTIN_PERSONAS


@pytest.mark.asyncio
async def test_sqlite_persistence_and_recovery():
    tmp_db = tempfile.mktemp(suffix=".db")
    try:
        # 1. Initialize store with SQLite db
        store1 = HubStore(db_path=tmp_db)

        # Add goal, task, post, comment, preemption
        goal = Goal(id="g-101", title="Launch SaaS", status=GoalStatus.IN_PROGRESS)
        await store1.add_goal(goal)

        task = Task(
            id="t-101",
            goal_id="g-101",
            title="Setup DB",
            action=TaskAction(action_type=TaskActionType.SHELL, command="echo 'db ready'"),
            status=TaskStatus.READY,
        )
        await store1.add_task(task)

        post = SocialPost(
            id="p-101",
            author_id="node-dan",
            author_name="DevOps Dan",
            author_role="SRE",
            content="Deploying new infra #k8s",
            mood=AgentMood.FOCUSED,
        )
        await store1.add_post(post)

        comment = SocialComment(
            id="c-101",
            post_id="p-101",
            author_id="node-fiona",
            author_name="Frontend Fiona",
            author_role="UI",
            content="Looking forward to it!",
        )
        await store1.add_comment(comment)

        sig = PreemptionSignal(
            signal_id="sig-01",
            signal_type=PreemptionSignalType.USER_DETECTED,
            node_id="node-dan",
            username="alice",
            details="Keyboard press",
        )
        await store1.record_preemption(sig)

        # 2. Simulate server restart with a brand new store pointing to the same db
        store2 = HubStore(db_path=tmp_db)

        # Verify all entities were successfully recovered
        recovered_goal = await store2.get_goal("g-101")
        assert recovered_goal is not None
        assert recovered_goal.title == "Launch SaaS"

        recovered_task = await store2.get_task("t-101")
        assert recovered_task is not None
        assert recovered_task.title == "Setup DB"
        assert recovered_task.action.command == "echo 'db ready'"

        recovered_posts = await store2.get_all_posts()
        assert len(recovered_posts) == 1
        assert recovered_posts[0].id == "p-101"

        comments = await store2.get_comments_for_post("p-101")
        assert len(comments) == 1
        assert comments[0].id == "c-101"
        assert comments[0].author_name == "Frontend Fiona"

        history = await store2.get_preemption_history()
        assert len(history) == 1
        assert history[0].username == "alice"

    finally:
        if os.path.exists(tmp_db):
            os.remove(tmp_db)


@pytest.mark.asyncio
async def test_dead_node_task_requeue_prevents_dag_deadlock():
    store = HubStore(db_path=None)
    orchestrator = Orchestrator(store)

    # Register node
    node = NodeInfo(
        node_id="worker-1",
        name="Worker 1",
        hostname="box-1",
        capabilities=["backend", "shell"],
    )
    await store.register_node(node)

    # Assign task to worker-1
    task = Task(
        id="task-crash-test",
        goal_id="g1",
        title="Critical Task",
        required_capabilities=["backend"],
        action=TaskAction(action_type=TaskActionType.SHELL, command="echo 'critical'"),
        status=TaskStatus.RUNNING,
        assigned_node_id="worker-1",
    )
    await store.add_task(task)
    node.current_task_id = "task-crash-test"
    node.status = NodeStatus.BUSY

    # Simulate node heartbeat timeout (node crashed or network severed)
    node.last_heartbeat = 0.0  # long ago
    dead_nodes = await store.prune_dead_nodes(heartbeat_timeout_seconds=5.0)

    assert "worker-1" in dead_nodes
    assert node.status == NodeStatus.OFFLINE
    assert node.current_task_id is None

    # The running task must be re-queued to PENDING so another node can complete it
    refreshed_task = await store.get_task("task-crash-test")
    assert refreshed_task.status == TaskStatus.PENDING
    assert refreshed_task.assigned_node_id is None


@pytest.mark.asyncio
async def test_preempted_task_does_not_fail():
    tmp_workspace = tempfile.mkdtemp()
    node = AgentNodeDaemon(
        node_id="safe-node",
        name="DevOps Dan",
        capabilities=["shell"],
        persona=BUILTIN_PERSONAS["devops_dan"],
        workspace_dir=tmp_workspace,
        enable_social_banter=False,
    )

    sent_messages = []

    async def mock_send(msg):
        sent_messages.append(msg)

    node.send_message = mock_send

    # Trigger preemption before task starts
    node.monitor.trigger_user_detected("tester")

    gui_task = Task(
        goal_id="g1",
        title="Automated GUI Click",
        action=TaskAction(
            action_type=TaskActionType.GUI,
            params={"steps": [{"action": "click", "x": 10, "y": 10}]},
        ),
    )

    # Execute task while preempted: it must pause, NOT report TASK_FAILED
    await node._process_assigned_task(gui_task)

    event_types = [m.event_type for m in sent_messages]
    assert "TASK_PAUSED" in event_types
    assert "TASK_FAILED" not in event_types
