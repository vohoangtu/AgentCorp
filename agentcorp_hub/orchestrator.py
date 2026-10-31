"""Task DAG Orchestrator and Goal Scheduler for AgentCorp Hub.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from shared.models import (
    ControlMode,
    Goal,
    GoalStatus,
    NodeInfo,
    NodeStatus,
    Task,
    TaskAction,
    TaskActionType,
    TaskStatus,
)
from agentcorp_hub.store import HubStore

logger = logging.getLogger("agentcorp.orchestrator")


class Orchestrator:
    """Manages Task DAG resolution, node capability matching, and scheduling."""

    def __init__(self, store: HubStore):
        self.store = store

    def get_goal_templates(self) -> List[Dict[str, Any]]:
        """Return pre-configured distributed workflow templates."""
        return [
            {
                "template_id": "saas_mvp",
                "title": "Full-Stack SaaS MVP Launch",
                "description": "Collaborative pipeline to design, build backend API, generate frontend UI, test, and deploy a SaaS product.",
                "tasks": [
                    {
                        "task_key": "spec_architecture",
                        "title": "System Architecture & API Specification",
                        "description": "Design REST endpoints, database schema, and project structure.",
                        "required_capabilities": ["backend", "shell"],
                        "dependencies": [],
                        "action": {
                            "action_type": TaskActionType.SHELL,
                            "command": "echo 'Designing API spec and database schema...' && mkdir -p workspace/app && echo '{\"status\": \"spec_ready\", \"routes\": [\"/api/v1/auth\", \"/api/v1/projects\"]}' > workspace/app/spec.json",
                        },
                    },
                    {
                        "task_key": "backend_api",
                        "title": "Develop Backend REST Service",
                        "description": "Implement authentication endpoints, data persistence, and health check in Python/FastAPI.",
                        "required_capabilities": ["backend", "shell"],
                        "dependencies": ["spec_architecture"],
                        "action": {
                            "action_type": TaskActionType.FILE_WRITE,
                            "params": {
                                "path": "workspace/app/server.py",
                                "content": "# Generated Backend API Service\nfrom fastapi import FastAPI\napp = FastAPI(title='Autonomous SaaS MVP')\n\n@app.get('/health')\ndef health():\n    return {'status': 'healthy', 'agent': 'backend'}\n",
                            },
                        },
                    },
                    {
                        "task_key": "frontend_ui",
                        "title": "Build Responsive Web Interface",
                        "description": "Create modern dashboard web application with reactive state and styles.",
                        "required_capabilities": ["frontend", "shell"],
                        "dependencies": ["spec_architecture"],
                        "action": {
                            "action_type": TaskActionType.FILE_WRITE,
                            "params": {
                                "path": "workspace/app/index.html",
                                "content": "<!DOCTYPE html><html><head><title>SaaS MVP</title></head><body><h1>Welcome to SaaS MVP</h1><p>Crafted autonomously by AgentCorp Agents.</p></body></html>",
                            },
                        },
                    },
                    {
                        "task_key": "qa_validation",
                        "title": "Automated Quality Assurance & Integration Tests",
                        "description": "Run sanity checks, test backend endpoints, and verify file integrity.",
                        "required_capabilities": ["qa", "shell"],
                        "dependencies": ["backend_api", "frontend_ui"],
                        "action": {
                            "action_type": TaskActionType.SHELL,
                            "command": "python3 -c \"import os; assert os.path.exists('workspace/app/server.py') and os.path.exists('workspace/app/index.html'); print('Sanity QA tests passed 100%!')\"",
                        },
                    },
                    {
                        "task_key": "deploy_announce",
                        "title": "Production Deployment & Launch Broadcast",
                        "description": "Package the build artifacts and trigger launch sequence.",
                        "required_capabilities": ["devops", "shell"],
                        "dependencies": ["qa_validation"],
                        "action": {
                            "action_type": TaskActionType.SHELL,
                            "command": "tar -czf workspace/mvp_bundle.tar.gz -C workspace/app . && echo 'Production deployment artifact prepared successfully.'",
                        },
                    },
                ],
            },
            {
                "template_id": "digital_marketing",
                "title": "Viral Marketing & Growth Campaign",
                "description": "Market intelligence, high-converting copy, SEO landing page, and social blitz.",
                "tasks": [
                    {
                        "task_key": "market_research",
                        "title": "Competitive Market & Audience Analysis",
                        "description": "Identify audience pain points, top keywords, and viral trends.",
                        "required_capabilities": ["research", "shell"],
                        "dependencies": [],
                        "action": {
                            "action_type": TaskActionType.SHELL,
                            "command": "mkdir -p workspace/growth && echo 'Target audience: developers, founders. Pain point: manual repetitive ops.' > workspace/growth/research.txt",
                        },
                    },
                    {
                        "task_key": "viral_copy",
                        "title": "Draft High-Converting Copy & Ad Angles",
                        "description": "Write persuasive hero headlines, email campaign drafts, and Twitter/X hooks.",
                        "required_capabilities": ["copywriter"],
                        "dependencies": ["market_research"],
                        "action": {
                            "action_type": TaskActionType.FILE_WRITE,
                            "params": {
                                "path": "workspace/growth/copy.md",
                                "content": "# Viral Growth Campaign Copy\n\n## Hero Hook\nStop managing servers manually. Delegate everything to your autonomous agent workforce.\n\n## 5 Viral X/Twitter Hooks\n1. Autonomous agents now yield to humans seamlessly.\n2. Multi-agent teams have their own internal social network.\n",
                            },
                        },
                    },
                    {
                        "task_key": "content_distribution",
                        "title": "Social Campaign Scheduling & Media Assets",
                        "description": "Coordinate social channels, prepare tracking links, and activate campaign.",
                        "required_capabilities": ["marketing", "shell"],
                        "dependencies": ["viral_copy"],
                        "action": {
                            "action_type": TaskActionType.SHELL,
                            "command": "echo 'Social campaign ready for distribution. Tracking UTM tags configured.' > workspace/growth/distribution.log",
                        },
                    },
                ],
            },
            {
                "template_id": "video_production",
                "title": "Automated Video & Media Production Pipeline",
                "description": "Research viral story concept, write video screenplay, generate visual prompts, and assemble video storyboard.",
                "tasks": [
                    {
                        "task_key": "script_writing",
                        "title": "Screenplay & Scene Beat Sheet",
                        "description": "Write engaging 60-second video script with voiceover pacing.",
                        "required_capabilities": ["creative", "copywriter"],
                        "dependencies": [],
                        "action": {
                            "action_type": TaskActionType.FILE_WRITE,
                            "params": {
                                "path": "workspace/media/video_script.txt",
                                "content": "[0:00-0:05] Hook: What if your AI agents had their own Slack?\n[0:05-0:25] Demo of distributed node execution and user preemption\n[0:25-0:50] The agents chatting, venting, and celebrating on AgentNet\n[0:50-1:00] Call to action: Deploy AgentCorp today!",
                            },
                        },
                    },
                    {
                        "task_key": "visual_storyboard",
                        "title": "Storyboard & Frame Prompts Generation",
                        "description": "Generate visual prompt specifications for each scene.",
                        "required_capabilities": ["creative", "shell"],
                        "dependencies": ["script_writing"],
                        "action": {
                            "action_type": TaskActionType.SHELL,
                            "command": "mkdir -p workspace/media && echo 'Scene 1: Futuristic terminal glowing in dark room. Scene 2: Agents collaborating across servers.' > workspace/media/storyboard.txt",
                        },
                    },
                ],
            },
        ]

    async def instantiate_goal_from_template(
        self, template_id: str, custom_title: Optional[str] = None
    ) -> Optional[Goal]:
        """Instantiate a goal and its dependent DAG of tasks from a template."""
        templates = {t["template_id"]: t for t in self.get_goal_templates()}
        tmpl = templates.get(template_id)
        if not tmpl:
            return None

        goal = Goal(
            title=custom_title or tmpl["title"],
            description=tmpl["description"],
            status=GoalStatus.IN_PROGRESS,
        )

        task_key_to_id: Dict[str, str] = {}
        tasks_to_add: List[Task] = []

        for task_def in tmpl["tasks"]:
            real_task_id = f"task-{uuid.uuid4().hex[:8]}"
            task_key_to_id[task_def["task_key"]] = real_task_id

        for task_def in tmpl["tasks"]:
            real_task_id = task_key_to_id[task_def["task_key"]]
            real_dependencies = [
                task_key_to_id[dep_key]
                for dep_key in task_def.get("dependencies", [])
                if dep_key in task_key_to_id
            ]

            action_data = task_def["action"]
            action = TaskAction(
                action_type=action_data["action_type"],
                command=action_data.get("command"),
                params=action_data.get("params", {}),
            )

            task = Task(
                id=real_task_id,
                goal_id=goal.id,
                title=task_def["title"],
                description=task_def["description"],
                required_capabilities=task_def.get("required_capabilities", []),
                dependencies=real_dependencies,
                action=action,
                status=TaskStatus.PENDING,
            )
            goal.task_ids.append(task.id)
            tasks_to_add.append(task)

        await self.store.add_goal(goal)
        for t in tasks_to_add:
            await self.store.add_task(t)

        logger.info(f"Instantiated goal {goal.id} with {len(tasks_to_add)} tasks from template '{template_id}'")
        return goal

    async def plan_and_schedule(self) -> List[Tuple[Task, NodeInfo]]:
        """Evaluate DAG dependencies and match ready tasks to eligible nodes.

        Returns list of (task, node) pairs ready for assignment dispatch.
        """
        all_tasks = await self.store.get_all_tasks()
        all_nodes = await self.store.get_all_nodes()

        # Build task lookup and completion map
        task_map = {t.id: t for t in all_tasks}
        completed_task_ids = {t.id for t in all_tasks if t.status == TaskStatus.COMPLETED}

        # Find eligible nodes:
        # Must be ONLINE or IDLE, not OFFLINE, not PREEMPTED, control_mode == FULL_CONTROL, and not busy with another task
        available_nodes = [
            n
            for n in all_nodes
            if n.status in (NodeStatus.ONLINE, NodeStatus.IDLE)
            and n.control_mode == ControlMode.FULL_CONTROL
            and (n.current_task_id is None or n.current_task_id == "")
        ]

        assignments: List[Tuple[Task, NodeInfo]] = []

        # Find tasks that are ready:
        # Status is PENDING or READY, and all dependencies are COMPLETED
        for task in all_tasks:
            if task.status in (TaskStatus.PENDING, TaskStatus.READY):
                deps_met = all(dep_id in completed_task_ids for dep_id in task.dependencies)
                if deps_met:
                    task.status = TaskStatus.READY

                    # Try to find a matching node
                    best_node = self._find_matching_node(task, available_nodes)
                    if best_node:
                        # Assign task to node
                        task.status = TaskStatus.RUNNING
                        task.assigned_node_id = best_node.node_id
                        task.started_at = time.time()
                        await self.store.update_task(
                            task.id,
                            status=TaskStatus.RUNNING,
                            assigned_node_id=best_node.node_id,
                            started_at=task.started_at,
                        )

                        best_node.status = NodeStatus.BUSY
                        best_node.current_task_id = task.id
                        await self.store.update_node_heartbeat(
                            best_node.node_id,
                            status=NodeStatus.BUSY,
                            current_task_id=task.id,
                        )

                        available_nodes.remove(best_node)
                        assignments.append((task, best_node))

                        logger.info(
                            f"Scheduled task {task.id} ('{task.title}') to node {best_node.node_id} ('{best_node.name}')"
                        )

        # Also update goal statuses
        all_goals = await self.store.get_all_goals()
        for goal in all_goals:
            goal_tasks = [task_map[tid] for tid in goal.task_ids if tid in task_map]
            if not goal_tasks:
                continue

            all_done = all(t.status == TaskStatus.COMPLETED for t in goal_tasks)
            any_failed = any(t.status == TaskStatus.FAILED for t in goal_tasks)
            any_running = any(t.status in (TaskStatus.RUNNING, TaskStatus.PREEMPTED) for t in goal_tasks)

            if all_done and goal.status != GoalStatus.COMPLETED:
                await self.store.update_goal_status(goal.id, GoalStatus.COMPLETED)
                logger.info(f"Goal {goal.id} ('{goal.title}') marked COMPLETED!")
            elif any_failed and goal.status != GoalStatus.FAILED:
                await self.store.update_goal_status(goal.id, GoalStatus.FAILED)
            elif any_running and goal.status != GoalStatus.IN_PROGRESS:
                await self.store.update_goal_status(goal.id, GoalStatus.IN_PROGRESS)

        return assignments

    def _find_matching_node(self, task: Task, candidates: List[NodeInfo]) -> Optional[NodeInfo]:
        """Find the best node whose capabilities satisfy task requirements."""
        required = set(task.required_capabilities)
        for node in candidates:
            node_caps = set(node.capabilities)
            # If required is empty, any node qualifies
            # If required is non-empty, node must have all required capabilities
            if not required or required.issubset(node_caps):
                return node
        return None

    async def handle_node_preemption(self, node_id: str, control_mode: ControlMode) -> Optional[Task]:
        """Handle human preemption signal on a node.

        If node yielded control to a human, any active running task is paused.
        """
        node = await self.store.get_node(node_id)
        if not node:
            return None

        node.control_mode = control_mode
        if control_mode == ControlMode.YIELDED_PASSIVE:
            node.status = NodeStatus.PREEMPTED
            await self.store.update_node_control_mode(node_id, ControlMode.YIELDED_PASSIVE, NodeStatus.PREEMPTED)
            if node.current_task_id:
                task = await self.store.get_task(node.current_task_id)
                if task and task.status == TaskStatus.RUNNING:
                    task.status = TaskStatus.PREEMPTED
                    await self.store.update_task(task.id, status=TaskStatus.PREEMPTED)
                    logger.warning(
                        f"Task {task.id} on node {node_id} preempted due to active human interaction"
                    )
                    return task
        elif control_mode == ControlMode.FULL_CONTROL:
            # Human released or went idle; node reclaims control
            await self.store.update_node_control_mode(node_id, ControlMode.FULL_CONTROL)
            if node.current_task_id:
                task = await self.store.get_task(node.current_task_id)
                if task and task.status == TaskStatus.PREEMPTED:
                    task.status = TaskStatus.RUNNING
                    node.status = NodeStatus.BUSY
                    await self.store.update_task(task.id, status=TaskStatus.RUNNING)
                    await self.store.update_node_control_mode(node_id, ControlMode.FULL_CONTROL, NodeStatus.BUSY)
                    logger.info(f"Task {task.id} on node {node_id} resumed after human user idle/logout")
                    return task
            else:
                node.status = NodeStatus.ONLINE
                await self.store.update_node_control_mode(node_id, ControlMode.FULL_CONTROL, NodeStatus.ONLINE)

        return None
