import json
from typing import Callable, Dict, Any
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, StreamingResponse

from coral_inference.core import logger

from pipeline_cache import PipelineCache


class HookPipelineMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, pipeline_cache: PipelineCache, *args, **kwargs):
        super().__init__(app, *args, **kwargs)
        self.pipeline_cache = pipeline_cache
        self.route_handlers: Dict[str, Callable] = {
            "/inference_pipelines/list": self._handle_list_pipelines,
            "/inference_pipelines/initialise": self._handle_initialize_pipeline,
        }

    async def _process_response_content(self, response) -> dict:
        if isinstance(response, StreamingResponse):
            content = b""
            async for chunk in response.body_iterator:
                content += chunk
            return json.loads(content.decode())
        return response.json()

    async def _create_response(self, data: dict, response, is_streaming: bool = False):
        response.headers.update({"Content-Length": str(len(json.dumps(data).encode()))})

        if is_streaming:
            return StreamingResponse(
                iter([json.dumps(data).encode()]),
                headers=response.headers,
                status_code=response.status_code,
            )
        return JSONResponse(content=data, headers=response.headers)

    async def _handle_list_pipelines(
        self, request_data, response: Response
    ) -> Response:
        if response.status_code != 200:
            logger.warning(
                f"Failed to list pipelines, status code: {response.status_code}"
            )
            return response
        
        data = await self._process_response_content(response)
        pipeline_ids = data.get("pipelines", [])
        data["fixed_pipelines"] = self.pipeline_cache.list(pipeline_ids)

        return await self._create_response(
            data, response, isinstance(response, StreamingResponse)
        )

    async def _handle_initialize_pipeline(
        self, request_data, response: Response
    ) -> Response:
        if response.status_code != 200:
            logger.warning(
                f"Failed to create pipeline, status code: {response.status_code}"
            )
            return response
        data = await self._process_response_content(response)
        pipeline_id = data.get("context", {}).get("pipeline_id")
        self.pipeline_cache.create(pipeline_id, request_data)

        return await self._create_response(
            data, response, isinstance(response, StreamingResponse)
        )

    async def _handle_pipeline_operations(
        self, request: Request, call_next, pipeline_id: str
    ) -> Response:
        transformed_id = self.pipeline_cache.get(pipeline_id)
        if transformed_id:
            request.scope["path"] = request.url.path.replace(
                pipeline_id, transformed_id
            )
            logger.info(
                f"Transformed pipeline id from {pipeline_id} to {transformed_id}"
            )
        else:
            logger.warning(f"Failed to find transformed pipeline id for {pipeline_id}")

        return await call_next(request)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        # Handle direct route matches
        handler = self.route_handlers.get(path)
        if handler:
            request_data = await request.json() if request.method.lower() == 'post' else {}
            response = await call_next(request)
            return await handler(request_data, response)

        # Handle pipeline operations
        if path.startswith("/inference_pipelines/"):
            operations = {"pause", "resume", "terminate", "consume", "status"}
            if any(op in path for op in operations):
                pipeline_id = path.split("/")[2]
                response = await self._handle_pipeline_operations(
                    request, call_next, pipeline_id
                )

                if "terminate" in request.url.path:
                    self.pipeline_cache.terminate(pipeline_id)
                return response

        return await call_next(request)
