"""Unit tests for Agent Client Configuration Engine."""

import os
import pytest
from shared.config import (
    AgentClientConfig,
    PreemptionConfig,
    load_agent_client_config,
    save_agent_client_config,
)
from shared.models import WorkstationMode


def test_default_client_config():
    cfg = AgentClientConfig()
    assert cfg.node_id.startswith("node-")
    assert cfg.hub_url == "ws://127.0.0.1:8000/ws/hub"
    assert cfg.persona_id == "devops_dan"
    assert "backend" in cfg.capabilities
    assert cfg.workstation_mode == WorkstationMode.BACKGROUND
    assert cfg.inactivity_threshold_seconds == 15.0


def test_dynamic_update():
    cfg = AgentClientConfig()
    changed = cfg.update_dynamic({
        "workstation_mode": "EXCLUSIVE",
        "inactivity_threshold_seconds": 30.0,
        "capabilities": ["shell", "qa"],
        "name": "CustomAgent",
    })
    assert "preemption.workstation_mode" in changed
    assert cfg.workstation_mode == WorkstationMode.EXCLUSIVE
    assert cfg.inactivity_threshold_seconds == 30.0
    assert cfg.capabilities == ["shell", "qa"]
    assert cfg.name == "CustomAgent"


def test_load_config_with_cli_overrides(tmp_path):
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("""
node:
  hub_url: "ws://hub.internal:9000/ws/hub"
  name: "FileAgent"
  persona_id: "frontend_fiona"
  preemption:
    inactivity_threshold_seconds: 20.0
    workstation_mode: "BACKGROUND"
""")

    cli_args = {
        "name": "OverriddenAgent",
        "workstation_mode": "EXCLUSIVE",
        "inactivity_threshold_seconds": 5.0,
    }

    cfg = load_agent_client_config(config_path=str(config_file), cli_args=cli_args)
    # CLI args should override file
    assert cfg.name == "OverriddenAgent"
    assert cfg.workstation_mode == WorkstationMode.EXCLUSIVE
    assert cfg.inactivity_threshold_seconds == 5.0
    # Non-overridden should come from file
    assert cfg.hub_url == "ws://hub.internal:9000/ws/hub"
    assert cfg.persona_id == "frontend_fiona"


def test_load_config_with_env_overrides(monkeypatch):
    monkeypatch.setenv("AGENTCORP_HUB_URL", "ws://env.internal:8888/ws/hub")
    monkeypatch.setenv("AGENTCORP_NODE_NAME", "EnvNode")
    monkeypatch.setenv("AGENTCORP_WORKSTATION_MODE", "EXCLUSIVE")
    monkeypatch.setenv("AGENTCORP_INACTIVITY_THRESHOLD", "42.0")

    cfg = load_agent_client_config(config_path="non_existent_file.yaml")
    assert cfg.hub_url == "ws://env.internal:8888/ws/hub"
    assert cfg.name == "EnvNode"
    assert cfg.workstation_mode == WorkstationMode.EXCLUSIVE
    assert cfg.inactivity_threshold_seconds == 42.0


def test_save_and_reload_config(tmp_path):
    target = tmp_path / "saved_config.yaml"
    cfg = AgentClientConfig(
        name="SavedAgent",
        persona_id="growth_gary",
        preemption=PreemptionConfig(inactivity_threshold_seconds=12.5, workstation_mode=WorkstationMode.EXCLUSIVE),
    )
    save_agent_client_config(cfg, str(target))

    loaded = load_agent_client_config(config_path=str(target))
    assert loaded.name == "SavedAgent"
    assert loaded.persona_id == "growth_gary"
    assert loaded.inactivity_threshold_seconds == 12.5
    assert loaded.workstation_mode == WorkstationMode.EXCLUSIVE
