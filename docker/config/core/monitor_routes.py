import time
from datetime import datetime
from typing import List, Dict, Optional

from fastapi import FastAPI, Query, Depends
from fastapi.exceptions import HTTPException
from pydantic import BaseModel

from inference.core.interfaces.http.http_api import with_route_exceptions

from core.monitor import PipelineMonitor
from core.routing_utils import get_monitor


class MetricsResponse(BaseModel):
    dates: List[str]
    datasets: List[Dict]


def register_monitor_routes(app: FastAPI) -> None:
    @app.get(
        "/inference_pipelines/{pipeline_id}/metrics",
        response_model=MetricsResponse,
        summary="获取Pipeline指标数据",
        description="获取指定时间范围内的Pipeline指标数据，用于图表展示",
    )
    @with_route_exceptions
    async def get_pipeline_metrics(
        pipeline_id: str,
        start_time: Optional[float] = Query(None, description="开始时间戳（秒）"),
        end_time: Optional[float] = Query(None, description="结束时间戳（秒）"),
        minutes: Optional[int] = Query(5, description="最近几分钟的数据，当start_time和end_time为空时使用"),
        monitor: PipelineMonitor = Depends(get_monitor),
    ) -> MetricsResponse:
        try:
            if start_time is None or end_time is None:
                end_time = time.time()
                start_time = end_time - (minutes * 60)
            metrics = await monitor.get_metrics_by_timerange(pipeline_id, start_time, end_time)
            dates: List[str] = []
            throughput_data: List[float] = []
            source_states: Dict[str, Dict[str, List]] = {}
            for metric in metrics:
                date_str = datetime.fromtimestamp(metric["timestamp"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
                dates.append(date_str)
                throughput_data.append(metric["throughput"])
                for source in metric["sources"]:
                    source_id = source["source_id"]
                    if source_id not in source_states:
                        source_states[source_id] = {
                            "frame_decoding_latency": [],
                            "inference_latency": [],
                            "e2e_latency": [],
                            "states": [],
                        }
                    source_states[source_id]["frame_decoding_latency"].append(source.get("frame_decoding_latency", 0))
                    source_states[source_id]["inference_latency"].append(source.get("inference_latency", 0))
                    source_states[source_id]["e2e_latency"].append(source.get("e2e_latency", 0))
                    source_states[source_id]["states"].append(source.get("state", "unknown"))
            datasets = [{"name": "Throughput", "data": throughput_data}]
            for source_id, data in source_states.items():
                datasets.append({"name": f"Frame Decoding Latency ({source_id})", "data": data["frame_decoding_latency"]})
                datasets.append({"name": f"Inference Latency ({source_id})", "data": data["inference_latency"]})
                datasets.append({"name": f"E2E Latency ({source_id})", "data": data["e2e_latency"]})
                datasets.append({"name": f"State ({source_id})", "data": data["states"]})
            return MetricsResponse(dates=dates, datasets=datasets)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post(
        "/monitor/flush-cache",
        summary="手动刷新监控器缓存",
        description="手动将监控器缓存中的数据刷新到文件系统",
    )
    @with_route_exceptions
    async def flush_monitor_cache(monitor: PipelineMonitor = Depends(get_monitor)):
        try:
            await monitor.flush_cache()
            return {"status": "success", "message": "缓存数据已成功刷新到文件"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"刷新缓存失败: {str(e)}")

    @app.get(
        "/monitor/status",
        summary="获取监控器状态",
        description="获取当前监控器的运行状态",
    )
    @with_route_exceptions
    async def get_monitor_status(monitor: PipelineMonitor = Depends(get_monitor)):
        try:
            return {
                "status": "success",
                "data": {
                    "running": monitor.running,
                    "output_dir": str(monitor.output_dir),
                    "poll_interval": monitor.poll_interval,
                    "pipeline_count": len(monitor.pipeline_ids_mapper),
                    "cached_metrics_count": sum(
                        len(metrics) for metrics in monitor.metrics_collector.metrics_cache.values()
                    ),
                    "cached_results_count": sum(
                        len(results) for results in monitor.results_collector.results_cache.values()
                    ),
                },
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

    @app.get(
        "/monitor/disk-usage",
        summary="获取磁盘使用状态",
        description="获取当前监控器的磁盘使用情况",
    )
    @with_route_exceptions
    async def get_disk_usage(monitor: PipelineMonitor = Depends(get_monitor)):
        try:
            disk_info = await monitor.cleanup_manager.get_disk_usage_info()
            return {"status": "success", "data": disk_info}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取磁盘使用状态失败: {str(e)}")

    @app.post(
        "/monitor/cleanup",
        summary="手动触发磁盘清理",
        description="手动触发磁盘清理，根据磁盘使用情况删除旧的结果文件",
    )
    @with_route_exceptions
    async def trigger_cleanup(monitor: PipelineMonitor = Depends(get_monitor)):
        try:
            await monitor.cleanup_manager.check_disk_usage_and_cleanup()
            return {"status": "success", "message": "磁盘清理已完成"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"磁盘清理失败: {str(e)}")


