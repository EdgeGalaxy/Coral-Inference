import asyncio
import os

from inference.core.interfaces.http.http_api import HttpInterface
from inference.core.env import MODEL_CACHE_DIR
from inference.core.managers.base import ModelManager
from inference.core.managers.decorators.fixed_size_cache import WithFixedSizeCache
from inference.core.registries.roboflow import (
    RoboflowModelRegistry,
)

from inference.core.env import (
    MAX_ACTIVE_MODELS,
)
from inference.models.utils import ROBOFLOW_MODEL_TYPES

from coral_inference.core import runtime_platform
from coral_inference.core.managers.patch_pingback import get_influxdb_metrics
from loguru import logger

from core.route import init_app


model_registry = RoboflowModelRegistry(ROBOFLOW_MODEL_TYPES)

model_manager = ModelManager(model_registry=model_registry)

model_manager = WithFixedSizeCache(model_manager, max_size=MAX_ACTIVE_MODELS)
model_manager.init_pingback()
model_manager.pingback.environment_info.update(get_influxdb_metrics())
interface = HttpInterface(model_manager)

app = interface.app
stream_manager_client = interface.stream_manager_client
pipeline_cache = init_app(app, stream_manager_client)

logger.info(f"runtime_platform is {runtime_platform}")
