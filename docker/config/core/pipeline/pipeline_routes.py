from typing import Dict, Optional

from fastapi import FastAPI, Query, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException

from inference.core.interfaces.http.http_api import with_route_exceptions
from inference.core.interfaces.stream_manager.api.entities import (
    InitializeWebRTCPipelineResponse,
    CommandResponse,
    ConsumePipelineResponse,
    InferencePipelineStatusResponse,
)
from inference.core.interfaces.stream_manager.api.stream_manager_client import (
    StreamManagerClient,
)
from inference.core.interfaces.stream_manager.manager_app.entities import (
    InitialisePipelinePayload,
    ConsumeResultsPayload,
)

from ..cache import PipelineCache
from ..pipeline.pipeline_utils import (
    download_videos_parallel,
    cleanup_pipeline_videos,
)


def register_pipeline_routes(app: FastAPI, stream_manager_client: StreamManagerClient, pipeline_cache: PipelineCache) -> None:
    @app.get(
        "/inference_pipelines/list",
        summary="[EXPERIMENTAL] List active InferencePipelines",
        description="[EXPERIMENTAL] Listing all active InferencePipelines processing videos",
    )
    @with_route_exceptions
    async def list_pipelines() -> JSONResponse:
        resp = await stream_manager_client.list_pipelines()
        content = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()
        content["fixed_pipelines"] = pipeline_cache.list()
        return JSONResponse(content=content)

    @app.post(
        "/inference_pipelines/initialise",
        summary="[EXPERIMENTAL] Starts new InferencePipeline",
        description="[EXPERIMENTAL] Starts new InferencePipeline",
    )
    @with_route_exceptions
    async def initialise(request: Request) -> CommandResponse:
        req_dict: Dict[str, any] = await request.json()

        processing_configuration = req_dict.get("processing_configuration") or {}
        workflows_parameters = processing_configuration.get("workflows_parameters") or {}

        is_file_source =  workflows_parameters.get("is_file_source", False)

        if is_file_source:
            video_references = (
                req_dict.get("video_configuration", {}).get("video_reference", [])
            )
            if isinstance(video_references, list) and video_references:
                downloaded_paths = await download_videos_parallel(video_references)
                req_dict.setdefault("video_configuration", {})[
                    "video_reference"
                ] = downloaded_paths

        output_image_fields = (
            workflows_parameters.get("output_image_fields", [])
            + ["source_image"]
        )
        pipeline_name = workflows_parameters.get("pipeline_name", "")
        auto_restart = workflows_parameters.get("auto_restart", not is_file_source)

        patched_request = InitialisePipelinePayload(**req_dict)
        print(f'patch_requests: {patched_request}')
        resp = await stream_manager_client.initialise_pipeline(
            initialisation_request=patched_request
        )

        try:
            resp_dict = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()
            pipeline_id = (resp_dict.get("context", {}) or {}).get("pipeline_id")
        except Exception:
            pipeline_id = None
        if pipeline_id:
            workflows_parameters.update({"used_pipeline_id": pipeline_id})
            pipeline_cache.create(
                pipeline_id,
                pipeline_name,
                req_dict,
                {"output_image_fields": output_image_fields},
                auto_restart,
            )
        return resp

    def _map_pipeline_id(pipeline_id: str) -> str:
        mapped = pipeline_cache.get(pipeline_id)
        if mapped:
            return mapped["restore_pipeline_id"]
        return pipeline_id

    @app.get(
        "/inference_pipelines/{pipeline_id}/status",
        summary="[EXPERIMENTAL] Get status of InferencePipeline",
        description="[EXPERIMENTAL] Get status of InferencePipeline",
    )
    @with_route_exceptions
    async def get_status(pipeline_id: str) -> InferencePipelineStatusResponse:
        real_id = _map_pipeline_id(pipeline_id)
        return await stream_manager_client.get_status(pipeline_id=real_id)

    @app.post(
        "/inference_pipelines/{pipeline_id}/pause",
        summary="[EXPERIMENTAL] Pauses the InferencePipeline",
        description="[EXPERIMENTAL] Pauses the InferencePipeline",
    )
    @with_route_exceptions
    async def pause(pipeline_id: str) -> CommandResponse:
        real_id = _map_pipeline_id(pipeline_id)
        return await stream_manager_client.pause_pipeline(pipeline_id=real_id)

    @app.post(
        "/inference_pipelines/{pipeline_id}/resume",
        summary="[EXPERIMENTAL] Resumes the InferencePipeline",
        description="[EXPERIMENTAL] Resumes the InferencePipeline",
    )
    @with_route_exceptions
    async def resume(pipeline_id: str) -> CommandResponse:
        real_id = _map_pipeline_id(pipeline_id)
        return await stream_manager_client.resume_pipeline(pipeline_id=real_id)

    @app.post(
        "/inference_pipelines/{pipeline_id}/terminate",
        summary="[EXPERIMENTAL] Terminates the InferencePipeline",
        description="[EXPERIMENTAL] Terminates the InferencePipeline",
    )
    @with_route_exceptions
    async def terminate(pipeline_id: str) -> CommandResponse:
        real_id = _map_pipeline_id(pipeline_id)
        resp = await stream_manager_client.terminate_pipeline(pipeline_id=real_id)
        try:
            pipeline_cache.terminate(pipeline_id)
            cleanup_pipeline_videos(pipeline_id)
        except Exception:
            pass
        return resp

    @app.get(
        "/inference_pipelines/{pipeline_id}/consume",
        summary="[EXPERIMENTAL] Consumes InferencePipeline result",
        description="[EXPERIMENTAL] Consumes InferencePipeline result",
    )
    @with_route_exceptions
    async def consume(
        pipeline_id: str, request: Optional[ConsumeResultsPayload] = None
    ) -> ConsumePipelineResponse:
        if request is None:
            request = ConsumeResultsPayload()
        real_id = _map_pipeline_id(pipeline_id)
        return await stream_manager_client.consume_pipeline_result(
            pipeline_id=real_id, excluded_fields=request.excluded_fields
        )


