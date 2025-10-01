import asyncio
import threading
from typing import Dict, Callable, Optional, Any
from threading import Event
from collections import deque

import numpy as np
from loguru import logger
from pydantic import BaseModel

from inference.core.interfaces.camera.entities import VideoFrame
from inference.core.interfaces.stream.sinks import render_statistics
from inference.core.interfaces.stream_manager.manager_app.entities import (
    WebRTCOffer,
    WebRTCTURNConfig,
)
from inference.core.utils.async_utils import Queue as SyncAsyncQueue
from inference.core.workflows.execution_engine.entities.base import WorkflowImageData

from coral_inference.core.inference.stream_manager.webrtc import (
    RTCPeerConnectionWithFPS,
    init_rtc_peer_connection,
)
from coral_inference.core.utils.image_utils import merge_frames


class WebRTCConnectionConfig(BaseModel):
    """WebRTC连接配置参数"""

    webrtc_offer: WebRTCOffer
    webrtc_turn_config: Optional[WebRTCTURNConfig] = None
    webcam_fps: Optional[float] = 30
    processing_timeout: float = 0.1
    max_consecutive_timeouts: int = 30
    min_consecutive_on_time: int = 5
    stream_output: Optional[list] = None


class WebRTCConnectionResult(BaseModel):
    """WebRTC连接结果"""

    success: bool
    sdp: Optional[str] = None
    type: Optional[str] = None
    error: Optional[str] = None
    peer_connection: Optional[Any] = None

    class Config:
        arbitrary_types_allowed = True


class WebRTCManager:
    """WebRTC连接管理器，提供统一的WebRTC连接创建和管理功能"""

    def __init__(self):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.from_inference_queue: Optional[SyncAsyncQueue] = None
        self.stop_event: Optional[Event] = None
        self.peer_connection: Optional[RTCPeerConnectionWithFPS] = None

    def _start_event_loop(self, loop: asyncio.AbstractEventLoop):
        """启动异步事件循环"""
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def _create_video_frame_processor(
        self, config: WebRTCConnectionConfig
    ) -> Callable[[Dict[str, WorkflowImageData], VideoFrame], np.ndarray]:
        """创建视频帧处理函数，参考patch_pipeline_manager.py的实现"""

        def get_video_frame(
            prediction: Dict[str, WorkflowImageData], video_frame: VideoFrame
        ) -> np.ndarray:
            if (
                not any(isinstance(v, WorkflowImageData) for v in prediction.values())
                or not config.stream_output
            ):
                result_frame = render_statistics(
                    video_frame.image.copy(), video_frame.frame_timestamp, fps=None
                )
                return result_frame

            if config.stream_output[0] not in prediction or not isinstance(
                prediction[config.stream_output[0]], WorkflowImageData
            ):
                for output in prediction.values():
                    if isinstance(output, WorkflowImageData):
                        return render_statistics(
                            output.numpy_image, video_frame.frame_timestamp, fps=None
                        )

            return render_statistics(
                prediction[config.stream_output[0]].numpy_image,
                video_frame.frame_timestamp,
                fps=None,
            )

        return get_video_frame

    async def _process_video_frames(
        self, webrtc_buffer: deque, video_frame_func: Callable
    ):
        """处理视频帧，参考patch_pipeline_manager.py的实现"""
        while not self.stop_event.is_set():
            try:
                if not webrtc_buffer:
                    await asyncio.sleep(1 / 60)
                    continue

                predictions, frames = webrtc_buffer.popleft()
                predictions = (
                    predictions if isinstance(predictions, list) else [predictions]
                )
                frames = frames if isinstance(frames, list) else [frames]
                show_frames = {
                    frame.source_id: video_frame_func(prediction, frame)
                    for prediction, frame in zip(predictions, frames)
                    if frame
                }

                # 合并所有帧
                merged_frame = merge_frames(show_frames, layout="grid")
                await self.from_inference_queue.async_put(merged_frame)

            except Exception as e:
                logger.error(f"Error processing video frames: {e}")
                await asyncio.sleep(1 / 60)

    def create_webrtc_connection(
        self, config: WebRTCConnectionConfig, webrtc_buffer: Optional[deque] = None
    ) -> WebRTCConnectionResult:
        """
        创建WebRTC连接，主要参考patch_pipeline_manager.py的实现

        Args:
            config: WebRTC连接配置
            webrtc_buffer: 视频帧缓冲区（可选，用于pipeline模式）

        Returns:
            WebRTC连接结果
        """
        try:
            logger.info("开始创建WebRTC连接")

            # 创建新的异步事件循环和线程（参考patch_pipeline_manager.py）
            self.loop = asyncio.new_event_loop()
            self.thread = threading.Thread(
                target=self._start_event_loop, args=(self.loop,), daemon=True
            )
            self.thread.start()

            # 创建队列和事件
            self.from_inference_queue = SyncAsyncQueue(loop=self.loop)
            self.stop_event = Event()

            # 调用init_rtc_peer_connection创建连接
            future = asyncio.run_coroutine_threadsafe(
                init_rtc_peer_connection(
                    webrtc_offer=config.webrtc_offer,
                    webrtc_turn_config=config.webrtc_turn_config,
                    from_inference_queue=self.from_inference_queue,
                    feedback_stop_event=self.stop_event,
                    webcam_fps=config.webcam_fps,
                    max_consecutive_timeouts=config.max_consecutive_timeouts,
                    min_consecutive_on_time=config.min_consecutive_on_time,
                    processing_timeout=config.processing_timeout,
                ),
                self.loop,
            )
            self.peer_connection = future.result()

            # 如果提供了webrtc_buffer，启动视频帧处理（pipeline模式）
            if webrtc_buffer is not None:
                video_frame_func = self._create_video_frame_processor(config)
                webrtc_buffer.clear()  # 清理buffer
                asyncio.run_coroutine_threadsafe(
                    self._process_video_frames(webrtc_buffer, video_frame_func),
                    self.loop,
                )

            logger.info("WebRTC连接创建成功")

            return WebRTCConnectionResult(
                success=True,
                sdp=self.peer_connection.localDescription.sdp,
                type=self.peer_connection.localDescription.type,
                peer_connection=self.peer_connection,
            )

        except Exception as e:
            logger.error(f"创建WebRTC连接失败: {e}")
            return WebRTCConnectionResult(success=False, error=str(e))

    def get_inference_queue(self) -> Optional[SyncAsyncQueue]:
        """获取推理队列"""
        return self.from_inference_queue

    def get_stop_event(self) -> Optional[Event]:
        """获取停止事件"""
        return self.stop_event

    def cleanup(self):
        """清理资源"""
        if self.stop_event:
            self.stop_event.set()

        if self.peer_connection:
            try:
                # 注意：peer_connection的清理需要在正确的事件循环中进行
                if self.loop and not self.loop.is_closed():
                    future = asyncio.run_coroutine_threadsafe(
                        self.peer_connection.close(), self.loop
                    )
                    try:
                        future.result(timeout=5.0)  # 5秒超时
                    except:
                        pass
            except Exception as e:
                logger.warning(f"清理peer_connection时出错: {e}")

        if self.loop and not self.loop.is_closed():
            try:
                self.loop.call_soon_threadsafe(self.loop.stop)
            except:
                pass

        logger.info("WebRTC资源清理完成")


# 便捷函数，简化使用
def create_webrtc_connection_with_pipeline_buffer(
    config: WebRTCConnectionConfig, webrtc_buffer: deque
) -> WebRTCConnectionResult:
    """
    为pipeline模式创建WebRTC连接的便捷函数
    参考patch_pipeline_manager.py的使用方式
    """
    manager = WebRTCManager()
    return manager.create_webrtc_connection(config, webrtc_buffer)


def create_webrtc_connection_standalone(
    config: WebRTCConnectionConfig,
) -> tuple[WebRTCConnectionResult, WebRTCManager]:
    """
    创建独立的WebRTC连接的便捷函数
    返回连接结果和管理器实例（用于后续管理）
    """
    manager = WebRTCManager()
    result = manager.create_webrtc_connection(config)
    return result, manager
