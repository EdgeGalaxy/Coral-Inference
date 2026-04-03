import json
from pathlib import Path
from typing import Any, Dict

from coral_inference.runtime.contracts import RuntimeModelBinding


def _coalesce_model_architecture(binding: RuntimeModelBinding) -> str | None:
    standardized_metadata = binding.standardized_metadata or {}
    package_manifest = binding.package_manifest_snapshot or {}
    return (
        standardized_metadata.get("model_architecture")
        or package_manifest.get("modelArchitecture")
        or binding.framework
    )


def _coalesce_task_type(binding: RuntimeModelBinding) -> str | None:
    standardized_metadata = binding.standardized_metadata or {}
    package_manifest = binding.package_manifest_snapshot or {}
    return (
        standardized_metadata.get("task_type")
        or package_manifest.get("taskType")
        or binding.task_type
    )


def _coalesce_backend_type(binding: RuntimeModelBinding) -> str | None:
    package_manifest = binding.package_manifest_snapshot or {}
    return (
        binding.selected_backend
        or package_manifest.get("backendType")
    )


def build_model_config(binding: RuntimeModelBinding) -> Dict[str, Any]:
    return {
        "model_architecture": _coalesce_model_architecture(binding),
        "task_type": _coalesce_task_type(binding),
        "backend_type": _coalesce_backend_type(binding),
    }


def write_model_config(
    *,
    package_dir: str,
    binding: RuntimeModelBinding,
) -> str:
    target_path = Path(package_dir) / "model_config.json"
    target_path.write_text(
        json.dumps(build_model_config(binding), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(target_path)
