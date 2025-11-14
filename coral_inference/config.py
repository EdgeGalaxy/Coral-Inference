from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

try:  # pragma: no cover - optional dependency
    import yaml
except Exception:  # pragma: no cover
    yaml = None

_BOOL_TRUE = {"1", "true", "yes", "y", "on"}
_BOOL_FALSE = {"0", "false", "no", "n", "off"}
_LIST_FIELDS = {"backend_entry_modules", "extra_patches"}
_DICT_FIELDS = {"services"}
_ENV_FIELD_MAP = {
    "RUNTIME_PLATFORM": "platform",
    "ENABLE_STREAM_MANAGER": "enable_stream_manager_patch",
    "ENABLE_CAMERA": "enable_camera_patch",
    "ENABLE_SINK": "enable_sink_patch",
    "ENABLE_WEBRTC": "enable_webrtc",
    "ENABLE_PLUGINS": "enable_plugins",
    "ENABLE_BUFFER_SINK": "enable_buffer_sink_patch",
    "ENABLE_METRIC_SINK": "enable_metric_sink_patch",
    "ENABLE_VIDEO_SINK": "enable_video_sink_patch",
    "AUTO_PATCH_RKNN": "auto_patch_rknn",
    "AUTO_DISCOVER_BACKENDS": "auto_discover_backends",
    "BACKEND_MODULES": "backend_entry_modules",
    "EXTRA_PATCHES": "extra_patches",
}
_PATCH_FIELD_MAP = {
    "stream_manager": "enable_stream_manager_patch",
    "camera": "enable_camera_patch",
    "sink": "enable_sink_patch",
    "buffer_sink": "enable_buffer_sink_patch",
    "metric_sink": "enable_metric_sink_patch",
    "video_sink": "enable_video_sink_patch",
    "webrtc": "enable_webrtc",
    "plugins": "enable_plugins",
}


@dataclass
class RuntimeDescriptor:
    platform: Optional[str] = None
    enable_stream_manager_patch: Optional[bool] = None
    enable_camera_patch: Optional[bool] = None
    enable_sink_patch: Optional[bool] = None
    enable_webrtc: Optional[bool] = None
    enable_plugins: Optional[bool] = None
    enable_buffer_sink_patch: Optional[bool] = None
    enable_metric_sink_patch: Optional[bool] = None
    enable_video_sink_patch: Optional[bool] = None
    auto_patch_rknn: Optional[bool] = None
    auto_discover_backends: Optional[bool] = None
    backend_entry_modules: Optional[List[str]] = field(default=None)
    extra_patches: Optional[List[str]] = field(default=None)
    services: Optional[Dict[str, Any]] = field(default=None)

    def merged_with(self, override: "RuntimeDescriptor") -> "RuntimeDescriptor":
        """Return a new descriptor with override taking precedence."""
        data: Dict[str, Any] = {}
        for descriptor_field in fields(self):
            current_value = getattr(self, descriptor_field.name)
            override_value = getattr(override, descriptor_field.name)
            value = override_value if override_value is not None else current_value
            if descriptor_field.name in _LIST_FIELDS and value is not None:
                value = list(value)
            if descriptor_field.name in _DICT_FIELDS and value is not None:
                value = dict(value)
            data[descriptor_field.name] = value
        return RuntimeDescriptor(**data)

    @classmethod
    def merge_many(cls, descriptors: Iterable["RuntimeDescriptor"]) -> "RuntimeDescriptor":
        result = cls()
        for descriptor in descriptors:
            result = result.merged_with(descriptor)
        return result

    def to_dict(self) -> Dict[str, Any]:
        serialized: Dict[str, Any] = {}
        for descriptor_field in fields(self):
            value = getattr(self, descriptor_field.name)
            if value is None:
                continue
            if descriptor_field.name in _LIST_FIELDS:
                serialized[descriptor_field.name] = list(value)
            elif descriptor_field.name in _DICT_FIELDS:
                serialized[descriptor_field.name] = dict(value)
            else:
                serialized[descriptor_field.name] = value
        return serialized

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RuntimeDescriptor":
        if not isinstance(data, Mapping):
            raise ValueError("Runtime descriptor expects a mapping/dict")
        descriptor = cls()
        descriptor._apply_mapping(data)
        patches = data.get("patches")
        if isinstance(patches, Mapping):
            for patch_name, field_name in _PATCH_FIELD_MAP.items():
                if patch_name in patches:
                    descriptor._assign_field(field_name, cls._coerce_bool(patches[patch_name]))
        backends = data.get("backends")
        if isinstance(backends, Mapping):
            if "modules" in backends:
                descriptor._assign_field(
                    "backend_entry_modules", cls._coerce_list(backends["modules"])
                )
            if "auto_discover" in backends:
                descriptor._assign_field(
                    "auto_discover_backends", cls._coerce_bool(backends["auto_discover"])
                )
        return descriptor

    @classmethod
    def from_file(cls, path: str) -> "RuntimeDescriptor":
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        suffix = file_path.suffix.lower()
        text = file_path.read_text()
        if suffix in {".yaml", ".yml"}:
            if yaml is None:  # pragma: no cover - PyYAML optional
                raise RuntimeError("PyYAML is required to parse YAML configuration files")
            parsed = yaml.safe_load(text) or {}
        else:
            parsed = json.loads(text or "{}")
        if not isinstance(parsed, Mapping):
            raise ValueError("Configuration file root must be a mapping/object")
        return cls.from_dict(parsed)

    @classmethod
    def from_env(
        cls,
        env: Optional[Mapping[str, str]] = None,
        prefix: str = "CORAL_",
    ) -> "RuntimeDescriptor":
        env = env or os.environ
        descriptor = cls()

        def read(field: str) -> Optional[str]:
            return env.get(f"{prefix}{field}")

        for env_key, field_name in _ENV_FIELD_MAP.items():
            value = read(env_key)
            if field_name in _LIST_FIELDS:
                descriptor._assign_field(field_name, cls._coerce_list(value))
            elif cls._is_bool_field(field_name):
                descriptor._assign_field(field_name, cls._coerce_bool(value))
            elif field_name == "platform" and value:
                descriptor.platform = value
        return descriptor

    @classmethod
    def from_overrides(cls, overrides: Mapping[str, str]) -> "RuntimeDescriptor":
        descriptor = cls()
        for raw_key, raw_value in overrides.items():
            key = raw_key.strip().lower().replace("-", "_")
            if key.startswith("patch.") or key.startswith("patches."):
                patch_name = key.split(".", 1)[1]
                field_name = _PATCH_FIELD_MAP.get(patch_name)
                if field_name:
                    descriptor._assign_field(field_name, cls._coerce_bool(raw_value))
                continue
            if key.startswith("backends."):
                sub_key = key.split(".", 1)[1]
                if sub_key in {"modules", "module"}:
                    descriptor._assign_field(
                        "backend_entry_modules", cls._coerce_list(raw_value)
                    )
                elif sub_key in {"auto", "auto_discover"}:
                    descriptor._assign_field(
                        "auto_discover_backends", cls._coerce_bool(raw_value)
                    )
                continue
            if key in _DESCRIPTOR_FIELDS:
                if key in _LIST_FIELDS:
                    descriptor._assign_field(key, cls._coerce_list(raw_value))
                elif cls._is_bool_field(key):
                    descriptor._assign_field(key, cls._coerce_bool(raw_value))
                elif key == "platform" and raw_value:
                    descriptor.platform = raw_value
        return descriptor

    def to_runtime_config(self, base_config=None):
        from coral_inference.runtime.config import RuntimeConfig  # lazy import

        config = base_config or RuntimeConfig()
        for descriptor_field in fields(self):
            value = getattr(self, descriptor_field.name)
            if value is None:
                continue
            assign_value = list(value) if descriptor_field.name in _LIST_FIELDS else value
            setattr(config, descriptor_field.name, assign_value)
        return config

    def _apply_mapping(self, data: Mapping[str, Any]) -> None:
        for key in _DESCRIPTOR_FIELDS:
            if key == "platform":
                value = data.get(key)
                if value:
                    self.platform = str(value)
                continue
            if key in data:
                if key in _LIST_FIELDS:
                    self._assign_field(key, self._coerce_list(data[key]))
                elif key in _DICT_FIELDS:
                    self._assign_field(key, self._coerce_mapping(data[key]))
                elif self._is_bool_field(key):
                    self._assign_field(key, self._coerce_bool(data[key]))

    def _assign_field(self, name: str, value: Any) -> None:
        if value is None:
            return
        if name in _LIST_FIELDS:
            setattr(self, name, list(value))
        elif name in _DICT_FIELDS:
            setattr(self, name, dict(value))
        else:
            setattr(self, name, value)

    @staticmethod
    def _coerce_bool(value: Any) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _BOOL_TRUE:
                return True
            if lowered in _BOOL_FALSE:
                return False
        return None

    @staticmethod
    def _coerce_list(value: Any) -> Optional[List[str]]:
        if value is None:
            return None
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
            return items
        if isinstance(value, Iterable):
            result = []
            for item in value:
                if item is None:
                    continue
                text = str(item).strip()
                if text:
                    result.append(text)
            return result
        return None

    @staticmethod
    def _coerce_mapping(value: Any) -> Optional[Dict[str, Any]]:
        if value is None:
            return None
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception:
                return None
            return parsed if isinstance(parsed, Mapping) else None
        return None

    @staticmethod
    def _is_bool_field(name: str) -> bool:
        return name in _BOOL_FIELDS


_DESCRIPTOR_FIELDS = {field.name for field in fields(RuntimeDescriptor)}
_BOOL_FIELDS = {
    "enable_stream_manager_patch",
    "enable_camera_patch",
    "enable_sink_patch",
    "enable_webrtc",
    "enable_plugins",
    "enable_buffer_sink_patch",
    "enable_metric_sink_patch",
    "enable_video_sink_patch",
    "auto_patch_rknn",
    "auto_discover_backends",
}

__all__ = ["RuntimeDescriptor"]
