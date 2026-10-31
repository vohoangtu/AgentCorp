"""FastAPI Hub Master Server for AgentCorp.
Coordinates distributed nodes, task DAGs, preemption signals, and the AgentNet social network.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from shared.events import AgentCorpMessage, EventType
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
    TaskStatus,
    WorkstationMode,
)
from agentcorp_hub.orchestrator import Orchestrator
from agentcorp_hub.social_manager import SocialManager
from agentcorp_hub.store import HubStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("agentcorp.hub")


class ConnectionManager:
    """Manages active WebSockets for nodes and UI clients."""

    def __init__(self):
        self.node_connections: Dict[str, WebSocket] = {}  # node_id -> ws
        self.ui_connections: Set[WebSocket] = set()

    async def connect_node(self, node_id: str, websocket: WebSocket):
        await websocket.accept()
        self.node_connections[node_id] = websocket
        logger.info(f"Node connected via WS: {node_id}")

    def disconnect_node(self, node_id: str):
        if node_id in self.node_connections:
            del self.node_connections[node_id]
            logger.info(f"Node disconnected: {node_id}")

    async def connect_ui(self, websocket: WebSocket):
        await websocket.accept()
        self.ui_connections.add(websocket)
        logger.info(f"UI client connected via WS. Total UI clients: {len(self.ui_connections)}")

    def disconnect_ui(self, websocket: WebSocket):
        self.ui_connections.discard(websocket)
        logger.info(f"UI client disconnected. Total UI clients: {len(self.ui_connections)}")

    async def send_to_node(self, node_id: str, message: AgentCorpMessage):
        ws = self.node_connections.get(node_id)
        if ws:
            try:
                await ws.send_text(message.model_dump_json())
            except Exception as e:
                logger.warning(f"Error sending message to node {node_id}: {e}")

    async def broadcast(self, message: AgentCorpMessage, skip_node: Optional[str] = None):
        """Broadcast message to all UI clients and all nodes (except skip_node if given)."""
        payload_json = message.model_dump_json()

        # Send to UI clients
        ui_dead: List[WebSocket] = []
        for ws in self.ui_connections:
            try:
                await ws.send_text(payload_json)
            except Exception:
                ui_dead.append(ws)
        for dead in ui_dead:
            self.ui_connections.discard(dead)

        # Send to nodes
        node_dead: List[str] = []
        for nid, ws in self.node_connections.items():
            if skip_node and nid == skip_node:
                continue
            try:
                await ws.send_text(payload_json)
            except Exception:
                node_dead.append(nid)
        for dead in node_dead:
            self.node_connections.pop(dead, None)


# Global instances
db_env = os.getenv("AGENTCORP_DB_PATH", "agentcorp.db")
db_path = None if db_env.lower() in ("none", "", "off", "false") else db_env
store = HubStore(db_path=db_path)
orchestrator = Orchestrator(store)
social_mgr = SocialManager(store)
connections = ConnectionManager()
background_tasks = []
pending_command_results: Dict[str, asyncio.Future] = {}


async def orchestrator_loop():
    """Background scheduler loop to match ready tasks with nodes."""
    logger.info("Orchestrator scheduler loop started.")
    while True:
        try:
            assignments = await orchestrator.plan_and_schedule()
            for task, node in assignments:
                # Dispatch TASK_ASSIGNED message to the node
                msg = AgentCorpMessage(
                    event_type=EventType.TASK_ASSIGNED,
                    source="hub",
                    target=f"node:{node.node_id}",
                    payload={"task": task.model_dump(), "node_id": node.node_id},
                )
                await connections.send_to_node(node.node_id, msg)
                # Broadcast update to UI
                await connections.broadcast(msg)

            # Prune stale nodes
            dead_nodes = await store.prune_dead_nodes(heartbeat_timeout_seconds=45.0)
            if dead_nodes:
                for dead_id in dead_nodes:
                    disc_msg = AgentCorpMessage(
                        event_type=EventType.NODE_DISCONNECTED,
                        source="hub",
                        payload={"node_id": dead_id},
                    )
                    await connections.broadcast(disc_msg)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in orchestrator loop: {e}", exc_info=True)

        await asyncio.sleep(1.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: seed social network and start background orchestrator loop
    await social_mgr.seed_initial_posts()
    loop_task = asyncio.create_task(orchestrator_loop())
    background_tasks.append(loop_task)
    yield
    # Shutdown
    loop_task.cancel()
    try:
        await loop_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="AgentCorp Hub Master", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- REST API Request Payloads ---
class GoalCreateRequest(BaseModel):
    template_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class PostCreateRequest(BaseModel):
    author_id: str
    author_name: str
    author_role: str
    content: str
    author_avatar: str = "🤖"
    mood: Optional[str] = "focused"
    is_ceo: bool = False
    tags: Optional[List[str]] = None


class CommentCreateRequest(BaseModel):
    author_id: str
    author_name: str
    author_role: str
    content: str
    author_avatar: str = "🤖"


class ReactRequest(BaseModel):
    emoji: str
    author_id: str


class ControlModeRequest(BaseModel):
    control_mode: ControlMode


class PreemptionSimulateRequest(BaseModel):
    node_id: str
    signal_type: PreemptionSignalType
    username: Optional[str] = "human_operator"
    details: str = "Manual simulation trigger"


class NodePauseRequest(BaseModel):
    reason: Optional[str] = "Paused by operator"


class NodeResumeRequest(BaseModel):
    reason: Optional[str] = "Resumed by operator"


class TaskCancelRequest(BaseModel):
    task_id: Optional[str] = None
    reason: Optional[str] = "Cancelled by operator"


class WorkstationModeRequest(BaseModel):
    workstation_mode: WorkstationMode


class NodeExecuteCommandRequest(BaseModel):
    command: str
    timeout: float = 15.0


class NodeReconfigRequest(BaseModel):
    config: Dict[str, Any]


# --- REST Endpoints ---
@app.get("/api/stats")
async def get_stats():
    nodes = await store.get_all_nodes()
    goals = await store.get_all_goals()
    tasks = await store.get_all_tasks()
    posts = await store.get_all_posts()
    return {
        "nodes_total": len(nodes),
        "nodes_online": sum(1 for n in nodes if n.status != NodeStatus.OFFLINE),
        "nodes_preempted": sum(1 for n in nodes if n.status == NodeStatus.PREEMPTED or n.control_mode == ControlMode.YIELDED_PASSIVE),
        "goals_total": len(goals),
        "goals_completed": sum(1 for g in goals if g.status == GoalStatus.COMPLETED),
        "tasks_total": len(tasks),
        "tasks_running": sum(1 for t in tasks if t.status == TaskStatus.RUNNING),
        "tasks_completed": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
        "posts_total": len(posts),
    }


@app.get("/api/nodes")
async def list_nodes():
    return await store.get_all_nodes()


@app.get("/api/nodes/{node_id}")
async def get_node(node_id: str):
    node = await store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@app.post("/api/nodes/{node_id}/control_mode")
async def set_node_control_mode(node_id: str, req: ControlModeRequest):
    node = await store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    new_mode = req.control_mode
    sig_type = PreemptionSignalType.MANUAL_TAKEOVER if new_mode == ControlMode.YIELDED_PASSIVE else PreemptionSignalType.MANUAL_RELEASE
    signal = PreemptionSignal(
        signal_type=sig_type,
        node_id=node_id,
        username="admin_ui",
        details=f"Admin set control mode to {new_mode}",
    )
    await store.record_preemption(signal)
    await orchestrator.handle_node_preemption(node_id, new_mode)

    # Broadcast mode change to cluster & node
    msg = AgentCorpMessage(
        event_type=EventType.CONTROL_MODE_CHANGED,
        source="hub",
        target=f"node:{node_id}",
        payload={"node_id": node_id, "control_mode": new_mode, "signal": signal.model_dump()},
    )
    await connections.broadcast(msg)
    return {"status": "ok", "node_id": node_id, "control_mode": new_mode}


@app.post("/api/nodes/{node_id}/pause")
async def pause_node(node_id: str, req: Optional[NodePauseRequest] = None):
    node = await store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    reason = req.reason if req else "Paused by operator"
    node.is_drained = True
    if node.status == NodeStatus.ONLINE:
        node.status = NodeStatus.IDLE
    await store.update_node_info(node)

    msg = AgentCorpMessage(
        event_type=EventType.CLIENT_PAUSE,
        source="hub",
        target=f"node:{node_id}",
        payload={"node_id": node_id, "reason": reason},
    )
    await connections.send_to_node(node_id, msg)
    await connections.broadcast(
        AgentCorpMessage(
            event_type=EventType.NODE_UPDATED,
            source="hub",
            payload={"node": node.model_dump()},
        )
    )
    return {"status": "ok", "node_id": node_id, "is_drained": True, "reason": reason}


@app.post("/api/nodes/{node_id}/resume")
async def resume_node(node_id: str, req: Optional[NodeResumeRequest] = None):
    node = await store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    reason = req.reason if req else "Resumed by operator"
    node.is_drained = False
    if node.status == NodeStatus.IDLE:
        node.status = NodeStatus.ONLINE
    await store.update_node_info(node)

    msg = AgentCorpMessage(
        event_type=EventType.CLIENT_RESUME,
        source="hub",
        target=f"node:{node_id}",
        payload={"node_id": node_id, "reason": reason},
    )
    await connections.send_to_node(node_id, msg)
    await connections.broadcast(
        AgentCorpMessage(
            event_type=EventType.NODE_UPDATED,
            source="hub",
            payload={"node": node.model_dump()},
        )
    )
    return {"status": "ok", "node_id": node_id, "is_drained": False, "reason": reason}


@app.post("/api/nodes/{node_id}/cancel_task")
async def cancel_node_task(node_id: str, req: Optional[TaskCancelRequest] = None):
    node = await store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    task_id = (req.task_id if req and req.task_id else None) or node.current_task_id
    reason = req.reason if req else "Cancelled by operator"

    # Send abort signal to node daemon
    msg = AgentCorpMessage(
        event_type=EventType.CLIENT_TASK_CANCEL,
        source="hub",
        target=f"node:{node_id}",
        payload={"node_id": node_id, "task_id": task_id, "reason": reason},
    )
    await connections.send_to_node(node_id, msg)

    if task_id:
        await orchestrator.handle_task_cancelled(task_id, reason)

    return {"status": "ok", "node_id": node_id, "cancelled_task_id": task_id}


@app.post("/api/nodes/{node_id}/workstation_mode")
async def set_workstation_mode(node_id: str, req: WorkstationModeRequest):
    node = await store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    node.workstation_mode = req.workstation_mode
    await store.update_node_info(node)

    msg = AgentCorpMessage(
        event_type=EventType.CLIENT_SET_MODE,
        source="hub",
        target=f"node:{node_id}",
        payload={"node_id": node_id, "workstation_mode": req.workstation_mode.value},
    )
    await connections.send_to_node(node_id, msg)
    await connections.broadcast(
        AgentCorpMessage(
            event_type=EventType.NODE_UPDATED,
            source="hub",
            payload={"node": node.model_dump()},
        )
    )
    return {"status": "ok", "node_id": node_id, "workstation_mode": req.workstation_mode}


@app.post("/api/nodes/{node_id}/execute")
async def execute_command_on_node(node_id: str, req: NodeExecuteCommandRequest):
    node = await store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if node_id not in connections.node_connections:
        raise HTTPException(status_code=400, detail="Node is not currently connected via WebSocket")

    import uuid
    cmd_id = f"cmd-{uuid.uuid4().hex[:8]}"
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    pending_command_results[cmd_id] = fut

    msg = AgentCorpMessage(
        event_type=EventType.CLIENT_EXEC_COMMAND,
        source="hub",
        target=f"node:{node_id}",
        payload={"command_id": cmd_id, "node_id": node_id, "command": req.command},
    )
    await connections.send_to_node(node_id, msg)

    try:
        timeout = min(max(req.timeout, 1.0), 60.0)
        result = await asyncio.wait_for(fut, timeout=timeout)
        return {"status": "success", "result": result}
    except asyncio.TimeoutError:
        pending_command_results.pop(cmd_id, None)
        return {"status": "timeout", "detail": "Command timed out waiting for node response"}


@app.get("/api/nodes/{node_id}/config")
async def get_node_config(node_id: str):
    node = await store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node.config or {
        "node_id": node.node_id,
        "name": node.name,
        "capabilities": node.capabilities,
        "workstation_mode": node.workstation_mode,
        "is_drained": node.is_drained,
    }


@app.post("/api/nodes/{node_id}/config")
async def update_node_config(node_id: str, req: NodeReconfigRequest):
    node = await store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    msg = AgentCorpMessage(
        event_type=EventType.CLIENT_RECONFIG,
        source="hub",
        target=f"node:{node_id}",
        payload={"node_id": node_id, "config": req.config},
    )
    await connections.send_to_node(node_id, msg)
    return {"status": "ok", "node_id": node_id, "sent_config": req.config}


@app.get("/api/templates")
async def get_templates():
    return orchestrator.get_goal_templates()


@app.get("/api/goals")
async def list_goals():
    return await store.get_all_goals()


@app.post("/api/goals")
async def create_goal(req: GoalCreateRequest):
    if req.template_id:
        goal = await orchestrator.instantiate_goal_from_template(req.template_id, req.title)
        if not goal:
            raise HTTPException(status_code=400, detail="Invalid template ID")
        # Broadcast goal creation
        await connections.broadcast(
            AgentCorpMessage(
                event_type=EventType.GOAL_UPDATED,
                source="hub",
                payload={"goal": goal.model_dump()},
            )
        )
        return goal

    # Custom blank goal
    goal = Goal(
        title=req.title or "Untitled Autonomous Goal",
        description=req.description or "",
        status=GoalStatus.IN_PROGRESS,
    )
    await store.add_goal(goal)
    return goal


@app.get("/api/tasks")
async def list_tasks(goal_id: Optional[str] = None):
    if goal_id:
        return await store.get_tasks_for_goal(goal_id)
    return await store.get_all_tasks()


@app.get("/api/feed")
async def list_feed():
    posts = await store.get_all_posts()
    result = []
    for p in posts:
        cmts = await store.get_comments_for_post(p.id)
        p_dict = p.model_dump()
        p_dict["comments"] = [c.model_dump() for c in cmts]
        result.append(p_dict)
    return result


@app.post("/api/feed")
async def create_post(req: PostCreateRequest):
    post = await social_mgr.create_post(
        author_id=req.author_id,
        author_name=req.author_name,
        author_role=req.author_role,
        content=req.content,
        mood=req.mood or "focused",
        author_avatar=req.author_avatar,
        is_ceo=req.is_ceo,
        tags=req.tags,
    )
    msg = AgentCorpMessage(
        event_type=EventType.SOCIAL_POST_CREATED,
        source=f"user:{req.author_id}",
        payload={"post": post.model_dump()},
    )
    await connections.broadcast(msg)
    return post


@app.post("/api/feed/{post_id}/comments")
async def add_comment(post_id: str, req: CommentCreateRequest):
    comment = await social_mgr.add_comment(
        post_id=post_id,
        author_id=req.author_id,
        author_name=req.author_name,
        author_role=req.author_role,
        content=req.content,
        author_avatar=req.author_avatar,
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Post not found")

    msg = AgentCorpMessage(
        event_type=EventType.SOCIAL_COMMENT_CREATED,
        source=f"user:{req.author_id}",
        payload={"comment": comment.model_dump(), "post_id": post_id},
    )
    await connections.broadcast(msg)
    return comment


@app.post("/api/feed/{post_id}/react")
async def react_to_post(post_id: str, req: ReactRequest):
    updated_post = await social_mgr.react_to_post(post_id, req.emoji, req.author_id)
    if not updated_post:
        raise HTTPException(status_code=404, detail="Post not found")

    msg = AgentCorpMessage(
        event_type=EventType.SOCIAL_REACTION_ADDED,
        source=f"user:{req.author_id}",
        payload={"post_id": post_id, "emoji": req.emoji, "author_id": req.author_id},
    )
    await connections.broadcast(msg)
    return updated_post


@app.get("/api/preemption/history")
async def get_preemption_history():
    return await store.get_preemption_history()


@app.post("/api/preemption/simulate")
async def simulate_preemption(req: PreemptionSimulateRequest):
    signal = PreemptionSignal(
        signal_type=req.signal_type,
        node_id=req.node_id,
        username=req.username,
        details=req.details,
    )
    await store.record_preemption(signal)

    # Determine mode
    if req.signal_type in (PreemptionSignalType.USER_DETECTED, PreemptionSignalType.MANUAL_TAKEOVER):
        new_mode = ControlMode.YIELDED_PASSIVE
    else:
        new_mode = ControlMode.FULL_CONTROL

    await orchestrator.handle_node_preemption(req.node_id, new_mode)

    msg = AgentCorpMessage(
        event_type=EventType.PREEMPTION_SIGNAL,
        source="hub_simulation",
        target=f"node:{req.node_id}",
        payload={"signal": signal.model_dump(), "control_mode": new_mode},
    )
    await connections.broadcast(msg)
    return {"status": "ok", "signal": signal, "control_mode": new_mode}


# --- WebSocket Endpoint for Nodes & UI ---
@app.websocket("/ws/hub")
async def websocket_hub_endpoint(websocket: WebSocket):
    query_params = websocket.query_params
    client_type = query_params.get("client_type", "ui")  # "node" or "ui"
    node_id = query_params.get("node_id")

    if client_type == "node" and node_id:
        await connections.connect_node(node_id, websocket)
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    payload_dict = json.loads(data)
                    msg = AgentCorpMessage(**payload_dict)
                    await handle_node_message(node_id, msg)
                except Exception as ex:
                    logger.warning(f"Malformed message from node {node_id}: {ex}")
        except (WebSocketDisconnect, asyncio.CancelledError):
            connections.disconnect_node(node_id)
            node = await store.get_node(node_id)
            if node:
                node.status = NodeStatus.OFFLINE
                if node.current_task_id:
                    task = await store.get_task(node.current_task_id)
                    if task and task.status in (TaskStatus.RUNNING, TaskStatus.PREEMPTED):
                        await store.update_task(task.id, status=TaskStatus.PENDING, assigned_node_id=None)
                    node.current_task_id = None
                await connections.broadcast(
                    AgentCorpMessage(
                        event_type=EventType.NODE_DISCONNECTED,
                        source="hub",
                        payload={"node_id": node_id},
                    )
                )
    else:
        # UI connection
        await connections.connect_ui(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                # UI might send actions (e.g. quick reactions)
                try:
                    payload_dict = json.loads(data)
                    msg = AgentCorpMessage(**payload_dict)
                    await handle_ui_message(msg)
                except Exception as ex:
                    logger.debug(f"UI message parse error: {ex}")
        except (WebSocketDisconnect, asyncio.CancelledError):
            connections.disconnect_ui(websocket)


async def handle_node_message(node_id: str, msg: AgentCorpMessage):
    """Handle inbound messages sent by an autonomous node."""
    event = msg.event_type

    if event == EventType.NODE_REGISTER:
        node_info = NodeInfo(**msg.payload["node"])
        await store.register_node(node_info)
        # Reply confirmation
        ack = AgentCorpMessage(
            event_type=EventType.NODE_REGISTERED,
            source="hub",
            target=f"node:{node_id}",
            payload={"status": "registered", "node_id": node_id},
        )
        await connections.send_to_node(node_id, ack)
        # Broadcast node joined
        await connections.broadcast(
            AgentCorpMessage(
                event_type=EventType.NODE_UPDATED,
                source="hub",
                payload={"node": node_info.model_dump()},
            )
        )

    elif event == EventType.NODE_UPDATED:
        if "node" in msg.payload:
            node_info = NodeInfo(**msg.payload["node"])
            await store.update_node_info(node_info)
        await connections.broadcast(msg)

    elif event == EventType.NODE_HEARTBEAT:
        raw_status = msg.payload.get("status")
        raw_mode = msg.payload.get("control_mode")
        raw_ws_mode = msg.payload.get("workstation_mode")
        await store.update_node_heartbeat(
            node_id=node_id,
            cpu_pct=msg.payload.get("cpu_percent", 0.0),
            mem_pct=msg.payload.get("memory_percent", 0.0),
            status=NodeStatus(raw_status) if raw_status else None,
            control_mode=ControlMode(raw_mode) if raw_mode else None,
            current_task_id=msg.payload.get("current_task_id"),
            is_drained=msg.payload.get("is_drained"),
            workstation_mode=WorkstationMode(raw_ws_mode) if raw_ws_mode else None,
        )

    elif event == EventType.CLIENT_TASK_CANCEL:
        task_id = msg.payload.get("task_id")
        reason = msg.payload.get("reason", "Cancelled by operator")
        if task_id:
            await orchestrator.handle_task_cancelled(task_id, reason)
        await connections.broadcast(msg)

    elif event == EventType.CLIENT_COMMAND_RESULT:
        cmd_id = msg.payload.get("command_id")
        if cmd_id and cmd_id in pending_command_results:
            fut = pending_command_results.pop(cmd_id)
            if not fut.done():
                fut.set_result(msg.payload)
        await connections.broadcast(msg)

    elif event == EventType.PREEMPTION_SIGNAL:
        signal = PreemptionSignal(**msg.payload["signal"])
        await store.record_preemption(signal)
        control_mode = msg.payload.get("control_mode", ControlMode.YIELDED_PASSIVE)
        await orchestrator.handle_node_preemption(node_id, control_mode)
        # Broadcast to UI
        await connections.broadcast(msg)

    elif event == EventType.TASK_PROGRESS:
        task_id = msg.payload["task_id"]
        progress = msg.payload.get("progress", 0.0)
        await store.update_task(task_id, progress=progress)
        await connections.broadcast(msg)

    elif event == EventType.TASK_PAUSED:
        task_id = msg.payload["task_id"]
        reason = msg.payload.get("reason", "Preempted by human")
        await store.update_task(task_id, status=TaskStatus.PREEMPTED, error=reason)
        await connections.broadcast(msg)

    elif event == EventType.TASK_RESUMED:
        task_id = msg.payload["task_id"]
        await store.update_task(task_id, status=TaskStatus.RUNNING)
        await connections.broadcast(msg)

    elif event == EventType.TASK_COMPLETED:
        task_id = msg.payload["task_id"]
        result = msg.payload.get("result", {})
        artifacts = msg.payload.get("artifacts", [])
        await store.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100.0,
            result=result,
            artifacts=artifacts,
        )
        # Free up node
        node = await store.get_node(node_id)
        if node and node.control_mode == ControlMode.FULL_CONTROL:
            node.status = NodeStatus.ONLINE
            node.current_task_id = None

        await connections.broadcast(msg)

    elif event == EventType.TASK_FAILED:
        task_id = msg.payload["task_id"]
        error = msg.payload.get("error", "Unknown error")
        await store.update_task(task_id, status=TaskStatus.FAILED, error=error)
        node = await store.get_node(node_id)
        if node and node.control_mode == ControlMode.FULL_CONTROL:
            node.status = NodeStatus.ONLINE
            node.current_task_id = None
        await connections.broadcast(msg)

    elif event == EventType.SOCIAL_POST_CREATED:
        post = SocialPost(**msg.payload["post"])
        await store.add_post(post)
        await connections.broadcast(msg, skip_node=node_id)

    elif event == EventType.SOCIAL_COMMENT_CREATED:
        comment = SocialComment(**msg.payload["comment"])
        await store.add_comment(comment)
        await connections.broadcast(msg, skip_node=node_id)

    elif event == EventType.SOCIAL_REACTION_ADDED:
        post_id = msg.payload["post_id"]
        emoji = msg.payload["emoji"]
        author_id = msg.payload["author_id"]
        await store.add_reaction_to_post(post_id, emoji, author_id)
        await connections.broadcast(msg, skip_node=node_id)


async def handle_ui_message(msg: AgentCorpMessage):
    """Handle inbound messages sent by UI clients."""
    if msg.event_type == EventType.CEO_ANNOUNCEMENT:
        # Create a CEO post
        post = await social_mgr.create_post(
            author_id="ceo-001",
            author_name="CEO / Founder",
            author_role="Executive",
            author_avatar="👑",
            content=msg.payload.get("content", ""),
            mood="hyped",
            is_ceo=True,
        )
        await connections.broadcast(
            AgentCorpMessage(
                event_type=EventType.SOCIAL_POST_CREATED,
                source="ceo",
                payload={"post": post.model_dump()},
            )
        )


# --- Serve Static UI Files ---
UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agentcorp_ui")
if os.path.isdir(UI_DIR):
    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")

    @app.get("/")
    async def serve_index():
        index_file = os.path.join(UI_DIR, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return HTMLResponse("<h1>AgentCorp UI files initializing...</h1>")
