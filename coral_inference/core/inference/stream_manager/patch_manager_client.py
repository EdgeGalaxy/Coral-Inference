
from inference.core.interfaces.stream_manager.api.entities import (
    CommandContext,
    InitializeWebRTCPipelineResponse
)
from inference.core.interfaces.stream_manager.manager_app.entities import (
    CommandType,
    TYPE_KEY, 
    REQUEST_ID_KEY, 
    STATUS_KEY, 
    RESPONSE_KEY, 
    PIPELINE_ID_KEY,
)
from inference.core.interfaces.stream_manager.api.stream_manager_client import StreamManagerClient

from coral_inference.core.inference.stream_manager.entities import (
    ExtendCommandType,
    PatchInitialiseWebRTCPipelinePayload,
)


async def offer(self: StreamManagerClient, pipeline_id: str, offer_request: PatchInitialiseWebRTCPipelinePayload):
    command = offer_request.model_dump(exclude_none=True)
    command[TYPE_KEY] = ExtendCommandType.OFFER
    command[PIPELINE_ID_KEY] = pipeline_id
    response = await self._handle_command(command=command)
    status = response[RESPONSE_KEY][STATUS_KEY]
    context = CommandContext(
        request_id=response.get(REQUEST_ID_KEY),
        pipeline_id=response.get(PIPELINE_ID_KEY),
    )
    return InitializeWebRTCPipelineResponse(
        status=status,
        context=context,
        sdp=response["response"]["sdp"],
        type=response["response"]["type"],
    )