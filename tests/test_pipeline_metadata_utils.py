from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "docker"))

from config.core.pipeline.metadata_utils import resolve_output_image_fields


def test_resolve_output_image_fields_merges_cache_payload_and_package_fields():
    fields = resolve_output_image_fields(
        parameters={"output_image_fields": ["source_image", "cached_image"]},
        payload={
            "processing_configuration": {
                "workflows_parameters": {
                    "output_image_fields": ["payload_image", "cached_image"]
                }
            }
        },
        package={
            "stream_config": {"output_image_fields": ["package_image"]},
            "parameters": {"output_image_fields": ["parameter_image"]},
        },
    )

    assert fields == [
        "source_image",
        "cached_image",
        "payload_image",
        "package_image",
        "parameter_image",
    ]


def test_resolve_output_image_fields_falls_back_to_image_outputs_from_workflow_spec():
    fields = resolve_output_image_fields(
        payload={
            "processing_configuration": {
                "workflow_specification": {
                    "outputs": [
                        {
                            "type": "JsonField",
                            "name": "count_objects",
                            "selector": "$steps.count.output",
                        },
                        {
                            "type": "JsonField",
                            "name": "output_image",
                            "selector": "$steps.visualization.image",
                        },
                        {
                            "type": "JsonField",
                            "name": "predictions",
                            "selector": "$steps.model.predictions",
                        },
                    ]
                }
            }
        }
    )

    assert fields == ["source_image", "output_image"]
