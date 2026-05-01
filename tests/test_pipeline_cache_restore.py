import asyncio
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "docker"))

from config.core.cache import PipelineCache


def test_runtime_deployment_uses_restored_pipeline_id_after_restore(tmp_path):
    cache = PipelineCache(
        stream_manager_client=None,
        db_file_path=str(tmp_path / "pipelines.db"),
    )
    cache.create(
        pipeline_id="old-pipeline",
        pipeline_name="deployment",
        payload={"processing_configuration": {}},
        parameters={"deployment_id": "dep-1", "workspace_id": "ws-1"},
    )

    async def fake_restore(payload):
        return "new-pipeline"

    cache.remote_call_restore = fake_restore

    asyncio.run(cache.restore())

    deployment = cache.get_runtime_deployment("dep-1")
    assert deployment is not None
    assert deployment["pipeline_id"] == "old-pipeline"
    assert deployment["restore_pipeline_id"] == "new-pipeline"
    assert deployment["current_pipeline_id"] == "new-pipeline"

    cache.terminate("new-pipeline")
    assert cache.get_runtime_deployment("dep-1") is None
