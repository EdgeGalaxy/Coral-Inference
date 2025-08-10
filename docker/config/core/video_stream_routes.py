import asyncio
import base64
from typing import Dict, Optional, Union

import numpy as np
import cv2
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from pydantic import BaseModel

from inference.core.interfaces.http.http_api import with_route_exceptions
from inference.core.interfaces.stream_manager.api.entities import (
    CommandResponse,
    InitializeWebRTCPipelineResponse,
)
from inference.core.interfaces.stream_manager.api.stream_manager_client import (
    StreamManagerClient,
)
from inference.core.interfaces.stream_manager.manager_app.entities import WebRTCOffer

from coral_inference.core.inference.camera.webrtc_manager import (
    WebRTCConnectionConfig,
    create_webrtc_connection_standalone,
)
from coral_inference.core.inference.stream_manager.entities import (
    PatchInitialiseWebRTCPipelinePayload,
)
from coral_inference.core.inference.camera.patch_video_source import (
    PatchedCV2VideoFrameProducer,
)
from loguru import logger
from core.pipeline_cache import PipelineCache


class VideoCaptureRequest(BaseModel):
    video_source: Union[str, int] = 0
    api_key: str | None = None


class VideoCaptureResponse(BaseModel):
    status: str
    image_base64: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    error: Optional[str] = None


class WebRTCStreamRequest(BaseModel):
    video_source: Union[str, int] = 0
    webrtc_offer: Dict
    fps: Optional[float] = 30
    processing_timeout: Optional[float] = 0.1
    max_consecutive_timeouts: Optional[int] = 30
    min_consecutive_on_time: Optional[int] = 5


class WebRTCStreamResponse(BaseModel):
    status: str
    sdp: Optional[str] = None
    type: Optional[str] = None
    error: Optional[str] = None


def register_video_stream_routes(
    app: FastAPI,
    stream_manager_client: StreamManagerClient,
    pipeline_cache: PipelineCache,
) -> None:
    @app.post(
        "/inference_pipelines/{pipeline_id}/offer",
        response_model=InitializeWebRTCPipelineResponse,
        summary="[EXPERIMENTAL] Offer Pipeline Stream",
        description="[EXPERIMENTAL] Offer Pipeline Stream",
    )
    @with_route_exceptions
    async def initialize_offer(
        pipeline_id: str, request: PatchInitialiseWebRTCPipelinePayload
    ) -> CommandResponse:
        mapped = pipeline_cache.get(pipeline_id)
        real_id = mapped["restore_pipeline_id"] if mapped else pipeline_id
        return await stream_manager_client.offer(
            pipeline_id=real_id, offer_request=request
        )

    @app.post(
        "/inference_pipelines/video/capture",
        response_model=VideoCaptureResponse,
        summary="获取视频帧并返回base64图片",
        description="从指定的视频源读取一帧并返回base64编码的图片",
    )
    @with_route_exceptions
    async def capture_video_frame(request: VideoCaptureRequest) -> VideoCaptureResponse:
        video_producer = None
        try:
            video_producer = PatchedCV2VideoFrameProducer(video=request.video_source)
            if not video_producer.isOpened():
                return VideoCaptureResponse(
                    status="error", error=f"无法打开视频源: {request.video_source}"
                )
            success = video_producer.grab()
            if not success:
                return VideoCaptureResponse(status="error", error="无法获取视频帧")
            success, frame = video_producer.retrieve()
            if not success or frame is None:
                return VideoCaptureResponse(status="error", error="无法检索视频帧数据")
            height, width = frame.shape[:2]
            success, buffer = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95]
            )
            if not success:
                return VideoCaptureResponse(status="error", error="无法编码图片为JPEG格式")
            image_base64 = base64.b64encode(buffer).decode("utf-8")
            return VideoCaptureResponse(
                status="success", image_base64=image_base64, width=width, height=height
            )
        finally:
            if video_producer:
                video_producer.release()

    @app.post(
        "/inference_pipelines/video/webrtc-stream",
        response_model=WebRTCStreamResponse,
        summary="创建视频流WebRTC连接",
        description="持续获取视频帧并通过WebRTC协议返回",
    )
    @with_route_exceptions
    async def create_webrtc_video_stream(
        request: WebRTCStreamRequest,
    ) -> WebRTCStreamResponse:
        video_producer = None
        webrtc_manager = None
        try:
            if "type" not in request.webrtc_offer or "sdp" not in request.webrtc_offer:
                return WebRTCStreamResponse(
                    status="error", error="WebRTC offer格式错误，必须包含type和sdp字段"
                )
            video_producer = PatchedCV2VideoFrameProducer(video=request.video_source)
            if not video_producer.isOpened():
                return WebRTCStreamResponse(
                    status="error", error=f"无法打开视频源: {request.video_source}"
                )
            webrtc_offer = WebRTCOffer(
                type=request.webrtc_offer["type"], sdp=request.webrtc_offer["sdp"]
            )
            config = WebRTCConnectionConfig(
                webrtc_offer=webrtc_offer,
                webcam_fps=request.fps,
                processing_timeout=request.processing_timeout,
                max_consecutive_timeouts=request.max_consecutive_timeouts,
                min_consecutive_on_time=request.min_consecutive_on_time,
            )
            result, webrtc_manager = create_webrtc_connection_standalone(config)
            if not result.success:
                return WebRTCStreamResponse(
                    status="error", error=f"创建WebRTC连接失败: {result.error}"
                )
            from_inference_queue = webrtc_manager.get_inference_queue()
            feedback_stop_event = webrtc_manager.get_stop_event()
            if not from_inference_queue or not feedback_stop_event:
                raise HTTPException(status_code=500, detail="获取WebRTC队列或事件失败")

            async def video_frame_producer_task():
                try:
                    while not feedback_stop_event.is_set():
                        success = video_producer.grab()
                        if not success:
                            break
                        success, frame = video_producer.retrieve()
                        if success and frame is not None:
                            if isinstance(frame, np.ndarray):
                                await from_inference_queue.async_put(frame)
                        if request.fps > 0:
                            await asyncio.sleep(1.0 / request.fps)
                        else:
                            await asyncio.sleep(1.0 / 60)
                finally:
                    try:
                        video_producer.release()
                        webrtc_manager.cleanup()
                    except Exception:
                        pass

            if webrtc_manager.loop:
                asyncio.run_coroutine_threadsafe(
                    video_frame_producer_task(), webrtc_manager.loop
                )
            return WebRTCStreamResponse(status="success", sdp=result.sdp, type=result.type)
        except Exception as e:
            if video_producer:
                try:
                    video_producer.release()
                except Exception:
                    pass
            if webrtc_manager:
                try:
                    webrtc_manager.cleanup()
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail=f"创建WebRTC视频流失败: {str(e)}")


