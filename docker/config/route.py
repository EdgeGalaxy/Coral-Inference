import asyncio
import os
import time
from typing import List, Dict, Optional
from datetime import datetime

from fastapi import FastAPI, Query, Depends, Request
from starlette.routing import Mount
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import HTTPException
from loguru import logger
from pydantic import BaseModel

from inference.core.interfaces.http.http_api import with_route_exceptions
from inference.core.interfaces.stream_manager.api.entities import (
    InitializeWebRTCPipelineResponse,
    CommandResponse
)
from inference.core.interfaces.stream_manager.api.stream_manager_client import (
    StreamManagerClient
)
from inference.core.env import MODEL_CACHE_DIR

from coral_inference.core.inference.stream_manager.entities import PatchInitialiseWebRTCPipelinePayload

from pipeline_cache import PipelineCache
from pipeline_middleware import HookPipelineMiddleware
from monitor import setup_monitor, PipelineMonitor



class MetricsResponse(BaseModel):
    dates: List[str]
    datasets: List[Dict]


def remove_app_root_mount(app: FastAPI):
    # 1. 找到并移除所有挂载在 "/" 上的旧路由
    # 我们从后往前遍历，这样删除元素不会影响后续的索引
    indices_to_remove = []
    for i, route in enumerate(app.routes):
        if isinstance(route, Mount) and route.path == '' and route.name == "root":
            indices_to_remove.append(i)
        if isinstance(route, Mount) and route.path == "/static" and route.name == "static":
            indices_to_remove.append(i)

    for i in sorted(indices_to_remove, reverse=True):
        app.routes.pop(i)


def get_monitor(request: Request):
    return request.app.state.monitor


def init_app(app: FastAPI, stream_manager_client: StreamManagerClient):
    remove_app_root_mount(app)

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

                monitor = await setup_monitor(
                    stream_manager_client,
                    pipeline_cache,
                    poll_interval,
                    output_dir,
                    max_days,
                    cleanup_interval,
                    status_interval,
                    save_interval_minutes
                )

                app.state.monitor = monitor
                break

    @app.post(
        "/inference_pipelines/{pipeline_id}/offer",
        response_model=InitializeWebRTCPipelineResponse,
        summary="[EXPERIMENTAL] Offer Pipeline Stream",
        description="[EXPERIMENTAL] Offer Pipeline Stream",
    )
    @with_route_exceptions
    async def initialize_offer(pipeline_id: str, request: PatchInitialiseWebRTCPipelinePayload) -> CommandResponse:
        pipeline_id = pipeline_cache.get(pipeline_id)
        if pipeline_id is None:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return await stream_manager_client.offer(pipeline_id=pipeline_id, offer_request=request)

    @app.get(
        "/inference_pipelines/{pipeline_id}/metrics",
        response_model=MetricsResponse,
        summary="获取Pipeline指标数据",
        description="获取指定时间范围内的Pipeline指标数据，用于图表展示"
    )
    @with_route_exceptions
    async def get_pipeline_metrics(
        pipeline_id: str,
        start_time: Optional[float] = Query(None, description="开始时间戳（秒）"),
        end_time: Optional[float] = Query(None, description="结束时间戳（秒）"),
        minutes: Optional[int] = Query(5, description="最近几分钟的数据，当start_time和end_time为空时使用"),
        monitor: PipelineMonitor = Depends(get_monitor)
    ) -> MetricsResponse:
        try:
            # 如果没有指定时间范围，使用最近minutes分钟
            if start_time is None or end_time is None:
                end_time = time.time()
                start_time = end_time - (minutes * 60)

            # 获取原始指标数据
            metrics = await monitor.get_metrics_by_timerange(
                pipeline_id, start_time, end_time
            )
            logger.info(f'metrics: {metrics}')

            # 转换数据格式为图表所需格式
            dates = []
            throughput_data = []
            source_states = {}

            for metric in metrics:
                # 转换时间戳为可读格式
                date_str = datetime.fromtimestamp(metric["timestamp"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
                dates.append(date_str)
                
                # 收集吞吐量数据
                throughput_data.append(metric["throughput"])
                
                # 收集每个源的延迟数据和状态
                for source in metric["sources"]:
                    source_id = source["source_id"]
                    if source_id not in source_states:
                        source_states[source_id] = {
                            "frame_decoding_latency": [],
                            "inference_latency": [],
                            "e2e_latency": [],
                            "states": []
                        }
                    
                    # 添加延迟数据
                    frame_decoding_latency = source.get("frame_decoding_latency", 0)
                    inference_latency = source.get("inference_latency", 0)
                    e2e_latency = source.get("e2e_latency", 0)
                    source_states[source_id]["frame_decoding_latency"].append(frame_decoding_latency)
                    source_states[source_id]["inference_latency"].append(inference_latency)
                    source_states[source_id]["e2e_latency"].append(e2e_latency)
                    
                    # 添加状态数据
                    state = source.get("state", "unknown")
                    source_states[source_id]["states"].append(state)

            # 构建数据集
            datasets = [
                {
                    "name": "Throughput",
                    "data": throughput_data
                }
            ]

            # 为每个源添加延迟数据集
            for source_id, data in source_states.items():
                datasets.append({
                    "name": f"Frame Decoding Latency ({source_id})",
                    "data": data["frame_decoding_latency"]
                })
                datasets.append({
                    "name": f"Inference Latency ({source_id})",
                    "data": data["inference_latency"]
                })
                datasets.append({
                    "name": f"E2E Latency ({source_id})",
                    "data": data["e2e_latency"]
                })
                datasets.append({
                    "name": f"State ({source_id})",
                    "data": data["states"]
                })

            return MetricsResponse(
                dates=dates,
                datasets=datasets
            )

        except Exception as e:
            logger.error(f"获取Pipeline指标数据时出错: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    app.add_middleware(HookPipelineMiddleware, pipeline_cache=pipeline_cache)

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


class MetricsResponse(BaseModel):
    dates: List[str]
    datasets: List[Dict]

