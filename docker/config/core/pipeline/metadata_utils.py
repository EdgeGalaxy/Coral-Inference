from typing import Any, Dict, List, Optional


SOURCE_IMAGE_FIELD = "source_image"


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _dedupe_fields(fields: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for field in fields:
        if field in seen:
            continue
        seen.add(field)
        result.append(field)
    return result


def _extract_workflow_image_outputs(workflow_spec: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(workflow_spec, dict):
        return []

    fields: List[str] = []
    for output in workflow_spec.get("outputs") or []:
        if not isinstance(output, dict):
            continue

        name = output.get("name")
        selector = output.get("selector")
        if not isinstance(name, str) or not name.strip():
            continue

        selector_text = selector if isinstance(selector, str) else ""
        name_text = name.lower()
        selector_text_lower = selector_text.lower()

        if (
            name_text in {"image", "output_image", "annotated_image"}
            or name_text.endswith("_image")
            or selector_text_lower.endswith(".image")
        ):
            fields.append(name)

    return fields


def resolve_output_image_fields(
    *,
    parameters: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    package: Optional[Dict[str, Any]] = None,
) -> List[str]:
    parameters = parameters or {}
    payload = payload or {}
    package = package or {}

    processing_configuration = payload.get("processing_configuration") or {}
    workflows_parameters = (
        processing_configuration.get("workflows_parameters") or {}
    )
    workflow_spec = (
        processing_configuration.get("workflow_specification")
        or package.get("workflow_spec")
        or {}
    )
    stream_config = package.get("stream_config") or {}
    package_parameters = package.get("parameters") or {}

    fields = [
        SOURCE_IMAGE_FIELD,
        *_as_string_list(parameters.get("output_image_fields")),
        *_as_string_list(workflows_parameters.get("output_image_fields")),
        *_as_string_list(stream_config.get("output_image_fields")),
        *_as_string_list(package.get("output_image_fields")),
        *_as_string_list(package_parameters.get("output_image_fields")),
        *_extract_workflow_image_outputs(workflow_spec),
    ]
    return _dedupe_fields(fields)
