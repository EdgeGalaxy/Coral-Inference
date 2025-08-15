import os
import time
from functools import partial

import supervision as sv
from pydantic import ValidationError

from loguru import logger
from inference.core.exceptions import (
    MissingApiKeyError,
    RoboflowAPINotAuthorizedError,
    RoboflowAPINotNotFoundError,
)
from inference.core.interfaces.camera.video_source import CV2VideoFrameProducer
from inference.core.interfaces.stream.inference_pipeline import InferencePipeline
from inference.core.interfaces.stream.sinks import InMemoryBufferSink, multi_sink
from inference.core.interfaces.stream.watchdog import BasePipelineWatchDog
from inference.core.interfaces.stream_manager.manager_app.entities import (
    TYPE_KEY,
    STATUS_KEY,
    ErrorType,
    OperationStatus,
    InitialisePipelinePayload,
)
from inference.core.interfaces.stream_manager.manager_app.inference_pipeline_manager import InferencePipelineManager
from inference.core.workflows.errors import WorkflowSyntaxError

from coral_inference.core.inference.stream_manager.entities import (
    ExtendCommandType,
    PatchInitialiseWebRTCPipelinePayload,
    VideoRecordSinkConfiguration
)
from coral_inference.core.inference.camera.webrtc_manager import (
    WebRTCConnectionConfig,
    create_webrtc_connection_with_pipeline_buffer,
)
from coral_inference.core.inference.stream.video_sink import TimeBasedVideoSink
from coral_inference.core.inference.stream.metric_sink import MetricSink


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
        command_type = ExtendCommandType(payload[TYPE_KEY])
        if command_type is ExtendCommandType.INIT:
            return initialise_pipeline(self, request_id=request_id, payload=payload)
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


def initialise_pipeline(self: InferencePipelineManager, request_id: str, payload: dict) -> None:
    """
    修改版本的 _initialise_pipeline 函数，使用 multi_sink 方式支持多个 sink
    默认包含 InMemoryBufferSink，可以传入额外的 sinks
    """
    try:
        self._watchdog = BasePipelineWatchDog()
        parsed_payload = InitialisePipelinePayload.model_validate(payload)
        used_pipeline_id = parsed_payload.processing_configuration.workflows_parameters.get("used_pipeline_id")
        is_file_source = parsed_payload.processing_configuration.workflows_parameters.get("is_file_source")
        video_reference = parsed_payload.video_configuration.video_reference
        # source_buffer_filling_strategy = parsed_payload.video_configuration.source_buffer_filling_strategy if not is_file_source else None
        # source_buffer_consumption_strategy = parsed_payload.video_configuration.source_buffer_consumption_strategy if not is_file_source else None
        pipeline_id = used_pipeline_id or self._pipeline_id
        
        # 创建基础的 InMemoryBufferSink
        buffer_sink = InMemoryBufferSink.init(
            queue_size=parsed_payload.sink_configuration.results_buffer_size,
        )
        self._buffer_sink = buffer_sink
        
        # 构建 sinks 列表，默认包含 InMemoryBufferSink
        sinks = [buffer_sink.on_prediction]
        
        video_record_sink_configuration = VideoRecordSinkConfiguration.model_validate(parsed_payload.processing_configuration.workflows_parameters.get("video_record_sink_configuration", {}))
        # 检查是否启用录像功能
        if video_record_sink_configuration.is_open:
            video_info = None
            if is_file_source:
                first_video = video_reference[0] if isinstance(video_reference, list) else video_reference
                if os.path.exists(first_video):
                    video_info = sv.VideoInfo.from_video_path(first_video)

            video_sink = TimeBasedVideoSink.init(
                pipeline_id=pipeline_id,
                output_directory=video_record_sink_configuration.output_directory,
                video_info=video_info or video_record_sink_configuration.video_info,
                segment_duration=video_record_sink_configuration.segment_duration,
                max_disk_usage=video_record_sink_configuration.max_disk_usage,
                max_total_size=video_record_sink_configuration.max_total_size,
                video_field_name=video_record_sink_configuration.image_input_name,
            )
            sinks.append(video_sink.on_prediction)
        
        # 处理 MetricSink（视频指标采集）
        metrics_cfg = parsed_payload.processing_configuration.workflows_parameters.get("video_mertics_sink_configuration", {})
        try:
            is_open = bool(metrics_cfg.get("is_open", True))
            selected_fields = metrics_cfg.get("selected_fields") or []
            if is_open:
                metric_sink = MetricSink.init(pipeline_id=pipeline_id, selected_fields=selected_fields)
                sinks.append(metric_sink.on_prediction)
                logger.info(f"MetricSink attached. fields={selected_fields}")
            else:
                logger.info("MetricSink disabled by config.")
        except Exception as metric_error:
            logger.warning(f"Failed to configure MetricSink: {metric_error}")
        
        # 使用 multi_sink 创建链式 sink
        chained_sink = partial(multi_sink, sinks=sinks)

        print(f'workflow_with_init: {parsed_payload.model_dump()}')
        
        self._inference_pipeline = InferencePipeline.init_with_workflow(
            video_reference=parsed_payload.video_configuration.video_reference,
            workflow_specification=parsed_payload.processing_configuration.workflow_specification,
            workspace_name=parsed_payload.processing_configuration.workspace_name,
            workflow_id=parsed_payload.processing_configuration.workflow_id,
            api_key=parsed_payload.api_key,
            image_input_name=parsed_payload.processing_configuration.image_input_name,
            workflows_parameters=parsed_payload.processing_configuration.workflows_parameters,
            on_prediction=chained_sink,
            max_fps=parsed_payload.video_configuration.max_fps,
            watchdog=self._watchdog,
            source_buffer_filling_strategy=parsed_payload.video_configuration.source_buffer_filling_strategy,
            source_buffer_consumption_strategy=parsed_payload.video_configuration.source_buffer_consumption_strategy,
            video_source_properties=parsed_payload.video_configuration.video_source_properties,
            workflows_thread_pool_workers=parsed_payload.processing_configuration.workflows_thread_pool_workers,
            cancel_thread_pool_tasks_on_exit=parsed_payload.processing_configuration.cancel_thread_pool_tasks_on_exit,
            video_metadata_input_name=parsed_payload.processing_configuration.video_metadata_input_name,
            batch_collection_timeout=parsed_payload.video_configuration.batch_collection_timeout,
            decoding_buffer_size=parsed_payload.decoding_buffer_size,
            predictions_queue_size=parsed_payload.predictions_queue_size,
        )
        self._consumption_timeout = parsed_payload.consumption_timeout
        self._last_consume_time = time.monotonic()
        self._inference_pipeline.start(use_main_thread=False)
        self._responses_queue.put(
            (request_id, {STATUS_KEY: OperationStatus.SUCCESS})
        )
        logger.info(f"Pipeline initialised with multi_sink. request_id={request_id}...")
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
