import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any, Union

from fastapi import FastAPI, Query, Depends
from fastapi.exceptions import HTTPException
from pydantic import BaseModel, Field, validator
from loguru import logger

from inference.core.interfaces.http.http_api import with_route_exceptions_async

from .monitor_optimized_influxdb import OptimizedPipelineMonitorWithInfluxDB
from ..routing_utils import get_monitor


# ==================== Request Models ====================

class MetricsQueryParams(BaseModel):
    """指标查询参数模型"""
    start_time: Optional[float] = Field(None, description="开始时间戳（秒）", ge=0)
    end_time: Optional[float] = Field(None, description="结束时间戳（秒）", ge=0)
    minutes: Optional[int] = Field(5, description="最近几分钟的数据", ge=1, le=1440)
    
    @validator('end_time')
    def validate_time_range(cls, v, values):
        if 'start_time' in values and values['start_time'] and v:
            if v <= values['start_time']:
                raise ValueError('end_time must be greater than start_time')
        return v


class MetricsSummaryQueryParams(BaseModel):
    """指标摘要查询参数模型"""
    start_time: Optional[float] = Field(None, description="开始时间戳（秒）", ge=0)
    end_time: Optional[float] = Field(None, description="结束时间戳（秒）", ge=0)
    minutes: Optional[int] = Field(30, description="最近几分钟的数据", ge=1, le=1440)
    aggregation_window: Optional[str] = Field("1m", description="聚合窗口", pattern=r'^\d+[smhd]$')
    
    @validator('aggregation_window')
    def validate_aggregation_window(cls, v):
        valid_windows = ['1s', '10s', '30s', '1m', '5m', '10m', '15m', '30m', '1h', '2h', '6h', '12h', '1d']
        if v not in valid_windows:
            raise ValueError(f'aggregation_window must be one of: {", ".join(valid_windows)}')
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
    influxdb_buffer_size: Optional[int] = Field(None, description="InfluxDB缓冲区大小", ge=0)


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
    max_p99_latency: Optional[float] = Field(None, description="P99最大延迟（ms）", ge=0)
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
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="错误时间戳")


def register_monitor_routes(app: FastAPI) -> None:
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
        minutes: Optional[int] = Query(5, description="最近几分钟的数据，当start_time和end_time为空时使用"),
        level: Optional[str] = Query("source", description="指标级别：source 或 pipeline"),
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
                    aggregation_window="1m",  # 可以根据时间范围动态调整
                    level=level or "source",
                )
                
                # 转换 InfluxDB 数据为前端需要的格式
                if summary and summary.get('data'):
                    rows = summary['data']
                    # 按时间桶聚合
                    buckets = sorted({r.get('time') for r in rows if r.get('time')})
                    dates = buckets[:]
                    datasets = []

                    if (level or "source") == "pipeline":
                        # 期望每个 bucket 有一条记录
                        bucket_map = {r.get('time'): r for r in rows if r.get('time')}
                        throughput_data = [float(bucket_map.get(ts, {}).get('avg_throughput', 0) or 0) for ts in dates]
                        source_count_data = [float(bucket_map.get(ts, {}).get('avg_source_count', 0) or 0) for ts in dates]
                        datasets.append({"name": "Throughput", "data": throughput_data})
                        datasets.append({"name": "Source Count", "data": source_count_data})
                    else:
                        # source 级别：每个 bucket 可能存在多个 source 条目
                        # 1) 汇总吞吐量为 sum(avg_fps)
                        rows_by_bucket = {}
                        for r in rows:
                            ts = r.get('time')
                            if not ts:
                                continue
                            rows_by_bucket.setdefault(ts, []).append(r)

                        throughput_data = []
                        for ts in dates:
                            per_bucket = rows_by_bucket.get(ts, [])
                            s = sum(float(x.get('avg_fps') or 0) for x in per_bucket)
                            throughput_data.append(s)
                        datasets.append({"name": "Throughput", "data": throughput_data})

                        # 2) 按 source_id 构建多组数据
                        sources = sorted({str(r.get('source_id')) for r in rows if r.get('source_id') is not None})
                        # 索引 (bucket, source) -> row
                        idx = {(r.get('time'), str(r.get('source_id'))): r for r in rows if r.get('time') and r.get('source_id') is not None}

                        for sid in sources:
                            latency_mean = []
                            latency_p99 = []
                            fps = []
                            frames = []
                            dropped = []
                            for ts in dates:
                                rec = idx.get((ts, sid)) or {}
                                latency_mean.append(float(rec.get('avg_latency', 0) or 0))
                                latency_p99.append(float(rec.get('max_p99_latency', 0) or 0))
                                fps.append(float(rec.get('avg_fps', 0) or 0))
                                frames.append(float(rec.get('total_frames', 0) or 0))
                                dropped.append(float(rec.get('total_dropped', 0) or 0))

                            datasets.append({"name": f"Inference Latency ({sid})", "data": latency_mean})
                            datasets.append({"name": f"Inference Latency P99 ({sid})", "data": latency_p99})
                            datasets.append({"name": f"FPS ({sid})", "data": fps})
                            datasets.append({"name": f"Frames Processed ({sid})", "data": frames})
                            datasets.append({"name": f"Dropped Frames ({sid})", "data": dropped})

                    metrics = {"dates": dates, "datasets": datasets}
                else:
                    # 没有数据
                    metrics = {"dates": [], "datasets": []}
            else:
                # 如果没有启用 InfluxDB，返回空数据或模拟数据
                logger.warning(f"InfluxDB 未启用，无法查询 Pipeline {pipeline_id} 的指标")
                metrics = {"dates": [], "datasets": []}
            # 转换为 Pydantic 模型格式
            datasets = [
                MetricsDataset(name=dataset["name"], data=dataset["data"]) 
                for dataset in metrics.get("datasets", [])
            ]
            
            return MetricsResponse(
                dates=metrics.get("dates", []), 
                datasets=datasets
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post(
        "/monitor/flush-cache",
        response_model=OperationResponse,
        summary="手动刷新监控器缓存",
        description="手动将监控器缓存中的数据刷新到文件系统和 InfluxDB",
        responses={
            500: {"model": ErrorResponse, "description": "服务器内部错误"}
        }
    )
    @with_route_exceptions_async
    async def flush_monitor_cache(
        monitor: OptimizedPipelineMonitorWithInfluxDB = Depends(get_monitor)
    ) -> OperationResponse:
        try:
            # 刷新结果缓存
            await monitor.results_collector.flush_all_caches()
            
            # 如果启用了 InfluxDB，也刷新 InfluxDB 缓冲区
            if monitor.influxdb_collector:
                await monitor.influxdb_collector.flush_buffer()
                
            message = "缓存数据已成功刷新到文件系统" + (
                " 和 InfluxDB" if monitor.influxdb_collector else ""
            )
            
            return OperationResponse(
                status="success",
                message=message
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"刷新缓存失败: {str(e)}")

    @app.get(
        "/monitor/status",
        response_model=MonitorStatusResponse,
        summary="获取监控器状态",
        description="获取当前监控器的运行状态、性能指标和健康状态",
        responses={
            500: {"model": ErrorResponse, "description": "服务器内部错误"}
        }
    )
    @with_route_exceptions_async
    async def get_monitor_status(
        monitor: OptimizedPipelineMonitorWithInfluxDB = Depends(get_monitor)
    ) -> MonitorStatusResponse:
        try:
            # 获取性能指标
            performance_metrics_data = await monitor.get_performance_metrics()
            
            # 转换为 Pydantic 模型
            performance_metrics = PerformanceMetrics(**performance_metrics_data)
            
            status_data = MonitorStatusData(
                running=monitor.running,
                output_dir=str(monitor.output_dir),
                poll_interval=monitor.poll_interval,
                pipeline_count=len(monitor.pipeline_ids_mapper),
                is_healthy=monitor.is_healthy(),
                performance_metrics=performance_metrics,
                influxdb_enabled=monitor.enable_influxdb,
                influxdb_connected=(
                    monitor.influxdb_collector.enabled 
                    if monitor.influxdb_collector else False
                )
            )
            
            return MonitorStatusResponse(
                status="success",
                data=status_data
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

    @app.get(
        "/monitor/disk-usage",
        response_model=DiskUsageResponse,
        summary="获取磁盘使用状态",
        description="获取当前监控器的磁盘使用情况",
        responses={
            500: {"model": ErrorResponse, "description": "服务器内部错误"}
        }
    )
    @with_route_exceptions_async
    async def get_disk_usage(
        monitor: OptimizedPipelineMonitorWithInfluxDB = Depends(get_monitor)
    ) -> DiskUsageResponse:
        try:
            # 计算磁盘使用情况
            current_size = await asyncio.get_event_loop().run_in_executor(
                None, 
                monitor.cleanup_manager._get_directory_size_sync, 
                monitor.output_dir
            )
            
            usage_percentage = (current_size / monitor.cleanup_manager.max_size_gb) * 100
            free_space = max(0, monitor.cleanup_manager.max_size_gb - current_size)
            
            disk_data = DiskUsageData(
                output_dir=str(monitor.output_dir),
                current_size_gb=round(current_size, 2),
                max_size_gb=monitor.cleanup_manager.max_size_gb,
                usage_percentage=round(usage_percentage, 1),
                free_space_gb=round(free_space, 2)
            )
            
            return DiskUsageResponse(
                status="success",
                data=disk_data
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取磁盘使用状态失败: {str(e)}")

    @app.post(
        "/monitor/cleanup",
        response_model=OperationResponse,
        summary="手动触发磁盘清理",
        description="手动触发磁盘清理，根据磁盘使用情况删除旧的结果文件",
        responses={
            500: {"model": ErrorResponse, "description": "服务器内部错误"}
        }
    )
    @with_route_exceptions_async
    async def trigger_cleanup(
        monitor: OptimizedPipelineMonitorWithInfluxDB = Depends(get_monitor)
    ) -> OperationResponse:
        try:
            # 触发清理任务
            await monitor.cleanup_manager.check_and_cleanup_async()
            return OperationResponse(
                status="success",
                message="磁盘清理任务已触发"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"磁盘清理失败: {str(e)}")
    
    @app.get(
        "/inference_pipelines/{pipeline_id}/metrics/summary",
        response_model=MetricsSummaryResponse,
        summary="获取Pipeline指标摘要（InfluxDB）",
        description="从InfluxDB获取指定时间范围内的Pipeline指标摘要数据",
        responses={
            500: {"model": ErrorResponse, "description": "服务器内部错误"}
        }
    )
    @with_route_exceptions_async
    async def get_pipeline_metrics_summary(
        pipeline_id: str,
        start_time: Optional[float] = Query(None, description="开始时间戳（秒）"),
        end_time: Optional[float] = Query(None, description="结束时间戳（秒）"),
        minutes: Optional[int] = Query(30, description="最近几分钟的数据，当start_time和end_time为空时使用"),
        aggregation_window: Optional[str] = Query("1m", description="聚合窗口：1m, 5m, 15m, 1h等"),
        monitor: OptimizedPipelineMonitorWithInfluxDB = Depends(get_monitor),
    ) -> MetricsSummaryResponse:
        try:
            # 验证参数
            if start_time is None or end_time is None:
                end_time = time.time()
                start_time = end_time - (minutes * 60)
            
            if start_time >= end_time:
                raise HTTPException(
                    status_code=400, 
                    detail="start_time must be less than end_time"
                )
            
            start_dt = datetime.fromtimestamp(start_time, tz=timezone.utc)
            end_dt = datetime.fromtimestamp(end_time, tz=timezone.utc)
            
            summary = await monitor.get_metrics_summary(
                pipeline_id=pipeline_id,
                start_time=start_dt,
                end_time=end_dt,
                aggregation_window=aggregation_window
            )
            
            # 转换为 Pydantic 模型
            if summary and isinstance(summary, dict):
                # 转换数据点
                data_points = [
                    MetricDataPoint(
                        time=point.get('time'),
                        source_id=point.get('source_id'),
                        avg_latency=point.get('avg_latency'),
                        max_p99_latency=point.get('max_p99_latency'),
                        avg_fps=point.get('avg_fps'),
                        total_frames=point.get('total_frames'),
                        total_dropped=point.get('total_dropped')
                    )
                    for point in summary.get('data', [])
                ]
                
                summary_data = MetricsSummaryData(
                    pipeline_id=summary.get('pipeline_id', pipeline_id),
                    start_time=summary.get('start_time', start_dt.isoformat()),
                    end_time=summary.get('end_time', end_dt.isoformat()),
                    aggregation_window=summary.get('aggregation_window', aggregation_window),
                    data=data_points
                )
            else:
                # 空响应
                summary_data = MetricsSummaryData(
                    pipeline_id=pipeline_id,
                    start_time=start_dt.isoformat(),
                    end_time=end_dt.isoformat(),
                    aggregation_window=aggregation_window,
                    data=[]
                )
            
            return MetricsSummaryResponse(
                status="success",
                data=summary_data
            )
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取指标摘要失败: {str(e)}")
            
    @app.get(
        "/monitor/influxdb/status",
        response_model=InfluxDBStatusResponse,
        summary="获取InfluxDB连接状态",
        description="检查InfluxDB连接状态和可用性",
        responses={
            500: {"model": ErrorResponse, "description": "服务器内部错误"}
        }
    )
    @with_route_exceptions_async
    async def get_influxdb_status(
        monitor: OptimizedPipelineMonitorWithInfluxDB = Depends(get_monitor)
    ) -> InfluxDBStatusResponse:
        try:
            if not monitor.influxdb_collector:
                status_data = InfluxDBStatusData(
                    enabled=False,
                    connected=False,
                    message="InfluxDB 收集器未初始化"
                )
                return InfluxDBStatusResponse(
                    status="success",
                    data=status_data
                )
            
            # 执行健康检查
            is_healthy = False
            if monitor.influxdb_collector.connection_manager:
                is_healthy = await monitor.influxdb_collector.connection_manager.health_check()
            
            status_data = InfluxDBStatusData(
                enabled=monitor.enable_influxdb,
                connected=monitor.influxdb_collector.enabled,
                healthy=is_healthy,
                url=monitor.influxdb_collector.influxdb_url,
                database=monitor.influxdb_collector.influxdb_database,
                measurement=monitor.influxdb_collector.measurement,
                buffer_size=len(monitor.influxdb_collector.metrics_buffer),
                last_flush_time=monitor.influxdb_collector.last_flush_time
            )
            
            return InfluxDBStatusResponse(
                status="success",
                data=status_data
            )
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取InfluxDB状态失败: {str(e)}")

