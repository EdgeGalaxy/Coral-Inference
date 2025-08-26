from __future__ import annotations

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
    ) -> "MetricSink":
        return cls(
            pipeline_id=pipeline_id,
            selected_fields=selected_fields or [],
            measurement=measurement,
        )

    def __init__(
        self,
        pipeline_id: str,
        selected_fields: List[str],
        measurement: str,
    ):
        self._pipeline_id = pipeline_id
        self._selected_fields = selected_fields
        self._measurement = measurement
        self._enabled = False
        self._client: Optional[InfluxDBClient3] = None  # type: ignore

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
                test_result = self._client.query("SELECT 1 as connection_test LIMIT 1")
                logger.info("MetricSink InfluxDB 连接验证成功")
            except Exception as test_error:
                logger.warning(f"MetricSink InfluxDB 连接测试失败: {test_error}")
                # 对于新数据库，这可能是正常的
            
            self._enabled = True
            logger.info(
                f"MetricSink (v3) enabled for pipeline_id={pipeline_id}, database={INFLUXDB_METRICS_DATABASE}"
            )
        except Exception as error:
            logger.exception(f"Failed to initialise InfluxDB 3 client: {error}")
            self._enabled = False

    def close(self) -> None:
        try:
            if self._client is not None:
                self._client.close()
        except Exception:
            pass

    def on_prediction(
        self,
        predictions: Union[dict, List[Optional[dict]]],
        video_frame: Union[VideoFrame, List[Optional[VideoFrame]]],
    ) -> None:
        if not self._enabled:
            return

        frames = wrap_in_list(element=video_frame)
        preds = wrap_in_list(element=predictions)
        now = datetime.now(timezone.utc)

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
                    if isinstance(v, (int, float, bool)):
                        p = p.field(k, v)
                    elif v is None:
                        continue
                    else:
                        p = p.field(k, str(v))
                # timestamp 使用帧时间，若无则使用 now
                ts = single_frame.frame_timestamp or now
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                p = p.time(ts)

                # InfluxDB 3 简单写入
                assert self._client is not None
                self._client.write(p)
            except Exception as error:
                logger.warning(f"Failed to write metric point: {error}")
