from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

try:  # pragma: no cover - optional dependency
    import yaml
except Exception:  # pragma: no cover
    yaml = None

_BASE_DEFAULT_CONFIG: Dict[str, Any] = {
    "app": {
        "name": "Coral Inference Dashboard",
        "tagline": "实时推理管道监控与控制面板",
        "logoUrl": None,
        "docsUrl": None,
        "supportEmail": None,
    },
    "api": {
        "baseUrl": "runtime-default",
        "websocketUrl": None,
        "timeoutMs": 10_000,
        "headers": {},
    },
    "features": {
        "pipelines": {"enabled": True, "order": 1},
        "streams": {"enabled": True, "order": 2},
        "monitoring": {"enabled": True, "order": 3},
        "recordings": {"enabled": True, "order": 4},
        "customMetrics": {"enabled": True, "order": 5, "maxCharts": 6},
        "plugins": {"enabled": False, "order": 99},
    },
    "streams": {
        "iceServers": [],
        "peerConfig": {},
        "defaultFps": 30,
    },
    "monitoring": {
        "disk": {"maxSizeGb": 20, "warnPercentage": 85},
        "metrics": {"provider": "influxdb", "refreshIntervalSeconds": 10},
    },
    "plugins": {"web": []},
    "ui": {"theme": {"mode": "system", "primaryColor": "#0f172a"}, "layout": {}},
    "build": {"version": "dev", "gitCommit": None, "generatedAt": None},
}


@dataclass
class WebAppConfig:
    """Wrapper around the merged configuration payload."""

    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Return a deep copy that is safe to serialize."""
        return deepcopy(self.data)


def load_webapp_config(
    config_data: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> WebAppConfig:
    """Load the web application configuration from descriptor/env sources."""

    env = env or os.environ
    base_payload = _default_payload(env)

    if config_data is None:
        source_payload = _load_payload_from_env(env)
    else:
        if not isinstance(config_data, Mapping):
            raise ValueError("WebApp config overrides must be a mapping/object")
        source_payload = dict(config_data)

    merged = _deep_merge_dicts(base_payload, source_payload)

    env_overrides = _get_env_overrides(env)
    if env_overrides:
        merged = _deep_merge_dicts(merged, env_overrides)

    return WebAppConfig(data=merged)


def _default_payload(env: Mapping[str, str]) -> Dict[str, Any]:
    payload = deepcopy(_BASE_DEFAULT_CONFIG)
    payload.setdefault("build", {})
    payload["build"]["version"] = env.get(
        "CORAL_BUILD_VERSION", payload["build"].get("version") or "dev"
    )
    payload["build"]["gitCommit"] = env.get(
        "CORAL_GIT_COMMIT", payload["build"].get("gitCommit")
    )
    payload["build"]["generatedAt"] = datetime.now(timezone.utc).isoformat()
    return payload


def _load_payload_from_env(env: Mapping[str, str]) -> Dict[str, Any]:
    config_path = env.get("CORAL_WEBAPP_CONFIG_FILE")
    if config_path:
        return _read_config_file(config_path)
    raw = env.get("CORAL_WEBAPP_CONFIG_JSON")
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid CORAL_WEBAPP_CONFIG_JSON payload") from exc
        if isinstance(parsed, Mapping):
            return dict(parsed)
        raise ValueError("CORAL_WEBAPP_CONFIG_JSON must contain a JSON object")
    return {}


def _read_config_file(path: str) -> Dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"WebApp config file not found: {file_path}")
    text = file_path.read_text()
    suffix = file_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:  # pragma: no cover - PyYAML optional
            raise RuntimeError("PyYAML is required to parse YAML config files")
        parsed = yaml.safe_load(text) or {}
    else:
        parsed = json.loads(text or "{}")
    if not isinstance(parsed, Mapping):
        raise ValueError("WebApp config file must contain an object at the root")
    return dict(parsed)


def _get_env_overrides(env: Mapping[str, str]) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    app_name = env.get("APP_NAME") or env.get("CORAL_APP_NAME")
    if app_name:
        overrides.setdefault("app", {})["name"] = app_name
    tagline = env.get("APP_TAGLINE")
    if tagline:
        overrides.setdefault("app", {})["tagline"] = tagline
    logo_url = env.get("APP_LOGO_URL")
    if logo_url:
        overrides.setdefault("app", {})["logoUrl"] = logo_url
    api_base = env.get("NEXT_PUBLIC_API_BASE_URL") or env.get("CORAL_API_BASE_URL")
    if api_base:
        overrides.setdefault("api", {})["baseUrl"] = api_base
    websocket_url = env.get("CORAL_API_WEBSOCKET_URL")
    if websocket_url:
        overrides.setdefault("api", {})["websocketUrl"] = websocket_url
    return overrides


def _deep_merge_dicts(base: Dict[str, Any], override: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not override:
        return deepcopy(base)
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge_dicts(result[key], value)
        elif isinstance(value, list):
            result[key] = list(value)
        else:
            result[key] = value
    return result


__all__ = ["WebAppConfig", "load_webapp_config"]
