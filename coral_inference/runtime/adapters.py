from typing import Dict, Optional, Type

from inference.core.env import API_KEY
from inference.core.exceptions import ModelArtefactError
from inference.core.models.inference_models_adapters import (
    InferenceModelsClassificationAdapter,
    InferenceModelsInstanceSegmentationAdapter,
    InferenceModelsKeyPointsDetectionAdapter,
    InferenceModelsObjectDetectionAdapter,
    InferenceModelsSemanticSegmentationAdapter,
)

from coral_inference.runtime.contracts import (
    RuntimeModelBinding,
)
from coral_inference.runtime.loaders.inference_models_loader import (
    load_inference_models_package,
)
from coral_inference.runtime.compat import get_runtime_model_binding
from coral_inference.runtime.materialized_packages import (
    ensure_runtime_package_materialized,
)


class _CoralRuntimeInferenceModelsMixin:
    runtime_task_type: Optional[str] = None

    def __init__(self, model_id: str, api_key: Optional[str] = None, **kwargs):
        binding_payload = get_runtime_model_binding(model_id)
        if not binding_payload:
            raise ModelArtefactError(
                f"Could not resolve runtime binding for model endpoint {model_id}"
            )
        binding = RuntimeModelBinding.model_validate(binding_payload)
        if binding.selected_loader_type != "inference_models":
            raise ModelArtefactError(
                f"Runtime endpoint {model_id} is configured for loader "
                f"{binding.selected_loader_type}, not inference_models"
            )
        self.metrics = {"num_inferences": 0, "avg_inference_time": 0.0}
        self.api_key = api_key if api_key else API_KEY
        self.endpoint = model_id
        self.binding = binding
        self.materialized_package = ensure_runtime_package_materialized(binding=binding)
        self.task_type = self.runtime_task_type or binding.task_type
        self._model = load_inference_models_package(
            package_dir=self.materialized_package.package_dir,
            **kwargs,
        )
        class_names = getattr(self._model, "class_names", None) or []
        self.class_names = list(class_names)


class CoralRuntimeObjectDetectionAdapter(
    _CoralRuntimeInferenceModelsMixin,
    InferenceModelsObjectDetectionAdapter,
):
    runtime_task_type = "object-detection"


class CoralRuntimeInstanceSegmentationAdapter(
    _CoralRuntimeInferenceModelsMixin,
    InferenceModelsInstanceSegmentationAdapter,
):
    runtime_task_type = "instance-segmentation"


class CoralRuntimeKeyPointsDetectionAdapter(
    _CoralRuntimeInferenceModelsMixin,
    InferenceModelsKeyPointsDetectionAdapter,
):
    runtime_task_type = "keypoint-detection"


class CoralRuntimeClassificationAdapter(
    _CoralRuntimeInferenceModelsMixin,
    InferenceModelsClassificationAdapter,
):
    runtime_task_type = "classification"


class CoralRuntimeSemanticSegmentationAdapter(
    _CoralRuntimeInferenceModelsMixin,
    InferenceModelsSemanticSegmentationAdapter,
):
    runtime_task_type = "semantic-segmentation"


_TASK_TO_ADAPTER: Dict[str, Type] = {
    "object-detection": CoralRuntimeObjectDetectionAdapter,
    "instance-segmentation": CoralRuntimeInstanceSegmentationAdapter,
    "keypoint-detection": CoralRuntimeKeyPointsDetectionAdapter,
    "classification": CoralRuntimeClassificationAdapter,
    "semantic-segmentation": CoralRuntimeSemanticSegmentationAdapter,
}


def get_runtime_inference_models_adapter(
    model_id: str,
    binding: Optional[RuntimeModelBinding] = None,
) -> Type:
    if binding is None:
        binding_payload = get_runtime_model_binding(model_id)
        if not binding_payload:
            raise ModelArtefactError(
                f"Could not resolve runtime binding for model endpoint {model_id}"
            )
        binding = RuntimeModelBinding.model_validate(binding_payload)
    task_type = str(binding.task_type or "").strip()
    if task_type not in _TASK_TO_ADAPTER:
        raise ModelArtefactError(
            f"Runtime endpoint {model_id} uses unsupported inference_models task type: "
            f"{binding.task_type}"
        )
    return _TASK_TO_ADAPTER[task_type]
