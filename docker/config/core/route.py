import asyncio
import os
import time
import base64
from typing import List, Dict, Optional, Union
from datetime import datetime

import cv2
import numpy as np
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
from inference.core.interfaces.stream_manager.manager_app.entities import WebRTCOffer

from coral_inference.core.inference.camera.webrtc_manager import (
    WebRTCConnectionConfig,
    create_webrtc_connection_standalone,
)

from coral_inference.core.inference.stream_manager.entities import PatchInitialiseWebRTCPipelinePayload
from coral_inference.core.inference.camera.patch_video_source import PatchedCV2VideoFrameProducer

from core.pipeline_cache import PipelineCache
from core.pipeline_middleware import HookPipelineMiddleware
from core.monitor import setup_monitor, PipelineMonitor



class MetricsResponse(BaseModel):
    dates: List[str]
    datasets: List[Dict]


class VideoCaptureRequest(BaseModel):
    video_source: Union[str, int] = 0  # 视频源，可以是摄像头ID或视频文件路径
    api_key: str = None

class VideoCaptureResponse(BaseModel):
    status: str
    image_base64: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    error: Optional[str] = None


class WebRTCStreamRequest(BaseModel):
    video_source: Union[str, int] = 0  # 视频源，可以是摄像头ID或视频文件路径
    webrtc_offer: Dict  # WebRTC offer信息
    fps: Optional[float] = 30  # 视频帧率
    processing_timeout: Optional[float] = 0.1
    max_consecutive_timeouts: Optional[int] = 30
    min_consecutive_on_time: Optional[int] = 5


class WebRTCStreamResponse(BaseModel):
    status: str
    sdp: Optional[str] = None
    type: Optional[str] = None
    error: Optional[str] = None


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

    @app.post(
        "/inference_pipelines/{pipeline_id}/offer",
        response_model=InitializeWebRTCPipelineResponse,
        summary="[EXPERIMENTAL] Offer Pipeline Stream",
        description="[EXPERIMENTAL] Offer Pipeline Stream",
    )
    @with_route_exceptions
    async def initialize_offer(pipeline_id: str, request: PatchInitialiseWebRTCPipelinePayload) -> CommandResponse:
        pipeline_id = pipeline_cache.get(pipeline_id)['restore_pipeline_id']
        if pipeline_id is None:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return await stream_manager_client.offer(pipeline_id=pipeline_id, offer_request=request)

    @app.get(
        "/inference_pipelines/{pipeline_id}/info",
        summary="获取Pipeline信息",
        description="获取指定Pipeline的详细信息，包括参数配置"
    )
    @with_route_exceptions
    async def get_pipeline_info(pipeline_id: str):
        """获取Pipeline信息"""
        try:
            pipeline_info = pipeline_cache.get(pipeline_id)
            if pipeline_info is None:
                raise HTTPException(status_code=404, detail="Pipeline not found")
            
            return {
                "status": "success",
                "data": {
                    "pipeline_id": pipeline_id,
                    "restore_pipeline_id": pipeline_info["restore_pipeline_id"],
                    "parameters": pipeline_info["parameters"]
                }
            }
        except Exception as e:
            logger.error(f"获取Pipeline信息时出错: {e}")
            raise HTTPException(status_code=500, detail=f"获取Pipeline信息失败: {str(e)}")

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

    @app.post(
        "/monitor/flush-cache",
        summary="手动刷新监控器缓存",
        description="手动将监控器缓存中的数据刷新到文件系统"
    )
    @with_route_exceptions
    async def flush_monitor_cache(monitor: PipelineMonitor = Depends(get_monitor)):
        """手动刷新监控器缓存"""
        try:
            await monitor.flush_cache()
            return {"status": "success", "message": "缓存数据已成功刷新到文件"}
        except Exception as e:
            logger.error(f"手动刷新缓存时出错: {e}")
            raise HTTPException(status_code=500, detail=f"刷新缓存失败: {str(e)}")

    @app.get(
        "/monitor/status",
        summary="获取监控器状态",
        description="获取当前监控器的运行状态"
    )
    @with_route_exceptions
    async def get_monitor_status(monitor: PipelineMonitor = Depends(get_monitor)):
        """获取监控器状态"""
        try:
            return {
                "status": "success",
                "data": {
                    "running": monitor.running,
                    "output_dir": str(monitor.output_dir),
                    "poll_interval": monitor.poll_interval,
                    "pipeline_count": len(monitor.pipeline_ids_mapper),
                    "cached_metrics_count": sum(len(metrics) for metrics in monitor.metrics_collector.metrics_cache.values()),
                    "cached_results_count": sum(len(results) for results in monitor.results_collector.results_cache.values())
                }
            }
        except Exception as e:
            logger.error(f"获取监控器状态时出错: {e}")
            raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

    @app.get(
        "/monitor/disk-usage",
        summary="获取磁盘使用状态",
        description="获取当前监控器的磁盘使用情况"
    )
    @with_route_exceptions
    async def get_disk_usage(monitor: PipelineMonitor = Depends(get_monitor)):
        """获取磁盘使用状态"""
        try:
            disk_info = await monitor.cleanup_manager.get_disk_usage_info()
            return {
                "status": "success",
                "data": disk_info
            }
        except Exception as e:
            logger.error(f"获取磁盘使用状态时出错: {e}")
            raise HTTPException(status_code=500, detail=f"获取磁盘使用状态失败: {str(e)}")

    @app.post(
        "/monitor/cleanup",
        summary="手动触发磁盘清理",
        description="手动触发磁盘清理，根据磁盘使用情况删除旧的结果文件"
    )
    @with_route_exceptions
    async def trigger_cleanup(monitor: PipelineMonitor = Depends(get_monitor)):
        """手动触发磁盘清理"""
        try:
            await monitor.cleanup_manager.check_disk_usage_and_cleanup()
            return {"status": "success", "message": "磁盘清理已完成"}
        except Exception as e:
            logger.error(f"手动触发磁盘清理时出错: {e}")
            raise HTTPException(status_code=500, detail=f"磁盘清理失败: {str(e)}")

    @app.post(
        "/inference_pipelines/video/capture",
        response_model=VideoCaptureResponse,
        summary="获取视频帧并返回base64图片",
        description="从指定的视频源读取一帧并返回base64编码的图片"
    )
    @with_route_exceptions
    async def capture_video_frame(request: VideoCaptureRequest) -> VideoCaptureResponse:
        """获取视频帧并返回base64格式的图片"""
        video_producer = None
        try:
            logger.info(f"开始获取视频帧，视频源: {request.video_source}")
            
            # 创建视频帧生产者
            video_producer = PatchedCV2VideoFrameProducer(video=request.video_source)
            
            if not video_producer.isOpened():
                return VideoCaptureResponse(
                    status="error",
                    error=f"无法打开视频源: {request.video_source}"
                )
            
            # 获取视频帧
            success = video_producer.grab()
            if not success:
                return VideoCaptureResponse(
                    status="error", 
                    error="无法获取视频帧"
                )
            success, frame = video_producer.retrieve()
            if not success or frame is None:
                return VideoCaptureResponse(
                    status="error",
                    error="无法检索视频帧数据"
                )
            
            # 获取帧尺寸
            height, width = frame.shape[:2]
            
            # 将numpy数组编码为JPEG格式
            success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not success:
                return VideoCaptureResponse(
                    status="error",
                    error="无法编码图片为JPEG格式"
                )
            
            # 转换为base64
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            
            logger.info(f"成功获取视频帧，尺寸: {width}x{height}")
            
            return VideoCaptureResponse(
                status="success",
                image_base64=image_base64,
                width=width,
                height=height
            )
        finally:
            video_producer.release()

    @app.post(
        "/inference_pipelines/video/webrtc-stream",
        response_model=WebRTCStreamResponse,
        summary="创建视频流WebRTC连接",
        description="持续获取视频帧并通过WebRTC协议返回"
    )
    @with_route_exceptions
    async def create_webrtc_video_stream(request: WebRTCStreamRequest) -> WebRTCStreamResponse:
        """创建视频流WebRTC连接"""
        video_producer = None
        webrtc_manager = None
        try:
            logger.info(f"开始创建WebRTC视频流，视频源: {request.video_source}")
            
            # 验证WebRTC offer格式
            if "type" not in request.webrtc_offer or "sdp" not in request.webrtc_offer:
                return WebRTCStreamResponse(
                    status="error",
                    error="WebRTC offer格式错误，必须包含type和sdp字段"
                )
            
            # 创建视频帧生产者并验证
            video_producer = PatchedCV2VideoFrameProducer(video=request.video_source)
            
            if not video_producer.isOpened():
                return WebRTCStreamResponse(
                    status="error",
                    error=f"无法打开视频源: {request.video_source}"
                )
            
            webrtc_offer = WebRTCOffer(
                type=request.webrtc_offer["type"],
                sdp=request.webrtc_offer["sdp"]
            )
            
            # 创建WebRTC连接配置
            config = WebRTCConnectionConfig(
                webrtc_offer=webrtc_offer,
                webcam_fps=request.fps,
                processing_timeout=request.processing_timeout,
                max_consecutive_timeouts=request.max_consecutive_timeouts,
                min_consecutive_on_time=request.min_consecutive_on_time
            )
            
            # 使用WebRTCManager创建独立连接
            result, webrtc_manager = create_webrtc_connection_standalone(config)
            
            if not result.success:
                return WebRTCStreamResponse(
                    status="error",
                    error=f"创建WebRTC连接失败: {result.error}"
                )
            
            # 获取队列和停止事件
            from_inference_queue = webrtc_manager.get_inference_queue()
            feedback_stop_event = webrtc_manager.get_stop_event()
            
            if not from_inference_queue or not feedback_stop_event:
                raise HTTPException(status_code=500, detail="获取WebRTC队列或事件失败")
            
            # 启动视频帧获取任务
            async def video_frame_producer_task():
                """持续获取视频帧并放入队列"""
                try:
                    frame_count = 0
                    while not feedback_stop_event.is_set():
                        success = video_producer.grab()
                        if not success:
                            logger.warning("无法获取视频帧，停止生产")
                            break
                        
                        success, frame = video_producer.retrieve()
                        if success and frame is not None:
                            # 确保传递的是numpy数组（BGR格式）
                            if isinstance(frame, np.ndarray):
                                await from_inference_queue.async_put(frame)
                                frame_count += 1
                                if frame_count % 30 == 0:  # 每30帧记录一次
                                    logger.debug(f"已生产 {frame_count} 帧")
                        
                        # 控制帧率
                        if request.fps > 0:
                            await asyncio.sleep(1.0 / request.fps)
                        else:
                            await asyncio.sleep(1.0 / 60)  # 默认60fps

                except Exception as e:
                    logger.error(f"视频帧生产出错: {e}")
                finally:
                    try:
                        video_producer.release()
                        webrtc_manager.cleanup()
                    except:
                        pass
            
            # 在WebRTC Manager的事件循环中启动视频帧生产任务
            if webrtc_manager.loop:
                asyncio.run_coroutine_threadsafe(
                    video_frame_producer_task(),
                    webrtc_manager.loop
                )

            logger.info("WebRTC连接创建成功")
            
            return WebRTCStreamResponse(
                status="success",
                sdp=result.sdp,
                type=result.type
            )
            
        except Exception as e:
            logger.error(f"创建WebRTC视频流时出错: {e}")
            # 确保清理资源
            if video_producer:
                try:
                    video_producer.release()
                except:
                    pass
            if webrtc_manager:
                try:
                    webrtc_manager.cleanup()
                except:
                    pass
            raise HTTPException(status_code=500, detail=f"创建WebRTC视频流失败: {str(e)}")

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

