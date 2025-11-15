from __future__ import annotations

import json
from pathlib import Path

import pytest

from coral_inference.webapp import load_webapp_config


def test_load_webapp_config_defaults():
    config = load_webapp_config(env={})
    data = config.to_dict()
    assert data["app"]["name"] == "Coral Inference Dashboard"
    assert data["api"]["baseUrl"] == "runtime-default"
    assert data["features"]["pipelines"]["enabled"] is True


def test_load_webapp_config_descriptor_override():
    overrides = {"app": {"name": "Custom"}, "api": {"baseUrl": "https://api.example.com"}}
    config = load_webapp_config(config_data=overrides, env={})
    data = config.to_dict()
    assert data["app"]["name"] == "Custom"
    assert data["api"]["baseUrl"] == "https://api.example.com"


def test_load_webapp_config_from_file(tmp_path: Path):
    payload = {"app": {"name": "FromFile"}}
    file_path = tmp_path / "config.json"
    file_path.write_text(json.dumps(payload))
    config = load_webapp_config(env={"CORAL_WEBAPP_CONFIG_FILE": str(file_path)})
    assert config.to_dict()["app"]["name"] == "FromFile"


def test_load_webapp_config_env_overrides_base_url():
    config = load_webapp_config(env={"NEXT_PUBLIC_API_BASE_URL": "https://env.example.com"})
    assert config.to_dict()["api"]["baseUrl"] == "https://env.example.com"


def test_invalid_env_json_raises():
    with pytest.raises(ValueError):
        load_webapp_config(env={"CORAL_WEBAPP_CONFIG_JSON": "not-json"})
