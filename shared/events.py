"""WebSocket and IPC event types and message structures for AgentCorp.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class EventType(str, Enum):
    # Node lifecycle
    NODE_REGISTER = "NODE_REGISTER"
    NODE_REGISTERED = "NODE_REGISTERED"
    NODE_HEARTBEAT = "NODE_HEARTBEAT"
    NODE_DISCONNECTED = "NODE_DISCONNECTED"
    NODE_UPDATED = "NODE_UPDATED"

    # Preemption events
    PREEMPTION_SIGNAL = "PREEMPTION_SIGNAL"
    CONTROL_MODE_CHANGED = "CONTROL_MODE_CHANGED"

    # Task & DAG events
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_PAUSED = "TASK_PAUSED"
    TASK_RESUMED = "TASK_RESUMED"
    GOAL_UPDATED = "GOAL_UPDATED"

    # Agent Client Control Events
    CLIENT_PAUSE = "CLIENT_PAUSE"              # Drain/pause node from receiving new tasks
    CLIENT_RESUME = "CLIENT_RESUME"            # Resume node to accept tasks
    CLIENT_TASK_CANCEL = "CLIENT_TASK_CANCEL"  # Abort currently running task
    CLIENT_RECONFIG = "CLIENT_RECONFIG"        # Dynamic remote configuration
    CLIENT_EXEC_COMMAND = "CLIENT_EXEC_COMMAND"# Ad-hoc command dispatch
    CLIENT_COMMAND_RESULT = "CLIENT_COMMAND_RESULT" # Response to ad-hoc command
    CLIENT_SET_MODE = "CLIENT_SET_MODE"        # Set workstation mode (BACKGROUND / EXCLUSIVE)

    # AgentNet Social events
    SOCIAL_POST_CREATED = "SOCIAL_POST_CREATED"
    SOCIAL_COMMENT_CREATED = "SOCIAL_COMMENT_CREATED"
    SOCIAL_REACTION_ADDED = "SOCIAL_REACTION_ADDED"
    SOCIAL_FEED_SYNC = "SOCIAL_FEED_SYNC"

    # System broadcast / operator
    CEO_ANNOUNCEMENT = "CEO_ANNOUNCEMENT"
    SYSTEM_ALERT = "SYSTEM_ALERT"


class AgentCorpMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:8]}")
    event_type: EventType
    source: str  # "hub", "node:{node_id}", "ui", "ceo"
    target: Optional[str] = None  # None = broadcast, or "node:{node_id}", "ui"
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
