import copy
import json
import threading
from typing import Any, Dict, List, Optional

from coral_inference.runtime.contracts import RuntimeLockfile, RuntimeModelBinding
from coral_inference.runtime.registry import RuntimeRegistry


RUNTIME_MODEL_ENDPOINT_PREFIX = "coral-runtime"
_REGISTRY = RuntimeRegistry()
_RUNTIME_MODEL_BINDINGS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def _normalise_runtime_package_contract(package: Dict[str, Any]) -> Dict[str, Any]:
    return RuntimeLockfile.model_validate(package).model_dump(exclude_none=True)


def _normalise_runtime_binding_contract(binding: Dict[str, Any]) -> Dict[str, Any]:
    return RuntimeModelBinding.model_validate(binding).model_dump(exclude_none=True)


def is_runtime_model_endpoint(endpoint: Optional[str]) -> bool:
    return isinstance(endpoint, str) and endpoint.startswith(
        f"{RUNTIME_MODEL_ENDPOINT_PREFIX}-"
    )


def make_runtime_model_endpoint(binding: Dict[str, Any]) -> str:
    binding_id = str(binding.get("binding_id") or "").strip()
    if not binding_id:
        raise ValueError("binding_id is required to create runtime model endpoint")
    return f"{RUNTIME_MODEL_ENDPOINT_PREFIX}-{binding_id}"


def get_runtime_model_binding(endpoint: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        binding = _RUNTIME_MODEL_BINDINGS.get(endpoint)
        if not binding:
            return None
        return _normalise_runtime_binding_contract(copy.deepcopy(binding))


def get_runtime_deployment(deployment_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        deployment = _REGISTRY.get_lockfile(deployment_id)
        if deployment is None:
            return None
        return deployment.model_dump(exclude_none=True)


def _register_runtime_model_bindings_unlocked(
    model_bindings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    registered_bindings: List[Dict[str, Any]] = []
    for binding in model_bindings or []:
        if not isinstance(binding, dict):
            continue
        runtime_endpoint = binding.get("runtime_model_endpoint")
        if not runtime_endpoint:
            runtime_endpoint = make_runtime_model_endpoint(binding)
            binding["runtime_model_endpoint"] = runtime_endpoint
        normalised_binding = _normalise_runtime_binding_contract(copy.deepcopy(binding))
        _RUNTIME_MODEL_BINDINGS[runtime_endpoint] = normalised_binding
        registered_bindings.append(copy.deepcopy(normalised_binding))
    return registered_bindings


def register_runtime_model_bindings(
    model_bindings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    with _LOCK:
        return _register_runtime_model_bindings_unlocked(model_bindings)


def _normalise_model_metadata(binding: Dict[str, Any]) -> Dict[str, Any]:
    model_metadata = copy.deepcopy(binding.get("model_metadata") or {})
    if not model_metadata:
        model_asset = copy.deepcopy(binding.get("model_asset") or {})
        standardized_metadata = model_asset.get("standardized_metadata") or {}
        if isinstance(standardized_metadata, dict) and standardized_metadata:
            model_metadata = standardized_metadata
        else:
            runtime_environment = copy.deepcopy(binding.get("runtime_environment") or {})
            preprocessing = runtime_environment.get("PREPROCESSING") or {}
            class_mapping = runtime_environment.get("CLASS_MAP") or {}
            model_metadata = {
                "model_id": binding.get("model_id"),
                "model_name": binding.get("model_name"),
                "model_title": binding.get("model_title"),
                "task_type": binding.get("task_type"),
                "framework": binding.get("framework") or binding.get("model_type"),
                "selected_runtime": binding.get("selected_runtime"),
                "selected_package_id": binding.get("selected_package_id"),
                "selected_loader_type": binding.get("selected_loader_type"),
                "selected_backend": binding.get("selected_backend"),
                "source": {
                    "source_type": binding.get("source_type"),
                    "source_model_asset_id": binding.get("source_model_asset_id"),
                    "source_version_id": binding.get("source_version_id"),
                },
                "dataset": copy.deepcopy(binding.get("dataset") or {}),
                "class_mapping": class_mapping if isinstance(class_mapping, dict) else {},
                "preprocessing": preprocessing if isinstance(preprocessing, dict) else {},
                "metrics_summary": copy.deepcopy(binding.get("metrics_summary") or {}),
                "label_schema": copy.deepcopy(binding.get("label_schema") or {}),
                "io_schema": copy.deepcopy(binding.get("io_schema") or {}),
                "metric_schema": copy.deepcopy(binding.get("metric_schema") or {}),
                "postprocessing": copy.deepcopy(binding.get("postprocessing") or {}),
                "runtime_profile": {
                    "supported_runtimes": copy.deepcopy(binding.get("supported_runtimes") or []),
                    "preferred_runtime": binding.get("preferred_runtime"),
                },
            }

    source = copy.deepcopy(model_metadata.get("source") or {})
    if binding.get("source_type") is not None:
        source.setdefault("source_type", binding.get("source_type"))
    if binding.get("source_model_asset_id") is not None:
        source.setdefault("source_model_asset_id", binding.get("source_model_asset_id"))
    if binding.get("source_version_id") is not None:
        source.setdefault("source_version_id", binding.get("source_version_id"))
    if source:
        model_metadata["source"] = source

    model_metadata.setdefault("selected_runtime", binding.get("selected_runtime"))
    reference_profile = copy.deepcopy(binding.get("reference_profile") or {})
    model_metadata["execution_reference"] = {
        "model_reference": binding.get("model_reference"),
        "model_reference_type": reference_profile.get("primary_reference_kind"),
        "asset_reference": reference_profile.get("asset_reference"),
        "requested_binding_ref": reference_profile.get("requested_binding_ref"),
        "effective_binding_ref": (
            reference_profile.get("effective_binding_ref") or binding.get("binding_ref")
        ),
        "binding_type": binding.get("binding_type"),
        "binding_ref_changed": bool(reference_profile.get("binding_ref_changed")),
        "resolution_source": reference_profile.get("resolution_source"),
        "reference_profile": reference_profile if reference_profile else None,
    }
    return model_metadata


def _normalise_environment(binding: Dict[str, Any]) -> Dict[str, Any]:
    runtime_environment = copy.deepcopy(binding.get("runtime_environment") or {})
    if runtime_environment:
        preprocessing = runtime_environment.get("PREPROCESSING") or {}
        if isinstance(preprocessing, str):
            try:
                preprocessing = json.loads(preprocessing)
            except Exception:
                preprocessing = {}
        return {
            "PREPROCESSING": json.dumps(preprocessing),
            "CLASS_MAP": runtime_environment.get("CLASS_MAP") or {},
            "COLORS": runtime_environment.get("COLORS") or {},
            "BATCH_SIZE": runtime_environment.get("BATCH_SIZE") or 8,
        }

    model_asset = copy.deepcopy(binding.get("model_asset") or {})
    model_asset_environment = model_asset.get("environment") or {}
    if model_asset_environment:
        preprocessing = model_asset_environment.get("PREPROCESSING") or {}
        if isinstance(preprocessing, str):
            try:
                preprocessing = json.loads(preprocessing)
            except Exception:
                preprocessing = {}
        return {
            "PREPROCESSING": json.dumps(preprocessing),
            "CLASS_MAP": model_asset_environment.get("CLASS_MAP") or {},
            "COLORS": model_asset_environment.get("COLORS") or {},
            "BATCH_SIZE": model_asset_environment.get("BATCH_SIZE") or 8,
        }

    environment = copy.deepcopy(binding.get("model_environment") or {})
    if environment:
        return environment

    artifact_manifest = binding.get("artifact_manifest") or {}
    return {
        "PREPROCESSING": json.dumps(
            artifact_manifest.get("preprocessing") or artifact_manifest.get("preproc") or {}
        ),
        "CLASS_MAP": (
            artifact_manifest.get("class_mapping")
            or artifact_manifest.get("class_map")
            or {}
        ),
        "COLORS": artifact_manifest.get("colors") or {},
        "BATCH_SIZE": artifact_manifest.get("batch_size") or 8,
    }


def materialize_runtime_workflow_specification(
    specification: Dict[str, Any],
    model_bindings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    binding_by_ref: Dict[str, Dict[str, Any]] = {}
    for binding in model_bindings:
        if not isinstance(binding, dict):
            continue
        reference_profile = binding.get("reference_profile") or {}
        for reference in (
            binding.get("model_reference"),
            reference_profile.get("asset_reference"),
            reference_profile.get("requested_binding_ref"),
            binding.get("binding_ref"),
        ):
            if reference:
                binding_by_ref[reference] = binding

    def _replace(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: _replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_replace(item) for item in value]
        if isinstance(value, str) and value in binding_by_ref:
            binding = binding_by_ref[value]
            if binding.get("binding_type") == "hosted_alias":
                return binding.get("inference_target") or value
            runtime_endpoint = make_runtime_model_endpoint(binding)
            binding["runtime_model_endpoint"] = runtime_endpoint
            return runtime_endpoint
        return value

    return _replace(copy.deepcopy(specification))


def register_runtime_package(package: Dict[str, Any]) -> Dict[str, Any]:
    package = _normalise_runtime_package_contract(package)
    deployment_id = str(package.get("deployment_id") or "").strip()
    if not deployment_id:
        raise ValueError("deployment_id is required")

    model_bindings = copy.deepcopy(package.get("model_bindings") or [])
    for binding in model_bindings:
        if isinstance(binding, dict):
            binding["model_metadata"] = _normalise_model_metadata(binding)
    workflow_spec = materialize_runtime_workflow_specification(
        specification=package.get("workflow_spec") or {},
        model_bindings=model_bindings,
    )

    registered_package = copy.deepcopy(package)
    registered_package["workflow_spec"] = workflow_spec
    registered_package["model_bindings"] = model_bindings
    registered_package = _normalise_runtime_package_contract(registered_package)

    with _LOCK:
        _REGISTRY.register_lockfile(RuntimeLockfile.model_validate(registered_package))
        _register_runtime_model_bindings_unlocked(model_bindings)

    return copy.deepcopy(registered_package)


def build_initialise_payload_from_runtime_package(
    package: Dict[str, Any],
    api_key: Optional[str] = None,
    existing_pipeline_id: Optional[str] = None,
) -> Dict[str, Any]:
    stream_config = package.get("stream_config") or {}
    workflows_parameters = {
        "output_image_fields": stream_config.get("output_image_fields") or [],
        "pipeline_name": package.get("deployment_name") or package.get("workflow_name") or "",
        "is_file_source": bool(stream_config.get("is_file_source")),
        "used_pipeline_id": existing_pipeline_id,
        "deployment_id": package.get("deployment_id"),
        "gateway_id": package.get("gateway_id"),
        "gateway_run_env": package.get("gateway_run_env"),
        "runtime_package_enabled": True,
        "model_bindings": package.get("model_bindings") or [],
    }

    sinks = package.get("sinks") or {}
    if isinstance(sinks, dict):
        workflows_parameters.update(sinks)

    return {
        "video_configuration": {
            "type": "VideoConfiguration",
            "video_reference": package.get("video_reference") or [],
            "max_fps": stream_config.get("max_fps"),
            "video_source_properties": stream_config.get("video_source_properties"),
        },
        "processing_configuration": {
            "type": "WorkflowConfiguration",
            "workflow_specification": package.get("workflow_spec") or {},
            "workspace_name": package.get("workspace_name"),
            "workflow_id": package.get("workflow_id"),
            "image_input_name": "image",
            "workflows_parameters": workflows_parameters,
        },
        "sink_configuration": {
            "type": "MemorySinkConfiguration",
            "results_buffer_size": 64,
        },
        "api_key": api_key,
    }
