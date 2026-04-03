import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from coral_inference.runtime.capabilities import (
    get_runtime_binding_missing_required_files,
    get_runtime_binding_model_dependencies,
    get_runtime_binding_support_issue,
    resolve_runtime_binding_backend_type,
    resolve_runtime_binding_model_signature,
)
from coral_inference.runtime.contracts import RuntimeModelBinding


def list_package_file_handles(package_dir: str) -> List[str]:
    root = Path(package_dir)
    if not root.exists():
        raise FileNotFoundError(f"package directory does not exist: {package_dir}")
    if not root.is_dir():
        raise NotADirectoryError(f"package path is not a directory: {package_dir}")
    return sorted(
        str(path.relative_to(root).as_posix())
        for path in root.rglob("*")
        if path.is_file()
    )


def build_runtime_binding_from_local_package(
    *,
    package_dir: str,
    loader_type: str,
    backend_type: Optional[str] = None,
    task_type: Optional[str] = None,
    framework: Optional[str] = None,
    model_name: str = "local-package",
    model_id: str = "local-package",
    binding_id: str = "local-binding",
    binding_ref: str = "binding:local-binding",
    package_id: Optional[str] = None,
    selected_runtime: Optional[str] = None,
) -> RuntimeModelBinding:
    file_handles = list_package_file_handles(package_dir)
    binding_payload = {
        "node_name": "local",
        "field_name": "model",
        "model_reference": f"local:{model_id}",
        "binding_id": binding_id,
        "binding_ref": binding_ref,
        "binding_type": "package_ref",
        "model_id": model_id,
        "model_name": model_name,
        "task_type": task_type,
        "framework": framework,
        "selected_package_id": package_id or model_id,
        "selected_loader_type": loader_type,
        "selected_backend": backend_type,
        "selected_runtime": selected_runtime,
        "package_files_snapshot": [
            {"file_handle": file_handle}
            for file_handle in file_handles
        ],
    }
    return RuntimeModelBinding.model_validate(binding_payload)


def load_runtime_binding_from_json(payload: str | Dict[str, Any]) -> RuntimeModelBinding:
    if isinstance(payload, str):
        return RuntimeModelBinding.model_validate(json.loads(payload))
    return RuntimeModelBinding.model_validate(payload)


def summarize_runtime_binding_validation(
    binding: RuntimeModelBinding,
) -> Dict[str, Any]:
    task_type, model_architecture = resolve_runtime_binding_model_signature(binding)
    backend_type = resolve_runtime_binding_backend_type(binding)
    missing_required_files = sorted(
        get_runtime_binding_missing_required_files(binding)
    )
    support_issue = get_runtime_binding_support_issue(binding)
    return {
        "binding_id": binding.binding_id,
        "loader_type": binding.selected_loader_type,
        "backend_type": backend_type,
        "task_type": task_type,
        "model_architecture": model_architecture,
        "selected_runtime": binding.selected_runtime,
        "model_dependencies": get_runtime_binding_model_dependencies(binding),
        "package_files": [
            package_file.file_handle for package_file in binding.package_files_snapshot
        ],
        "missing_required_files": missing_required_files,
        "is_supported": support_issue is None,
        "support_issue": support_issue,
    }
