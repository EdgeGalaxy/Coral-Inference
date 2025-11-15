from __future__ import annotations

import pytest

from coral_inference.webapp import HealthService, PipelineService


@pytest.mark.asyncio
async def test_health_service_handles_sync_and_async_checks():
    service = HealthService()
    service.register_check("sync", lambda: (True, {"kind": "sync"}))

    async def async_ok():
        return True

    service.register_check("async", async_ok)

    status = await service.readiness()
    assert status.healthy is True
    assert status.details["checks"]["sync"]["healthy"] is True
    assert status.details["checks"]["sync"]["info"] == {"kind": "sync"}
    assert status.details["checks"]["async"]["healthy"] is True
    assert status.details["timestamp"]


class _DummyCache:
    def __init__(self) -> None:
        self._records = [
            {"restore_pipeline_id": "restored-id", "pipeline_id": "p-1", "pipeline_name": "demo"}
        ]

    def get(self, pipeline_id: str):
        if pipeline_id == "p-1":
            return {"restore_pipeline_id": "restored-id"}
        return None

    def get_restore_pipeline_id(self, pipeline_id: str):
        if pipeline_id == "restored-id":
            return {"pipeline_id": "p-1"}
        return None

    def list(self):
        return self._records


class _DummyClient:
    def __init__(self) -> None:
        self.calls = {"status": [], "pause": [], "resume": [], "terminate": [], "consume": []}

    async def list_pipelines(self):
        return [{"pipeline_id": "p-1"}]

    async def get_status(self, pipeline_id: str):
        self.calls["status"].append(pipeline_id)
        return {"id": pipeline_id}

    async def pause_pipeline(self, pipeline_id: str):
        self.calls["pause"].append(pipeline_id)
        return {"paused": pipeline_id}

    async def resume_pipeline(self, pipeline_id: str):
        self.calls["resume"].append(pipeline_id)
        return {"resumed": pipeline_id}

    async def terminate_pipeline(self, pipeline_id: str):
        self.calls["terminate"].append(pipeline_id)
        return {"terminated": pipeline_id}

    async def consume_pipeline_result(self, pipeline_id: str, excluded_fields=None):
        self.calls["consume"].append((pipeline_id, tuple(excluded_fields or [])))
        return {"pipeline_id": pipeline_id, "excluded_fields": excluded_fields or []}


@pytest.mark.asyncio
async def test_pipeline_service_maps_pipeline_ids_and_reports_health():
    cache_calls = {"terminated": [], "cleaned": []}
    pipeline_cache = _DummyCache()
    client = _DummyClient()

    def cache_terminate(pid: str):
        cache_calls["terminated"].append(pid)

    def cleanup(pid: str):
        cache_calls["cleaned"].append(pid)

    service = PipelineService(
        client,
        cache_terminate=cache_terminate,
        pipeline_cache=pipeline_cache,
        video_cleanup=cleanup,
    )

    await service.status("p-1")
    await service.pause("p-1")
    await service.resume("p-1")
    await service.consume("p-1", excluded_fields=["a"])
    await service.terminate("p-1")

    assert client.calls["status"] == ["restored-id"]
    assert client.calls["pause"] == ["restored-id"]
    assert client.calls["resume"] == ["restored-id"]
    assert client.calls["consume"] == [("restored-id", ("a",))]
    assert client.calls["terminate"] == ["restored-id"]
    assert cache_calls["terminated"] == ["p-1"]
    assert cache_calls["cleaned"] == ["p-1"]

    healthy, info = await service.health()
    assert healthy is True
    assert info["remote_pipelines"] == 1
    assert info["cached"] == len(pipeline_cache.list())
