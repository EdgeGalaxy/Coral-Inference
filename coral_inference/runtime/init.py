from typing import Optional

from loguru import logger
from coral_inference.core.models import utils as model_utils
from coral_inference.core.models.utils import get_runtime_platform
from coral_inference.runtime import patches
from coral_inference.runtime import backends
from coral_inference.runtime import plugins as runtime_plugins
from coral_inference.runtime.compat import (
    inference_version,
    get_inference_version_tuple,
)
from .config import RuntimeConfig
from .context import RuntimeContext, RuntimeState

_CURRENT_CONTEXT: Optional[RuntimeContext] = None


model_utils.roboflow.get_from_url = model_utils.get_from_url


def init(config: Optional[RuntimeConfig] = None) -> RuntimeContext:
    global _CURRENT_CONTEXT
    config = config or RuntimeConfig.from_env()

    platform = config.platform or get_runtime_platform()
    state = RuntimeState(platform=platform)
    log_messages = []

    def _apply_patch(flag: bool, patch_name: str, func) -> None:
        if not flag:
            state.patches_enabled[patch_name] = False
            log_messages.append(f"Patch {patch_name} disabled via config")
            return
        result = func()
        state.patches_enabled[patch_name] = result
        if result:
            log_messages.append(f"Patch {patch_name} enabled")
        else:
            log_messages.append(f"Patch {patch_name} skipped (version incompatible)")

    _apply_patch(
        config.enable_camera_patch, patches.PATCH_CAMERA, patches.enable_camera_patch
    )
    _apply_patch(
        config.enable_sink_patch and config.enable_buffer_sink_patch,
        patches.PATCH_BUFFER_SINK,
        patches.enable_buffer_sink_patch,
    )
    _apply_patch(
        config.enable_sink_patch and config.enable_video_sink_patch,
        patches.PATCH_VIDEO_SINK,
        patches.enable_video_sink_patch,
    )
    _apply_patch(
        config.enable_sink_patch and config.enable_metric_sink_patch,
        patches.PATCH_METRIC_SINK,
        patches.enable_metric_sink_patch,
    )
    _apply_patch(
        config.enable_stream_manager_patch,
        patches.PATCH_STREAM_MANAGER,
        patches.enable_stream_manager_patch,
    )
    _apply_patch(config.enable_webrtc, patches.PATCH_WEBRTC, patches.enable_webrtc_patch)
    _apply_patch(config.enable_plugins, patches.PATCH_PLUGINS, patches.enable_plugins_patch)

    discovered_adapters = []
    if config.auto_discover_backends:
        discovered_adapters = backends.discover_entry_point_adapters()
        if discovered_adapters:
            log_messages.append(
                f"Discovered backend adapters via entry points: {discovered_adapters}"
            )

    imported_modules = backends.import_backend_modules(config.backend_entry_modules)
    if imported_modules:
        log_messages.append(
            f"Imported backend adapter modules: {imported_modules}"
        )

    activated_backends = backends.activate_backends(platform, config)
    state.backends_enabled = activated_backends
    if activated_backends:
        log_messages.append(f"Activated backends: {activated_backends}")

    plugin_statuses = {}
    if config.enable_plugins:
        plugin_statuses = runtime_plugins.load_runtime_plugins(
            config, get_inference_version_tuple()
        )
        state.plugins_loaded = plugin_statuses
        if plugin_statuses:
            log_messages.append(f"Loaded plugins: {plugin_statuses}")


    context = RuntimeContext(
        config=config,
        state=state,
        inference_version=inference_version,
        log_messages=log_messages,
    )
    _CURRENT_CONTEXT = context
    logger.info(f'{context.log_messages}')
    return context


def get_current_context() -> Optional[RuntimeContext]:
    return _CURRENT_CONTEXT


def reset_runtime():  # pragma: no cover - testing utility
    global _CURRENT_CONTEXT
    _CURRENT_CONTEXT = None
