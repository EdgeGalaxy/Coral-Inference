from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from inference.core.interfaces.http.http_api import with_route_exceptions
from inference.core.interfaces.stream_manager.api.entities import (
    InitializeWebRTCPipelineResponse,
    CommandResponse
)
from inference.core.interfaces.stream_manager.api.stream_manager_client import (
    StreamManagerClient
)

from coral_inference.core.inference.stream_manager.entities import PatchInitialiseWebRTCPipelinePayload

from pipeline_cache import PipelineCache
from pipeline_middleware import HookPipelineMiddleware


def init_app(app: FastAPI, stream_manager_client: StreamManagerClient):
    pipeline_cache = PipelineCache(stream_manager_client=stream_manager_client)

    @app.post(
        "/inference_pipelines/{pipeline_id}/offer",
        response_model=InitializeWebRTCPipelineResponse,
        summary="[EXPERIMENTAL] Offer Pipeline Stream",
        description="[EXPERIMENTAL] Offer Pipeline Stream",
    )
    @with_route_exceptions
    async def initialize_offer(pipeline_id: str, request: PatchInitialiseWebRTCPipelinePayload) -> CommandResponse:
        return await stream_manager_client.offer(pipeline_id=pipeline_id, offer_request=request)

    
    app.add_middleware(HookPipelineMiddleware, pipeline_cache=pipeline_cache)

    app.add_middleware(
        CORSMiddleware,
        allow_origins='*',
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return pipeline_cache