import asyncio
import threading
from threading import Event
from typing import Dict, Callable
from collections import deque

import cv2 as cv
import numpy as np
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
    ErrorType,
    OperationStatus,
)
from inference.core.interfaces.stream_manager.manager_app.inference_pipeline_manager import InferencePipelineManager
from inference.core.workflows.errors import WorkflowSyntaxError

from coral_inference.core.inference.stream_manager.entities import (
    ExtendCommandType,
    PatchInitialiseWebRTCPipelinePayload
)
from coral_inference.core.inference.camera.webrtc_manager import (
    WebRTCConnectionConfig,
    create_webrtc_connection_with_pipeline_buffer,
)

def offer(self: InferencePipelineManager, request_id: str, payload: dict) -> None:
    try:
        logger.info(f"使用WebRTCManager创建WebRTC连接 request_id={request_id}")
        
        # 解析payload
        parsed_payload = PatchInitialiseWebRTCPipelinePayload.model_validate(payload)

        # 创建WebRTC连接配置
        config = WebRTCConnectionConfig(
            webrtc_offer=parsed_payload.webrtc_offer,
            webrtc_turn_config=parsed_payload.webrtc_turn_config,
            webcam_fps=parsed_payload.webcam_fps,
            processing_timeout=parsed_payload.processing_timeout,
            max_consecutive_timeouts=parsed_payload.max_consecutive_timeouts,
            min_consecutive_on_time=parsed_payload.min_consecutive_on_time,
            stream_output=parsed_payload.stream_output
        )

        # 使用便捷函数创建WebRTC连接（pipeline模式）
        result = create_webrtc_connection_with_pipeline_buffer(
            config=config,
            webrtc_buffer=self._buffer_sink._webrtc_buffer
        )

        if result.success:
            # 成功创建连接，返回SDP响应
            self._responses_queue.put(
                (
                    request_id,
                    {
                        STATUS_KEY: OperationStatus.SUCCESS,
                        "sdp": result.sdp,
                        "type": result.type,
                    },
                )
            )
            logger.info(f"WebRTC pipeline initialised successfully. request_id={request_id}")
        else:
            # 连接创建失败
            self._handle_error(
                request_id=request_id,
                error=Exception(result.error),
                public_error_message=f"Failed to create WebRTC connection: {result.error}",
                error_type=ErrorType.INTERNAL_ERROR,
            )
            
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
            return offer(self, request_id=request_id, payload=payload)
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
