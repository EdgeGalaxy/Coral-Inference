import asyncio
import os

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger


from inference.core.interfaces.stream_manager.api.stream_manager_client import (
    StreamManagerClient
)
from inference.core.env import MODEL_CACHE_DIR

from core.pipeline_cache import PipelineCache
from core.monitor import setup_monitor, PipelineMonitor
from core.routing_utils import remove_app_root_mount, remove_existing_inference_pipeline_routes
from core.video_stream_routes import register_video_stream_routes
from core.pipeline_routes import register_pipeline_routes
from core.monitor_routes import register_monitor_routes


def init_app(app: FastAPI, stream_manager_client: StreamManagerClient):
    remove_app_root_mount(app)
    remove_existing_inference_pipeline_routes(app)

    pipeline_cache = PipelineCache(stream_manager_client=stream_manager_client)

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
                output_dir = os.environ.get("PIPELINE_RESULTS_DIR", f"{MODEL_CACHE_DIR}/pipelines")
                max_days = int(os.environ.get("PIPELINE_RESULTS_MAX_DAYS", "7"))
                cleanup_interval = float(os.environ.get("PIPELINE_CLEANUP_INTERVAL", "3600"))
                
                # 状态监控配置
                status_interval = float(os.environ.get("PIPELINE_STATUS_INTERVAL", "1"))
                save_interval_minutes = int(os.environ.get("PIPELINE_SAVE_INTERVAL_MINUTES", "5"))

                # 结果缓存配置
                results_batch_size = int(os.environ.get("PIPELINE_RESULTS_BATCH_SIZE", "10"))
                results_flush_interval = float(os.environ.get("PIPELINE_RESULTS_FLUSH_INTERVAL", "30"))
                
                # 磁盘使用监控配置
                max_size_gb = float(os.environ.get("PIPELINE_MAX_SIZE_GB", "10"))
                size_check_interval = float(os.environ.get("PIPELINE_SIZE_CHECK_INTERVAL", "300"))

                monitor = await setup_monitor(
                    stream_manager_client,
                    pipeline_cache,
                    poll_interval,
                    output_dir,
                    max_days,
                    cleanup_interval,
                    status_interval,
                    save_interval_minutes,
                    results_batch_size,
                    results_flush_interval,
                    max_size_gb,
                    size_check_interval
                )

                app.state.monitor = monitor
                break

    @app.on_event("shutdown")
    async def shutdown_event():
        """应用程序关闭时的清理工作"""
        logger.info("应用程序正在关闭，开始清理资源...")
        
        # 停止监控器并刷新缓存
        if hasattr(app.state, 'monitor') and app.state.monitor:
            try:
                await app.state.monitor.stop_async()
                logger.info("监控器已成功停止并刷新缓存")
            except Exception as e:
                logger.error(f"停止监控器时发生错误: {e}")
        
        logger.info("应用程序清理完成")

    register_pipeline_routes(app, stream_manager_client, pipeline_cache)

    register_monitor_routes(app)

    register_video_stream_routes(app, stream_manager_client, pipeline_cache)

    app.add_middleware(
        CORSMiddleware,
        allow_origins='*',
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )   

    app.mount(
        "/",
        StaticFiles(directory="./inference/landing/out", html=True),
        name="coral_root",
    )

    return pipeline_cache

