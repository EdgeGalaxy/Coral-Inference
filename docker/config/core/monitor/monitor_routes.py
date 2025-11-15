import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any, Union

from fastapi import FastAPI, Query, Depends
from fastapi.exceptions import HTTPException
from pydantic import BaseModel, Field, validator
from loguru import logger

from inference.core.interfaces.http.http_api import with_route_exceptions_async

from .influxdb_service import influx_client, metrics_processor, InfluxQueryParams
from .custom_metrics_routes import register_custom_metrics_routes
from .monitor_optimized_influxdb import OptimizedPipelineMonitorWithInfluxDB
from ..routing_utils import get_monitor
from coral_inference.webapp import MonitorService


# ==================== Request Models ====================


class MetricsQueryParams(BaseModel):
    """指标查询参数模型"""

    start_time: Optional[float] = Field(None, description="开始时间戳（秒）", ge=0)
    end_time: Optional[float] = Field(None, description="结束时间戳（秒）", ge=0)
    minutes: Optional[int] = Field(5, description="最近几分钟的数据", ge=1, le=1440)

    @validator("end_time")
    def validate_time_range(cls, v, values):
        if "start_time" in values and values["start_time"] and v:
            if v <= values["start_time"]:
                raise ValueError("end_time must be greater than start_time")
        return v


class MetricsSummaryQueryParams(BaseModel):
    """指标摘要查询参数模型"""

    start_time: Optional[float] = Field(None, description="开始时间戳（秒）", ge=0)
    end_time: Optional[float] = Field(None, description="结束时间戳（秒）", ge=0)
    minutes: Optional[int] = Field(30, description="最近几分钟的数据", ge=1, le=1440)
    aggregation_window: Optional[str] = Field(
        "1m", description="聚合窗口", pattern=r"^\d+[smhd]$"
    )

    @validator("aggregation_window")
    def validate_aggregation_window(cls, v):
        valid_windows = [
            "1s",
            "10s",
            "30s",
            "1m",
            "5m",
            "10m",
            "15m",
            "30m",
            "1h",
            "2h",
            "6h",
            "12h",
            "1d",
        ]
        if v not in valid_windows:
            raise ValueError(
                f'aggregation_window must be one of: {", ".join(valid_windows)}'
            )
        return v


# ==================== Response Models ====================


class MetricsDataset(BaseModel):
    """指标数据集模型"""

    name: str = Field(..., description="数据集名称")
    data: List[Union[float, int, str]] = Field(..., description="数据点列表")


class MetricsResponse(BaseModel):
    """指标响应模型"""

    dates: List[str] = Field(..., description="时间点列表")
    datasets: List[MetricsDataset] = Field(..., description="数据集列表")


class PerformanceMetrics(BaseModel):
    """性能指标模型"""

    poll_count: int = Field(..., description="轮询次数", ge=0)
    poll_duration: float = Field(..., description="轮询持续时间（秒）", ge=0)
    last_poll_time: float = Field(..., description="最后轮询时间戳", ge=0)
    influxdb_enabled: bool = Field(..., description="是否启用InfluxDB")
    error_count: int = Field(..., description="错误计数", ge=0)
    last_error_time: float = Field(..., description="最后错误时间戳", ge=0)
    background_queue_size: int = Field(..., description="后台队列大小", ge=0)
    results_cache_size: int = Field(..., description="结果缓存大小", ge=0)
    influxdb_buffer_size: Optional[int] = Field(
        None, description="InfluxDB缓冲区大小", ge=0
    )


class MonitorStatusData(BaseModel):
    """监控器状态数据模型"""

    running: bool = Field(..., description="是否运行中")
    output_dir: str = Field(..., description="输出目录路径")
    poll_interval: float = Field(..., description="轮询间隔（秒）", gt=0)
    pipeline_count: int = Field(..., description="Pipeline数量", ge=0)
    is_healthy: bool = Field(..., description="是否健康")
    performance_metrics: PerformanceMetrics = Field(..., description="性能指标")
    influxdb_enabled: bool = Field(..., description="是否启用InfluxDB")
    influxdb_connected: bool = Field(..., description="InfluxDB是否连接")


class MonitorStatusResponse(BaseModel):
    """监控器状态响应模型"""

    status: str = Field("success", description="响应状态")
    data: MonitorStatusData = Field(..., description="状态数据")


class DiskUsageData(BaseModel):
    """磁盘使用数据模型"""

    output_dir: str = Field(..., description="输出目录路径")
    current_size_gb: float = Field(..., description="当前使用大小（GB）", ge=0)
    max_size_gb: float = Field(..., description="最大允许大小（GB）", gt=0)
    usage_percentage: float = Field(..., description="使用百分比", ge=0, le=100)
    free_space_gb: float = Field(..., description="剩余空间（GB）", ge=0)


class DiskUsageResponse(BaseModel):
    """磁盘使用响应模型"""

    status: str = Field("success", description="响应状态")
    data: DiskUsageData = Field(..., description="磁盘使用数据")


class OperationResponse(BaseModel):
    """操作响应模型"""

    status: str = Field("success", description="响应状态")
    message: str = Field(..., description="操作结果消息")


class MetricDataPoint(BaseModel):
    """指标数据点模型"""

    time: Optional[str] = Field(None, description="时间戳")
    source_id: Optional[str] = Field(None, description="源ID")
    avg_latency: Optional[float] = Field(None, description="平均延迟（ms）", ge=0)
    avg_fps: Optional[float] = Field(None, description="平均FPS", ge=0)
    total_frames: Optional[int] = Field(None, description="总帧数", ge=0)
    total_dropped: Optional[int] = Field(None, description="总丢帧数", ge=0)


class MetricsSummaryData(BaseModel):
    """指标摘要数据模型"""

    pipeline_id: str = Field(..., description="Pipeline ID")
    start_time: str = Field(..., description="开始时间")
    end_time: str = Field(..., description="结束时间")
    aggregation_window: str = Field(..., description="聚合窗口")
    data: List[MetricDataPoint] = Field(..., description="指标数据点列表")


class MetricsSummaryResponse(BaseModel):
    """指标摘要响应模型"""

    status: str = Field("success", description="响应状态")
    data: MetricsSummaryData = Field(..., description="摘要数据")


class InfluxDBStatusData(BaseModel):
    """InfluxDB状态数据模型"""

    enabled: bool = Field(..., description="是否启用")
    connected: bool = Field(..., description="是否连接")
    healthy: Optional[bool] = Field(None, description="是否健康")
    url: Optional[str] = Field(None, description="服务器地址")
    database: Optional[str] = Field(None, description="数据库/桶名称")
    measurement: Optional[str] = Field(None, description="测量表名称")
    buffer_size: Optional[int] = Field(None, description="缓冲区大小", ge=0)
    last_flush_time: Optional[float] = Field(None, description="最后刷新时间戳", ge=0)
    message: Optional[str] = Field(None, description="状态消息")


class InfluxDBStatusResponse(BaseModel):
    """InfluxDB状态响应模型"""

    status: str = Field("success", description="响应状态")
    data: InfluxDBStatusData = Field(..., description="InfluxDB状态数据")


# ==================== Error Response Models ====================


class ErrorDetail(BaseModel):
    """错误详情模型"""

    field: Optional[str] = Field(None, description="错误字段")
    message: str = Field(..., description="错误消息")
    code: Optional[str] = Field(None, description="错误代码")


class ErrorResponse(BaseModel):
    """错误响应模型"""

    status: str = Field("error", description="响应状态")
    message: str = Field(..., description="错误消息")
    details: Optional[List[ErrorDetail]] = Field(None, description="错误详情列表")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="错误时间戳",
    )


def register_monitor_routes(app: FastAPI) -> None:
    # expose MonitorService for other parts (health checks, DI)
    if not hasattr(app.state, "monitor_service"):
        app.state.monitor_service = None

    def _monitor_service_dep() -> MonitorService:
        svc = getattr(app.state, "monitor_service", None)
        if svc is None:
            raise HTTPException(status_code=503, detail="Monitor service not initialized")
        return svc
    @app.get(
        "/inference_pipelines/{pipeline_id}/metrics",
        response_model=MetricsResponse,
        summary="获取Pipeline指标数据",
        description="获取指定时间范围内的Pipeline指标数据，用于图表展示",
    )
    @with_route_exceptions_async
    async def get_pipeline_metrics(
        pipeline_id: str,
        start_time: Optional[float] = Query(None, description="开始时间戳（秒）"),
        end_time: Optional[float] = Query(None, description="结束时间戳（秒）"),
        minutes: Optional[int] = Query(
            5, description="最近几分钟的数据，当start_time和end_time为空时使用"
        ),
        level: Optional[str] = Query(
            "pipeline", description="指标级别：source 或 pipeline"
        ),
        monitor: OptimizedPipelineMonitorWithInfluxDB = Depends(get_monitor),
    ) -> MetricsResponse:
        try:
            if start_time is None or end_time is None:
                end_time = time.time()
                start_time = end_time - (minutes * 60)
            # 使用新的指标查询方法
            if monitor.influxdb_collector and monitor.influxdb_collector.enabled:
                # 从 InfluxDB 查询指标
                start_dt = datetime.fromtimestamp(start_time, tz=timezone.utc)
                end_dt = datetime.fromtimestamp(end_time, tz=timezone.utc)

                summary = await monitor.get_metrics_summary(
                    pipeline_id=pipeline_id,
                    start_time=start_dt,
                    end_time=end_dt,
                    aggregation_window="10s",  # 可以根据时间范围动态调整
                    level=level or "pipeline",
                )

                logger.info('summary', summary)

                # 转换 InfluxDB 数据为前端需要的格式
                if summary and summary.get("data"):
                    rows = summary["data"]
                    # 按时间桶聚合
                    buckets = sorted({r.get("time") for r in rows if r.get("time")})
                    dates = buckets[:]
                    datasets = []

                    if (level or "pipeline") == "pipeline":
                        # 期望每个 bucket 有一条记录
                        bucket_map = {r.get("time"): r for r in rows if r.get("time")}
                        throughput_data = [
                            float(bucket_map.get(ts, {}).get("avg_throughput", 0) or 0)
                            for ts in dates
                        ]
                        source_count_data = [
                            float(
                                bucket_map.get(ts, {}).get("avg_source_count", 0) or 0
                            )
                            for ts in dates
                        ]
                        e2e_latency_data = [
                            float(bucket_map.get(ts, {}).get("avg_e2e_latency", 0) or 0)
                            for ts in dates
                        ]
                        datasets.append({"name": "Throughput", "data": throughput_data})
                        datasets.append(
                            {"name": "Source Count", "data": source_count_data}
                        )
                        datasets.append(
                            {"name": "E2E Latency", "data": e2e_latency_data}
                        )
                    else:
                        rows_by_bucket = {}
                        for r in rows:
                            ts = r.get("time")
                            if not ts:
                                continue
                            rows_by_bucket.setdefault(ts, []).append(r)

                        sources = sorted(
                            {
                                str(r.get("source_id"))
                                for r in rows
                                if r.get("source_id") is not None
                            }
                        )
                        idx = {
                            (r.get("time"), str(r.get("source_id"))): r
                            for r in rows
                            if r.get("time") and r.get("source_id") is not None
                        }

                        for sid in sources:
                            frame_decoding = []
                            inference_lat = []
                            e2e_lat = []
                            for ts in dates:
                                rec = idx.get((ts, sid)) or {}
                                frame_decoding.append(
                                    float(
                                        rec.get("avg_frame_decoding_latency", 0)
                                        or 0
                                    )
                                )
                                inference_lat.append(
                                    float(rec.get("avg_inference_latency", 0) or 0)
                                )
                                e2e_lat.append(
                                    float(rec.get("avg_e2e_latency", 0) or 0)
                                )

                                datasets.append(
                                    {
                                        "name": f"Frame Decoding ({sid})",
                                        "data": frame_decoding,
                                    }
                                )
                                datasets.append(
                                    {
                                        "name": f"Inference Latency ({sid})",
                                        "data": inference_lat,
                                    }
                                )
                                datasets.append(
                                    {"name": f"E2E Latency ({sid})", "data": e2e_lat}
                                )

                    metrics = {"dates": dates, "datasets": datasets}
                else:
                    # 没有数据
                    metrics = {"dates": [], "datasets": []}
            else:
                # 如果没有启用 InfluxDB，返回空数据或模拟数据
                logger.warning(
                    f"InfluxDB 未启用，无法查询 Pipeline {pipeline_id} 的指标"
                )
                metrics = {"dates": [], "datasets": []}
            # 转换为 Pydantic 模型格式
            datasets = [
                MetricsDataset(name=dataset["name"], data=dataset["data"])
                for dataset in metrics.get("datasets", [])
            ]

            return MetricsResponse(dates=metrics.get("dates", []), datasets=datasets)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post(
        "/monitor/flush-cache",
        response_model=OperationResponse,
        summary="手动刷新监控器缓存",
        description="手动将监控器缓存中的数据刷新到文件系统和 InfluxDB",
        responses={500: {"model": ErrorResponse, "description": "服务器内部错误"}},
    )
    @with_route_exceptions_async
    async def flush_monitor_cache(
        monitor_service: MonitorService = Depends(_monitor_service_dep),
    ) -> OperationResponse:
        try:
            res = await monitor_service.flush_cache()
            return OperationResponse(status="success", message=res.get("message", "缓存刷新完成"))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"刷新缓存失败: {str(e)}")

    @app.get(
        "/monitor/status",
        response_model=MonitorStatusResponse,
        summary="获取监控器状态",
        description="获取当前监控器的运行状态、性能指标和健康状态",
        responses={500: {"model": ErrorResponse, "description": "服务器内部错误"}},
    )
    @with_route_exceptions_async
    async def get_monitor_status(
        monitor: OptimizedPipelineMonitorWithInfluxDB = Depends(get_monitor),
        monitor_service: MonitorService = Depends(_monitor_service_dep),
    ) -> MonitorStatusResponse:
        try:
            if hasattr(monitor_service, "status"):
                try:
                    status_payload = await monitor_service.status()
                    if status_payload and isinstance(status_payload, dict):
                        running = status_payload.get("running", getattr(monitor, "running", True))
                        pipeline_count = (
                            status_payload.get("pipeline_count")
                            if isinstance(status_payload.get("pipeline_count"), int)
                            else len(getattr(monitor, "pipeline_ids_mapper", {}))
                        )
                except Exception:
                    status_payload = None
                    running = getattr(monitor, "running", True)
                    pipeline_count = len(getattr(monitor, "pipeline_ids_mapper", {}))
            else:
                status_payload = None
                running = getattr(monitor, "running", True)
                pipeline_count = len(getattr(monitor, "pipeline_ids_mapper", {}))

            # 获取性能指标
            performance_metrics_data = await monitor.get_performance_metrics()

            # 转换为 Pydantic 模型
            performance_metrics = PerformanceMetrics(**performance_metrics_data)

            status_data = MonitorStatusData(
                running=running,
                output_dir=str(monitor.output_dir),
                poll_interval=monitor.poll_interval,
                pipeline_count=pipeline_count,
                is_healthy=monitor.is_healthy(),
                performance_metrics=performance_metrics,
                influxdb_enabled=monitor.enable_influxdb,
                influxdb_connected=(
                    monitor.influxdb_collector.enabled
                    if monitor.influxdb_collector
                    else False
                ),
            )

            return MonitorStatusResponse(status="success", data=status_data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

    @app.get(
        "/monitor/disk-usage",
        response_model=DiskUsageResponse,
        summary="获取磁盘使用状态",
        description="获取当前监控器的磁盘使用情况",
        responses={500: {"model": ErrorResponse, "description": "服务器内部错误"}},
    )
    @with_route_exceptions_async
    async def get_disk_usage(
        monitor_service: MonitorService = Depends(_monitor_service_dep),
    ) -> DiskUsageResponse:
        try:
            disk_info = await monitor_service.disk_usage()
            if not disk_info:
                disk_data = DiskUsageData(
                    output_dir="unknown",
                    current_size_gb=0,
                    max_size_gb=0,
                    usage_percentage=0,
                    free_space_gb=0,
                )
            else:
                disk_data = DiskUsageData(
                    output_dir=str(disk_info.get("output_dir", "")),
                    current_size_gb=round(float(disk_info.get("current_size_gb", 0)), 2),
                    max_size_gb=float(disk_info.get("max_size_gb", 0) or 1),
                    usage_percentage=round(float(disk_info.get("usage_percentage", 0)), 1),
                    free_space_gb=round(float(disk_info.get("free_space_gb", 0)), 2),
                )

            return DiskUsageResponse(status="success", data=disk_data)
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"获取磁盘使用状态失败: {str(e)}"
            )

    @app.post(
        "/monitor/cleanup",
        response_model=OperationResponse,
        summary="手动触发磁盘清理",
        description="手动触发磁盘清理，根据磁盘使用情况删除旧的结果文件",
        responses={500: {"model": ErrorResponse, "description": "服务器内部错误"}},
    )
    @with_route_exceptions_async
    async def trigger_cleanup(
        monitor_service: MonitorService = Depends(_monitor_service_dep),
    ) -> OperationResponse:
        try:
            res = await monitor_service.trigger_cleanup()
            return OperationResponse(status="success", message=res.get("message", "磁盘清理任务已触发"))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"磁盘清理失败: {str(e)}")

    @app.get(
        "/monitor/influxdb/status",
        response_model=InfluxDBStatusResponse,
        summary="获取InfluxDB连接状态",
        description="检查InfluxDB连接状态和可用性",
        responses={500: {"model": ErrorResponse, "description": "服务器内部错误"}},
    )
    @with_route_exceptions_async
    async def get_influxdb_status(
        monitor_service: MonitorService = Depends(_monitor_service_dep),
    ) -> InfluxDBStatusResponse:
        try:
            payload = await monitor_service.influx_status()
            status_data = InfluxDBStatusData(
                enabled=payload.get("enabled", False),
                connected=payload.get("connected", False),
                healthy=payload.get("healthy"),
                url=payload.get("url"),
                database=payload.get("database"),
                measurement=payload.get("measurement"),
                buffer_size=payload.get("buffer_size"),
                last_flush_time=payload.get("last_flush_time"),
                message=payload.get("message"),
            )

            return InfluxDBStatusResponse(status="success", data=status_data)

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"获取InfluxDB状态失败: {str(e)}"
            )

    # ==================== InfluxDB 查询接口（新增） ====================

    @app.post(
        "/metrics/query",
        summary="执行 InfluxDB 查询",
        description="执行通用的 InfluxDB 查询并返回结果",
    )
    @with_route_exceptions_async
    async def execute_influx_query(
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        执行 InfluxDB 查询

        请求体:
        {
            "measurement": "pipeline_system_metrics",
            "fields": ["throughput", "e2e_latency"],
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-02T00:00:00Z",
            "aggregation": "mean",
            "group_by": ["source_id"],
            "group_by_time": "5m",
            "tag_filters": {"pipeline_id": "abc123"}
        }
        """
        try:
            query = influx_client.build_query(
                measurement=payload["measurement"],
                fields=payload["fields"],
                start_time=datetime.fromisoformat(payload["start_time"])
                if payload.get("start_time")
                else None,
                end_time=datetime.fromisoformat(payload["end_time"])
                if payload.get("end_time")
                else None,
                aggregation=payload.get("aggregation", "mean"),
                group_by=payload.get("group_by"),
                group_by_time=payload.get("group_by_time", "5s"),
                tag_filters=payload.get("tag_filters"),
            )

            # 执行查询
            params = InfluxQueryParams(db=influx_client.database, q=query)
            resp = await influx_client.query(params, payload.get("group_by", []))

            # 转换为字典格式返回
            return {
                "results": [
                    {
                        "series": [
                            {
                                "name": s.name,
                                "columns": s.columns,
                                "values": s.values,
                                "tags": s.tags or {},
                            }
                            for s in (resp.results[0].series or [])
                        ]
                        if resp.results
                        else [],
                        "messages": resp.results[0].messages if resp.results else [],
                        "partial": resp.results[0].partial if resp.results else False,
                    }
                ],
                "error": resp.error,
            }

        except Exception as e:
            logger.exception(f"Execute query failed: {e}")
            raise HTTPException(status_code=500, detail=f"执行查询失败: {str(e)}")

    # 注册自定义指标相关路由
    register_custom_metrics_routes(app)

    @app.get(
        "/metrics/fields",
        summary="获取指标字段列表",
        description="获取指定 measurement 的所有字段",
    )
    @with_route_exceptions_async
    async def get_metrics_fields(
        measurement: str = Query(..., description="Measurement 名称"),
    ) -> List[Dict[str, Any]]:
        """获取字段列表 (SHOW FIELD KEYS)"""
        try:

            fields = await metrics_processor.get_available_metrics_via_influx(
                influx_client, measurement
            )
            return fields

        except Exception as e:
            logger.exception(f"Get fields failed: {e}")
            raise HTTPException(status_code=500, detail=f"获取字段失败: {str(e)}")

    @app.get(
        "/metrics/tag-keys",
        summary="获取标签键列表",
        description="获取指定 measurement 的所有标签键",
    )
    @with_route_exceptions_async
    async def get_metrics_tag_keys(
        measurement: str = Query(..., description="Measurement 名称"),
    ) -> List[str]:
        """获取标签键列表 (SHOW TAG KEYS)"""
        try:
            keys = await metrics_processor.get_tag_keys_via_influx(influx_client, measurement)
            return keys

        except Exception as e:
            logger.exception(f"Get tag keys failed: {e}")
            raise HTTPException(status_code=500, detail=f"获取标签键失败: {str(e)}")

    @app.get(
        "/metrics/tag-values",
        summary="获取标签值列表",
        description="获取指定标签的所有可能值",
    )
    @with_route_exceptions_async
    async def get_metrics_tag_values(
        measurement: str = Query(..., description="Measurement 名称"),
        tag: str = Query(..., description="标签名"),
    ) -> List[str]:
        """获取标签值列表 (SHOW TAG VALUES)"""
        try:
            values = await metrics_processor.get_tag_values_via_influx(
                influx_client, measurement, tag
            )
            return values

        except Exception as e:
            logger.exception(f"Get tag values failed: {e}")
            raise HTTPException(status_code=500, detail=f"获取标签值失败: {str(e)}")

    @app.post(
        "/metrics/chart-data",
        summary="获取图表数据",
        description="查询并转换为图表格式的数据",
    )
    @with_route_exceptions_async
    async def get_metrics_chart_data(
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        获取图表数据

        请求体格式同 /metrics/query
        """
        try:
            # 构建查询
            query = influx_client.build_query(
                measurement=payload["measurement"],
                fields=payload["fields"],
                start_time=datetime.fromisoformat(payload["start_time"])
                if payload.get("start_time")
                else None,
                end_time=datetime.fromisoformat(payload["end_time"])
                if payload.get("end_time")
                else None,
                aggregation=payload.get("aggregation", "mean"),
                group_by=payload.get("group_by"),
                group_by_time=payload.get("group_by_time", "5s"),
                tag_filters=payload.get("tag_filters"),
            )

            # 执行查询
            params = InfluxQueryParams(db=influx_client.database, q=query)
            resp = await influx_client.query(params, payload.get("group_by", []))

            # 转换为图表数据
            chart_data = metrics_processor.convert_to_chart_data(
                resp, payload["fields"], payload.get("group_by", [])
            )

            # 序列化 series 结构
            series = []
            if resp.results and resp.results[0].series:
                for s in resp.results[0].series:
                    series.append(
                        {
                            "name": s.name,
                            "tags": s.tags_metadata or {},
                            "columns": s.columns,
                            "values": s.values,
                        }
                    )

            return {
                "executed_query": query,
                "series": series,
                "chart_data": chart_data,
            }

        except Exception as e:
            logger.exception(f"Get chart data failed: {e}")
            raise HTTPException(status_code=500, detail=f"获取图表数据失败: {str(e)}")
