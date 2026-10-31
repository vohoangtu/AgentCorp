"""State repository for AgentCorp Hub: nodes, tasks, goals, social posts, and preemption log.
Supports hybrid in-memory caching with SQLite persistence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from typing import Dict, List, Optional
from shared.models import (
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
    TaskStatus,
)

logger = logging.getLogger("agentcorp.store")


class HubStore:
    """Thread-safe state repository for the central hub with optional SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None):
        self._lock = asyncio.Lock()
        self.db_path = db_path
        self.nodes: Dict[str, NodeInfo] = {}
        self.goals: Dict[str, Goal] = {}
        self.tasks: Dict[str, Task] = {}
        self.posts: Dict[str, SocialPost] = {}
        self.comments: Dict[str, List[SocialComment]] = {}  # post_id -> list of comments
        self.preemption_history: List[PreemptionSignal] = []

        if self.db_path:
            self._init_sqlite()
            self._load_from_sqlite()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite(self):
        """Create tables if they don't exist."""
        if not self.db_path:
            return
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS nodes (
                        node_id TEXT PRIMARY KEY,
                        name TEXT,
                        hostname TEXT,
                        platform_name TEXT,
                        ip TEXT,
                        capabilities TEXT,
                        status TEXT,
                        control_mode TEXT,
                        current_task_id TEXT,
                        cpu_percent REAL,
                        memory_percent REAL,
                        last_heartbeat REAL,
                        persona_name TEXT,
                        persona_role TEXT,
                        persona_avatar TEXT
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS goals (
                        id TEXT PRIMARY KEY,
                        title TEXT,
                        description TEXT,
                        task_ids TEXT,
                        status TEXT,
                        created_at REAL,
                        completed_at REAL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT PRIMARY KEY,
                        goal_id TEXT,
                        title TEXT,
                        description TEXT,
                        required_capabilities TEXT,
                        dependencies TEXT,
                        action TEXT,
                        status TEXT,
                        assigned_node_id TEXT,
                        progress REAL,
                        result TEXT,
                        error TEXT,
                        artifacts TEXT,
                        created_at REAL,
                        started_at REAL,
                        completed_at REAL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS posts (
                        id TEXT PRIMARY KEY,
                        author_id TEXT,
                        author_name TEXT,
                        author_role TEXT,
                        author_avatar TEXT,
                        content TEXT,
                        mood TEXT,
                        tags TEXT,
                        mentions TEXT,
                        reactions TEXT,
                        comments_count INTEGER,
                        created_at REAL,
                        is_ceo INTEGER
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS comments (
                        id TEXT PRIMARY KEY,
                        post_id TEXT,
                        author_id TEXT,
                        author_name TEXT,
                        author_role TEXT,
                        author_avatar TEXT,
                        content TEXT,
                        reactions TEXT,
                        created_at REAL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS preemption_history (
                        signal_id TEXT PRIMARY KEY,
                        signal_type TEXT,
                        node_id TEXT,
                        username TEXT,
                        details TEXT,
                        timestamp REAL
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not initialize SQLite schema: {e}")

    def _load_from_sqlite(self):
        """Populate in-memory cache from persistent SQLite database."""
        if not self.db_path or not os.path.exists(self.db_path):
            return
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()

                # Goals
                for row in cur.execute("SELECT * FROM goals").fetchall():
                    self.goals[row["id"]] = Goal(
                        id=row["id"],
                        title=row["title"],
                        description=row["description"],
                        task_ids=json.loads(row["task_ids"] or "[]"),
                        status=GoalStatus(row["status"]),
                        created_at=row["created_at"],
                        completed_at=row["completed_at"],
                    )

                # Tasks
                for row in cur.execute("SELECT * FROM tasks").fetchall():
                    action_data = json.loads(row["action"] or "{}")
                    self.tasks[row["id"]] = Task(
                        id=row["id"],
                        goal_id=row["goal_id"],
                        title=row["title"],
                        description=row["description"],
                        required_capabilities=json.loads(row["required_capabilities"] or "[]"),
                        dependencies=json.loads(row["dependencies"] or "[]"),
                        action=TaskAction(**action_data),
                        status=TaskStatus(row["status"]),
                        assigned_node_id=row["assigned_node_id"],
                        progress=row["progress"],
                        result=json.loads(row["result"]) if row["result"] else None,
                        error=row["error"],
                        artifacts=json.loads(row["artifacts"] or "[]"),
                        created_at=row["created_at"],
                        started_at=row["started_at"],
                        completed_at=row["completed_at"],
                    )

                # Posts
                for row in cur.execute("SELECT * FROM posts").fetchall():
                    self.posts[row["id"]] = SocialPost(
                        id=row["id"],
                        author_id=row["author_id"],
                        author_name=row["author_name"],
                        author_role=row["author_role"],
                        author_avatar=row["author_avatar"] or "🤖",
                        content=row["content"],
                        mood=row["mood"] or "focused",
                        tags=json.loads(row["tags"] or "[]"),
                        mentions=json.loads(row["mentions"] or "[]"),
                        reactions=json.loads(row["reactions"] or "{}"),
                        comments_count=row["comments_count"] or 0,
                        created_at=row["created_at"],
                        is_ceo=bool(row["is_ceo"]),
                    )
                    self.comments[row["id"]] = []

                # Comments
                for row in cur.execute("SELECT * FROM comments ORDER BY created_at ASC").fetchall():
                    cmt = SocialComment(
                        id=row["id"],
                        post_id=row["post_id"],
                        author_id=row["author_id"],
                        author_name=row["author_name"],
                        author_role=row["author_role"],
                        author_avatar=row["author_avatar"] or "🤖",
                        content=row["content"],
                        reactions=json.loads(row["reactions"] or "{}"),
                        created_at=row["created_at"],
                    )
                    if cmt.post_id not in self.comments:
                        self.comments[cmt.post_id] = []
                    self.comments[cmt.post_id].append(cmt)

                # Preemption
                for row in cur.execute("SELECT * FROM preemption_history ORDER BY timestamp ASC LIMIT 200").fetchall():
                    self.preemption_history.append(
                        PreemptionSignal(
                            signal_id=row["signal_id"],
                            signal_type=PreemptionSignalType(row["signal_type"]),
                            node_id=row["node_id"],
                            username=row["username"],
                            details=row["details"] or "",
                            timestamp=row["timestamp"],
                        )
                    )

            logger.info(
                f"Loaded from SQLite: {len(self.goals)} goals, {len(self.tasks)} tasks, "
                f"{len(self.posts)} posts, {len(self.preemption_history)} preemption logs"
            )
        except Exception as e:
            logger.warning(f"Error loading state from SQLite: {e}")

    # --- SQLite Persistence Helpers ---
    def _persist_node(self, node: NodeInfo):
        if not self.db_path:
            return
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    node.node_id, node.name, node.hostname, node.platform_name, node.ip,
                    json.dumps(node.capabilities), node.status.value, node.control_mode.value,
                    node.current_task_id, node.cpu_percent, node.memory_percent, node.last_heartbeat,
                    node.persona_name, node.persona_role, node.persona_avatar
                ))
                conn.commit()
        except Exception as e:
            logger.debug(f"SQLite persist node error: {e}")

    def _persist_goal(self, goal: Goal):
        if not self.db_path:
            return
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO goals VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    goal.id, goal.title, goal.description, json.dumps(goal.task_ids),
                    goal.status.value, goal.created_at, goal.completed_at
                ))
                conn.commit()
        except Exception as e:
            logger.debug(f"SQLite persist goal error: {e}")

    def _persist_task(self, task: Task):
        if not self.db_path:
            return
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task.id, task.goal_id, task.title, task.description,
                    json.dumps(task.required_capabilities), json.dumps(task.dependencies),
                    task.action.model_dump_json(), task.status.value, task.assigned_node_id,
                    task.progress, json.dumps(task.result) if task.result else None,
                    task.error, json.dumps(task.artifacts),
                    task.created_at, task.started_at, task.completed_at
                ))
                conn.commit()
        except Exception as e:
            logger.debug(f"SQLite persist task error: {e}")

    def _persist_post(self, post: SocialPost):
        if not self.db_path:
            return
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO posts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    post.id, post.author_id, post.author_name, post.author_role,
                    post.author_avatar, post.content, post.mood.value, json.dumps(post.tags),
                    json.dumps(post.mentions), json.dumps(post.reactions), post.comments_count,
                    post.created_at, 1 if post.is_ceo else 0
                ))
                conn.commit()
        except Exception as e:
            logger.debug(f"SQLite persist post error: {e}")

    def _persist_comment(self, comment: SocialComment):
        if not self.db_path:
            return
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO comments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    comment.id, comment.post_id, comment.author_id, comment.author_name,
                    comment.author_role, comment.author_avatar, comment.content,
                    json.dumps(comment.reactions), comment.created_at
                ))
                conn.commit()
        except Exception as e:
            logger.debug(f"SQLite persist comment error: {e}")

    def _persist_preemption(self, signal: PreemptionSignal):
        if not self.db_path:
            return
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO preemption_history VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    signal.signal_id, signal.signal_type.value, signal.node_id,
                    signal.username, signal.details, signal.timestamp
                ))
                conn.commit()
        except Exception as e:
            logger.debug(f"SQLite persist preemption error: {e}")

    # --- Node Management ---
    async def register_node(self, node: NodeInfo) -> NodeInfo:
        async with self._lock:
            node.last_heartbeat = time.time()
            self.nodes[node.node_id] = node
            self._persist_node(node)
            return node

    async def get_node(self, node_id: str) -> Optional[NodeInfo]:
        async with self._lock:
            return self.nodes.get(node_id)

    async def get_all_nodes(self) -> List[NodeInfo]:
        async with self._lock:
            return list(self.nodes.values())

    async def update_node_heartbeat(
        self,
        node_id: str,
        cpu_pct: float = 0.0,
        mem_pct: float = 0.0,
        status: Optional[NodeStatus] = None,
        control_mode: Optional[ControlMode] = None,
        current_task_id: Optional[str] = None,
    ) -> Optional[NodeInfo]:
        async with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                return None
            node.last_heartbeat = time.time()
            node.cpu_percent = cpu_pct
            node.memory_percent = mem_pct
            if status is not None:
                node.status = status
            if control_mode is not None:
                node.control_mode = control_mode
            if current_task_id is not None:
                node.current_task_id = current_task_id
            self._persist_node(node)
            return node

    async def update_node_control_mode(
        self, node_id: str, control_mode: ControlMode, status: Optional[NodeStatus] = None
    ) -> Optional[NodeInfo]:
        async with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                return None
            node.control_mode = control_mode
            if status is not None:
                node.status = status
            self._persist_node(node)
            return node

    async def prune_dead_nodes(self, heartbeat_timeout_seconds: float = 30.0) -> List[str]:
        """Mark nodes that missed heartbeats as OFFLINE and re-queue their running tasks."""
        dead_ids: List[str] = []
        now = time.time()
        async with self._lock:
            for node_id, node in self.nodes.items():
                if node.status != NodeStatus.OFFLINE and (now - node.last_heartbeat) > heartbeat_timeout_seconds:
                    node.status = NodeStatus.OFFLINE
                    dead_ids.append(node_id)
                    self._persist_node(node)

                    # Re-queue active tasks so the DAG is not deadlocked
                    if node.current_task_id and node.current_task_id in self.tasks:
                        task = self.tasks[node.current_task_id]
                        if task.status in (TaskStatus.RUNNING, TaskStatus.PREEMPTED):
                            task.status = TaskStatus.PENDING
                            task.assigned_node_id = None
                            self._persist_task(task)
                        node.current_task_id = None
        return dead_ids

    # --- Goals ---
    async def add_goal(self, goal: Goal) -> Goal:
        async with self._lock:
            self.goals[goal.id] = goal
            self._persist_goal(goal)
            return goal

    async def get_goal(self, goal_id: str) -> Optional[Goal]:
        async with self._lock:
            return self.goals.get(goal_id)

    async def get_all_goals(self) -> List[Goal]:
        async with self._lock:
            return sorted(self.goals.values(), key=lambda g: g.created_at, reverse=True)

    async def update_goal_status(self, goal_id: str, status: GoalStatus) -> Optional[Goal]:
        async with self._lock:
            goal = self.goals.get(goal_id)
            if goal:
                goal.status = status
                if status in (GoalStatus.COMPLETED, GoalStatus.FAILED):
                    goal.completed_at = time.time()
                self._persist_goal(goal)
            return goal

    # --- Tasks ---
    async def add_task(self, task: Task) -> Task:
        async with self._lock:
            self.tasks[task.id] = task
            self._persist_task(task)
            return task

    async def get_task(self, task_id: str) -> Optional[Task]:
        async with self._lock:
            return self.tasks.get(task_id)

    async def get_all_tasks(self) -> List[Task]:
        async with self._lock:
            return sorted(self.tasks.values(), key=lambda t: t.created_at)

    async def get_tasks_for_goal(self, goal_id: str) -> List[Task]:
        async with self._lock:
            return [t for t in self.tasks.values() if t.goal_id == goal_id]

    async def update_task(self, task_id: str, **kwargs) -> Optional[Task]:
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return None
            for key, val in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, val)
            self._persist_task(task)
            return task

    # --- Preemption ---
    async def record_preemption(self, signal: PreemptionSignal) -> None:
        async with self._lock:
            self.preemption_history.append(signal)
            if len(self.preemption_history) > 200:
                self.preemption_history = self.preemption_history[-200:]
            self._persist_preemption(signal)

    async def get_preemption_history(self, limit: int = 50) -> List[PreemptionSignal]:
        async with self._lock:
            return list(reversed(self.preemption_history[-limit:]))

    # --- Social Feed ---
    async def add_post(self, post: SocialPost) -> SocialPost:
        async with self._lock:
            self.posts[post.id] = post
            if post.id not in self.comments:
                self.comments[post.id] = []
            self._persist_post(post)
            return post

    async def get_all_posts(self, limit: int = 50) -> List[SocialPost]:
        async with self._lock:
            sorted_posts = sorted(self.posts.values(), key=lambda p: p.created_at, reverse=True)
            return sorted_posts[:limit]

    async def get_post(self, post_id: str) -> Optional[SocialPost]:
        async with self._lock:
            return self.posts.get(post_id)

    async def add_comment(self, comment: SocialComment) -> Optional[SocialComment]:
        async with self._lock:
            post = self.posts.get(comment.post_id)
            if not post:
                return None
            if comment.post_id not in self.comments:
                self.comments[comment.post_id] = []
            self.comments[comment.post_id].append(comment)
            post.comments_count = len(self.comments[comment.post_id])
            self._persist_comment(comment)
            self._persist_post(post)
            return comment

    async def get_comments_for_post(self, post_id: str) -> List[SocialComment]:
        async with self._lock:
            return list(self.comments.get(post_id, []))

    async def add_reaction_to_post(self, post_id: str, emoji: str, user_id: str) -> Optional[SocialPost]:
        async with self._lock:
            post = self.posts.get(post_id)
            if not post:
                return None
            if emoji not in post.reactions:
                post.reactions[emoji] = []
            if user_id not in post.reactions[emoji]:
                post.reactions[emoji].append(user_id)
            self._persist_post(post)
            return post
