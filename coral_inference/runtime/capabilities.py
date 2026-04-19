from typing import Any, Dict, Optional, Tuple

from coral_inference.runtime.contracts import RuntimeModelBinding


_PRIMARY_FILE_HANDLES_BY_BACKEND = {
    "onnx": {"weights.onnx"},
    "trt": {"engine.plan"},
    "torch": {"weights.pt"},
    "torch-script": {"weights.pt"},
    "hf": {"weights.pt"},
    "mediapipe": {"model.task"},
    "rknn": {"weights.rknn"},
}
_INFERENCE_MODELS_REQUIRED_SIDECAR_FILES = {
    "class_names.txt",
    "inference_config.json",
}
_CORAL_RKNN_REQUIRED_FILES = {
    "weights.rknn",
    "class_names.txt",
    "inference_config.json",
    "runtime_metadata.json",
}


def normalise_runtime_model_architecture(
    raw_value: Optional[str],
    task_type: Optional[str],
) -> Optional[str]:
    if not raw_value:
        return None
    normalized = str(raw_value).strip().lower()
    if not normalized:
        return None
    if "rfdetr-seg" in normalized:
        return "rfdetr-seg-preview"
    if "rfdetr" in normalized:
        return "rfdetr"
    if "yolov8" in normalized:
        return "yolov8"
    if normalized.startswith("yolo") or "ultralytics" in normalized:
        if task_type == "classification":
            return "yolov8"
        return "yolov8"
    return normalized


def resolve_runtime_binding_model_signature(
    binding: RuntimeModelBinding,
) -> Tuple[Optional[str], Optional[str]]:
    standardized_metadata = binding.standardized_metadata or {}
    artifact_manifest = binding.artifact_manifest or {}
    package_manifest = binding.package_manifest_snapshot or {}
    task_type = (
        binding.task_type
        or standardized_metadata.get("task_type")
        or artifact_manifest.get("task_type")
        or (artifact_manifest.get("label_schema") or {}).get("task_type")
        or package_manifest.get("taskType")
    )
    model_architecture = (
        normalise_runtime_model_architecture(binding.framework, task_type)
        or normalise_runtime_model_architecture(
            standardized_metadata.get("model_architecture"), task_type
        )
        or normalise_runtime_model_architecture(
            package_manifest.get("modelArchitecture"), task_type
        )
        or normalise_runtime_model_architecture(binding.model_name, task_type)
    )
    return (
        str(task_type) if task_type else None,
        str(model_architecture) if model_architecture else None,
    )


def resolve_runtime_binding_backend_type(binding: RuntimeModelBinding) -> Optional[str]:
    package_manifest = binding.package_manifest_snapshot or {}
    backend_type = binding.selected_backend or package_manifest.get("backendType")
    if backend_type is None:
        return None
    return str(backend_type)


def get_runtime_binding_file_handles(binding: RuntimeModelBinding) -> set[str]:
    return {
        package_file.file_handle
        for package_file in binding.package_files_snapshot
        if package_file.file_handle
    }


def get_runtime_binding_model_dependencies(
    binding: RuntimeModelBinding,
) -> list[dict[str, Any]]:
    standardized_metadata = binding.standardized_metadata or {}
    dependencies = standardized_metadata.get("model_dependencies") or []
    return [
        dict(dependency)
        for dependency in dependencies
        if isinstance(dependency, dict)
    ]


def get_runtime_binding_missing_required_files(
    binding: RuntimeModelBinding,
) -> set[str]:
    file_handles = get_runtime_binding_file_handles(binding)
    if binding.selected_loader_type == "inference_models":
        backend_type = resolve_runtime_binding_backend_type(binding)
        required = set(_INFERENCE_MODELS_REQUIRED_SIDECAR_FILES)
        if backend_type in _PRIMARY_FILE_HANDLES_BY_BACKEND:
            required.update(_PRIMARY_FILE_HANDLES_BY_BACKEND[backend_type])
        return {file_handle for file_handle in required if file_handle not in file_handles}
    if binding.selected_loader_type == "coral_rknn":
        return {
            file_handle
            for file_handle in _CORAL_RKNN_REQUIRED_FILES
            if file_handle not in file_handles
        }
    return set()


def get_runtime_binding_support_issue(
    binding: RuntimeModelBinding,
) -> Optional[str]:
    if binding.binding_type != "package_ref":
        return (
            "Current Coral runtime only supports package_ref bindings; "
            f"{binding.binding_type} bindings are no longer supported"
        )

    loader_type = binding.selected_loader_type
    if loader_type == "inference_models":
        model_dependencies = get_runtime_binding_model_dependencies(binding)
        if model_dependencies:
            return (
                "Current Coral inference_models runtime does not yet support "
                "packages with modelDependencies"
            )
        task_type, _ = resolve_runtime_binding_model_signature(binding)
        supported_tasks = {
            "object-detection",
            "instance-segmentation",
            "keypoint-detection",
            "classification",
            "semantic-segmentation",
        }
        if task_type in supported_tasks:
            missing_files = get_runtime_binding_missing_required_files(binding)
            if not missing_files:
                return None
            return (
                "Current Coral inference_models runtime is missing required package files: "
                + ", ".join(sorted(missing_files))
            )
        return (
            "Current Coral inference_models runtime only supports "
            "object-detection, instance-segmentation, keypoint-detection, "
            "classification, and semantic-segmentation"
        )
    if loader_type == "coral_rknn":
        task_type, model_architecture = resolve_runtime_binding_model_signature(binding)
        if (
            task_type == "object-detection"
            and model_architecture in {"yolov8", "rfdetr"}
        ):
            missing_files = get_runtime_binding_missing_required_files(binding)
            if not missing_files:
                return None
            return (
                "Current Coral RKNN runtime is missing required package files: "
                + ", ".join(sorted(missing_files))
            )
        return (
            "Current Coral RKNN runtime only supports object-detection "
            "packages with yolov8 or rfdetr architecture"
        )
    return None


def is_runtime_binding_supported(binding: RuntimeModelBinding) -> bool:
    return get_runtime_binding_support_issue(binding) is None
