from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Union, Dict, Any

import numpy as np

from loguru import logger
from influxdb_client_3 import InfluxDBClient3, Point

from inference.core.interfaces.camera.entities import VideoFrame
from inference.core.interfaces.stream.utils import wrap_in_list


from coral_inference.core.env import (
    INFLUXDB_METRICS_URL,
    INFLUXDB_METRICS_TOKEN,
    INFLUXDB_METRICS_DATABASE,
)


def _ns_between(now: datetime, then: Optional[datetime]) -> int:
    if then is None:
        return 0
    # 确保时区一致，统一使用 UTC
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta = now - then
    # 以纳秒返回
    return int(delta.total_seconds() * 1_000_000_000)


def _extract_fields_from_prediction(pred: Optional[dict], selected_fields: List[str]) -> Dict[str, Any]:
    if not pred:
        return {}
    result: Dict[str, Any] = {}
    for field in selected_fields:
        # 支持点号路径 e.g. "metrics.count"
        try:
            value: Any = pred
            for part in field.split("."):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    value = None
                    break
            if value is not None:
                result[field] = value
        except Exception:
            # 忽略单字段解析错误
            continue
    return result


class MetricSink:
    @classmethod
    def init(
        cls,
        pipeline_id: str,
        selected_fields: Optional[List[str]] = None,
        measurement: str = "pipeline_metrics",
        queue_size: int = 1000,
    ) -> "MetricSink":
        return cls(
            pipeline_id=pipeline_id,
            selected_fields=selected_fields or [],
            measurement=measurement,
            queue_size=queue_size,
        )

    def __init__(
        self,
        pipeline_id: str,
        selected_fields: List[str],
        measurement: str,
        queue_size: int = 1000,
    ):
        self._pipeline_id = pipeline_id
        self._selected_fields = selected_fields
        self._measurement = measurement
        self._enabled = False
        self._client: Optional[InfluxDBClient3] = None  # type: ignore
        
        # 异步处理队列和线程管理
        self._metrics_queue = queue.Queue(maxsize=queue_size)
        self._worker_thread = None
        self._shutdown_event = threading.Event()
        self._batch_size = min(50, max(1, queue_size // 20))  # 批处理大小

        # InfluxDB 3 使用 host/token/database；这里将 METRICS_DATABASE 作为 database 使用
        if not (INFLUXDB_METRICS_TOKEN and INFLUXDB_METRICS_URL and INFLUXDB_METRICS_DATABASE):
            logger.warning(
                "Missing InfluxDB env (INFLUXDB_METRICS_URL/INFLUXDB_METRICS_TOKEN/INFLUXDB_METRICS_DATABASE). MetricSink disabled."
            )
            return

        try:
            self._client = InfluxDBClient3(
                host=INFLUXDB_METRICS_URL,
                token=INFLUXDB_METRICS_TOKEN,
                database=INFLUXDB_METRICS_DATABASE,
            )
            
            # 测试连接
            try:
                # 尝试一个简单的查询来验证连接
                test_result = self._client.query("SELECT 1 as connection_test")
                logger.info("MetricSink InfluxDB 连接验证成功")
            except Exception as test_error:
                logger.warning(f"MetricSink InfluxDB 连接测试失败: {test_error}")
                # 对于新数据库，这可能是正常的
            
            self._enabled = True
            logger.info(
                f"MetricSink (v3) enabled for pipeline_id={pipeline_id}, database={INFLUXDB_METRICS_DATABASE}, queue_size={queue_size}"
            )
            
            # 启动后台工作线程
            self._start_worker_thread()
        except Exception as error:
            logger.exception(f"Failed to initialise InfluxDB 3 client: {error}")
            self._enabled = False

    def close(self) -> None:
        """优雅关闭，等待队列处理完毕"""
        try:
            if self._enabled:
                logger.info(f"MetricSink closing for pipeline {self._pipeline_id}")
                self._shutdown_event.set()
                
                # 等待工作线程处理完队列中的数据
                if self._worker_thread and self._worker_thread.is_alive():
                    self._worker_thread.join(timeout=5.0)
                    if self._worker_thread.is_alive():
                        logger.warning(f"MetricSink worker thread did not finish within timeout")
                
            if self._client is not None:
                self._client.close()
        except Exception as e:
            logger.error(f"Error closing MetricSink: {e}")

    def on_prediction(
        self,
        predictions: Union[dict, List[Optional[dict]]],
        video_frame: Union[VideoFrame, List[Optional[VideoFrame]]],
    ) -> None:
        """异步推送指标数据到处理队列"""
        if not self._enabled:
            return
        
        try:
            # 将数据打包推送到队列
            queue_item = {
                'predictions': predictions,
                'video_frame': video_frame,
                'timestamp': datetime.now(timezone.utc)
            }
            
            # 非阻塞推送，避免阻塞主线程
            try:
                self._metrics_queue.put_nowait(queue_item)
            except queue.Full:
                logger.warning(f"Metrics queue full, dropping metrics for pipeline {self._pipeline_id}")
                
        except Exception as e:
            logger.error(f"Error in MetricSink.on_prediction: {e}")
    
    def _start_worker_thread(self):
        """启动后台工作线程"""
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=False,
            name=f"MetricSink-{self._pipeline_id}"
        )
        self._worker_thread.start()
        logger.info(f"Started metrics sink worker thread for pipeline {self._pipeline_id}")
    
    def _worker_loop(self):
        """后台工作线程主循环 - 批处理指标数据"""
        logger.info(f"Metrics sink worker thread started for pipeline {self._pipeline_id}")
        
        while not self._shutdown_event.is_set():
            try:
                # 批量获取队列项
                batch_items = self._get_batch_items()
                if not batch_items:
                    continue
                
                # 批量处理指标数据
                self._process_batch_metrics(batch_items)
                
                # 批量标记任务完成
                for _ in batch_items:
                    self._metrics_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error in metrics sink worker loop: {e}")
                
        # 处理剩余队列中的数据
        logger.info(f"Processing remaining metrics queue items for pipeline {self._pipeline_id}...")
        remaining_items = []
        while True:
            try:
                queue_item = self._metrics_queue.get_nowait()
                remaining_items.append(queue_item)
            except queue.Empty:
                break
        
        if remaining_items:
            self._process_batch_metrics(remaining_items)
            for _ in remaining_items:
                self._metrics_queue.task_done()
                
        logger.info(f"Metrics sink worker thread finished for pipeline {self._pipeline_id}")
    
    def _get_batch_items(self) -> List[Dict]:
        """批量获取队列项，提升InfluxDB写入效率"""
        batch_items = []
        
        # 至少获取一个项目，带超时
        try:
            first_item = self._metrics_queue.get(timeout=1.0)
            batch_items.append(first_item)
        except queue.Empty:
            return batch_items
        
        # 尽量获取更多项目组成批次
        for _ in range(self._batch_size - 1):
            try:
                item = self._metrics_queue.get_nowait()
                batch_items.append(item)
            except queue.Empty:
                break
                
        return batch_items
    
    def _process_batch_metrics(self, batch_items: List[Dict]) -> None:
        """批量处理指标数据，提升InfluxDB写入性能"""
        if not batch_items or not self._enabled:
            return
            
        try:
            points = []
            
            for queue_item in batch_items:
                points.extend(self._create_points_from_item(queue_item))
            
            # 批量写入InfluxDB
            if points and self._client:
                self._client.write(points)
                
        except Exception as e:
            logger.error(f"Error in batch metrics processing: {e}")
    
    def _create_points_from_item(self, queue_item: Dict) -> List[Point]:
        """从队列项创建InfluxDB Points"""
        points = []
        
        try:
            predictions = queue_item['predictions']
            video_frame = queue_item['video_frame'] 
            now = queue_item['timestamp']
            
            frames = wrap_in_list(element=video_frame)
            preds = wrap_in_list(element=predictions)
            
            for single_frame, single_pred in zip(frames, preds):
                if single_frame is None:
                    continue

                source_id = single_frame.source_id
                duration_ns = _ns_between(now, single_frame.frame_timestamp)

                fields: Dict[str, Any] = {}
                # 从配置中提取字段
                fields.update(_extract_fields_from_prediction(single_pred, self._selected_fields))
                # 补充 duration 字段（纳秒）
                fields["duration"] = duration_ns

                try:
                    # 构建 Point（InfluxDB 3 客户端）
                    p = Point(self._measurement)
                    # tags
                    p = p.tag("pipeline_id", self._pipeline_id)
                    if source_id is not None:
                        p = p.tag("source_id", str(source_id))
                    # fields
                    for k, v in fields.items():
                        if isinstance(v, (int, bool)):
                            p = p.field(k, v)
                        elif isinstance(v, float):
                            p = p.field(k, str(round(v, 2)))
                        elif v is None:
                            continue
                        else:
                            p = p.field(k, str(v))
                    # timestamp 使用帧时间，若无则使用 now
                    ts = single_frame.frame_timestamp or now
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    p = p.time(ts)

                    points.append(p)
                except Exception as point_error:
                    logger.warning(f"Failed to create metric point: {point_error}")
                    
        except Exception as e:
            logger.error(f"Error creating points from metrics item: {e}")
            
        return points
