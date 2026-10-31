"""Tests for AgentCorp shared data models and schemas.
"""

import time
import pytest
from shared.models import (
    ControlMode,
    NodeInfo,
    NodeStatus,
    PreemptionSignal,
    PreemptionSignalType,
    Task,
    TaskAction,
    TaskActionType,
    TaskStatus,
    Goal,
    GoalStatus,
    AgentMood,
    SocialPost,
    SocialComment,
)


def test_node_info_defaults():
    node = NodeInfo(
        node_id="node-test-1",
        name="Test Worker",
        hostname="worker-box",
        capabilities=["shell", "backend"],
    )
    assert node.node_id == "node-test-1"
    assert node.status == NodeStatus.ONLINE
    assert node.control_mode == ControlMode.FULL_CONTROL
    assert "backend" in node.capabilities
    assert node.persona_avatar == "🤖"


def test_task_model_and_action():
    action = TaskAction(
        action_type=TaskActionType.SHELL,
        command="echo hello",
    )
    task = Task(
        goal_id="goal-123",
        title="Sample Task",
        action=action,
        dependencies=["task-001"],
    )
    assert task.status == TaskStatus.PENDING
    assert task.dependencies == ["task-001"]
    assert task.action.action_type == TaskActionType.SHELL


def test_preemption_signal():
    sig = PreemptionSignal(
        signal_type=PreemptionSignalType.USER_DETECTED,
        node_id="node-1",
        username="alice",
        details="Keypress on /dev/input/event0",
    )
    assert sig.signal_type == PreemptionSignalType.USER_DETECTED
    assert sig.username == "alice"
    assert sig.timestamp <= time.time()


def test_social_post_reactions():
    post = SocialPost(
        author_id="node-dan",
        author_name="DevOps Dan",
        author_role="SRE",
        content="Production is smooth today #devops @fiona",
        mood=AgentMood.CAFFEINATED,
    )
    assert post.mood == AgentMood.CAFFEINATED
    assert post.comments_count == 0
    # Simulate reaction
    post.reactions["☕"] = ["node-fiona"]
    assert len(post.reactions["☕"]) == 1
