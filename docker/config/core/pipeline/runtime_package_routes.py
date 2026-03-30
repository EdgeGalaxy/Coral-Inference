import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, Field

from inference.core.env import API_KEY
from inference.core.interfaces.http.http_api import with_route_exceptions_async
from inference.core.interfaces.stream_manager.api.entities import (
    CommandContext,
    CommandResponse,
    ConsumePipelineResponse,
)
from inference.core.interfaces.stream_manager.api.errors import (
    ProcessesManagerClientError,
    ProcessesManagerNotFoundError,
)
from inference.core.interfaces.stream_manager.api.stream_manager_client import (
    StreamManagerClient,
)
from inference.core.interfaces.stream_manager.manager_app.entities import (
    InitialisePipelinePayload,
)

from coral_inference.core.env import (
    CORAL_BACKEND_INTERNAL_SECRET,
    CORAL_BACKEND_PACKAGE_TIMEOUT,
    CORAL_BACKEND_URL,
)
from coral_inference.core.runtime_package import (
    build_initialise_payload_from_runtime_package,
    get_runtime_deployment,
    register_runtime_package,
)
from coral_inference.core.log import logger

from ..cache import PipelineCache
from ..routing_utils import get_monitor


class RuntimePackageInitialiseRequest(BaseModel):
    workspace_id: str
    deployment_id: str
    backend_url: Optional[str] = None
    backend_secret: Optional[str] = None
    pipeline_name: Optional[str] = None
    existing_pipeline_id: Optional[str] = None
    auto_restart: Optional[bool] = True


class RuntimePackagePreviewRequest(BaseModel):
    workspace_id: str
    deployment_id: str
    backend_url: Optional[str] = None
    backend_secret: Optional[str] = None


class RuntimeDeploymentRequest(BaseModel):
    workspace_id: str
    backend_url: Optional[str] = None
    backend_secret: Optional[str] = None
    pipeline_name: Optional[str] = None
    existing_pipeline_id: Optional[str] = None
    auto_restart: Optional[bool] = True


def _extract_runtime_identity_fields(
    *,
    package: Optional[Dict[str, Any]] = None,
    runtime_deployment: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[str]]:
    source = package or ((runtime_deployment or {}).get("parameters") or {})
    return {
        "deployment_revision": source.get("deployment_revision"),
        "package_digest": source.get("package_digest"),
        "workflow_digest": source.get("workflow_digest"),
        "model_bindings_digest": source.get("model_bindings_digest"),
        "package_generated_at": source.get("package_generated_at"),
    }


def _default_runtime_phase(running_status: str) -> str:
    mapping = {
        "pending": "pending",
        "running": "running",
        "warning": "degraded",
        "failure": "failure",
        "muted": "muted",
        "stopped": "stopped",
        "not_found": "pipeline_missing",
        "timeout": "timeout",
    }
    return mapping.get(str(running_status or "").lower(), "unknown")


def _map_report_to_running_status(report: Optional[Dict[str, Any]]) -> str:
    if not report:
        return "pending"
    sources_metadata = report.get("sources_metadata") or []
    if not sources_metadata:
        return "pending"
    source_states = [str(source.get("state", "")).upper() for source in sources_metadata]
    if source_states and all(state == "RUNNING" for state in source_states):
        return "running"
    if source_states and all(state == "MUTED" for state in source_states):
        return "muted"
    return "warning"


def _extract_command_response(
    response: CommandResponse | Dict[str, Any],
) -> Dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if hasattr(response, "dict"):
        return response.dict()
    return dict(response)


def _build_runtime_deployment_response(
    *,
    deployment_id: str,
    workspace_id: str,
    pipeline_id: Optional[str],
    running_status: str,
    report: Optional[Dict[str, Any]] = None,
    runtime_deployment: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
    runtime_phase: Optional[str] = None,
    phase_message: Optional[str] = None,
    observed_at: Optional[str] = None,
    package: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    identity_fields = _extract_runtime_identity_fields(
        package=package,
        runtime_deployment=runtime_deployment,
    )
    return {
        "deployment_id": deployment_id,
        "workspace_id": workspace_id,
        "pipeline_id": pipeline_id,
        "running_status": running_status,
        "report": report,
        "error_message": error_message,
        "runtime_phase": runtime_phase or _default_runtime_phase(running_status),
        "phase_message": phase_message,
        "observed_at": observed_at or datetime.now(timezone.utc).isoformat(),
        "runtime_deployment": runtime_deployment,
        **identity_fields,
    }


def _empty_consume_pipeline_response(
    pipeline_id: Optional[str],
) -> ConsumePipelineResponse:
    return ConsumePipelineResponse(
        status="not_found",
        context=CommandContext(request_id=None, pipeline_id=pipeline_id),
        outputs=[],
        frames_metadata=[],
    )


async def _get_runtime_deployment_metrics(
    *,
    deployment_id: str,
    workspace_id: str,
    pipeline_cache: PipelineCache,
    monitor: Any,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    minutes: int = 5,
    level: str = "pipeline",
) -> Dict[str, Any]:
    runtime_deployment = pipeline_cache.get_runtime_deployment(deployment_id)
    if runtime_deployment is None:
        return {"dates": [], "datasets": []}

    pipeline_id = runtime_deployment["pipeline_id"]
    if start_time is None or end_time is None:
        end_time = time.time()
        start_time = end_time - (minutes * 60)

    if not getattr(monitor, "influxdb_collector", None) or not monitor.influxdb_collector.enabled:
        logger.warning(
            "InfluxDB monitor unavailable for runtime deployment metrics. "
            "workspace_id={} deployment_id={} pipeline_id={}",
            workspace_id,
            deployment_id,
            pipeline_id,
        )
        return {"dates": [], "datasets": []}

    start_dt = datetime.fromtimestamp(start_time, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(end_time, tz=timezone.utc)
    summary = await monitor.get_metrics_summary(
        pipeline_id=pipeline_id,
        start_time=start_dt,
        end_time=end_dt,
        aggregation_window="10s",
        level=level or "pipeline",
    )
    if not summary or not summary.get("data"):
        return {"dates": [], "datasets": []}

    rows = summary["data"]
    dates = sorted({row.get("time") for row in rows if row.get("time")})
    datasets: List[Dict[str, Any]] = []

    if (level or "pipeline") == "pipeline":
        bucket_map = {row.get("time"): row for row in rows if row.get("time")}
        datasets.append(
            {
                "name": "Throughput",
                "data": [
                    float(bucket_map.get(ts, {}).get("avg_throughput", 0) or 0)
                    for ts in dates
                ],
            }
        )
        datasets.append(
            {
                "name": "Source Count",
                "data": [
                    float(bucket_map.get(ts, {}).get("avg_source_count", 0) or 0)
                    for ts in dates
                ],
            }
        )
        datasets.append(
            {
                "name": "E2E Latency",
                "data": [
                    float(bucket_map.get(ts, {}).get("avg_e2e_latency", 0) or 0)
                    for ts in dates
                ],
            }
        )
        return {"dates": dates, "datasets": datasets}

    source_rows = {
        (row.get("time"), str(row.get("source_id"))): row
        for row in rows
        if row.get("time") and row.get("source_id") is not None
    }
    source_ids = sorted(
        {
            str(row.get("source_id"))
            for row in rows
            if row.get("source_id") is not None
        }
    )
    for source_id in source_ids:
        datasets.append(
            {
                "name": f"Frame Decoding ({source_id})",
                "data": [
                    float(
                        (
                            source_rows.get((ts, source_id), {}) or {}
                        ).get("avg_frame_decoding_latency", 0)
                        or 0
                    )
                    for ts in dates
                ],
            }
        )
        datasets.append(
            {
                "name": f"Inference Latency ({source_id})",
                "data": [
                    float(
                        (source_rows.get((ts, source_id), {}) or {}).get(
                            "avg_inference_latency", 0
                        )
                        or 0
                    )
                    for ts in dates
                ],
            }
        )
        datasets.append(
            {
                "name": f"E2E Latency ({source_id})",
                "data": [
                    float(
                        (source_rows.get((ts, source_id), {}) or {}).get(
                            "avg_e2e_latency", 0
                        )
                        or 0
                    )
                    for ts in dates
                ],
            }
        )
    return {"dates": dates, "datasets": datasets}


async def _initialise_runtime_deployment(
    *,
    deployment_id: str,
    request: RuntimeDeploymentRequest,
    stream_manager_client: StreamManagerClient,
    pipeline_cache: PipelineCache,
) -> Dict[str, Any]:
    package: Optional[Dict[str, Any]] = None
    try:
        package = await _fetch_runtime_package(
            workspace_id=request.workspace_id,
            deployment_id=deployment_id,
            backend_url=request.backend_url,
            backend_secret=request.backend_secret,
        )
        await _emit_runtime_phase_to_backend(
            workspace_id=request.workspace_id,
            deployment_id=deployment_id,
            backend_url=request.backend_url,
            backend_secret=request.backend_secret,
            pipeline_id=request.existing_pipeline_id,
            running_status="pending",
            runtime_phase="package_fetched",
            phase_message="Runtime package fetched from CoralReefBackend",
            package=package,
        )

        package = register_runtime_package(package)
        await _emit_runtime_phase_to_backend(
            workspace_id=request.workspace_id,
            deployment_id=deployment_id,
            backend_url=request.backend_url,
            backend_secret=request.backend_secret,
            pipeline_id=request.existing_pipeline_id,
            running_status="pending",
            runtime_phase="package_registered",
            phase_message="Runtime package registered in Coral-Inference runtime",
            package=package,
        )
        if request.pipeline_name:
            package["deployment_name"] = request.pipeline_name

        initialisation_payload = build_initialise_payload_from_runtime_package(
            package=package,
            api_key=API_KEY,
            existing_pipeline_id=request.existing_pipeline_id,
        )
        initialisation_request = InitialisePipelinePayload.model_validate(
            initialisation_payload
        )
        response = await stream_manager_client.initialise_pipeline(
            initialisation_request=initialisation_request
        )
        response_dict = _extract_command_response(response)
        pipeline_id = (response_dict.get("context", {}) or {}).get("pipeline_id")
        parameters = None
        if pipeline_id:
            parameters = {
                "deployment_id": package.get("deployment_id"),
                "workspace_id": package.get("workspace_id"),
                "gateway_id": package.get("gateway_id"),
                "output_image_fields": package.get("stream_config", {}).get(
                    "output_image_fields", []
                ),
                "deployment_mode": "runtime_package",
                "deployment_revision": package.get("deployment_revision"),
                "package_digest": package.get("package_digest"),
                "workflow_digest": package.get("workflow_digest"),
                "model_bindings_digest": package.get("model_bindings_digest"),
                "package_generated_at": package.get("package_generated_at"),
                "last_initialised_at": datetime.now(timezone.utc).isoformat(),
            }
            pipeline_cache.create(
                pipeline_id=pipeline_id,
                pipeline_name=package.get("deployment_name") or package.get("workflow_name") or "",
                payload=initialisation_request.model_dump(),
                parameters=parameters,
                auto_restart=bool(request.auto_restart),
            )
            runtime_deployment = pipeline_cache.get_runtime_deployment(deployment_id)
            await _emit_runtime_phase_to_backend(
                workspace_id=request.workspace_id,
                deployment_id=deployment_id,
                backend_url=request.backend_url,
                backend_secret=request.backend_secret,
                pipeline_id=pipeline_id,
                running_status="pending",
                runtime_phase="pipeline_initialised",
                phase_message="Runtime pipeline initialised on edge runtime",
                package=package,
                runtime_deployment=runtime_deployment,
            )

        return {
            "command_response": response_dict,
            "pipeline_id": pipeline_id,
            "package": package,
        }
    except Exception as error:
        error_message = getattr(error, "public_message", None) or str(error)
        try:
            await _emit_runtime_phase_to_backend(
                workspace_id=request.workspace_id,
                deployment_id=deployment_id,
                backend_url=request.backend_url,
                backend_secret=request.backend_secret,
                pipeline_id=request.existing_pipeline_id,
                running_status="failure",
                runtime_phase="failure",
                phase_message="Runtime package initialisation failed",
                package=package,
                error_message=error_message,
            )
        except Exception as callback_error:
            logger.warning(
                "Failed to report runtime deployment initialisation failure. "
                "deployment_id={} error={}",
                deployment_id,
                callback_error,
            )
        raise


async def _get_runtime_deployment_status(
    *,
    deployment_id: str,
    workspace_id: str,
    stream_manager_client: StreamManagerClient,
    pipeline_cache: PipelineCache,
) -> Dict[str, Any]:
    runtime_deployment = pipeline_cache.get_runtime_deployment(deployment_id)
    if runtime_deployment is None:
        return _build_runtime_deployment_response(
            deployment_id=deployment_id,
            workspace_id=workspace_id,
            pipeline_id=None,
            running_status="stopped",
            runtime_deployment=None,
            runtime_phase="stopped",
            phase_message="Runtime deployment is not registered in local cache",
        )

    pipeline_id = runtime_deployment["pipeline_id"]
    try:
        response = await stream_manager_client.get_status(pipeline_id=pipeline_id)
        response_dict = _extract_command_response(response)
        report = response_dict.get("report") or {}
        running_status = _map_report_to_running_status(report)
        runtime_deployment = (
            pipeline_cache.update_runtime_deployment_parameters(
                deployment_id,
                {"last_runtime_status_at": datetime.now(timezone.utc).isoformat()},
            )
            or runtime_deployment
        )
        return _build_runtime_deployment_response(
            deployment_id=deployment_id,
            workspace_id=workspace_id,
            pipeline_id=pipeline_id,
            running_status=running_status,
            report=report,
            runtime_deployment=runtime_deployment,
            runtime_phase=_default_runtime_phase(running_status),
            phase_message="Runtime deployment status collected from edge runtime",
        )
    except ProcessesManagerNotFoundError:
        try:
            pipeline_cache.terminate(pipeline_id)
        except Exception:
            pass
        return _build_runtime_deployment_response(
            deployment_id=deployment_id,
            workspace_id=workspace_id,
            pipeline_id=None,
            running_status="not_found",
            runtime_deployment=runtime_deployment,
            error_message="Runtime deployment pipeline not found",
            runtime_phase="pipeline_missing",
            phase_message="Runtime deployment pipeline not found on edge runtime",
        )
    except ProcessesManagerClientError as error:
        return _build_runtime_deployment_response(
            deployment_id=deployment_id,
            workspace_id=workspace_id,
            pipeline_id=pipeline_id,
            running_status="failure",
            runtime_deployment=runtime_deployment,
            error_message=error.public_message or str(error),
            runtime_phase="failure",
            phase_message="Failed to fetch runtime deployment status from edge runtime",
        )


async def _fetch_runtime_package(
    workspace_id: str,
    deployment_id: str,
    backend_url: Optional[str],
    backend_secret: Optional[str],
) -> Dict[str, Any]:
    resolved_backend_url = (backend_url or CORAL_BACKEND_URL or "").rstrip("/")
    if not resolved_backend_url:
        raise ValueError("CORAL_BACKEND_URL is required to fetch runtime package")

    secret = backend_secret or CORAL_BACKEND_INTERNAL_SECRET
    if not secret:
        raise ValueError(
            "CORAL_BACKEND_INTERNAL_SECRET is required to fetch runtime package"
        )

    url = (
        f"{resolved_backend_url}/api/reef/workspaces/{workspace_id}"
        f"/deployments/{deployment_id}/runtime-package/noauth"
    )
    timeout = aiohttp.ClientTimeout(total=CORAL_BACKEND_PACKAGE_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers={"X-Internal-Secret": secret}) as response:
            response.raise_for_status()
            return await response.json()


async def _report_runtime_status_to_backend(
    *,
    workspace_id: str,
    deployment_id: str,
    status_payload: Dict[str, Any],
    backend_url: Optional[str] = None,
    backend_secret: Optional[str] = None,
) -> None:
    resolved_backend_url = (backend_url or CORAL_BACKEND_URL or "").rstrip("/")
    secret = backend_secret or CORAL_BACKEND_INTERNAL_SECRET
    if not resolved_backend_url or not secret:
        return

    payload = {
        "pipeline_id": status_payload.get("pipeline_id"),
        "running_status": status_payload.get("running_status"),
        "report": status_payload.get("report"),
        "error_message": status_payload.get("error_message"),
        "deployment_revision": status_payload.get("deployment_revision"),
        "package_digest": status_payload.get("package_digest"),
        "workflow_digest": status_payload.get("workflow_digest"),
        "model_bindings_digest": status_payload.get("model_bindings_digest"),
        "runtime_phase": status_payload.get("runtime_phase"),
        "phase_message": status_payload.get("phase_message"),
        "observed_at": status_payload.get("observed_at"),
    }
    url = (
        f"{resolved_backend_url}/api/reef/workspaces/{workspace_id}"
        f"/deployments/{deployment_id}/runtime-status/noauth"
    )
    timeout = aiohttp.ClientTimeout(total=CORAL_BACKEND_PACKAGE_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            url,
            json=payload,
            headers={"X-Internal-Secret": secret},
        ) as response:
            response.raise_for_status()
            await response.text()


async def _emit_runtime_phase_to_backend(
    *,
    workspace_id: str,
    deployment_id: str,
    backend_url: Optional[str],
    backend_secret: Optional[str],
    pipeline_id: Optional[str],
    running_status: str,
    runtime_phase: str,
    phase_message: str,
    package: Optional[Dict[str, Any]] = None,
    runtime_deployment: Optional[Dict[str, Any]] = None,
    report: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> None:
    await _report_runtime_status_to_backend(
        workspace_id=workspace_id,
        deployment_id=deployment_id,
        backend_url=backend_url,
        backend_secret=backend_secret,
        status_payload=_build_runtime_deployment_response(
            deployment_id=deployment_id,
            workspace_id=workspace_id,
            pipeline_id=pipeline_id,
            running_status=running_status,
            report=report,
            runtime_deployment=runtime_deployment,
            error_message=error_message,
            runtime_phase=runtime_phase,
            phase_message=phase_message,
            package=package,
        ),
    )


def register_runtime_package_routes(
    app: FastAPI,
    stream_manager_client: StreamManagerClient,
    pipeline_cache: PipelineCache,
) -> None:
    @app.post(
        "/coral/runtime-packages/preview",
        summary="Preview runtime package materialization from CoralReefBackend",
    )
    @with_route_exceptions_async
    async def preview_runtime_package(
        request: RuntimePackagePreviewRequest,
    ) -> Dict[str, Any]:
        package = await _fetch_runtime_package(
            workspace_id=request.workspace_id,
            deployment_id=request.deployment_id,
            backend_url=request.backend_url,
            backend_secret=request.backend_secret,
        )
        return register_runtime_package(package)

    @app.post(
        "/coral/runtime-packages/initialise",
        summary="Fetch a CoralReefBackend runtime package and initialise a local pipeline",
    )
    @with_route_exceptions_async
    async def initialise_runtime_package(
        request: RuntimePackageInitialiseRequest,
    ) -> CommandResponse:
        runtime_request = RuntimeDeploymentRequest(
            workspace_id=request.workspace_id,
            backend_url=request.backend_url,
            backend_secret=request.backend_secret,
            pipeline_name=request.pipeline_name,
            existing_pipeline_id=request.existing_pipeline_id,
            auto_restart=request.auto_restart,
        )
        initialised = await _initialise_runtime_deployment(
            deployment_id=request.deployment_id,
            request=runtime_request,
            stream_manager_client=stream_manager_client,
            pipeline_cache=pipeline_cache,
        )
        return initialised["command_response"]

    @app.post(
        "/coral/runtime-deployments/{deployment_id}/initialise",
        summary="Initialise a runtime deployment identified by Coral deployment_id",
    )
    @with_route_exceptions_async
    async def initialise_runtime_deployment(
        deployment_id: str,
        request: RuntimeDeploymentRequest,
    ) -> Dict[str, Any]:
        existing = pipeline_cache.get_runtime_deployment(deployment_id)
        if existing is not None:
            existing_pipeline_id = existing["pipeline_id"]
            try:
                await stream_manager_client.terminate_pipeline(
                    pipeline_id=existing_pipeline_id
                )
            except ProcessesManagerNotFoundError:
                logger.warning(
                    "Runtime deployment {} old pipeline {} not found during initialise",
                    deployment_id,
                    existing_pipeline_id,
                )
            finally:
                try:
                    pipeline_cache.terminate(existing_pipeline_id)
                except Exception:
                    pass
        initialised = await _initialise_runtime_deployment(
            deployment_id=deployment_id,
            request=request,
            stream_manager_client=stream_manager_client,
            pipeline_cache=pipeline_cache,
        )
        status_response = await _get_runtime_deployment_status(
            deployment_id=deployment_id,
            workspace_id=request.workspace_id,
            stream_manager_client=stream_manager_client,
            pipeline_cache=pipeline_cache,
        )
        try:
            await _report_runtime_status_to_backend(
                workspace_id=request.workspace_id,
                deployment_id=deployment_id,
                status_payload=status_response,
                backend_url=request.backend_url,
                backend_secret=request.backend_secret,
            )
        except Exception as error:
            logger.warning(
                "Failed to report runtime deployment status to backend after initialise. "
                "deployment_id={} error={}",
                deployment_id,
                error,
            )
        return {
            **status_response,
            "command_response": initialised["command_response"],
            "package": initialised["package"],
        }

    @app.post(
        "/coral/runtime-deployments/{deployment_id}/restart",
        summary="Restart a runtime deployment identified by Coral deployment_id",
    )
    @with_route_exceptions_async
    async def restart_runtime_deployment(
        deployment_id: str,
        request: RuntimeDeploymentRequest,
    ) -> Dict[str, Any]:
        existing = pipeline_cache.get_runtime_deployment(deployment_id)
        existing_pipeline_id = None
        if existing is not None:
            existing_pipeline_id = existing["pipeline_id"]
            try:
                await stream_manager_client.terminate_pipeline(
                    pipeline_id=existing_pipeline_id
                )
            except ProcessesManagerNotFoundError:
                logger.warning(
                    "Runtime deployment {} old pipeline {} not found during restart",
                    deployment_id,
                    existing_pipeline_id,
                )
            finally:
                try:
                    pipeline_cache.terminate(existing_pipeline_id)
                except Exception:
                    pass

        runtime_request = RuntimeDeploymentRequest(
            workspace_id=request.workspace_id,
            backend_url=request.backend_url,
            backend_secret=request.backend_secret,
            pipeline_name=request.pipeline_name,
            existing_pipeline_id=existing_pipeline_id,
            auto_restart=request.auto_restart,
        )
        initialised = await _initialise_runtime_deployment(
            deployment_id=deployment_id,
            request=runtime_request,
            stream_manager_client=stream_manager_client,
            pipeline_cache=pipeline_cache,
        )
        status_response = await _get_runtime_deployment_status(
            deployment_id=deployment_id,
            workspace_id=request.workspace_id,
            stream_manager_client=stream_manager_client,
            pipeline_cache=pipeline_cache,
        )
        try:
            await _report_runtime_status_to_backend(
                workspace_id=request.workspace_id,
                deployment_id=deployment_id,
                status_payload=status_response,
                backend_url=request.backend_url,
                backend_secret=request.backend_secret,
            )
        except Exception as error:
            logger.warning(
                "Failed to report runtime deployment status to backend after restart. "
                "deployment_id={} error={}",
                deployment_id,
                error,
            )
        return {
            **status_response,
            "command_response": initialised["command_response"],
        }

    @app.post(
        "/coral/runtime-deployments/{deployment_id}/terminate",
        summary="Terminate a runtime deployment identified by Coral deployment_id",
    )
    @with_route_exceptions_async
    async def terminate_runtime_deployment(
        deployment_id: str,
        request: RuntimeDeploymentRequest,
    ) -> Dict[str, Any]:
        existing = pipeline_cache.get_runtime_deployment(deployment_id)
        if existing is None:
            return _build_runtime_deployment_response(
                deployment_id=deployment_id,
                workspace_id=request.workspace_id,
                pipeline_id=None,
                running_status="stopped",
                runtime_phase="stopped",
                phase_message="Runtime deployment already stopped",
            )

        pipeline_id = existing["pipeline_id"]
        try:
            response = await stream_manager_client.terminate_pipeline(
                pipeline_id=pipeline_id
            )
        except ProcessesManagerNotFoundError:
            logger.warning(
                "Runtime deployment {} pipeline {} already missing during terminate",
                deployment_id,
                pipeline_id,
            )
            response = {
                "status": "success",
                "context": {"pipeline_id": pipeline_id},
            }
        try:
            pipeline_cache.terminate(pipeline_id)
        except Exception:
            pass
        status_response = {
            **_build_runtime_deployment_response(
                deployment_id=deployment_id,
                workspace_id=request.workspace_id,
                pipeline_id=None,
                running_status="stopped",
                runtime_deployment=existing,
                runtime_phase="stopped",
                phase_message="Runtime deployment terminated on edge runtime",
            ),
            "command_response": _extract_command_response(response),
        }
        try:
            await _report_runtime_status_to_backend(
                workspace_id=request.workspace_id,
                deployment_id=deployment_id,
                status_payload=status_response,
                backend_url=request.backend_url,
                backend_secret=request.backend_secret,
            )
        except Exception as error:
            logger.warning(
                "Failed to report runtime deployment status to backend after terminate. "
                "deployment_id={} error={}",
                deployment_id,
                error,
            )
        return status_response

    @app.get(
        "/coral/runtime-deployments/{deployment_id}/status",
        summary="Get status of a runtime deployment identified by Coral deployment_id",
    )
    @with_route_exceptions_async
    async def get_runtime_deployment_status(
        deployment_id: str,
        workspace_id: str,
    ) -> Dict[str, Any]:
        status_response = await _get_runtime_deployment_status(
            deployment_id=deployment_id,
            workspace_id=workspace_id,
            stream_manager_client=stream_manager_client,
            pipeline_cache=pipeline_cache,
        )
        try:
            await _report_runtime_status_to_backend(
                workspace_id=workspace_id,
                deployment_id=deployment_id,
                status_payload=status_response,
            )
        except Exception as error:
            logger.warning(
                "Failed to report runtime deployment status to backend after status query. "
                "deployment_id={} error={}",
                deployment_id,
                error,
            )
        return status_response

    @app.get(
        "/coral/runtime-deployments/{deployment_id}/results",
        summary="Consume results of a runtime deployment identified by Coral deployment_id",
    )
    @with_route_exceptions_async
    async def get_runtime_deployment_results(
        deployment_id: str,
        workspace_id: str,
        excluded_fields: Optional[List[str]] = Query(None),
    ) -> Dict[str, Any]:
        runtime_deployment = pipeline_cache.get_runtime_deployment(deployment_id)
        if runtime_deployment is None:
            return _empty_consume_pipeline_response(pipeline_id=None).model_dump()

        response = await stream_manager_client.consume_pipeline_result(
            pipeline_id=runtime_deployment["pipeline_id"],
            excluded_fields=excluded_fields or [],
        )
        return response.model_dump()

    @app.get(
        "/coral/runtime-deployments/{deployment_id}/metrics",
        summary="Get metrics of a runtime deployment identified by Coral deployment_id",
    )
    @with_route_exceptions_async
    async def get_runtime_deployment_metrics(
        deployment_id: str,
        workspace_id: str,
        start_time: Optional[float] = Query(None, description="开始时间戳（秒）"),
        end_time: Optional[float] = Query(None, description="结束时间戳（秒）"),
        minutes: int = Query(
            5, description="最近几分钟的数据，当start_time和end_time为空时使用"
        ),
        level: str = Query("pipeline", description="指标级别：source 或 pipeline"),
        monitor: Any = Depends(get_monitor),
    ) -> Dict[str, Any]:
        return await _get_runtime_deployment_metrics(
            deployment_id=deployment_id,
            workspace_id=workspace_id,
            pipeline_cache=pipeline_cache,
            monitor=monitor,
            start_time=start_time,
            end_time=end_time,
            minutes=minutes,
            level=level,
        )

    @app.get(
        "/coral/runtime-packages/{deployment_id}",
        summary="Inspect registered runtime package in local Coral-Inference process",
    )
    @with_route_exceptions_async
    async def get_registered_runtime_package(deployment_id: str) -> Dict[str, Any]:
        package = get_runtime_deployment(deployment_id)
        if package is None:
            return {"status": "not_found", "deployment_id": deployment_id}
        return package
