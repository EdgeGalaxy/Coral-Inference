from __future__ import annotations

from typing import Any, Dict


class StreamService:
    """Stream/WebRTC service abstraction placeholder."""

    def __init__(self, stream_manager_client) -> None:
        self._client = stream_manager_client

    async def status(self, pipeline_id: str) -> Dict[str, Any]:
        return await self._client.get_pipeline_status(pipeline_id=pipeline_id)

    async def offer(self, pipeline_id: str, offer_request) -> Any:
        return await self._client.offer(pipeline_id=pipeline_id, offer_request=offer_request)

    async def health(self):
        try:
            pipelines = await self._client.list_pipelines()
            return True, {"pipelines": len(pipelines or [])}
        except Exception as exc:
            return False, {"error": str(exc)}


__all__ = ["StreamService"]
