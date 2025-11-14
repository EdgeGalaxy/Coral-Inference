from dataclasses import dataclass
from typing import Optional, Tuple

from inference.core.interfaces.stream import sinks
from inference.core.interfaces.camera import video_source
from inference.core.interfaces.stream_manager.api import stream_manager_client
from inference.core.interfaces.stream_manager.manager_app import app
from inference.core.interfaces.stream_manager.manager_app import (
    inference_pipeline_manager,
)
from inference.core.logger import logger

from coral_inference.core.inference.camera import patch_video_source
from coral_inference.core.inference.stream_manager import patch_app
from coral_inference.core.inference.stream_manager import patch_manager_client
from coral_inference.core.inference.stream_manager import patch_pipeline_manager
from coral_inference.core.inference.stream import patch_sinks
from coral_inference.runtime.compat import (
    get_inference_version_tuple,
    is_version_supported,
)

PATCH_CAMERA = "camera"
PATCH_STREAM_MANAGER = "stream_manager"
PATCH_BUFFER_SINK = "buffer_sink"
PATCH_VIDEO_SINK = "video_sink"
PATCH_METRIC_SINK = "metric_sink"
PATCH_WEBRTC = "webrtc"
PATCH_PLUGINS = "plugins"

Version = Tuple[int, int, int]


@dataclass
class PatchInfo:
    name: str
    min_version: Optional[Version] = None
    max_version: Optional[Version] = None
    description: str = ""


PATCH_META = {
    PATCH_CAMERA: PatchInfo(name=PATCH_CAMERA, description="Camera video source patch"),
    PATCH_STREAM_MANAGER: PatchInfo(name=PATCH_STREAM_MANAGER, description="Stream manager robustness"),
    PATCH_BUFFER_SINK: PatchInfo(name=PATCH_BUFFER_SINK, description="In-memory buffer sink"),
    PATCH_VIDEO_SINK: PatchInfo(name=PATCH_VIDEO_SINK, description="Video recording sink"),
    PATCH_METRIC_SINK: PatchInfo(name=PATCH_METRIC_SINK, description="InfluxDB metric sink"),
    PATCH_WEBRTC: PatchInfo(name=PATCH_WEBRTC, description="WebRTC helpers"),
    PATCH_PLUGINS: PatchInfo(name=PATCH_PLUGINS, description="Workflow plugin registration"),
}


def _is_supported(name: str) -> bool:
    meta = PATCH_META.get(name)
    if not meta:
        return True
    if not is_version_supported(meta.min_version, meta.max_version):
        logger.warning(
            "Patch %s disabled due to inference version %s outside range %s-%s",
            name,
            get_inference_version_tuple(),
            meta.min_version,
            meta.max_version,
        )
        return False
    return True


def enable_camera_patch() -> bool:
    if not _is_supported(PATCH_CAMERA):
        return False
    video_source.CV2VideoFrameProducer = patch_video_source.PatchedCV2VideoFrameProducer
    return True


def enable_sink_patch() -> bool:
    return enable_buffer_sink_patch()


def enable_buffer_sink_patch() -> bool:
    if not _is_supported(PATCH_BUFFER_SINK):
        return False
    sinks.InMemoryBufferSink.__init__ = patch_sinks.extend_init(
        sinks.InMemoryBufferSink.__init__
    )
    sinks.InMemoryBufferSink.on_prediction = patch_sinks.extend_on_prediction(
        sinks.InMemoryBufferSink.on_prediction
    )
    return True


def enable_stream_manager_patch() -> bool:
    if not _is_supported(PATCH_STREAM_MANAGER):
        return False
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
    app.ensure_idle_pipelines_warmed_up = patch_app.patched_ensure_idle_pipelines_warmed_up
    return True


def enable_webrtc_patch() -> bool:
    if not _is_supported(PATCH_WEBRTC):
        return False
    return True


def enable_plugins_patch() -> bool:
    if not _is_supported(PATCH_PLUGINS):
        return False
    import coral_inference.plugins  # noqa: F401

    return True


__all__ = [
    "PATCH_CAMERA",
    "PATCH_STREAM_MANAGER",
    "PATCH_BUFFER_SINK",
    "PATCH_VIDEO_SINK",
    "PATCH_METRIC_SINK",
    "PATCH_WEBRTC",
    "PATCH_PLUGINS",
    "enable_camera_patch",
    "enable_stream_manager_patch",
    "enable_sink_patch",
    "enable_buffer_sink_patch",
    "enable_video_sink_patch",
    "enable_metric_sink_patch",
    "enable_webrtc_patch",
    "enable_plugins_patch",
]
def enable_video_sink_patch() -> bool:
    if not _is_supported(PATCH_VIDEO_SINK):
        return False
    # video sink patch lives in pipeline manager (TimeBasedVideoSink). placeholder for future toggles
    return True


def enable_metric_sink_patch() -> bool:
    if not _is_supported(PATCH_METRIC_SINK):
        return False
    # metric sink patch currently tied to pipeline manager multi_sink configuration
    return True
