import asyncio
from threading import Event
from typing import Dict, Callable, Optional
from collections import deque

import cv2 as cv
import numpy as np

from inference.core.interfaces.camera.entities import VideoFrame
from inference.core.utils.async_utils import Queue as SyncAsyncQueue
from inference.core.workflows.execution_engine.entities.base import WorkflowImageData

from coral_inference.core.utils.image_utils import merge_frames

async def process_video_frames(
    webrtc_buffer: deque,
    from_inference_queue: SyncAsyncQueue,
    stop_event: Event,
    video_frame_func: Callable,
):
    """
    处理视频帧的线程函数
    
    Args:
        webrtc_buffer: 包含视频帧的buffer
        from_inference_queue: 用于发送合并后帧的队列
        stop_event: 用于控制线程停止的事件
        video_frame_func: 处理单个视频帧的函数
    """
    while not stop_event.is_set():
        try:
            if not webrtc_buffer:
                await asyncio.sleep(1/60)
                continue

            predictions, frames = webrtc_buffer.popleft()
            predictions = predictions if isinstance(predictions, list) else [predictions]
            frames = frames if isinstance(frames, list) else [frames]
            show_frames = {frame.source_id: video_frame_func(prediction, frame) 
                          for prediction, frame in zip(predictions, frames)}
            
            # 合并所有帧
            merged_frame = merge_frames(show_frames, layout='grid')
            await from_inference_queue.async_put(merged_frame)
            
        except Exception as e:
            print(f"Error processing video frames: {e}")
            await asyncio.sleep(1/60)

def get_video_frame_processor(stream_output: Optional[list] = None):
    """
    创建视频帧处理函数
    
    Args:
        stream_output: 流输出配置
    Returns:
        处理视频帧的函数
    """
    def process_frame(
        prediction: Dict[str, WorkflowImageData], video_frame: VideoFrame
    ) -> None:
        errors = []
        if not any(
            isinstance(v, WorkflowImageData) for v in prediction.values()
        ) or not stream_output:
            errors.append("Visualisation blocks were not executed")
            errors.append("or workflow was not configured to output visuals.")
            errors.append(
                "Please try to adjust the scene so models detect objects"
            )
            errors.append("or stop preview, update workflow and try again.")
            result_frame = video_frame.image.copy()
            for row, error in enumerate(errors):
                result_frame = cv.putText(
                    result_frame,
                    error,
                    (10, 20 + 30 * row),
                    cv.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )
            return result_frame
        if stream_output[0] not in prediction or not isinstance(
            prediction[stream_output[0]], WorkflowImageData
        ):
            for output in prediction.values():
                if isinstance(output, WorkflowImageData):
                    return output.numpy_image
        return prediction[stream_output[0]].numpy_image
    
    return process_frame 