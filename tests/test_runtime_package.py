from coral_inference.core.runtime_package import (
    _normalise_model_metadata,
    materialize_runtime_workflow_specification,
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
