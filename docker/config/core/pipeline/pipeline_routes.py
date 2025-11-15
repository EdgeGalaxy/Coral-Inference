from typing import Dict, Optional, Any

from fastapi import FastAPI, Depends, Request

from inference.core.interfaces.http.http_api import with_route_exceptions_async
from inference.core.interfaces.stream_manager.api.entities import (
    CommandResponse,
    ConsumePipelineResponse,
    InferencePipelineStatusResponse,
)
from inference.core.interfaces.stream_manager.api.stream_manager_client import (
    StreamManagerClient,
)
from inference.core.interfaces.stream_manager.manager_app.entities import (
    ConsumeResultsPayload,
)

from ..cache import PipelineCache
from coral_inference.webapp import PipelineService


def register_pipeline_routes(
    app: FastAPI,
    stream_manager_client: StreamManagerClient,
    pipeline_cache: PipelineCache,
) -> None:
    def _pipeline_service_dep() -> PipelineService:
        # Prefer the app-scoped service to keep cache/video hooks wired
        return getattr(
            app.state, "pipeline_service", PipelineService(stream_manager_client, pipeline_cache=pipeline_cache)
        )

    @app.get(
        "/inference_pipelines/list",
        summary="[EXPERIMENTAL] List active InferencePipelines",
        description="[EXPERIMENTAL] Listing all active InferencePipelines processing videos",
    )
    @with_route_exceptions_async
    async def list_pipelines_view(
        pipeline_service: PipelineService = Depends(_pipeline_service_dep),
    ) -> Dict[str, Any]:
        pipelines = await pipeline_service.list()
        return {"pipelines": pipelines, "fixed_pipelines": pipeline_service.cached()}

    @app.post(
        "/inference_pipelines/initialise",
        summary="[EXPERIMENTAL] Starts new InferencePipeline",
        description="[EXPERIMENTAL] Starts new InferencePipeline",
    )
    @with_route_exceptions_async
    async def initialise(
        request: Request, pipeline_service: PipelineService = Depends(_pipeline_service_dep)
    ) -> CommandResponse:
        req_dict: Dict[str, Any] = await request.json()

        resp = await pipeline_service.initialise_from_request(req_dict)
        return resp

    @app.get(
        "/inference_pipelines/{pipeline_id}/status",
        summary="[EXPERIMENTAL] Get status of InferencePipeline",
        description="[EXPERIMENTAL] Get status of InferencePipeline",
    )
    @with_route_exceptions_async
    async def get_status(
        pipeline_id: str, pipeline_service: PipelineService = Depends(_pipeline_service_dep)
    ) -> InferencePipelineStatusResponse:
        return await pipeline_service.status(pipeline_id=pipeline_id)

    @app.post(
        "/inference_pipelines/{pipeline_id}/pause",
        summary="[EXPERIMENTAL] Pauses the InferencePipeline",
        description="[EXPERIMENTAL] Pauses the InferencePipeline",
    )
    @with_route_exceptions_async
    async def pause(
        pipeline_id: str, pipeline_service: PipelineService = Depends(_pipeline_service_dep)
    ) -> CommandResponse:
        return await pipeline_service.pause(pipeline_id=pipeline_id)

    @app.post(
        "/inference_pipelines/{pipeline_id}/resume",
        summary="[EXPERIMENTAL] Resumes the InferencePipeline",
        description="[EXPERIMENTAL] Resumes the InferencePipeline",
    )
    @with_route_exceptions_async
    async def resume(
        pipeline_id: str, pipeline_service: PipelineService = Depends(_pipeline_service_dep)
    ) -> CommandResponse:
        return await pipeline_service.resume(pipeline_id=pipeline_id)

    @app.post(
        "/inference_pipelines/{pipeline_id}/terminate",
        summary="[EXPERIMENTAL] Terminates the InferencePipeline",
        description="[EXPERIMENTAL] Terminates the InferencePipeline",
    )
    @with_route_exceptions_async
    async def terminate(
        pipeline_id: str, pipeline_service: PipelineService = Depends(_pipeline_service_dep)
    ) -> CommandResponse:
        return await pipeline_service.terminate(pipeline_id=pipeline_id)

    @app.get(
        "/inference_pipelines/{pipeline_id}/consume",
        summary="[EXPERIMENTAL] Consumes InferencePipeline result",
        description="[EXPERIMENTAL] Consumes InferencePipeline result",
    )
    @with_route_exceptions_async
    async def consume(
        pipeline_id: str,
        request: Optional[ConsumeResultsPayload] = None,
        pipeline_service: PipelineService = Depends(_pipeline_service_dep),
    ) -> ConsumePipelineResponse:
        if request is None:
            request = ConsumeResultsPayload()
        return await pipeline_service.consume(
            pipeline_id=pipeline_id, excluded_fields=request.excluded_fields
        )
