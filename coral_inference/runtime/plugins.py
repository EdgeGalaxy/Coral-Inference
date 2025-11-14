from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import metadata
from typing import TYPE_CHECKING, Callable, Dict, Iterable, List, Optional, Tuple, Union

from inference.core.logger import logger

from coral_inference.runtime.compat import get_inference_version_tuple

if TYPE_CHECKING:  # pragma: no cover
    from coral_inference.runtime.config import RuntimeConfig

Version = Tuple[int, int, int]
_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")

PLUGIN_GROUPS: Dict[str, str] = {
    "backends": "coral_inference.backends",
    "patches": "coral_inference.patches",
    "workflows": "coral_inference.workflows",
}

RUNTIME_PLUGIN_GROUPS: Dict[str, str] = {
    "patches": "coral_inference.patches",
    "workflows": "coral_inference.workflows",
}


@dataclass
class PluginSpec:
    name: str
    activate: Callable[["RuntimeConfig"], bool]
    description: str = ""
    min_core_version: Optional[str] = None
    min_inference_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "name": self.name,
            "description": self.description,
            "min_core_version": self.min_core_version,
            "min_inference_version": self.min_inference_version,
        }


def load_runtime_plugins(
    config: "RuntimeConfig",
    inference_version: Optional[Version] = None,
) -> Dict[str, bool]:
    inference_version = inference_version or get_inference_version_tuple()
    results: Dict[str, bool] = {}
    for alias, group in RUNTIME_PLUGIN_GROUPS.items():
        group_results = _load_plugins_for_group(alias, group, config, inference_version)
        results.update(group_results)
    return results


def list_plugins_for_group(group_name: str) -> List[Dict[str, object]]:
    group = PLUGIN_GROUPS.get(group_name, group_name)
    if group_name == "backends":
        return _list_backend_entry_points(group)

    try:
        selected = list(_select_entry_points(group))
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to enumerate plugins for %s: %s", group, exc)
        return []

    entries = []
    for ep in selected:
        info: Dict[str, object] = {
            "entry_point": ep.name,
            "value": getattr(ep, "value", None),
            "module": getattr(ep, "module", None),
        }
        try:
            specs = _normalise_plugin(ep.load(), ep.name)
            info["plugins"] = [spec.to_dict() for spec in specs]
        except Exception as exc:  # pragma: no cover - plugin errors reported to user
            info["error"] = str(exc)
        entries.append(info)
    return entries


def list_all_plugins(group: Optional[str] = None) -> Dict[str, List[Dict[str, object]]]:
    if group:
        key = group if group in PLUGIN_GROUPS else group
        return {key: list_plugins_for_group(group)}
    return {alias: list_plugins_for_group(alias) for alias in PLUGIN_GROUPS}


def _load_plugins_for_group(
    alias: str,
    entry_point_group: str,
    config: "RuntimeConfig",
    inference_version: Version,
) -> Dict[str, bool]:
    statuses: Dict[str, bool] = {}
    for ep in _select_entry_points(entry_point_group):
        try:
            specs = _normalise_plugin(ep.load(), ep.name)
        except Exception as exc:
            key = f"{alias}:{ep.name}"
            statuses[key] = False
            logger.warning("Failed to load plugin entry point %s: %s", ep.name, exc)
            continue
        for spec in specs:
            key = f"{alias}:{spec.name}"
            if not _is_plugin_supported(spec, inference_version):
                statuses[key] = False
                continue
            try:
                result = bool(spec.activate(config))
            except Exception as exc:  # pragma: no cover - plugin code
                logger.warning("Plugin %s raised error: %s", spec.name, exc)
                result = False
            statuses[key] = result
    return statuses


def _list_backend_entry_points(group: str) -> List[Dict[str, object]]:
    try:
        selected = list(_select_entry_points(group))
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to list backend entry points: %s", exc)
        return []

    entries = []
    for ep in selected:
        entries.append(
            {
                "entry_point": ep.name,
                "value": getattr(ep, "value", None),
                "module": getattr(ep, "module", None),
            }
        )
    return entries


def _select_entry_points(group: str):
    entry_points = metadata.entry_points()
    if hasattr(entry_points, "select"):
        return entry_points.select(group=group)
    return entry_points.get(group, [])  # type: ignore[attr-defined]


def _normalise_plugin(value: Union[PluginSpec, Callable, Iterable], default_name: str):
    specs: List[PluginSpec] = []
    if isinstance(value, PluginSpec):
        specs.append(value)
    elif callable(value):
        specs.append(
            PluginSpec(name=getattr(value, "__name__", default_name), activate=value)
        )
    elif isinstance(value, Iterable):
        for item in value:
            specs.extend(_normalise_plugin(item, default_name))
    else:
        raise TypeError(f"Unsupported plugin entry point type: {type(value)}")
    return specs


def _is_plugin_supported(spec: PluginSpec, inference_version: Version) -> bool:
    core_requirement = _parse_version(spec.min_core_version)
    inference_requirement = _parse_version(spec.min_inference_version)

    if core_requirement and _CORE_VERSION_TUPLE < core_requirement:
        logger.warning(
            "Plugin %s requires coral-inference >= %s (current %s)",
            spec.name,
            spec.min_core_version,
            _CORE_VERSION,
        )
        return False
    if inference_requirement and inference_version < inference_requirement:
        logger.warning(
            "Plugin %s requires inference >= %s",
            spec.name,
            spec.min_inference_version,
        )
        return False
    return True


def _parse_version(value: Optional[str]) -> Optional[Version]:
    if not value:
        return None
    match = _VERSION_PATTERN.match(value)
    if not match:
        return None
    return tuple(int(group) for group in match.groups())  # type: ignore


def _detect_core_version() -> str:
    try:
        return metadata.version("coral-inference")
    except metadata.PackageNotFoundError:  # pragma: no cover
        try:
            from version import __version__ as local_version  # type: ignore

            return local_version
        except Exception:
            return "0.0.0"


_CORE_VERSION = _detect_core_version()
_CORE_VERSION_TUPLE = _parse_version(_CORE_VERSION) or (0, 0, 0)

__all__ = [
    "PluginSpec",
    "load_runtime_plugins",
    "list_plugins_for_group",
    "list_all_plugins",
    "PLUGIN_GROUPS",
]
