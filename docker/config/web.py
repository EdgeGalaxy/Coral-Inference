import asyncio

from inference.core.interfaces.http.http_api import HttpInterface
from inference.core.managers.base import ModelManager
from inference.core.managers.decorators.fixed_size_cache import WithFixedSizeCache
from inference.core.registries.roboflow import (
    RoboflowModelRegistry,
)

from inference.core.env import (
    MAX_ACTIVE_MODELS,
)
from inference.models.utils import ROBOFLOW_MODEL_TYPES

from coral_inference.core import runtime_platform, logger as inference_logger
from loguru import logger

from route import init_app


model_registry = RoboflowModelRegistry(ROBOFLOW_MODEL_TYPES)

model_manager = ModelManager(model_registry=model_registry)

model_manager = WithFixedSizeCache(model_manager, max_size=MAX_ACTIVE_MODELS)
model_manager.init_pingback()
interface = HttpInterface(model_manager)

app = interface.app
stream_manager_client = interface.stream_manager_client
pipeline_cache = init_app(app, stream_manager_client)

@app.on_event("startup")
async def delayed_restore():
    while True:
        try:
            pipelines = await stream_manager_client.list_pipelines()
        except Exception as e:
            await asyncio.sleep(2)
            logger.error(f"Error call list pipelines: {e}")
        else:
            logger.info(f'fetch pipelines data: {pipelines} & start restore pipeline cache!')
            await pipeline_cache.restore()
            break

logger.info(f"runtime_platform is {runtime_platform}")
