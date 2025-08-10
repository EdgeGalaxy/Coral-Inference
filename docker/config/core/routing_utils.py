from typing import List

from fastapi import Request
from fastapi.routing import APIRoute
from starlette.routing import Mount
from fastapi import FastAPI


def remove_app_root_mount(app: FastAPI) -> None:
    indices_to_remove: List[int] = []
    for i, route in enumerate(app.routes):
        if isinstance(route, Mount) and route.path == "" and route.name == "root":
            indices_to_remove.append(i)
        if isinstance(route, Mount) and route.path == "/static" and route.name == "static":
            indices_to_remove.append(i)
    for i in sorted(indices_to_remove, reverse=True):
        app.routes.pop(i)


def remove_existing_inference_pipeline_routes(app: FastAPI) -> None:
    target_paths = {
        "/inference_pipelines/list",
        "/inference_pipelines/initialise",
        "/inference_pipelines/{pipeline_id}/pause",
        "/inference_pipelines/{pipeline_id}/resume",
        "/inference_pipelines/{pipeline_id}/terminate",
        "/inference_pipelines/{pipeline_id}/consume",
        "/inference_pipelines/{pipeline_id}/status",
    }
    indices_to_remove: List[int] = []
    for i, route in enumerate(app.routes):
        path = getattr(route, "path", None)
        if path in target_paths and isinstance(route, APIRoute):
            indices_to_remove.append(i)
    for i in sorted(indices_to_remove, reverse=True):
        app.routes.pop(i)


def get_monitor(request: Request):
    return request.app.state.monitor


