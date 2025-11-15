import asyncio
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger


from inference.core.interfaces.stream_manager.api.stream_manager_client import (
    StreamManagerClient,
)
from inference.core.env import MODEL_CACHE_DIR
from coral_inference.webapp import load_webapp_config
from coral_inference.webapp.services import HealthService
from coral_inference.runtime import get_current_context

from .cache import PipelineCache
from .pipeline.pipeline_utils import (
    download_videos_parallel,
    cleanup_pipeline_videos,
)
from .routing_utils import (
    remove_app_root_mount,
    remove_existing_inference_pipeline_routes,
)
from .stream.video_stream_routes import register_video_stream_routes
from .pipeline.pipeline_routes import register_pipeline_routes
from .monitor.monitor_routes import register_monitor_routes
from .monitor.monitor_optimized_influxdb import setup_optimized_monitor_with_influxdb
from coral_inference.webapp import PipelineService, StreamService, MonitorService


def init_app(app: FastAPI, stream_manager_client: StreamManagerClient):
    remove_app_root_mount(app)
    remove_existing_inference_pipeline_routes(app)

    pipeline_cache = PipelineCache(stream_manager_client=stream_manager_client)
    runtime_context = get_current_context()
    services_config = {}
    if runtime_context and runtime_context.config and runtime_context.config.services:
        services_config = runtime_context.config.services.get("webapp", {}) or {}
    webapp_config = load_webapp_config(config_data=services_config)
    app.state.webapp_config = webapp_config
    health_service = HealthService()
    app.state.health_service = health_service
    pipeline_service = PipelineService(
        stream_manager_client,
        cache_create=pipeline_cache.create,
        cache_terminate=pipeline_cache.terminate,
        pipeline_cache=pipeline_cache,
        video_downloader=download_videos_parallel,
        video_cleanup=cleanup_pipeline_videos,
    )
    stream_service = StreamService(stream_manager_client)
    app.state.pipeline_service = pipeline_service
    app.state.stream_service = stream_service
    try:
        health_service.register_check("stream_manager", stream_service.health)
        health_service.register_check(
            "pipeline_cache",
            lambda: (True, {"cached": len(pipeline_service.cached())}),
        )
    except Exception:
        logger.exception("failed to register base health checks")

    @app.get("/config.json")
    async def get_webapp_config():
        return JSONResponse(webapp_config.to_dict())

    @app.get("/healthz")
    async def healthz():
        status = await health_service.liveness()
        return JSONResponse(
            {
                "status": "ok" if status.healthy else "error",
                "checks": status.details.get("checks", {}),
                "timestamp": status.details.get("timestamp"),
            },
            status_code=200 if status.healthy else 503,
        )

    @app.get("/readyz")
    async def readyz():
        status = await health_service.readiness()
        return JSONResponse(
            {
                "status": "ok" if status.healthy else "error",
                "checks": status.details.get("checks", {}),
                "timestamp": status.details.get("timestamp"),
            },
            status_code=200 if status.healthy else 503,
        )

    @app.on_event("startup")
    async def delayed_restore():
        while True:
            try:
                pipelines = await stream_manager_client.list_pipelines()
            except Exception as e:
                await asyncio.sleep(2)
                logger.error(f"Error call list pipelines: {e}")
            else:
                logger.info(
                    f"fetch pipelines data: {pipelines} & start restore pipeline cache!"
                )
                await pipeline_cache.restore()

                # 启动pipeline结果监控 - 使用新的优化监控器
                await start_monitor_with_pipelines()
                break

    async def start_monitor_with_pipelines():
        """启动带有 pipeline 支持的监控器"""
        await _start_monitor(stream_manager_client, pipeline_cache)

    async def _start_monitor(sm_client, p_cache):
        """内部监控器启动函数"""
        poll_interval = float(os.environ.get("PIPELINE_MONITOR_INTERVAL", "0.1"))
        output_dir = os.environ.get(
            "PIPELINE_RESULTS_DIR", f"{MODEL_CACHE_DIR}/pipelines"
        )
        max_days = int(os.environ.get("PIPELINE_RESULTS_MAX_DAYS", "7"))
        cleanup_interval = float(os.environ.get("PIPELINE_CLEANUP_INTERVAL", "3600"))

        # 状态监控配置
        status_interval = float(
            os.environ.get("PIPELINE_STATUS_INTERVAL", "5")
        )  # 调整默认为5秒

        # 结果缓存配置
        results_batch_size = int(
            os.environ.get("PIPELINE_RESULTS_BATCH_SIZE", "100")
        )  # 调整默认批量大小
        results_flush_interval = float(
            os.environ.get("PIPELINE_RESULTS_FLUSH_INTERVAL", "30")
        )

        # 磁盘使用监控配置
        max_size_gb = float(os.environ.get("PIPELINE_MAX_SIZE_GB", "10"))
        size_check_interval = float(
            os.environ.get("PIPELINE_SIZE_CHECK_INTERVAL", "300")
        )

        # 后台工作线程配置
        max_background_workers = int(
            os.environ.get("PIPELINE_MAX_BACKGROUND_WORKERS", "5")
        )

        # InfluxDB 配置
        enable_influxdb = os.environ.get("ENABLE_INFLUXDB", "true").lower() == "true"
        influxdb_url = os.getenv("INFLUXDB_METRICS_URL", "")
        influxdb_token = os.getenv("INFLUXDB_METRICS_TOKEN", "")
        influxdb_database = os.getenv("INFLUXDB_METRICS_DATABASE", "")
        metrics_batch_size = int(os.environ.get("METRICS_BATCH_SIZE", "100"))
        metrics_flush_interval = float(os.environ.get("METRICS_FLUSH_INTERVAL", "10"))

        # 使用新的优化监控器
        monitor = setup_optimized_monitor_with_influxdb(
            stream_manager_client=sm_client,
            pipeline_cache=p_cache,
            poll_interval=poll_interval,
            output_dir=output_dir,
            max_days=max_days,
            cleanup_interval=cleanup_interval,
            status_interval=status_interval,
            results_batch_size=results_batch_size,
            results_flush_interval=results_flush_interval,
            max_size_gb=max_size_gb,
            size_check_interval=size_check_interval,
            max_background_workers=max_background_workers,
            # InfluxDB 配置（通过环境变量获取）
            enable_influxdb=enable_influxdb,
            metrics_batch_size=metrics_batch_size,
            metrics_flush_interval=metrics_flush_interval,
            auto_start=True,  # 自动启动
            influxdb_url=influxdb_url,
            influxdb_token=influxdb_token,
            influxdb_database=influxdb_database,
        )

        app.state.monitor = monitor
        app.state.monitor_service = MonitorService(monitor)
        try:
            health_service.register_check(
                "monitor",
                app.state.monitor_service.health,
            )
        except Exception:
            pass

    @app.on_event("shutdown")
    async def shutdown_event():
        """应用程序关闭时的清理工作"""
        logger.info("应用程序正在关闭，开始清理资源...")

        # 停止监控器并刷新缓存
        if hasattr(app.state, "monitor") and app.state.monitor:
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
        allow_origins="*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    os.makedirs(f"{MODEL_CACHE_DIR}/pipelines", exist_ok=True)

    app.mount(
        "/mount/pipelines",
        StaticFiles(directory=f"{MODEL_CACHE_DIR}/pipelines", html=True),
        name="coral_pipeline_root",
    )

    os.makedirs("inference/landing/out", exist_ok=True)

    app.mount(
        "/",
        StaticFiles(directory="./inference/landing/out", html=True),
        name="coral_root",
    )

    return pipeline_cache
