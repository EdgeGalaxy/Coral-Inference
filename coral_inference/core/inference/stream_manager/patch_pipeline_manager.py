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

from coral_inference.core.utils.image_utils import merge_frames
from coral_inference.core.inference.stream_manager.entities import (
    ExtendCommandType,
    PatchInitialiseWebRTCPipelinePayload
)

async def process_video_frames(
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
                asyncio.sleep(1/30)
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
            asyncio.sleep(1/30)
            continue


def get_frame_from_buffer_sink(buffer_sink, stop_event: Event, from_inference_queue: SyncAsyncQueue):
    print(f'get_frame_from_buffer_sink, {len(buffer_sink._webrtc_buffer)}')
    count = 0
    import time
    while not stop_event.is_set():
        if not buffer_sink._webrtc_buffer:
            time.sleep(1/10)
            continue
        
        import numpy as np
        mock_frame = np.full((480, 640, 3), [0, 255, 0], dtype=np.uint8)  # 创建绿色画布
        # 随机生成100个彩色点
        for _ in range(100):
            x = np.random.randint(0, 640)
            y = np.random.randint(0, 480)
            color = np.random.randint(0, 255, 3)
            mock_frame[y:y+5, x:x+5] = color  # 每个点大小为5x5像素
        
        from_inference_queue.sync_put(mock_frame)
        count += 1
        time.sleep(1/10)

        # predictions, frame = buffer_sink._webrtc_buffer.popleft()
        # predictions, frames = buffer_sink._webrtc_buffer.popleft()
        # from_inference_queue.sync_put(frames[0].numpy_image if isinstance(frames, list) else frames.numpy_image)


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
        # frame_processor = threading.Thread(
        #     target=process_video_frames,
        #     args=(
        #         self._buffer_sink,
        #         from_inference_queue,
        #         stop_event,
        #         get_video_frame,
        #         parsed_payload.stream_output
        #     ),
        # )
        # frame_processor.start()
        frame_processor = threading.Thread(
            target=get_frame_from_buffer_sink,
            args=(
                self._buffer_sink,
                stop_event,
                from_inference_queue,
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
        print(f"WebRTC pipeline initialised. request_id={request_id}...")
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


def rewrite_handle_command(self, request_id: str, payload: dict) -> None:
    try:
        logger.info(f"Processing request={request_id}...")
        command_type = ExtendCommandType(payload[TYPE_KEY])
        if command_type is ExtendCommandType.INIT:
            return self._initialise_pipeline(request_id=request_id, payload=payload)
        if command_type is ExtendCommandType.WEBRTC:
            return self._start_webrtc(request_id=request_id, payload=payload)
        if command_type is ExtendCommandType.TERMINATE:
            return self._terminate_pipeline(request_id=request_id)
        if command_type is ExtendCommandType.MUTE:
            return self._mute_pipeline(request_id=request_id)
        if command_type is ExtendCommandType.RESUME:
            return self._resume_pipeline(request_id=request_id)
        if command_type is ExtendCommandType.STATUS:
            return self._get_pipeline_status(request_id=request_id)
        if command_type is ExtendCommandType.CONSUME_RESULT:
            return self._consume_results(request_id=request_id, payload=payload)
        if command_type is ExtendCommandType.OFFER:
            return self._offer(request_id=request_id, payload=payload)
        raise NotImplementedError(
            f"Command type `{command_type}` cannot be handled"
        )
    except KeyError as error:
        logger.exception(f"Invalid command sent to InferencePipeline manager - malformed payload")
        self._handle_error(
            request_id=request_id,
            error=error,
            public_error_message="Invalid command sent to InferencePipeline manager - malformed payload",
            error_type=ErrorType.INVALID_PAYLOAD,
        )
    except NotImplementedError as error:
        self._handle_error(
            request_id=request_id,
            error=error,
            public_error_message=f"Invalid command sent to InferencePipeline manager - {error}",
            error_type=ErrorType.INVALID_PAYLOAD,
        )
    except Exception as error:
        self._handle_error(
            request_id=request_id,
            error=error,
            public_error_message="Unknown internal error. Raise this issue providing as "
            "much of a context as possible: https://github.com/roboflow/inference/issues",
            error_type=ErrorType.INTERNAL_ERROR,
        )
