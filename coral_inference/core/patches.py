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


def get_runtime_patch_installation_state() -> dict:
    return {
        "runtime_platform": runtime_platform,
        "default_dispatch_installed": _MODEL_DISPATCH_PATCHES_INSTALLED,
        "default_business_installed": _BUSINESS_RUNTIME_PATCHES_INSTALLED,
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
