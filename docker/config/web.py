import asyncio
from multiprocessing import Process

from inference.core.interfaces.http.http_api import HttpInterface
from inference.core.managers.base import ModelManager
from inference.core.managers.decorators.fixed_size_cache import WithFixedSizeCache
from inference.core.registries.roboflow import (
    RoboflowModelRegistry,
)

from inference.core.env import (
    MAX_ACTIVE_MODELS,
    ENABLE_STREAM_API,
)
from inference.models.utils import ROBOFLOW_MODEL_TYPES

from coral_inference.core import runtime_platform, logger

from route import init_app


model_registry = RoboflowModelRegistry(ROBOFLOW_MODEL_TYPES)

model_manager = ModelManager(model_registry=model_registry)

model_manager = WithFixedSizeCache(model_manager, max_size=MAX_ACTIVE_MODELS)
model_manager.init_pingback()
interface = HttpInterface(model_manager)

app = interface.app
stream_manager_client = interface.stream_manager_client
pipeline_cache = init_app(app, stream_manager_client)


async def delayed_restore():
    await asyncio.sleep(8)
    print('start restore pipeline cache!')
    await pipeline_cache.restore()


# if ENABLE_STREAM_API:
    # stream_manager_process = Process(
    #     target=start,
    # )
    # stream_manager_process.start()
    # 延迟恢复pipeline
    # asyncio.create_task(delayed_restore())


logger.info(f"runtime_platform is {runtime_platform}")
