from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib import metadata
from typing import Callable, Dict, Iterable, List, Optional

from inference.core.logger import logger
from inference.core.models import roboflow

from coral_inference.core.models import rknn_base


@dataclass
class BackendAdapter:
    name: str
    supports: Callable[[str, "RuntimeConfig"], bool]
    activate: Callable[[str, "RuntimeConfig"], bool]


_REGISTRY: Dict[str, BackendAdapter] = {}


def register_adapter(adapter: BackendAdapter):
    _REGISTRY[adapter.name] = adapter


def activate_backends(platform: str, config: "RuntimeConfig") -> List[str]:
    activated: List[str] = []
    for adapter in list(_REGISTRY.values()):
        if adapter.supports(platform, config):
            if adapter.activate(platform, config):
                activated.append(adapter.name)
    return activated


def reset_adapters():  # pragma: no cover - only used in tests
    _REGISTRY.clear()


def discover_entry_point_adapters(group: str = "coral_inference.backends") -> List[str]:
    loaded: List[str] = []
    try:
        eps = metadata.entry_points()
        selected = eps.select(group=group)
    except Exception as exc:  # pragma: no cover - metadata errors are rare
        logger.warning("Failed to load backend entry points: %s", exc)
        return loaded

    for ep in selected:
        try:
            value = ep.load()
            adapters = _normalise_adapter(value)
            for adapter in adapters:
                register_adapter(adapter)
                loaded.append(adapter.name)
        except Exception as exc:
            logger.warning("Failed to load backend adapter %s: %s", ep.name, exc)
    return loaded


def import_backend_modules(module_paths: Iterable[str]) -> List[str]:
    imported: List[str] = []
    for module_path in module_paths:
        if not module_path:
            continue
        try:
            import_module(module_path)
            imported.append(module_path)
        except Exception as exc:
            logger.warning("Failed to import backend module %s: %s", module_path, exc)
    return imported


def _normalise_adapter(value) -> List[BackendAdapter]:
    adapters: List[BackendAdapter] = []
    if isinstance(value, BackendAdapter):
        adapters.append(value)
    elif callable(value):
        result = value()
        adapters.extend(_normalise_adapter(result))
    elif isinstance(value, Iterable):
        for item in value:
            adapters.extend(_normalise_adapter(item))
    else:
        raise TypeError(f"Unsupported backend adapter type: {type(value)}")
    return adapters


def _register_default_adapters():
    def supports_rknn(platform: str, config: "RuntimeConfig") -> bool:
        return platform == "rknn" and config.auto_patch_rknn

    def activate_rknn(platform: str, config: "RuntimeConfig") -> bool:
        roboflow.OnnxRoboflowInferenceModel.initialize_model = (
            rknn_base.extend_initialize_model(
                roboflow.OnnxRoboflowInferenceModel.initialize_model
            )
        )
        roboflow.OnnxRoboflowInferenceModel.preproc_image = (
            rknn_base.extend_preproc_image(
                roboflow.OnnxRoboflowInferenceModel.preproc_image
            )
        )
        roboflow.OnnxRoboflowInferenceModel.get_all_required_infer_bucket_file = (
            rknn_base.extend_get_all_required_infer_bucket_file(
                roboflow.OnnxRoboflowInferenceModel.get_all_required_infer_bucket_file
            )
        )
        roboflow.OnnxRoboflowInferenceModel.download_model_artifacts_from_roboflow_api = (
            rknn_base.extend_download_model_artifacts(
                roboflow.OnnxRoboflowInferenceModel.download_model_artifacts_from_roboflow_api
            )
        )
        roboflow.OnnxRoboflowInferenceModel.rknn_weights_file = property(
            rknn_base.rknn_weights_file
        )

        logger.info(
            "runtime_platform is rknn, using RknnCoralInferenceModel replace OnnxRoboflowInferenceModel"
        )
        return True

    register_adapter(
        BackendAdapter(
            name="rknn",
            supports=supports_rknn,
            activate=activate_rknn,
        )
    )

    def supports_onnx(platform: str, config: "RuntimeConfig") -> bool:  # noqa: ARG001
        return platform != "rknn"

    def activate_onnx(platform: str, config: "RuntimeConfig") -> bool:  # noqa: ARG001
        logger.info(
            "runtime_platform is %s, using default OnnxRoboflowInferenceModel",
            platform,
        )
        return True

    register_adapter(
        BackendAdapter(
            name="onnx",
            supports=supports_onnx,
            activate=activate_onnx,
        )
    )


_register_default_adapters()

__all__ = [
    "BackendAdapter",
    "activate_backends",
    "register_adapter",
    "reset_adapters",
    "discover_entry_point_adapters",
    "import_backend_modules",
]
