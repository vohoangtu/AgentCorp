"""Data models and schemas for AgentCorp distributed autonomous multi-agent system.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ControlMode(str, Enum):
    FULL_CONTROL = "FULL_CONTROL"        # Autonomous full control over device (shell, GUI, browser)
    YIELDED_PASSIVE = "YIELDED_PASSIVE"  # Preempted by human, foreground input/actions paused
    PAUSED = "PAUSED"                    # Explicitly paused by operator or coordinator


class PreemptionSignalType(str, Enum):
    USER_DETECTED = "USER_DETECTED"      # Human input/interaction or login detected
    USER_IDLE = "USER_IDLE"              # Human user went idle, safe to reclaim
    USER_LOGOUT = "USER_LOGOUT"          # Human user logged out
    LOCK_SCREEN = "LOCK_SCREEN"          # Screen locked, device autonomous again
    MANUAL_TAKEOVER = "MANUAL_TAKEOVER"  # Manual human override from UI/CLI
    MANUAL_RELEASE = "MANUAL_RELEASE"    # Manual release back to agent control


class PreemptionSignal(BaseModel):
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    signal_type: PreemptionSignalType
    node_id: str
    username: Optional[str] = None
    details: str = ""
    timestamp: float = Field(default_factory=time.time)


class NodeStatus(str, Enum):
    ONLINE = "ONLINE"
    BUSY = "BUSY"
    PREEMPTED = "PREEMPTED"
    IDLE = "IDLE"
    OFFLINE = "OFFLINE"


class NodeInfo(BaseModel):
    node_id: str
    name: str
    hostname: str
    platform_name: str = "linux"
    ip: str = "127.0.0.1"
    capabilities: List[str] = Field(default_factory=list)
    status: NodeStatus = NodeStatus.ONLINE
    control_mode: ControlMode = ControlMode.FULL_CONTROL
    current_task_id: Optional[str] = None
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    last_heartbeat: float = Field(default_factory=time.time)
    persona_name: Optional[str] = None
    persona_role: Optional[str] = None
    persona_avatar: Optional[str] = "🤖"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    PREEMPTED = "PREEMPTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskActionType(str, Enum):
    SHELL = "SHELL"            # Execute bash/shell command
    FILE_WRITE = "FILE_WRITE"  # Write project file
    FILE_READ = "FILE_READ"    # Read file
    BROWSER = "BROWSER"        # Browser/HTTP task
    GUI = "GUI"                # Simulated GUI / desktop automation
    SYNTHETIC = "SYNTHETIC"    # Logical processing / cognitive task
    TUZYGENT = "TUZYGENT"      # High-level mission delegated to Tuzygent OODA loop


class TaskAction(BaseModel):
    action_type: TaskActionType
    command: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task-{uuid.uuid4().hex[:8]}")
    goal_id: str
    title: str
    description: str = ""
    required_capabilities: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)  # IDs of tasks that must complete first
    action: TaskAction
    status: TaskStatus = TaskStatus.PENDING
    assigned_node_id: Optional[str] = None
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    artifacts: List[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class GoalStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Goal(BaseModel):
    id: str = Field(default_factory=lambda: f"goal-{uuid.uuid4().hex[:8]}")
    title: str
    description: str = ""
    task_ids: List[str] = Field(default_factory=list)
    status: GoalStatus = GoalStatus.PENDING
    created_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None


class AgentMood(str, Enum):
    FOCUSED = "focused"
    CAFFEINATED = "caffeinated"
    FRUSTRATED = "frustrated"
    HYPED = "hyped"
    CHILL = "chill"
    EXHAUSTED = "exhausted"
    PROUD = "proud"
    PHILOSOPHICAL = "philosophical"


class SocialPost(BaseModel):
    id: str = Field(default_factory=lambda: f"post-{uuid.uuid4().hex[:8]}")
    author_id: str
    author_name: str
    author_role: str
    author_avatar: str = "🤖"
    content: str
    mood: AgentMood = AgentMood.FOCUSED
    tags: List[str] = Field(default_factory=list)
    mentions: List[str] = Field(default_factory=list)
    reactions: Dict[str, List[str]] = Field(default_factory=dict)  # emoji -> [author_id/name]
    comments_count: int = 0
    created_at: float = Field(default_factory=time.time)
    is_ceo: bool = False


class SocialComment(BaseModel):
    id: str = Field(default_factory=lambda: f"cmt-{uuid.uuid4().hex[:8]}")
    post_id: str
    author_id: str
    author_name: str
    author_role: str
    author_avatar: str = "🤖"
    content: str
    reactions: Dict[str, List[str]] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


class SocialReaction(BaseModel):
    post_id: str
    comment_id: Optional[str] = None
    emoji: str
    author_id: str
    author_name: str
