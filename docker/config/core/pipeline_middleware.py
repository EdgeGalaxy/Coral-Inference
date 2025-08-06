import json
import asyncio
import os
import aiohttp
from pathlib import Path
from typing import Callable, Dict, Any
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, StreamingResponse
from inference.core.env import MODEL_CACHE_DIR

from coral_inference.core import logger

from core.pipeline_cache import PipelineCache


class HookPipelineMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, pipeline_cache: PipelineCache, *args, **kwargs):
        super().__init__(app, *args, **kwargs)
        self.pipeline_cache = pipeline_cache
        self.route_handlers: Dict[str, Callable] = {
            "/inference_pipelines/list": self._handle_list_pipelines,
            "/inference_pipelines/initialise": self._handle_initialize_pipeline,
        }
        # 设置视频下载目录
        self.video_download_dir = Path(os.path.join(MODEL_CACHE_DIR, "pipeline_videos"))
        self.video_download_dir.mkdir(parents=True, exist_ok=True)

    async def _download_video(self, video_url: str, pipeline_id: str) -> str:
        """下载视频文件并返回本地路径"""
        try:
            # 从URL获取文件名，如果没有则使用随机名称
            filename = video_url.split("/")[-1].split("?")[0]
            if "." not in filename:
                filename = f"{filename}.mp4"
            
            # 为每个pipeline创建专用目录
            pipeline_dir = self.video_download_dir / pipeline_id
            pipeline_dir.mkdir(parents=True, exist_ok=True)
            
            local_path = pipeline_dir / filename
            
            async with aiohttp.ClientSession() as session:
                async with session.get(video_url) as response:
                    if response.status == 200:
                        with open(local_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        logger.info(f"Downloaded video from {video_url} to {local_path}")
                        return str(local_path)
                    else:
                        logger.error(f"Failed to download video from {video_url}, status: {response.status}")
                        return video_url  # 返回原始URL作为备用
        except Exception as e:
            logger.error(f"Error downloading video from {video_url}: {str(e)}")
            return video_url  # 返回原始URL作为备用

    async def _download_videos_parallel(self, video_references: list, pipeline_id: str) -> list:
        """并行下载多个视频文件"""
        tasks = []
        non_url_refs = []
        
        for video_ref in video_references:
            if isinstance(video_ref, str) and video_ref.startswith(('http://', 'https://')):
                task = self._download_video(video_ref, pipeline_id)
                tasks.append(task)
            else:
                # 如果不是URL，直接添加到结果中
                non_url_refs.append(video_ref)
        
        # 执行并行下载
        downloaded_results = []
        if tasks:
            downloaded_results = await asyncio.gather(*tasks)
        
        # 合并结果，保持原始顺序
        results = []
        download_idx = 0
        for video_ref in video_references:
            if isinstance(video_ref, str) and video_ref.startswith(('http://', 'https://')):
                results.append(downloaded_results[download_idx])
                download_idx += 1
            else:
                results.append(video_ref)
        
        return results

    def _cleanup_pipeline_videos(self, pipeline_id: str):
        """清理pipeline的视频文件"""
        try:
            pipeline_dir = self.video_download_dir / pipeline_id
            if pipeline_dir.exists():
                import shutil
                shutil.rmtree(pipeline_dir)
                logger.info(f"Cleaned up video files for pipeline {pipeline_id}")
        except Exception as e:
            logger.error(f"Error cleaning up video files for pipeline {pipeline_id}: {str(e)}")

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
        data["fixed_pipelines"] = self.pipeline_cache.list()

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
        output_image_fields = request_data.get("processing_configuration", {}) \
            .get("workflows_parameters", {}).get("output_image_fields", []) + ['source_image']
        pipeline_name = request_data.get("processing_configuration", {}) \
            .get("workflows_parameters", {}).get("pipeline_name", "")
        is_file_source = request_data.get("processing_configuration", {}) \
            .get("workflows_parameters", {}).get("is_file_source", False)
        
        # 获取自动重启参数，设置默认值
        auto_restart = request_data.get("processing_configuration", {}) \
            .get("workflows_parameters", {}).get("auto_restart", not is_file_source)
        
        # 如果是文件源，处理视频下载
        if is_file_source:
            video_references = request_data.get("video_configuration", {}).get("video_reference", [])
            if isinstance(video_references, list) and video_references:
                logger.info(f"Downloading {len(video_references)} videos for pipeline {pipeline_id}")
                # 并行下载视频文件
                downloaded_paths = await self._download_videos_parallel(video_references, pipeline_id)
                # 更新request_data中的video_reference
                request_data["video_configuration"]["video_reference"] = downloaded_paths
                logger.info(f"Updated video references: {downloaded_paths}")
        
        self.pipeline_cache.create(pipeline_id, pipeline_name, request_data, {"output_image_fields": output_image_fields}, auto_restart)

        return await self._create_response(
            data, response, isinstance(response, StreamingResponse)
        )

    async def _handle_pipeline_operations(
        self, request: Request, call_next, pipeline_id: str
    ) -> Response:
        transformed_id = self.pipeline_cache.get(pipeline_id)
        if transformed_id:
            request.scope["path"] = request.url.path.replace(
                pipeline_id, transformed_id['restore_pipeline_id']
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
                    # 清理pipeline的视频文件
                    self._cleanup_pipeline_videos(pipeline_id)
                return response

        return await call_next(request)
