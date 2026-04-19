import json
import os
import subprocess
import sys
import types

import numpy as np
import pytest

from coral_inference.core.runtime_contract import normalize_runtime_status_report
from coral_inference.core.models.utils import RknnInferenceSession
from coral_inference.core.patches import (
    get_runtime_patch_installation_state,
    install_business_runtime_patches,
    install_default_runtime_patches,
    install_runtime_model_dispatch_patches,
)
from coral_inference.runtime import (
    _normalise_environment,
    _normalise_model_metadata,
    get_runtime_deployment,
    get_runtime_model_binding,
    materialize_runtime_workflow_specification,
    register_runtime_model_bindings,
    register_runtime_package,
)
from coral_inference.runtime.capabilities import (
    get_runtime_binding_support_issue,
    get_runtime_binding_missing_required_files,
    get_runtime_binding_model_dependencies,
    resolve_runtime_binding_model_signature,
)
from coral_inference.runtime.contracts import RuntimeModelBinding
from coral_inference.runtime.model_type_resolver import (
    resolve_runtime_endpoint_model_type,
)
from coral_inference.runtime.model_registry import (
    resolve_runtime_model_adapter,
    extend_model_getter,
    extend_registry_get_model,
)
from coral_inference.runtime.rknn_adapters import (
    CoralRuntimeRFDETRRKNNObjectDetectionAdapter,
    get_runtime_rknn_adapter,
)
from coral_inference.runtime.adapters import CoralRuntimeObjectDetectionAdapter


def test_materialize_runtime_workflow_specification_uses_reference_profile_refs():
    specification = {
        "inputs": [
            {
                "type": "WorkflowParameter",
                "name": "model",
                "default_value": "binding:hosted-1",
            }
        ]
    }
    model_bindings = [
        {
            "model_reference": "asset:9",
            "reference_profile": {
                "primary_reference": "asset:9",
                "primary_reference_kind": "asset_reference",
                "asset_reference": "asset:9",
                "requested_binding_ref": "binding:hosted-1",
                "effective_binding_ref": "binding:rknn-1",
            },
            "binding_id": "rknn-1",
            "binding_ref": "binding:rknn-1",
            "binding_type": "package_ref",
        }
    ]

    materialized = materialize_runtime_workflow_specification(
        specification=specification,
        model_bindings=model_bindings,
    )

    assert (
        materialized["inputs"][0]["default_value"]
        == "coral-runtime-rknn-1"
    )


def test_runtime_patch_installers_are_idempotent_after_bootstrap():
    install_default_runtime_patches()
    assert install_runtime_model_dispatch_patches() is False
    assert install_business_runtime_patches() is False


def test_default_runtime_patch_state_in_fresh_process():
    command = [
        sys.executable,
        "-c",
        (
            "import json; "
            "import coral_inference.core as core; "
            "print(json.dumps(core.get_runtime_patch_installation_state()))"
        ),
    ]
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        cwd=os.getcwd(),
    )
    state = json.loads(result.stdout.strip().splitlines()[-1])

    assert state["default_dispatch_installed"] is True
    assert state["default_business_installed"] is True


def test_default_runtime_bootstrap_routes_model_api_to_api_base_url_when_configured():
    command = [
        sys.executable,
        "-c",
        (
            "import json; "
            "import inference.core.env as inference_env; "
            "import inference.core.roboflow_api as inference_roboflow_api; "
            "import inference_models.configuration as inference_models_configuration; "
            "import coral_inference.core as core; "
            "print(json.dumps({"
            "'state': core.get_runtime_patch_installation_state(), "
            "'inference_api_base_url': inference_env.API_BASE_URL, "
            "'roboflow_api_base_url': inference_roboflow_api.API_BASE_URL, "
            "'weights_provider_host': inference_models_configuration.ROBOFLOW_API_HOST"
            "}))"
        ),
    ]
    env = dict(os.environ)
    env["API_BASE_URL"] = "http://backend.example"
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        cwd=os.getcwd(),
        env=env,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])

    assert payload["state"]["model_api_base"] == "http://backend.example"
    assert payload["state"]["backend_model_api_configured"] is True
    assert payload["inference_api_base_url"] == "http://backend.example"
    assert payload["roboflow_api_base_url"] == "http://backend.example"
    assert payload["weights_provider_host"] == "http://backend.example"


def test_default_runtime_bootstrap_does_not_import_legacy_runtime_artifact_modules():
    command = [
        sys.executable,
        "-c",
        (
            "import json; "
            "import sys; "
            "import coral_inference.core; "
            "print(json.dumps({"
            "'runtime_artifact_compat_loaded': 'coral_inference.runtime.runtime_artifact_compat' in sys.modules, "
            "'rknn_base_loaded': 'coral_inference.core.models.rknn_base' in sys.modules"
            "}))"
        ),
    ]
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        cwd=os.getcwd(),
    )
    state = json.loads(result.stdout.strip().splitlines()[-1])

    assert state["runtime_artifact_compat_loaded"] is False
    assert state["rknn_base_loaded"] is False


def test_core_public_api_excludes_legacy_model_patch_installers():
    import coral_inference
    import coral_inference.core as core
    import coral_inference.core.patches as patches
    import coral_inference.runtime as runtime

    assert hasattr(core, "install_default_runtime_patches") is True
    assert hasattr(core, "install_business_runtime_patches") is True
    assert hasattr(core, "install_runtime_model_dispatch_patches") is False
    assert hasattr(core, "install_runtime_artifact_compatibility_patches") is False
    assert hasattr(core, "install_runtime_artifact_rknn_compatibility_patches") is False
    assert hasattr(core, "install_legacy_model_runtime_compatibility_patches") is False
    assert hasattr(core, "install_legacy_full_runtime_patches") is False

    assert hasattr(coral_inference, "install_default_runtime_patches") is True
    assert hasattr(coral_inference, "install_business_runtime_patches") is True
    assert hasattr(coral_inference, "install_runtime_model_dispatch_patches") is False
    assert hasattr(coral_inference, "install_runtime_artifact_compatibility_patches") is False
    assert hasattr(coral_inference, "install_runtime_artifact_rknn_compatibility_patches") is False
    assert hasattr(coral_inference, "install_legacy_model_runtime_compatibility_patches") is False
    assert hasattr(coral_inference, "install_legacy_full_runtime_patches") is False

    assert hasattr(patches, "install_runtime_artifact_compatibility_patches") is False
    assert hasattr(patches, "install_runtime_artifact_rknn_compatibility_patches") is False
    assert hasattr(patches, "install_legacy_model_runtime_compatibility_patches") is False
    assert hasattr(patches, "install_legacy_full_runtime_patches") is False

    assert hasattr(runtime, "extend_get_model_artifacts") is False
    assert hasattr(runtime, "extend_download_model_artifacts") is False
    assert hasattr(runtime, "cache_runtime_model_artifacts") is False


def test_normalise_model_metadata_uses_reference_profile_execution_reference():
    metadata = _normalise_model_metadata(
        {
            "model_reference": "asset:9",
            "reference_profile": {
                "primary_reference": "asset:9",
                "primary_reference_kind": "asset_reference",
                "asset_reference": "asset:9",
                "requested_binding_ref": "binding:hosted-1",
                "effective_binding_ref": "binding:rknn-1",
                "binding_ref_changed": True,
                "resolution_source": "source_model_asset_id",
            },
            "binding_ref": "binding:rknn-1",
            "binding_type": "package_ref",
            "model_id": "model-9",
            "model_name": "hard-hat-v7",
            "selected_runtime": "rknn",
        }
    )

    execution_reference = metadata["execution_reference"]
    assert execution_reference["model_reference"] == "asset:9"
    assert execution_reference["model_reference_type"] == "asset_reference"
    assert execution_reference["asset_reference"] == "asset:9"
    assert execution_reference["requested_binding_ref"] == "binding:hosted-1"
    assert execution_reference["effective_binding_ref"] == "binding:rknn-1"
    assert execution_reference["binding_ref_changed"] is True
    assert execution_reference["resolution_source"] == "source_model_asset_id"


def test_normalise_environment_prefers_standardized_class_mapping_fallback():
    environment = _normalise_environment(
        {
            "artifact_manifest": {
                "preprocessing": {"resize": {"width": 640, "height": 640}},
                "class_mapping": {"0": "helmet", "1": "vest"},
                "colors": {"0": "#ffcc00"},
                "batch_size": 4,
            }
        }
    )

    assert environment["PREPROCESSING"] == '{"resize": {"width": 640, "height": 640}}'
    assert environment["CLASS_MAP"] == {"0": "helmet", "1": "vest"}
    assert environment["COLORS"] == {"0": "#ffcc00"}
    assert environment["BATCH_SIZE"] == 4


def test_register_runtime_package_validates_runtime_contract():
    package = register_runtime_package(
        {
            "deployment_id": "dep-1",
            "deployment_name": "helmet monitor",
            "workflow_name": "helmet-workflow",
            "workflow_spec": {
                "inputs": [
                    {
                        "type": "WorkflowParameter",
                        "name": "model",
                        "default_value": "asset:9",
                    }
                ]
            },
            "model_bindings": [
                {
                    "node_name": "detect",
                    "field_name": "model",
                    "model_reference": "asset:9",
                    "reference_profile": {
                        "primary_reference": "asset:9",
                        "primary_reference_kind": "asset_reference",
                        "asset_reference": "asset:9",
                        "requested_binding_ref": "binding:hosted-1",
                        "effective_binding_ref": "binding:rknn-1",
                    },
                    "binding_id": "rknn-1",
                    "binding_ref": "binding:rknn-1",
                    "binding_type": "package_ref",
                    "model_id": "model-9",
                    "model_name": "hard-hat-v7",
                    "framework": "rfdetr",
                    "selected_runtime": "rknn",
                    "artifact_manifest": {
                        "runtime": {
                            "supported_runtimes": ["onnx", "rknn"],
                            "preferred_runtime": "rknn",
                            "weight_index_by_runtime": {
                                "onnx": "coral-models/model-9/weights.onnx",
                                "rknn": "coral-models/model-9/weights.rknn",
                            },
                        },
                        "label_schema": {
                            "schema_version": "v1",
                            "task_type": "object-detection",
                            "class_count": 1,
                            "classes": [{"id": "0", "name": "helmet"}],
                        },
                    },
                    "supported_runtimes": ["onnx", "rknn"],
                    "preferred_runtime": "rknn",
                    "runtime_environment": {
                        "PREPROCESSING": {"resize": {"width": 640, "height": 640}},
                        "CLASS_MAP": {"0": "helmet"},
                    },
                }
            ],
            "sources": [{"camera_id": "cam-1", "path": "rtsp://demo"}],
            "stream_config": {"output_image_fields": ["predictions"], "max_fps": 10},
            "metrics_config": {"deployment_id": "dep-1", "gateway_id": "gw-1"},
        }
    )

    assert package["deployment_id"] == "dep-1"
    assert package["model_bindings"][0]["binding_id"] == "rknn-1"
    assert package["model_bindings"][0]["artifact_manifest"]["runtime"]["preferred_runtime"] == "rknn"
    assert (
        package["workflow_spec"]["inputs"][0]["default_value"]
        == "coral-runtime-rknn-1"
    )
    assert get_runtime_deployment("dep-1") is not None
    assert get_runtime_deployment("dep-1")["model_bindings"][0]["binding_id"] == "rknn-1"
    assert (
        get_runtime_model_binding("coral-runtime-rknn-1")["artifact_manifest"]["runtime"]["preferred_runtime"]
        == "rknn"
    )
    assert resolve_runtime_endpoint_model_type("coral-runtime-rknn-1") == (
        "object-detection",
        "rfdetr",
    )


def test_register_runtime_model_bindings_registers_runtime_endpoint_without_lockfile():
    bindings = register_runtime_model_bindings(
        [
            {
                "node_name": "detect",
                "field_name": "model",
                "model_reference": "asset:9",
                "binding_id": "bind-standalone-1",
                "binding_ref": "binding:bind-standalone-1",
                "binding_type": "package_ref",
                "model_id": "model-9",
                "model_name": "hard-hat-v7",
                "task_type": "object-detection",
                "framework": "rfdetr",
                "selected_loader_type": "inference_models",
                "selected_runtime": "onnx",
                "artifact_manifest": {
                    "runtime": {
                        "supported_runtimes": ["onnx"],
                        "preferred_runtime": "onnx",
                    }
                },
            }
        ]
    )

    assert bindings[0]["runtime_model_endpoint"] == "coral-runtime-bind-standalone-1"
    assert get_runtime_model_binding("coral-runtime-bind-standalone-1") is not None


def test_normalize_runtime_status_report_standardizes_state_and_payload():
    report = normalize_runtime_status_report(
        {
            "sources_metadata": [
                {"source_id": 1, "state": "running", "source_reference": "rtsp://demo"}
            ],
            "latency_reports": [
                {
                    "source_id": 1,
                    "frame_decoding_latency": 0.01,
                    "inference_latency": 0.02,
                    "e2e_latency": 0.03,
                }
            ],
            "video_source_status_updates": [
                {
                    "timestamp": "2026-04-02T12:00:00Z",
                    "severity": "error",
                    "event_type": "SOURCE_ERROR",
                    "payload": None,
                }
            ],
            "inference_throughput": 5.5,
        }
    )

    assert report["sources_metadata"][0]["state"] == "RUNNING"
    assert report["video_source_status_updates"][0]["severity"] == "ERROR"
    assert report["video_source_status_updates"][0]["payload"] == {}


def test_normalize_runtime_status_report_coerces_numeric_severity():
    report = normalize_runtime_status_report(
        {
            "video_source_status_updates": [
                {
                    "timestamp": "2026-04-19T17:03:57Z",
                    "severity": 20,
                    "event_type": "HEALTH_CHECK_WARNING",
                    "payload": {},
                }
            ]
        }
    )

    assert report["video_source_status_updates"][0]["severity"] == "20"


def test_normalize_runtime_status_report_accepts_numeric_source_reference():
    report = normalize_runtime_status_report(
        {
            "sources_metadata": [
                {
                    "source_id": 0,
                    "source_reference": 0,
                    "state": "running",
                }
            ]
        }
    )

    assert report["sources_metadata"][0]["source_reference"] == 0
    assert report["sources_metadata"][0]["state"] == "RUNNING"


def test_resolve_runtime_binding_model_signature_uses_binding_contract():
    binding = {
        "node_name": "detect",
        "field_name": "model",
        "model_reference": "asset:9",
        "binding_id": "rknn-1",
        "binding_ref": "binding:rknn-1",
        "binding_type": "package_ref",
        "model_id": "model-9",
        "model_name": "helmet",
        "task_type": "object-detection",
        "framework": "rfdetr",
        "selected_loader_type": "coral_rknn",
        "package_files_snapshot": [
            {"file_handle": "weights.rknn"},
            {"file_handle": "class_names.txt"},
            {"file_handle": "inference_config.json"},
            {"file_handle": "runtime_metadata.json"},
        ],
    }

    assert resolve_runtime_binding_model_signature(
        RuntimeModelBinding.model_validate(binding)
    ) == ("object-detection", "rfdetr")


def test_get_runtime_binding_support_issue_rejects_unsupported_coral_rknn_binding():
    binding = RuntimeModelBinding.model_validate(
        {
            "node_name": "classify",
            "field_name": "model",
            "model_reference": "asset:9",
            "binding_id": "rknn-1",
            "binding_ref": "binding:rknn-1",
            "binding_type": "package_ref",
            "model_id": "model-9",
            "model_name": "helmet-cls",
            "task_type": "classification",
            "framework": "yolov8-cls",
            "selected_loader_type": "coral_rknn",
            "package_files_snapshot": [
                {"file_handle": "weights.rknn"},
                {"file_handle": "class_names.txt"},
                {"file_handle": "inference_config.json"},
                {"file_handle": "runtime_metadata.json"},
            ],
        }
    )

    assert (
        get_runtime_binding_support_issue(binding)
        == "Current Coral RKNN runtime only supports object-detection packages with yolov8 or rfdetr architecture"
    )


def test_get_runtime_binding_missing_required_files_for_inference_models():
    binding = RuntimeModelBinding.model_validate(
        {
            "node_name": "detect",
            "field_name": "model",
            "model_reference": "asset:9",
            "binding_id": "onnx-1",
            "binding_ref": "binding:onnx-1",
            "binding_type": "package_ref",
            "model_id": "model-9",
            "model_name": "helmet",
            "task_type": "object-detection",
            "framework": "yolov8",
            "selected_loader_type": "inference_models",
            "selected_backend": "onnx",
            "package_files_snapshot": [],
        }
    )

    assert get_runtime_binding_missing_required_files(binding) == {
        "class_names.txt",
        "inference_config.json",
        "weights.onnx",
    }


def test_get_runtime_binding_support_issue_rejects_missing_inference_models_files():
    binding = RuntimeModelBinding.model_validate(
        {
            "node_name": "detect",
            "field_name": "model",
            "model_reference": "asset:9",
            "binding_id": "onnx-1",
            "binding_ref": "binding:onnx-1",
            "binding_type": "package_ref",
            "model_id": "model-9",
            "model_name": "helmet",
            "task_type": "object-detection",
            "framework": "yolov8",
            "selected_loader_type": "inference_models",
            "selected_backend": "onnx",
            "package_files_snapshot": [],
        }
    )

    assert (
        get_runtime_binding_support_issue(binding)
        == "Current Coral inference_models runtime is missing required package files: class_names.txt, inference_config.json, weights.onnx"
    )


def test_extend_registry_get_model_uses_runtime_adapter(monkeypatch):
    class RuntimeAdapter:
        pass

    monkeypatch.setattr(
        "coral_inference.runtime.model_registry.resolve_runtime_model_adapter",
        lambda model_id: RuntimeAdapter if model_id == "coral-runtime-rknn-1" else None,
    )

    class DummyRegistry:
        pass

    original_called = {"value": False}

    def original(self, model_id, api_key, **kwargs):
        original_called["value"] = True
        return "legacy"

    wrapped = extend_registry_get_model(original)
    result = wrapped(DummyRegistry(), "coral-runtime-rknn-1", "api-key")

    assert result is RuntimeAdapter
    assert original_called["value"] is False


def test_extend_model_getter_uses_runtime_adapter(monkeypatch):
    class RuntimeAdapter:
        def __init__(self, model_id, api_key=None, **kwargs):
            self.model_id = model_id
            self.api_key = api_key
            self.kwargs = kwargs

    monkeypatch.setattr(
        "coral_inference.runtime.model_registry.resolve_runtime_model_adapter",
        lambda model_id: RuntimeAdapter if model_id == "coral-runtime-rknn-1" else None,
    )

    original_called = {"value": False}

    def original(model_id, api_key=None, **kwargs):
        original_called["value"] = True
        return {"model_id": model_id, "api_key": api_key, "kwargs": kwargs}

    wrapped = extend_model_getter(original)
    result = wrapped("coral-runtime-rknn-1", api_key="api-key", confidence=0.42)

    assert isinstance(result, RuntimeAdapter)
    assert result.model_id == "coral-runtime-rknn-1"
    assert result.api_key == "api-key"
    assert result.kwargs == {"confidence": 0.42}
    assert original_called["value"] is False


def test_extend_registry_get_model_falls_back_for_non_runtime(monkeypatch):
    monkeypatch.setattr(
        "coral_inference.runtime.model_registry.resolve_runtime_model_adapter",
        lambda model_id: None,
    )

    class DummyRegistry:
        pass

    def original(self, model_id, api_key, **kwargs):
        return (model_id, api_key, kwargs)

    wrapped = extend_registry_get_model(original)
    result = wrapped(
        DummyRegistry(),
        "project/1",
        "api-key",
        countinference=True,
    )

    assert result == ("project/1", "api-key", {"countinference": True, "service_secret": None})


def test_resolve_runtime_model_adapter_uses_coral_rknn_dispatch(monkeypatch):
    fake_module = types.ModuleType("coral_inference.runtime.rknn_adapters")

    class RuntimeAdapter:
        pass

    fake_module.get_runtime_rknn_adapter = lambda model_id, binding=None: RuntimeAdapter
    monkeypatch.setitem(
        sys.modules,
        "coral_inference.runtime.rknn_adapters",
        fake_module,
    )
    monkeypatch.setattr(
        "coral_inference.runtime.model_registry.is_runtime_model_endpoint",
        lambda model_id: True,
    )
    monkeypatch.setattr(
        "coral_inference.runtime.model_registry.get_runtime_model_binding",
        lambda model_id: {
            "node_name": "detect",
            "field_name": "model",
            "model_reference": "asset:9",
            "binding_id": "rknn-1",
            "binding_ref": "binding:rknn-1",
            "binding_type": "package_ref",
            "model_id": "model-9",
            "model_name": "helmet",
            "task_type": "object-detection",
            "framework": "rfdetr",
            "selected_loader_type": "coral_rknn",
            "package_files_snapshot": [
                {"file_handle": "weights.rknn"},
                {"file_handle": "class_names.txt"},
                {"file_handle": "inference_config.json"},
                {"file_handle": "runtime_metadata.json"},
            ],
        },
    )

    assert resolve_runtime_model_adapter("coral-runtime-rknn-1") is RuntimeAdapter


def test_coral_runtime_inference_models_adapter_instantiates_without_parent_init(monkeypatch):
    monkeypatch.setattr(
        "coral_inference.runtime.adapters.get_runtime_model_binding",
        lambda model_id: {
            "node_name": "detect",
            "field_name": "model",
            "model_reference": "asset:9",
            "binding_id": "onnx-1",
            "binding_ref": "binding:onnx-1",
            "binding_type": "package_ref",
            "model_id": "model-9",
            "model_name": "helmet",
            "task_type": "object-detection",
            "framework": "rfdetr",
            "selected_loader_type": "inference_models",
            "selected_runtime": "onnx",
            "package_files_snapshot": [{"file_handle": "weights.onnx"}],
        },
    )
    monkeypatch.setattr(
        "coral_inference.runtime.adapters.ensure_runtime_package_materialized",
        lambda binding: types.SimpleNamespace(package_dir="/tmp/runtime-package"),
    )
    monkeypatch.setattr(
        "coral_inference.runtime.adapters.load_inference_models_package",
        lambda package_dir, **kwargs: types.SimpleNamespace(class_names=["helmet"]),
    )

    adapter = CoralRuntimeObjectDetectionAdapter(
        model_id="coral-runtime-onnx-1",
        api_key="api-key",
    )

    assert adapter.endpoint == "coral-runtime-onnx-1"
    assert adapter.api_key == "api-key"
    assert adapter.class_names == ["helmet"]


def test_resolve_runtime_model_adapter_rejects_unsupported_binding(monkeypatch):
    monkeypatch.setattr(
        "coral_inference.runtime.model_registry.is_runtime_model_endpoint",
        lambda model_id: True,
    )
    monkeypatch.setattr(
        "coral_inference.runtime.model_registry.get_runtime_model_binding",
        lambda model_id: {
            "node_name": "classify",
            "field_name": "model",
            "model_reference": "asset:9",
            "binding_id": "rknn-1",
            "binding_ref": "binding:rknn-1",
            "binding_type": "package_ref",
            "model_id": "model-9",
            "model_name": "helmet-cls",
            "task_type": "classification",
            "framework": "yolov8-cls",
            "selected_loader_type": "coral_rknn",
            "package_files_snapshot": [
                {"file_handle": "weights.rknn"},
                {"file_handle": "class_names.txt"},
                {"file_handle": "inference_config.json"},
                {"file_handle": "runtime_metadata.json"},
            ],
        },
    )

    with pytest.raises(Exception) as exc:
        resolve_runtime_model_adapter("coral-runtime-rknn-1")

    assert "not supported by the current Coral runtime" in str(exc.value)


def test_get_runtime_binding_support_issue_rejects_dependency_aware_inference_models_package():
    binding = RuntimeModelBinding.model_validate(
        {
            "node_name": "detect",
            "field_name": "model",
            "model_reference": "asset:9",
            "binding_id": "bind-1",
            "binding_ref": "binding:bind-1",
            "binding_type": "package_ref",
            "model_id": "model-9",
            "model_name": "helmet-detector",
            "task_type": "object-detection",
            "framework": "yolov8",
            "selected_package_id": "pkg-onnx",
            "selected_loader_type": "inference_models",
            "selected_backend": "onnx",
            "selected_runtime": "onnx",
            "standardized_metadata": {
                "model_dependencies": [
                    {
                        "name": "text-encoder",
                        "modelId": "dep-model",
                        "modelPackageId": "dep-model-onnx",
                    }
                ]
            },
            "package_files_snapshot": [
                {"file_handle": "weights.onnx"},
                {"file_handle": "inference_config.json"},
            ],
        }
    )

    assert get_runtime_binding_model_dependencies(binding) == [
        {
            "name": "text-encoder",
            "modelId": "dep-model",
            "modelPackageId": "dep-model-onnx",
        }
    ]
    assert (
        get_runtime_binding_support_issue(binding)
        == "Current Coral inference_models runtime does not yet support packages with modelDependencies"
    )


def test_get_runtime_binding_support_issue_rejects_runtime_artifact_binding():
    binding = RuntimeModelBinding.model_validate(
        {
            "node_name": "detect",
            "field_name": "model",
            "model_reference": "asset:9",
            "binding_id": "bind-legacy",
            "binding_ref": "binding:bind-legacy",
            "binding_type": "runtime_artifact",
            "model_id": "model-9",
            "model_name": "helmet-detector",
            "task_type": "object-detection",
            "framework": "yolov8",
            "selected_runtime": "onnx",
        }
    )

    assert (
        get_runtime_binding_support_issue(binding)
        == "Current Coral runtime only supports package_ref bindings; runtime_artifact bindings are no longer supported"
    )


def test_rknn_inference_session_run_normalizes_multiple_outputs():
    class FakeSession:
        def inference(self, inputs):
            return [
                np.zeros((1, 84, 8400, 1), dtype=np.float32),
                np.zeros((1, 32, 160, 160), dtype=np.float32),
            ]

    session = RknnInferenceSession.__new__(RknnInferenceSession)
    session.input_name = "images"
    session.rknn_session = FakeSession()

    outputs = session.run(None, {"images": np.zeros((640, 640, 3), dtype=np.float32)})

    assert len(outputs) == 2
    assert outputs[0].shape == (1, 84, 8400)
    assert outputs[1].shape == (1, 32, 160, 160)


def test_rknn_inference_session_run_keeps_4d_input_shape():
    captured = {}

    class FakeSession:
        def inference(self, inputs):
            captured["shape"] = inputs.shape
            return [np.zeros((1, 84, 8400, 1), dtype=np.float32)]

    session = RknnInferenceSession.__new__(RknnInferenceSession)
    session.input_name = "images"
    session.rknn_session = FakeSession()

    outputs = session.run(
        None,
        {"images": np.zeros((1, 3, 640, 640), dtype=np.float32)},
    )

    assert captured["shape"] == (1, 3, 640, 640)
    assert outputs[0].shape == (1, 84, 8400)


def test_get_runtime_rknn_adapter_supports_rfdetr(monkeypatch):
    monkeypatch.setattr(
        "coral_inference.runtime.rknn_adapters.resolve_runtime_endpoint_model_type",
        lambda model_id: ("object-detection", "rfdetr"),
    )

    assert (
        get_runtime_rknn_adapter("coral-runtime-rknn-1")
        is CoralRuntimeRFDETRRKNNObjectDetectionAdapter
    )
