import asyncio
import threading
from functools import partial
from threading import Event
from typing import Dict

import cv2 as cv
from pydantic import ValidationError

from inference.core import logger
from inference.core.exceptions import (
    MissingApiKeyError,
    RoboflowAPINotAuthorizedError,
    RoboflowAPINotNotFoundError,
)
from inference.core.interfaces.camera.entities import VideoFrame
from inference.core.interfaces.stream_manager.manager_app.entities import (
    TYPE_KEY,
    STATUS_KEY,
    CommandType,
    ErrorType,
    OperationStatus,
)
from inference.core.interfaces.stream_manager.manager_app.webrtc import (
    RTCPeerConnectionWithFPS,
    init_rtc_peer_connection,
)
from inference.core.interfaces.stream_manager.manager_app.inference_pipeline_manager import InferencePipelineManager
from inference.core.utils.async_utils import Queue as SyncAsyncQueue
from inference.core.workflows.errors import WorkflowSyntaxError
from inference.core.workflows.execution_engine.entities.base import WorkflowImageData

from coral_inference.core.models.decorators import extend_method_before
from coral_inference.core.utils.image_utils import merge_frames
from coral_inference.core.inference.stream_manager.entities import (
    ExtendCommandType,
    PatchInitialiseWebRTCPipelinePayload
)

def process_video_frames(
    buffer_sink,
    from_inference_queue: SyncAsyncQueue,
    stop_event: Event,
    video_frame_func,
    stream_output: list
):
    """
    处理视频帧的线程函数
    
    Args:
        buffer_sink: 包含webrtc_buffer的sink对象
        from_inference_queue: 用于发送合并后帧的队列
        stop_event: 用于控制线程停止的事件
        video_frame_func: 处理单个视频帧的函数
        stream_output: 流输出配置
    """
    while not stop_event.is_set():
        try:
            if not buffer_sink._webrtc_buffer:
                continue
                
            predictions, frames = buffer_sink._webrtc_buffer.popleft()
            predictions = predictions if isinstance(predictions, list) else [predictions]
            frames = frames if isinstance(frames, list) else [frames]
            show_frames = {frame.source_id: video_frame_func(prediction, frame) 
                          for prediction, frame in zip(predictions, frames)}
            
            # 合并所有帧
            merged_frame = merge_frames(show_frames, layout='grid')
            from_inference_queue.sync_put(merged_frame)
            
        except Exception as e:
            logger.exception(f"Error processing video frames: {e}")
            continue


def offer(self: InferencePipelineManager, request_id: str, payload: dict) -> None:
    try:
        def start_loop(loop: asyncio.AbstractEventLoop):
            asyncio.set_event_loop(loop)
            loop.run_forever()
        
        parsed_payload = PatchInitialiseWebRTCPipelinePayload.model_validate(payload)

        loop = asyncio.new_event_loop()
        t = threading.Thread(target=start_loop, args=(loop,), daemon=True)
        t.start()

        webrtc_offer = parsed_payload.webrtc_offer
        webrtc_turn_config = parsed_payload.webrtc_turn_config
        webcam_fps = parsed_payload.webcam_fps
        to_inference_queue = SyncAsyncQueue(loop=loop)
        from_inference_queue = SyncAsyncQueue(loop=loop)

        stop_event = Event()

        future = asyncio.run_coroutine_threadsafe(
            init_rtc_peer_connection(
                webrtc_offer=webrtc_offer,
                webrtc_turn_config=webrtc_turn_config,
                to_inference_queue=to_inference_queue,
                from_inference_queue=from_inference_queue,
                feedback_stop_event=stop_event,
                asyncio_loop=loop,
                webcam_fps=webcam_fps,
                max_consecutive_timeouts=parsed_payload.max_consecutive_timeouts,
                min_consecutive_on_time=parsed_payload.min_consecutive_on_time,
                processing_timeout=parsed_payload.processing_timeout,
                fps_probe_frames=parsed_payload.fps_probe_frames,
            ),
            loop,
        )
        peer_connection: RTCPeerConnectionWithFPS = future.result()

        def get_video_frame(
            prediction: Dict[str, WorkflowImageData], video_frame: VideoFrame
        ) -> None:
            errors = []
            if not any(
                isinstance(v, WorkflowImageData) for v in prediction.values()
            ):
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
            if parsed_payload.stream_output[0] not in prediction or not isinstance(
                prediction[parsed_payload.stream_output[0]], WorkflowImageData
            ):
                for output in prediction.values():
                    if isinstance(output, WorkflowImageData):
                        return output.numpy_image
            return prediction[parsed_payload.stream_output[0]].numpy_image
        
        # 创建并启动处理视频帧的线程
        frame_processor = threading.Thread(
            target=process_video_frames,
            args=(
                self._buffer_sink,
                from_inference_queue,
                stop_event,
                get_video_frame,
                parsed_payload.stream_output
            ),
            daemon=True
        )
        frame_processor.start()
        
        # 将合并后的帧发送到WebRTC
        self._responses_queue.put(
            (
                request_id,
                {
                    STATUS_KEY: OperationStatus.SUCCESS,
                    "sdp": peer_connection.localDescription.sdp,
                    "type": peer_connection.localDescription.type,
                },
            )
        )
        logger.info(f"WebRTC pipeline initialised. request_id={request_id}...")
    except (
        ValidationError,
        MissingApiKeyError,
        KeyError,
        NotImplementedError,
    ) as error:
        self._handle_error(
            request_id=request_id,
            error=error,
            public_error_message="Could not decode InferencePipeline initialisation command payload.",
            error_type=ErrorType.INVALID_PAYLOAD,
        )
    except RoboflowAPINotAuthorizedError as error:
        self._handle_error(
            request_id=request_id,
            error=error,
            public_error_message="Invalid API key used or API key is missing. "
            "Visit https://docs.roboflow.com/api-reference/authentication#retrieve-an-api-key",
            error_type=ErrorType.AUTHORISATION_ERROR,
        )
    except RoboflowAPINotNotFoundError as error:
        self._handle_error(
            request_id=request_id,
            error=error,
            public_error_message="Requested Roboflow resources (models / workflows etc.) not available or "
            "wrong API key used.",
            error_type=ErrorType.NOT_FOUND,
        )
    except WorkflowSyntaxError as error:
        self._handle_error(
            request_id=request_id,
            error=error,
            public_error_message="Provided workflow configuration is not valid.",
            error_type=ErrorType.INVALID_PAYLOAD,
        )

@extend_method_before
def extend_handle_command(self: InferencePipelineManager, request_id: str, payload: dict) -> None:
    command_type = ExtendCommandType(payload[TYPE_KEY])
    if command_type is ExtendCommandType.OFFER:
        self._offer(request_id=request_id, payload=payload)

    