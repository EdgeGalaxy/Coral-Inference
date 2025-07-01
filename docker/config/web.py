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
from loguru import logger

from route import init_app
from monitor import setup_monitor


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
            
            # 启动pipeline结果监控
            poll_interval = float(os.environ.get("PIPELINE_MONITOR_INTERVAL", "0.1"))
            output_dir = os.environ.get("PIPELINE_RESULTS_DIR", f"{MODEL_CACHE_DIR}/pipeline_results")
            max_days = int(os.environ.get("PIPELINE_RESULTS_MAX_DAYS", "7"))
            cleanup_interval = float(os.environ.get("PIPELINE_CLEANUP_INTERVAL", "3600"))
            
            # 状态监控配置
            status_interval = float(os.environ.get("PIPELINE_STATUS_INTERVAL", "5"))
            status_cache_size = int(os.environ.get("PIPELINE_STATUS_CACHE_SIZE", "100"))
            
            logger.info(f"设置pipeline监控: 轮询间隔={poll_interval}秒, 输出目录={output_dir}")
            logger.info(f"设置自动清理: 保留天数={max_days}, 清理间隔={cleanup_interval}秒")
            logger.info(f"设置状态监控: 检查间隔={status_interval}秒, 缓存大小={status_cache_size}")
            
            await setup_monitor(
                stream_manager_client,
                pipeline_cache,
                poll_interval,
                output_dir,
                max_days,
                cleanup_interval,
                status_interval,
                status_cache_size
            )
            
            break

logger.info(f"runtime_platform is {runtime_platform}")
