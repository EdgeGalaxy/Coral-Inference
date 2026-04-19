import os

from inference.core import env as inference_env
from inference.core import roboflow_api as inference_roboflow_api
from inference.core.interfaces.camera import video_source
from inference.core.interfaces.stream import sinks
from inference.core.interfaces.stream_manager.api import stream_manager_client
from inference.core.interfaces.stream_manager.manager_app import app
from inference.core.interfaces.stream_manager.manager_app import (
    inference_pipeline_manager,
)
from inference.core.registries import roboflow as roboflow_registry
from inference.models import utils as inference_model_utils

from .inference.camera import patch_video_source
from .inference.stream import patch_sinks
from .inference.stream_manager import patch_app
from .inference.stream_manager import patch_manager_client
from .inference.stream_manager import patch_pipeline_manager
from .models.utils import get_runtime_platform
from coral_inference.runtime.model_registry import (
    extend_model_getter,
    extend_registry_get_model,
)
from coral_inference.runtime.model_type_resolver import (
    extend_access_check,
    extend_get_model_type,
)


runtime_platform = get_runtime_platform()
_BUSINESS_RUNTIME_PATCHES_INSTALLED = False
_MODEL_DISPATCH_PATCHES_INSTALLED = False
_BACKEND_MODEL_API_CONFIGURED = False


def configure_backend_model_api_base() -> bool:
    global _BACKEND_MODEL_API_CONFIGURED

    resolved_model_api_base = (
        os.getenv("API_BASE_URL")
        or getattr(inference_env, "API_BASE_URL", None)
        or ""
    ).rstrip("/")
    if not resolved_model_api_base:
        return False

    os.environ["API_BASE_URL"] = resolved_model_api_base
    os.environ["ROBOFLOW_API_HOST"] = resolved_model_api_base
    inference_env.API_BASE_URL = resolved_model_api_base
    inference_roboflow_api.API_BASE_URL = resolved_model_api_base

    try:
        import inference_models.configuration as inference_models_configuration
        from inference_models.weights_providers import roboflow as inference_models_roboflow

        inference_models_configuration.ROBOFLOW_API_HOST = resolved_model_api_base
        inference_models_roboflow.ROBOFLOW_API_HOST = resolved_model_api_base
    except Exception:
        # inference_models may be absent in some lightweight environments
        pass

    _BACKEND_MODEL_API_CONFIGURED = True
    return True


def get_runtime_patch_installation_state() -> dict:
    return {
        "runtime_platform": runtime_platform,
        "default_dispatch_installed": _MODEL_DISPATCH_PATCHES_INSTALLED,
        "default_business_installed": _BUSINESS_RUNTIME_PATCHES_INSTALLED,
        "model_api_base": (os.getenv("API_BASE_URL") or getattr(inference_env, "API_BASE_URL", None) or "").rstrip("/")
        or None,
        "backend_model_api_configured": _BACKEND_MODEL_API_CONFIGURED,
    }


def install_runtime_model_dispatch_patches() -> bool:
    global _MODEL_DISPATCH_PATCHES_INSTALLED

    if _MODEL_DISPATCH_PATCHES_INSTALLED:
        return False

    roboflow_registry.RoboflowModelRegistry.get_model = extend_registry_get_model(
        roboflow_registry.RoboflowModelRegistry.get_model
    )
    roboflow_registry.get_model_type = extend_get_model_type(
        roboflow_registry.get_model_type
    )
    roboflow_registry._check_if_api_key_has_access_to_model = extend_access_check(
        roboflow_registry._check_if_api_key_has_access_to_model
    )
    inference_model_utils.get_model_type = roboflow_registry.get_model_type
    inference_model_utils.get_model = extend_model_getter(
        inference_model_utils.get_model
    )
    inference_model_utils.get_roboflow_model = extend_model_getter(
        inference_model_utils.get_roboflow_model
    )

    _MODEL_DISPATCH_PATCHES_INSTALLED = True
    return True
def install_default_runtime_patches() -> None:
    configure_backend_model_api_base()
    install_runtime_model_dispatch_patches()
    install_business_runtime_patches()


def install_business_runtime_patches() -> bool:
    global _BUSINESS_RUNTIME_PATCHES_INSTALLED

    if _BUSINESS_RUNTIME_PATCHES_INSTALLED:
        return False

    sinks.InMemoryBufferSink.__init__ = patch_sinks.extend_init(
        sinks.InMemoryBufferSink.__init__
    )
    sinks.InMemoryBufferSink.on_prediction = patch_sinks.extend_on_prediction(
        sinks.InMemoryBufferSink.on_prediction
    )
    video_source.CV2VideoFrameProducer = patch_video_source.PatchedCV2VideoFrameProducer
    inference_pipeline_manager.InferencePipelineManager._offer = (
        patch_pipeline_manager.offer
    )
    inference_pipeline_manager.InferencePipelineManager._handle_command = (
        patch_pipeline_manager.rewrite_handle_command
    )
    stream_manager_client.StreamManagerClient.offer = patch_manager_client.offer
    app.InferencePipelinesManagerHandler.handle = patch_app.rewrite_handle
    app.get_response_ignoring_thrash = patch_app.patched_get_response_ignoring_thrash
    app.handle_command = patch_app.patched_handle_command
    app.execute_termination = patch_app.patched_execute_termination
    app.join_inference_pipeline = patch_app.patched_join_inference_pipeline
    app.check_process_health = patch_app.patched_check_process_health
    app.ensure_idle_pipelines_warmed_up = (
        patch_app.patched_ensure_idle_pipelines_warmed_up
    )

    _BUSINESS_RUNTIME_PATCHES_INSTALLED = True
    return True
