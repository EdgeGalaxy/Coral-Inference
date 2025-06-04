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
    STATUS_KEY,
    ErrorType,
    OperationStatus,
)
from inference.core.interfaces.stream.sinks import multi_sink
from inference.core.interfaces.stream_manager.manager_app.webrtc import (
    RTCPeerConnectionWithFPS,
    WebRTCVideoFrameProducer,
    init_rtc_peer_connection,
)
from inference.core.interfaces.stream_manager.manager_app.inference_pipeline_manager import InferencePipelineManager
from inference.core.utils.async_utils import Queue as SyncAsyncQueue
from inference.core.workflows.errors import WorkflowSyntaxError
from inference.core.workflows.execution_engine.entities.base import WorkflowImageData


async def offer(self: InferencePipelineManager, request_id: str, parsed_payload: dict) -> None:
    try:
        def start_loop(loop: asyncio.AbstractEventLoop):
            asyncio.set_event_loop(loop)
            loop.run_forever()

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
                webrtc_peer_timeout=parsed_payload.webrtc_peer_timeout,
                feedback_stop_event=stop_event,
                asyncio_loop=loop,
                webcam_fps=webcam_fps,
            ),
            loop,
        )
        peer_connection: RTCPeerConnectionWithFPS = future.result()
        
        predictions, frames = self._buffer_sink._webrtc_buffer.popleft()

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