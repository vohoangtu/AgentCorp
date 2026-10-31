"""Client Control CLI for AgentCorp Agent Nodes.
Provides operators and developers with direct terminal commands to inspect,
configure, and control edge worker agents locally or across the cluster.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional
import httpx

from shared.config import (
    AgentClientConfig,
    load_agent_client_config,
    save_agent_client_config,
)
from shared.models import WorkstationMode


def _get_hub_http_url(hub_url: str) -> str:
    """Convert ws:// to http:// and wss:// to https://"""
    if hub_url.startswith("ws://"):
        return hub_url.replace("ws://", "http://", 1).rstrip("/ws/hub")
    elif hub_url.startswith("wss://"):
        return hub_url.replace("wss://", "https://", 1).rstrip("/ws/hub")
    elif hub_url.startswith("http://") or hub_url.startswith("https://"):
        return hub_url.rstrip("/")
    return f"http://{hub_url.rstrip('/')}"


def cmd_status(args):
    """Query status of a node or all nodes."""
    config = load_agent_client_config(config_path=args.config_file)
    hub_url = _get_hub_http_url(args.hub_url or config.hub_url)
    target_node = args.node_id or config.node_id

    try:
        if target_node:
            res = httpx.get(f"{hub_url}/api/nodes/{target_node}", timeout=5.0)
            if res.status_code == 404:
                print(f"❌ Node '{target_node}' not found on Hub ({hub_url}).")
                sys.exit(1)
            res.raise_for_status()
            node = res.json()
            print("==================================================")
            print(f"⚡ Node Status: {node.get('persona_avatar', '🤖')} {node.get('name')} ({node.get('node_id')})")
            print("==================================================")
            print(f"  Hostname         : {node.get('hostname')}")
            print(f"  Status           : {node.get('status')}")
            print(f"  Control Mode     : {node.get('control_mode')}")
            print(f"  Workstation Mode : {node.get('workstation_mode')}")
            print(f"  Drained/Paused   : {'YES ⏸️' if node.get('is_drained') else 'NO ▶️'}")
            print(f"  Current Task     : {node.get('current_task_id') or 'Idle'}")
            print(f"  System Load      : CPU {node.get('cpu_percent', 0):.1f}% | RAM {node.get('memory_percent', 0):.1f}%")
            print(f"  Capabilities     : {', '.join(node.get('capabilities', []))}")
            print("==================================================")
        else:
            res = httpx.get(f"{hub_url}/api/nodes", timeout=5.0)
            res.raise_for_status()
            nodes = res.json()
            print(f"⚡ Active Nodes on Hub ({len(nodes)} total):")
            for n in nodes:
                drained = " [PAUSED]" if n.get("is_drained") else ""
                print(f"  - {n.get('persona_avatar', '🤖')} {n.get('name')} ({n.get('node_id')}) : {n.get('status')}{drained} [{n.get('control_mode')}]")
    except Exception as e:
        print(f"❌ Error contacting Hub at {hub_url}: {e}")
        sys.exit(1)


def cmd_pause(args):
    """Pause/drain a node."""
    config = load_agent_client_config(config_path=args.config_file)
    hub_url = _get_hub_http_url(args.hub_url or config.hub_url)
    node_id = args.node_id or config.node_id

    try:
        res = httpx.post(f"{hub_url}/api/nodes/{node_id}/pause", json={"reason": args.reason}, timeout=5.0)
        res.raise_for_status()
        data = res.json()
        print(f"⏸️ Successfully paused node '{node_id}' (Reason: {data.get('reason')}). Node will not accept new tasks.")
    except Exception as e:
        print(f"❌ Failed to pause node '{node_id}': {e}")
        sys.exit(1)


def cmd_resume(args):
    """Resume a paused node."""
    config = load_agent_client_config(config_path=args.config_file)
    hub_url = _get_hub_http_url(args.hub_url or config.hub_url)
    node_id = args.node_id or config.node_id

    try:
        res = httpx.post(f"{hub_url}/api/nodes/{node_id}/resume", json={"reason": args.reason}, timeout=5.0)
        res.raise_for_status()
        print(f"▶️ Successfully resumed node '{node_id}'. Node is ready for tasks.")
    except Exception as e:
        print(f"❌ Failed to resume node '{node_id}': {e}")
        sys.exit(1)


def cmd_cancel_task(args):
    """Cancel the current task on a node."""
    config = load_agent_client_config(config_path=args.config_file)
    hub_url = _get_hub_http_url(args.hub_url or config.hub_url)
    node_id = args.node_id or config.node_id

    try:
        payload = {"reason": args.reason}
        if args.task_id:
            payload["task_id"] = args.task_id
        res = httpx.post(f"{hub_url}/api/nodes/{node_id}/cancel_task", json=payload, timeout=5.0)
        res.raise_for_status()
        data = res.json()
        print(f"🛑 Aborted task '{data.get('cancelled_task_id')}' on node '{node_id}'.")
    except Exception as e:
        print(f"❌ Failed to cancel task on node '{node_id}': {e}")
        sys.exit(1)


def cmd_mode(args):
    """Change workstation mode."""
    config = load_agent_client_config(config_path=args.config_file)
    hub_url = _get_hub_http_url(args.hub_url or config.hub_url)
    node_id = args.node_id or config.node_id
    new_mode = args.mode.upper()

    try:
        res = httpx.post(f"{hub_url}/api/nodes/{node_id}/workstation_mode", json={"workstation_mode": new_mode}, timeout=5.0)
        res.raise_for_status()
        print(f"🔄 Set workstation mode of '{node_id}' to: {new_mode}")
    except Exception as e:
        print(f"❌ Failed to set workstation mode: {e}")
        sys.exit(1)


def cmd_exec(args):
    """Execute an ad-hoc command on a node."""
    config = load_agent_client_config(config_path=args.config_file)
    hub_url = _get_hub_http_url(args.hub_url or config.hub_url)
    node_id = args.node_id or config.node_id
    cmd = " ".join(args.command)

    print(f"⚡ Dispatching ad-hoc command to '{node_id}': {cmd}")
    try:
        res = httpx.post(
            f"{hub_url}/api/nodes/{node_id}/execute",
            json={"command": cmd, "timeout": args.timeout},
            timeout=args.timeout + 5.0,
        )
        res.raise_for_status()
        data = res.json()
        if data.get("status") == "success":
            r = data.get("result", {})
            print(f"--- Output (Exit code: {r.get('exit_code')}, Duration: {r.get('duration', 0):.2f}s) ---")
            if r.get("stdout"):
                print(r.get("stdout"))
            if r.get("stderr"):
                print(f"[stderr]: {r.get('stderr')}", file=sys.stderr)
        else:
            print(f"⚠️ Command execution response: {data}")
    except Exception as e:
        print(f"❌ Failed to execute command: {e}")
        sys.exit(1)


def cmd_config_get(args):
    """Inspect local or remote configuration."""
    if args.remote:
        config = load_agent_client_config(config_path=args.config_file)
        hub_url = _get_hub_http_url(args.hub_url or config.hub_url)
        node_id = args.node_id or config.node_id
        res = httpx.get(f"{hub_url}/api/nodes/{node_id}/config", timeout=5.0)
        res.raise_for_status()
        print(json.dumps(res.json(), indent=2))
    else:
        config = load_agent_client_config(config_path=args.config_file)
        print(json.dumps(config.to_dict(), indent=2))


def cmd_config_set(args):
    """Set local config or push remote reconfig."""
    config = load_agent_client_config(config_path=args.config_file)
    updates: Dict[str, Any] = {}
    if args.mode:
        updates["workstation_mode"] = args.mode.upper()
    if args.inactivity_seconds is not None:
        updates["inactivity_threshold_seconds"] = args.inactivity_seconds
    if args.banter is not None:
        updates["enable_social_banter"] = args.banter.lower() in ("true", "1", "yes")

    if not updates:
        print("No configuration updates specified.")
        return

    if args.remote:
        hub_url = _get_hub_http_url(args.hub_url or config.hub_url)
        node_id = args.node_id or config.node_id
        res = httpx.post(f"{hub_url}/api/nodes/{node_id}/config", json={"config": updates}, timeout=5.0)
        res.raise_for_status()
        print(f"🚀 Sent remote configuration update to '{node_id}': {updates}")
    else:
        config.update_dynamic(updates)
        save_path = args.config_file or "config.yaml"
        save_agent_client_config(config, save_path)
        print(f"💾 Updated local configuration saved to '{save_path}': {updates}")


def main():
    parser = argparse.ArgumentParser(description="AgentCorp Client Control Utility (client_ctl)")
    parser.add_argument("--hub-url", type=str, default=None, help="Hub HTTP/WS base URL")
    parser.add_argument("--config-file", type=str, default=None, help="Path to config.yaml")

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # status
    p_status = subparsers.add_parser("status", help="Check node status and metrics")
    p_status.add_argument("node_id", nargs="?", default=None, help="Optional node ID")
    p_status.set_defaults(func=cmd_status)

    # pause
    p_pause = subparsers.add_parser("pause", help="Pause/drain node from receiving new tasks")
    p_pause.add_argument("node_id", nargs="?", default=None, help="Node ID to pause")
    p_pause.add_argument("--reason", type=str, default="Paused via client_ctl", help="Reason for pausing")
    p_pause.set_defaults(func=cmd_pause)

    # resume
    p_resume = subparsers.add_parser("resume", help="Resume paused node to accept tasks")
    p_resume.add_argument("node_id", nargs="?", default=None, help="Node ID to resume")
    p_resume.add_argument("--reason", type=str, default="Resumed via client_ctl", help="Reason for resuming")
    p_resume.set_defaults(func=cmd_resume)

    # cancel-task
    p_cancel = subparsers.add_parser("cancel-task", help="Abort current running task on node")
    p_cancel.add_argument("node_id", nargs="?", default=None, help="Node ID")
    p_cancel.add_argument("--task-id", type=str, default=None, help="Optional Task ID")
    p_cancel.add_argument("--reason", type=str, default="Aborted via client_ctl", help="Reason")
    p_cancel.set_defaults(func=cmd_cancel_task)

    # mode
    p_mode = subparsers.add_parser("mode", help="Change workstation mode (BACKGROUND | EXCLUSIVE)")
    p_mode.add_argument("mode", choices=["BACKGROUND", "EXCLUSIVE", "background", "exclusive"], help="Mode")
    p_mode.add_argument("node_id", nargs="?", default=None, help="Optional Node ID")
    p_mode.set_defaults(func=cmd_mode)

    # exec
    p_exec = subparsers.add_parser("exec", help="Execute an ad-hoc shell command on node")
    p_exec.add_argument("node_id", type=str, help="Target Node ID")
    p_exec.add_argument("command", nargs="+", help="Command to execute")
    p_exec.add_argument("--timeout", type=float, default=15.0, help="Timeout in seconds")
    p_exec.set_defaults(func=cmd_exec)

    # config
    p_cfg = subparsers.add_parser("config", help="Manage client configuration")
    p_cfg_sub = p_cfg.add_subparsers(dest="config_action", required=True)

    p_cfg_get = p_cfg_sub.add_parser("get", help="Get configuration")
    p_cfg_get.add_argument("--node-id", type=str, default=None, help="Node ID")
    p_cfg_get.add_argument("--remote", action="store_true", help="Query live config from Hub")
    p_cfg_get.set_defaults(func=cmd_config_get)

    p_cfg_set = p_cfg_sub.add_parser("set", help="Update configuration")
    p_cfg_set.add_argument("--node-id", type=str, default=None, help="Node ID")
    p_cfg_set.add_argument("--remote", action="store_true", help="Update remote node via Hub")
    p_cfg_set.add_argument("--mode", choices=["BACKGROUND", "EXCLUSIVE"], default=None, help="Workstation mode")
    p_cfg_set.add_argument("--inactivity-seconds", type=float, default=None, help="Inactivity threshold")
    p_cfg_set.add_argument("--banter", type=str, choices=["true", "false"], default=None, help="Enable banter")
    p_cfg_set.set_defaults(func=cmd_config_set)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
