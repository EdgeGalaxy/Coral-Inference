from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable
import os
import inspect

from inference.core.env import MODEL_CACHE_DIR
from inference.core.interfaces.stream_manager.manager_app.entities import (
    InitialisePipelinePayload,
)


@dataclass
class PipelineSummary:
    pipeline_id: str
    name: Optional[str] = None
    status: Optional[str] = None


class PipelineService:
    """Pipeline service abstraction placeholder."""

    def __init__(
        self,
        stream_manager_client,
        cache_create: Optional[Callable[..., Any]] = None,
        cache_terminate: Optional[Callable[[str], Any]] = None,
        pipeline_cache=None,
        video_downloader: Optional[Callable[[List[Any]], Any]] = None,
        video_cleanup: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._client = stream_manager_client
        self._cache_create = cache_create
        self._cache_terminate = cache_terminate
        self._pipeline_cache = pipeline_cache
        self._video_downloader = video_downloader
        self._video_cleanup = video_cleanup

    def _map_pipeline_id(self, pipeline_id: str) -> str:
        if self._pipeline_cache:
            mapped = self._pipeline_cache.get(pipeline_id)
            if mapped and mapped.get("restore_pipeline_id"):
                return mapped["restore_pipeline_id"]
            restore = getattr(self._pipeline_cache, "get_restore_pipeline_id", None)
            if callable(restore):
                mapped_restore = restore(pipeline_id)
                if mapped_restore and mapped_restore.get("pipeline_id"):
                    return mapped_restore["pipeline_id"]
        return pipeline_id

    def cached(self) -> List[Dict[str, Any]]:
        if not self._pipeline_cache:
            return []
        try:
            return self._pipeline_cache.list()
        except Exception:
            return []

    async def _download_source_videos(self, video_references: List[Any]) -> List[Any]:
        if not video_references:
            return video_references
        if self._video_downloader:
            maybe_result = self._video_downloader(video_references)
            if inspect.isawaitable(maybe_result):
                return await maybe_result
            return maybe_result
        return video_references

    async def initialise_from_request(self, req_dict: Dict[str, Any]) -> Any:
        processing_configuration = req_dict.get("processing_configuration") or {}
        workflows_parameters = processing_configuration.get("workflows_parameters") or {}

        is_file_source = workflows_parameters.get("is_file_source", False)
        if is_file_source:
            video_references = req_dict.get("video_configuration", {}).get(
                "video_reference", []
            )
            downloaded_paths = await self._download_source_videos(video_references)
            req_dict.setdefault("video_configuration", {})["video_reference"] = (
                downloaded_paths
            )
            workflows_parameters.setdefault("auto_restart", False)
        else:
            workflows_parameters.setdefault("auto_restart", True)

        processing_configuration["workflows_parameters"] = workflows_parameters
        req_dict["processing_configuration"] = processing_configuration
        payload = InitialisePipelinePayload(**req_dict)
        return await self.initialise(payload)

    async def initialise(self, payload: InitialisePipelinePayload) -> Any:
        resp = await self._client.initialise_pipeline(initialisation_request=payload)
        try:
            resp_dict = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()
            pipeline_id = (resp_dict.get("context", {}) or {}).get("pipeline_id")
            pipeline_name = payload.processing_configuration.workflows_parameters.get(
                "pipeline_name", ""
            )
            output_image_fields = (
                payload.processing_configuration.workflows_parameters.get(
                    "output_image_fields", []
                )
                + ["source_image"]
            )
            auto_restart = payload.processing_configuration.workflows_parameters.get(
                "auto_restart", True
            )
            if pipeline_id and self._cache_create:
                self._cache_create(
                    pipeline_id,
                    pipeline_name,
                    payload.model_dump(),
                    {"output_image_fields": output_image_fields},
                    auto_restart,
                )
        except Exception:
            pass
        return resp

    async def list(self) -> List[PipelineSummary]:
        pipelines = await self._client.list_pipelines()
        result = []
        for item in pipelines or []:
            if isinstance(item, dict):
                result.append(
                    PipelineSummary(
                        pipeline_id=item.get("pipeline_id") or item.get("id"),
                        name=item.get("pipeline_name"),
                        status=item.get("status"),
                    )
                )
        return result

    async def info(self, pipeline_id: str) -> Dict[str, Any]:
        return await self._client.get_pipeline_info(pipeline_id=pipeline_id)

    def resolve_pipeline_dir(self, pipeline_id: str, output_directory: str = "records") -> str:
        return os.path.join(MODEL_CACHE_DIR, "pipelines", pipeline_id, output_directory)

    def list_video_files(self, pipeline_id: str, output_directory: str = "records") -> List[Dict[str, Any]]:
        base_dir = self.resolve_pipeline_dir(pipeline_id, output_directory)
        if not os.path.isdir(base_dir):
            return []
        items: List[Dict[str, Any]] = []
        for name in os.listdir(base_dir):
            if not name.lower().endswith(".mp4"):
                continue
            file_path = os.path.join(base_dir, name)
            if not os.path.isfile(file_path):
                continue
            stat = os.stat(file_path)
            items.append(
                {
                    "filename": name,
                    "size_bytes": stat.st_size,
                    "created_at": int(stat.st_ctime),
                    "modified_at": int(stat.st_mtime),
                }
            )
        items.sort(key=lambda x: x["created_at"], reverse=True)
        return items[1:] if len(items) > 1 else items

    async def status(self, pipeline_id: str) -> Any:
        real_id = self._map_pipeline_id(pipeline_id)
        return await self._client.get_status(pipeline_id=real_id)

    async def pause(self, pipeline_id: str) -> Any:
        real_id = self._map_pipeline_id(pipeline_id)
        return await self._client.pause_pipeline(pipeline_id=real_id)

    async def resume(self, pipeline_id: str) -> Any:
        real_id = self._map_pipeline_id(pipeline_id)
        return await self._client.resume_pipeline(pipeline_id=real_id)

    async def terminate(self, pipeline_id: str) -> Any:
        real_id = self._map_pipeline_id(pipeline_id)
        resp = await self._client.terminate_pipeline(pipeline_id=real_id)
        if self._cache_terminate:
            try:
                self._cache_terminate(pipeline_id)
            except Exception:
                pass
        if self._video_cleanup:
            try:
                self._video_cleanup(pipeline_id)
            except Exception:
                pass
        return resp

    async def consume(self, pipeline_id: str, excluded_fields=None) -> Any:
        return await self._client.consume_pipeline_result(
            pipeline_id=self._map_pipeline_id(pipeline_id), excluded_fields=excluded_fields
        )

    async def health(self):
        try:
            pipelines = await self._client.list_pipelines()
            info: Dict[str, Any] = {"remote_pipelines": len(pipelines or [])}
            if self._pipeline_cache:
                info["cached"] = len(self.cached())
            return True, info
        except Exception as exc:
            return False, {"error": str(exc)}


__all__ = ["PipelineService", "PipelineSummary"]
