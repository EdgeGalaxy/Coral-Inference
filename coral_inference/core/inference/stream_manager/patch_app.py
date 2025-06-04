
from typing import Optional
from uuid import uuid4

from inference.core import logger
from inference.core.interfaces.stream_manager.manager_app.communication import (
    receive_socket_data,
    send_data_trough_socket,
)
from inference.core.interfaces.stream_manager.manager_app.entities import (
    PIPELINE_ID_KEY,
    TYPE_KEY,
    ErrorType
)
from inference.core.interfaces.stream_manager.manager_app.app import (
    HEADER_SIZE,
    SOCKET_BUFFER_SIZE,
    handle_command
)
from inference.core.interfaces.stream_manager.manager_app.serialisation import (
    prepare_error_response,
    prepare_response,
)
from inference.core.interfaces.stream_manager.manager_app.errors import (
    MalformedPayloadError,
)

from coral_inference.core.inference.stream_manager.entities import ExtendCommandType


def rewrite_handle(self) -> None:
    pipeline_id: Optional[str] = None
    request_id = str(uuid4())
    try:
        data = receive_socket_data(
            source=self.request,
            header_size=HEADER_SIZE,
            buffer_size=SOCKET_BUFFER_SIZE,
        )
        data[TYPE_KEY] = ExtendCommandType(data[TYPE_KEY])
        if data[TYPE_KEY] is ExtendCommandType.LIST_PIPELINES:
            return self._list_pipelines(request_id=request_id)
        if data[TYPE_KEY] is ExtendCommandType.INIT:
            return self._initialise_pipeline(request_id=request_id, command=data)
        if data[TYPE_KEY] is ExtendCommandType.WEBRTC:
            return self._start_webrtc(request_id=request_id, command=data)

        pipeline_id = data[PIPELINE_ID_KEY]
        if data[TYPE_KEY] is ExtendCommandType.TERMINATE:
            self._terminate_pipeline(
                request_id=request_id, pipeline_id=pipeline_id, command=data
            )
        else:
            response = handle_command(
                processes_table=self._processes_table,
                request_id=request_id,
                pipeline_id=pipeline_id,
                command=data,
            )
            serialised_response = prepare_response(
                request_id=request_id, response=response, pipeline_id=pipeline_id
            )
            send_data_trough_socket(
                target=self.request,
                header_size=HEADER_SIZE,
                data=serialised_response,
                request_id=request_id,
                pipeline_id=pipeline_id,
            )
    except (KeyError, ValueError, MalformedPayloadError) as error:
        logger.error(
            f"Invalid payload in processes manager. error={error} request_id={request_id}..."
        )
        payload = prepare_error_response(
            request_id=request_id,
            error=error,
            error_type=ErrorType.INVALID_PAYLOAD,
            pipeline_id=pipeline_id,
        )
        send_data_trough_socket(
            target=self.request,
            header_size=HEADER_SIZE,
            data=payload,
            request_id=request_id,
            pipeline_id=pipeline_id,
        )
    except Exception as error:
        logger.error(
            f"Internal error in processes manager. error={error} request_id={request_id}..."
        )
        payload = prepare_error_response(
            request_id=request_id,
            error=error,
            error_type=ErrorType.INTERNAL_ERROR,
            pipeline_id=pipeline_id,
        )
        send_data_trough_socket(
            target=self.request,
            header_size=HEADER_SIZE,
            data=payload,
            request_id=request_id,
            pipeline_id=pipeline_id,
        )