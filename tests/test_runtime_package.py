from coral_inference.core.runtime_contract import normalize_runtime_status_report
from coral_inference.core.runtime_package import (
    _normalise_environment,
    _normalise_model_metadata,
    get_runtime_deployment,
    get_runtime_model_binding,
    materialize_runtime_workflow_specification,
    register_runtime_package,
)


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
            "binding_type": "runtime_artifact",
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
            "binding_type": "runtime_artifact",
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
                    "binding_type": "runtime_artifact",
                    "model_id": "model-9",
                    "model_name": "hard-hat-v7",
                    "selected_runtime": "rknn",
                    "artifact_uri": "coral-models/model-9/weights.rknn",
                    "artifact_manifest": {
                        "runtime": {
                            "supported_runtimes": ["onnx", "rknn"],
                            "preferred_runtime": "rknn",
                            "artifact_by_runtime": {
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
                    "artifact_by_runtime": {
                        "onnx": "coral-models/model-9/weights.onnx",
                        "rknn": "coral-models/model-9/weights.rknn",
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
