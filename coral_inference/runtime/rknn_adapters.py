import json
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional, Type

import numpy as np
from inference.core.env import API_KEY
from inference.core.exceptions import ModelArtefactError
from inference.core.models.roboflow import get_color_mapping_from_environment
from inference.models.rfdetr.rfdetr import RFDETRObjectDetection
from inference.models.yolov8.yolov8_object_detection import YOLOv8ObjectDetection

from coral_inference.core.models.utils import RknnInferenceSession
from coral_inference.runtime.compat import get_runtime_model_binding
from coral_inference.runtime.contracts import RuntimeModelBinding
from coral_inference.runtime.loaders.rknn_loader import load_coral_rknn_package
from coral_inference.runtime.materialized_packages import (
    ensure_runtime_package_materialized,
)
from coral_inference.runtime.model_type_resolver import resolve_runtime_endpoint_model_type


def _load_environment_from_package(package_dir: str) -> Dict[str, object]:
    environment_path = Path(package_dir) / "environment.json"
    if not environment_path.exists():
        return {}
    return json.loads(environment_path.read_text(encoding="utf-8"))


class _CoralRuntimeRKNNObjectDetectionMixin:
    runtime_input_layout = "nhwc"
    convert_preprocessed_image_to_rknn = True

    def __init__(self, model_id: str, api_key: Optional[str] = None, **kwargs):
        self._runtime_binding_payload = get_runtime_model_binding(model_id)
        if not self._runtime_binding_payload:
            raise ModelArtefactError(
                f"Could not resolve runtime binding for model endpoint {model_id}"
            )
        self._runtime_binding = RuntimeModelBinding.model_validate(
            self._runtime_binding_payload
        )
        if self._runtime_binding.selected_loader_type != "coral_rknn":
            raise ModelArtefactError(
                f"Runtime endpoint {model_id} is configured for loader "
                f"{self._runtime_binding.selected_loader_type}, not coral_rknn"
            )
        self._runtime_materialized_package = ensure_runtime_package_materialized(
            binding=self._runtime_binding
        )
        self._runtime_rknn_bundle = load_coral_rknn_package(
            package_dir=self._runtime_materialized_package.package_dir,
            binding=self._runtime_binding,
        )
        super().__init__(model_id=model_id, api_key=api_key or API_KEY, **kwargs)

    def get_model_artifacts(self, **kwargs) -> None:
        environment = _load_environment_from_package(
            self._runtime_materialized_package.package_dir
        )
        if not environment:
            environment = {
                "PREPROCESSING": json.dumps(
                    self._runtime_binding.runtime_environment.get("PREPROCESSING") or {}
                ),
                "CLASS_MAP": dict(
                    self._runtime_binding.runtime_environment.get("CLASS_MAP") or {}
                ),
                "COLORS": dict(
                    self._runtime_binding.runtime_environment.get("COLORS") or {}
                ),
                "BATCH_SIZE": int(
                    self._runtime_binding.runtime_environment.get("BATCH_SIZE") or 1
                ),
            }

        self.environment = environment
        self.class_names = list(self._runtime_rknn_bundle.class_names)
        self.colors = get_color_mapping_from_environment(
            environment=self.environment,
            class_names=self.class_names,
        )
        self.num_classes = len(self.class_names)

        if "PREPROCESSING" not in self.environment:
            raise ModelArtefactError(
                "Could not find `PREPROCESSING` key in runtime package environment."
            )
        preprocessing = self.environment["PREPROCESSING"]
        if isinstance(preprocessing, dict):
            self.preproc = preprocessing
        else:
            self.preproc = json.loads(preprocessing)
        if self.preproc.get("resize"):
            self.resize_method = self.preproc["resize"].get("format", "Stretch to")
        else:
            self.resize_method = "Stretch to"
        self.multiclass = self.environment.get("MULTICLASS", False)

    def initialize_model(self, **kwargs) -> None:
        self.get_model_artifacts(**kwargs)
        inference_config = self._runtime_rknn_bundle.inference_config or {}
        network_input = inference_config.get("network_input") or {}
        input_size = network_input.get("training_input_size") or {}
        input_height = int(input_size.get("height") or 640)
        input_width = int(input_size.get("width") or 640)
        batch_size = 1
        if self.runtime_input_layout == "nchw":
            input_shape = [batch_size, 3, input_height, input_width]
        else:
            input_shape = [batch_size, input_height, input_width, 3]
        input_spec = SimpleNamespace(
            name="images",
            shape=input_shape,
        )
        self.onnx_session = RknnInferenceSession(
            model_fp=self._runtime_rknn_bundle.weights_path,
            inputs=input_spec,
        )
        self.batch_size = batch_size
        self.img_size_h = input_height
        self.img_size_w = input_width
        self.input_name = input_spec.name
        self.batching_enabled = False
        self.write_model_metadata_to_memcache(
            {
                "batch_size": self.batch_size,
                "img_size_h": self.img_size_h,
                "img_size_w": self.img_size_w,
            }
        )

    def preproc_image(self, image, **kwargs):
        img_in, img_dims = super().preproc_image(image, **kwargs)
        if hasattr(img_in, "detach"):
            img_in = img_in.detach().cpu().numpy()
        if (
            self.convert_preprocessed_image_to_rknn
            and isinstance(img_in, np.ndarray)
            and img_in.ndim == 4
        ):
            img_in = np.transpose(img_in, (0, 2, 3, 1))
            img_in = np.squeeze(img_in, axis=0)
            img_in = img_in * 255.0
        return img_in, img_dims


class CoralRuntimeYOLORKNNObjectDetectionAdapter(
    _CoralRuntimeRKNNObjectDetectionMixin,
    YOLOv8ObjectDetection,
):
    pass


class CoralRuntimeRFDETRRKNNObjectDetectionAdapter(
    _CoralRuntimeRKNNObjectDetectionMixin,
    RFDETRObjectDetection,
):
    runtime_input_layout = "nchw"
    convert_preprocessed_image_to_rknn = False


_RKNN_OBJECT_DETECTION_ADAPTERS: Dict[str, Type] = {
    "yolov8": CoralRuntimeYOLORKNNObjectDetectionAdapter,
    "rfdetr": CoralRuntimeRFDETRRKNNObjectDetectionAdapter,
}


def get_runtime_rknn_adapter(
    model_id: str,
    binding: Optional[RuntimeModelBinding] = None,
) -> Optional[Type]:
    resolved_type = resolve_runtime_endpoint_model_type(model_id)
    if resolved_type is None:
        return None
    task_type, model_type = resolved_type
    if task_type != "object-detection":
        return None
    return _RKNN_OBJECT_DETECTION_ADAPTERS.get(model_type)
