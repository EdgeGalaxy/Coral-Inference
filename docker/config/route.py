import asyncio

from fastapi import FastAPI, APIRouter
from starlette.routing import Mount
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

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


def remove_app_root_mount(app: FastAPI):
    # 1. 找到并移除所有挂载在 "/" 上的旧路由
    # 我们从后往前遍历，这样删除元素不会影响后续的索引
    indices_to_remove = []
    for i, route in enumerate(app.routes):
        if isinstance(route, Mount) and route.path == '' and route.name == "root":
            indices_to_remove.append(i)
        if isinstance(route, Mount) and route.path == "/static" and route.name == "static":
            indices_to_remove.append(i)

    for i in sorted(indices_to_remove, reverse=True):
        app.routes.pop(i)


def init_app(app: FastAPI, stream_manager_client: StreamManagerClient):
    remove_app_root_mount(app)

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

    app.mount(
        "/",
        StaticFiles(directory="./inference/landing/out", html=True),
        name="coral_root",
    )

    return pipeline_cache