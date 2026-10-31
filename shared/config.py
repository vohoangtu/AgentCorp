"""Configuration models and loader for AgentCorp Agent Client (Node Daemon).
Supports YAML/JSON file configs, environment variable overrides, and CLI overrides.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from shared.models import WorkstationMode

try:
    import yaml
except ImportError:
    yaml = None


def _default_node_id() -> str:
    host = socket.gethostname().lower().replace(" ", "-")
    return f"node-{host}"


def _default_node_name() -> str:
    host = socket.gethostname()
    return f"Agent-{host}"


class PreemptionConfig(BaseModel):
    inactivity_threshold_seconds: float = 15.0
    poll_interval_seconds: float = 0.5
    flag_file_path: Optional[str] = "/tmp/.agentcorp_user_active"
    workstation_mode: WorkstationMode = WorkstationMode.BACKGROUND


class SocialConfig(BaseModel):
    enable_social_banter: bool = True
    spontaneous_post_interval_seconds: float = 90.0


class BrainConfig(BaseModel):
    provider: Optional[str] = None  # gemini, openai, ollama, tuzygent, rule_based
    model_name: Optional[str] = None
    temperature: float = 0.7


class AgentClientConfig(BaseModel):
    """Complete runtime configuration for an Agent Client node."""

    node_id: str = Field(default_factory=_default_node_id)
    name: str = Field(default_factory=_default_node_name)
    hub_url: str = "ws://127.0.0.1:8000/ws/hub"
    persona_id: str = "devops_dan"
    capabilities: List[str] = Field(
        default_factory=lambda: ["backend", "frontend", "devops", "marketing", "qa", "shell", "gui", "browser"]
    )
    workspace_dir: str = "./workspace"
    heartbeat_interval_seconds: float = 4.0
    reconnect_backoff_initial: float = 1.0
    reconnect_backoff_max: float = 10.0
    enable_ethical_guard: bool = True

    preemption: PreemptionConfig = Field(default_factory=PreemptionConfig)
    social: SocialConfig = Field(default_factory=SocialConfig)
    brain: BrainConfig = Field(default_factory=BrainConfig)

    # Convenience properties for flat access
    @property
    def workstation_mode(self) -> WorkstationMode:
        return self.preemption.workstation_mode

    @workstation_mode.setter
    def workstation_mode(self, val: WorkstationMode) -> None:
        self.preemption.workstation_mode = val

    @property
    def inactivity_threshold_seconds(self) -> float:
        return self.preemption.inactivity_threshold_seconds

    @inactivity_threshold_seconds.setter
    def inactivity_threshold_seconds(self, val: float) -> None:
        self.preemption.inactivity_threshold_seconds = val

    @property
    def enable_social_banter(self) -> bool:
        return self.social.enable_social_banter

    @enable_social_banter.setter
    def enable_social_banter(self, val: bool) -> None:
        self.social.enable_social_banter = val

    def update_dynamic(self, updates: Dict[str, Any]) -> List[str]:
        """Apply dynamic configuration updates in-place.
        Returns list of fields modified.
        """
        changed = []
        for key, val in updates.items():
            if val is None:
                continue
            if key == "workstation_mode":
                self.preemption.workstation_mode = WorkstationMode(val)
                changed.append("preemption.workstation_mode")
            elif key == "inactivity_threshold_seconds":
                self.preemption.inactivity_threshold_seconds = float(val)
                changed.append("preemption.inactivity_threshold_seconds")
            elif key == "poll_interval_seconds":
                self.preemption.poll_interval_seconds = float(val)
                changed.append("preemption.poll_interval_seconds")
            elif key == "enable_social_banter":
                self.social.enable_social_banter = bool(val)
                changed.append("social.enable_social_banter")
            elif key == "spontaneous_post_interval_seconds":
                self.social.spontaneous_post_interval_seconds = float(val)
                changed.append("social.spontaneous_post_interval_seconds")
            elif key == "capabilities" and isinstance(val, list):
                self.capabilities = list(val)
                changed.append("capabilities")
            elif key == "name":
                self.name = str(val)
                changed.append("name")
            elif key == "hub_url":
                self.hub_url = str(val)
                changed.append("hub_url")
            elif key == "enable_ethical_guard":
                self.enable_ethical_guard = bool(val)
                changed.append("enable_ethical_guard")
        return changed

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


def load_agent_client_config(
    config_path: Optional[str] = None,
    cli_args: Optional[Dict[str, Any]] = None,
) -> AgentClientConfig:
    """Load configuration with precedence:
    CLI args > Environment Variables > Config File (YAML/JSON) > Defaults.
    """
    raw_data: Dict[str, Any] = {}

    # 1. Search for config file if not explicitly specified
    candidate_paths = []
    if config_path:
        candidate_paths.append(Path(config_path))
    else:
        env_cfg = os.getenv("AGENTCORP_CONFIG_PATH")
        if env_cfg:
            candidate_paths.append(Path(env_cfg))
        candidate_paths.extend([
            Path("config.yaml"),
            Path("config.yml"),
            Path("client_config.yaml"),
            Path("config.example.yaml"),
        ])

    for p in candidate_paths:
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8")
                if yaml:
                    loaded = yaml.safe_load(content)
                else:
                    import json
                    loaded = json.loads(content)

                if isinstance(loaded, dict):
                    # Check if wrapped in "node" key (like config.example.yaml)
                    if "node" in loaded and isinstance(loaded["node"], dict):
                        node_section = loaded["node"]
                        raw_data.update(node_section)
                    # Also take root-level keys if any
                    for k, v in loaded.items():
                        if k not in ("hub", "node", "personas"):
                            raw_data[k] = v
                break
            except Exception as e:
                if config_path:
                    # If user explicitly asked for this file, re-raise or log
                    raise RuntimeError(f"Error parsing config file '{p}': {e}") from e

    # 2. Environment Variables override
    if "AGENTCORP_HUB_URL" in os.environ:
        raw_data["hub_url"] = os.environ["AGENTCORP_HUB_URL"]
    if "AGENTCORP_NODE_ID" in os.environ:
        raw_data["node_id"] = os.environ["AGENTCORP_NODE_ID"]
    if "AGENTCORP_NODE_NAME" in os.environ:
        raw_data["name"] = os.environ["AGENTCORP_NODE_NAME"]
    if "AGENTCORP_PERSONA" in os.environ:
        raw_data["persona_id"] = os.environ["AGENTCORP_PERSONA"]
    if "AGENTCORP_WORKSPACE_DIR" in os.environ:
        raw_data["workspace_dir"] = os.environ["AGENTCORP_WORKSPACE_DIR"]
    if "AGENTCORP_WORKSTATION_MODE" in os.environ:
        raw_data.setdefault("preemption", {})["workstation_mode"] = os.environ["AGENTCORP_WORKSTATION_MODE"]
    if "AGENTCORP_INACTIVITY_THRESHOLD" in os.environ:
        raw_data.setdefault("preemption", {})["inactivity_threshold_seconds"] = float(
            os.environ["AGENTCORP_INACTIVITY_THRESHOLD"]
        )

    # 3. CLI arguments override (highest precedence)
    if cli_args:
        if cli_args.get("hub_url"):
            raw_data["hub_url"] = cli_args["hub_url"]
        if cli_args.get("node_id"):
            raw_data["node_id"] = cli_args["node_id"]
        if cli_args.get("name"):
            raw_data["name"] = cli_args["name"]
        if cli_args.get("persona"):
            raw_data["persona_id"] = cli_args["persona"]
        if cli_args.get("workspace"):
            raw_data["workspace_dir"] = cli_args["workspace"]
        if cli_args.get("capabilities"):
            raw_data["capabilities"] = cli_args["capabilities"]
        if cli_args.get("workstation_mode"):
            raw_data.setdefault("preemption", {})["workstation_mode"] = cli_args["workstation_mode"]
        if cli_args.get("inactivity_threshold_seconds") is not None:
            raw_data.setdefault("preemption", {})["inactivity_threshold_seconds"] = float(
                cli_args["inactivity_threshold_seconds"]
            )

    return AgentClientConfig.model_validate(raw_data)


def save_agent_client_config(config: AgentClientConfig, config_path: str = "config.yaml") -> None:
    """Save current configuration to YAML."""
    data = {
        "node": config.model_dump(mode="json"),
    }
    target = Path(config_path)
    if yaml:
        target.write_text(yaml.dump(data, sort_keys=False, indent=2), encoding="utf-8")
    else:
        import json
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
