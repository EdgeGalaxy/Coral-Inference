from __future__ import annotations

import threading
from queue import Queue, Empty, Full
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Union, Dict, Any

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
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta = now - then
    return int(delta.total_seconds() * 1_000_000_000)


def _extract_fields_from_prediction(pred: Optional[dict], selected_fields: List[str]) -> Dict[str, Any]:
    if not pred:
        return {}
    result: Dict[str, Any] = {}
    for field in selected_fields:
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
            continue
    return result


class MetricSink:
    @classmethod
    def init(
        cls,
        pipeline_id: str,
        selected_fields: Optional[List[str]] = None,
        measurement: str = "pipeline_metrics",
        queue_maxsize: int = 500,
        queue_policy: str = "drop_oldest",  # drop_oldest | drop_newest | block
        batch_size: int = 100,
        flush_interval_s: float = 1.0,
    ) -> "MetricSink":
        return cls(
            pipeline_id=pipeline_id,
            selected_fields=selected_fields or [],
            measurement=measurement,
            queue_maxsize=queue_maxsize,
            queue_policy=queue_policy,
            batch_size=batch_size,
            flush_interval_s=flush_interval_s,
        )

    def __init__(
        self,
        pipeline_id: str,
        selected_fields: List[str],
        measurement: str,
        queue_maxsize: int = 500,
        queue_policy: str = "drop_oldest",
        batch_size: int = 100,
        flush_interval_s: float = 1.0,
    ):
        self._pipeline_id = pipeline_id
        self._selected_fields = selected_fields
        self._measurement = measurement

        self._enabled = False
        self._client: Optional[InfluxDBClient3] = None  # type: ignore

        # 异步控制
        self._q: Queue = Queue(maxsize=max(1, queue_maxsize))
        self._queue_policy = queue_policy
        self._stop_event = threading.Event()
        self._sentinel = object()
        self._worker: Optional[threading.Thread] = None

        # 批量参数与指标
        self._batch_size = max(1, batch_size)
        self._flush_interval = max(0.05, flush_interval_s)
        self._enqueued = 0
        self._dropped = 0
        self._errors = 0

        # 只有在环境齐备时才启用
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
            try:
                _ = self._client.query("SELECT 1 as connection_test LIMIT 1")
                logger.info("MetricSink InfluxDB 连接验证成功")
            except Exception as test_err:
                logger.warning(f"MetricSink InfluxDB 连接测试失败: {test_err}")
            self._enabled = True

            # 启动后台线程
            self._worker = threading.Thread(
                target=self._worker_loop,
                name=f"MetricSinkWorker-{pipeline_id}",
                daemon=True,
            )
            self._worker.start()
            logger.info(
                f"MetricSink enabled for pipeline_id={pipeline_id}, db={INFLUXDB_METRICS_DATABASE}, "
                f"queue_maxsize={queue_maxsize}, policy={queue_policy}, batch_size={self._batch_size}, "
                f"flush_interval_s={self._flush_interval}"
            )
        except Exception as error:
            logger.exception(f"Failed to initialise InfluxDB 3 client: {error}")
            self._enabled = False

    def _build_point(self, single_frame: Optional[VideoFrame], single_pred: Optional[dict], now: datetime) -> Optional[Point]:
        try:
            if single_frame is None:
                return None

            source_id = single_frame.source_id
            duration_ns = _ns_between(now, single_frame.frame_timestamp)

            fields: Dict[str, Any] = {}
            fields.update(_extract_fields_from_prediction(single_pred, self._selected_fields))
            fields["duration"] = duration_ns

            p = Point(self._measurement)
            p = p.tag("pipeline_id", self._pipeline_id)
            if source_id is not None:
                p = p.tag("source_id", str(source_id))

            for k, v in fields.items():
                if isinstance(v, (int, bool)):
                    p = p.field(k, v)
                elif isinstance(v, float):
                    # InfluxDB 3 有时对float精度/类型较敏感，这里统一为字符串（与旧实现一致）
                    p = p.field(k, str(round(v, 2)))
                elif v is None:
                    continue
                else:
                    p = p.field(k, str(v))

            ts = single_frame.frame_timestamp or now
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            p = p.time(ts)
            return p
        except Exception as e:
            self._errors += 1
            logger.warning(f"Build metric point failed: {e}")
            return None

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
            task = {"frame": single_frame, "pred": single_pred, "now": now}
            try:
                self._q.put_nowait(task)
                self._enqueued += 1
            except Full:
                if self._queue_policy == "drop_oldest":
                    try:
                        _ = self._q.get_nowait()
                        self._dropped += 1
                    except Empty:
                        pass
                    try:
                        self._q.put_nowait(task)
                        self._enqueued += 1
                    except Full:
                        self._dropped += 1
                elif self._queue_policy == "drop_newest":
                    self._dropped += 1
                else:  # block
                    try:
                        self._q.put(task, timeout=0.1)
                        self._enqueued += 1
                    except Full:
                        self._dropped += 1

    def _worker_loop(self):
        logger.info(f"MetricSink worker started for pipeline {self._pipeline_id}")
        last_log = datetime.now(timezone.utc)
        batch: List[Point] = []
        last_flush_at = datetime.now(timezone.utc)

        try:
            while not self._stop_event.is_set():
                time_left = self._flush_interval - (datetime.now(timezone.utc) - last_flush_at).total_seconds()
                timeout = max(0.05, min(self._flush_interval, time_left)) if batch else self._flush_interval

                try:
                    item = self._q.get(timeout=timeout)
                except Empty:
                    item = None

                if item is self._sentinel:
                    break

                if item:
                    try:
                        frame = item.get("frame")
                        pred = item.get("pred")
                        now = item.get("now", datetime.now(timezone.utc))
                        p = self._build_point(frame, pred, now)
                        if p is not None:
                            batch.append(p)
                    except Exception as e:
                        self._errors += 1
                        logger.warning(f"MetricSink worker item error: {e}")

                # 条件触发flush：达到批量或到达时间窗口
                need_flush = len(batch) >= self._batch_size or (
                    batch and (datetime.now(timezone.utc) - last_flush_at).total_seconds() >= self._flush_interval
                )
                if need_flush:
                    self._flush_batch(batch)
                    batch.clear()
                    last_flush_at = datetime.now(timezone.utc)

                # 周期日志
                if (datetime.now(timezone.utc) - last_log).total_seconds() >= 30:
                    last_log = datetime.now(timezone.utc)
                    logger.info(
                        f"[MetricSink] qsize={self._q.qsize()} enq={self._enqueued} drop={self._dropped} errors={self._errors}"
                    )

            # 收到停止信号，flush剩余批次
            if batch:
                self._flush_batch(batch)
                batch.clear()

        except Exception as e:
            self._errors += 1
            logger.error(f"MetricSink worker crashed: {e}")
        finally:
            logger.info(f"MetricSink worker exiting for pipeline {self._pipeline_id}")

    def _flush_batch(self, batch: List[Point]) -> None:
        if not batch or not self._client:
            return
        try:
            # 为兼容性起见，逐条写入（避免因write(list)签名差异导致失败）
            self._client.write(batch)
        except Exception as e:
            self._errors += 1
            logger.warning(f"MetricSink flush batch failed (size={len(batch)}): {e}")

    def close(self) -> None:
        # 优雅关闭后台线程并关闭客户端
        try:
            if not self._enabled:
                if self._client:
                    try:
                        self._client.close()
                    except Exception:
                        pass
                return

            if self._stop_event.is_set():
                # 避免重复关闭
                if self._client:
                    try:
                        self._client.close()
                    except Exception:
                        pass
                return

            self._stop_event.set()
            try:
                self._q.put_nowait(self._sentinel)
            except Full:
                try:
                    _ = self._q.get_nowait()
                except Empty:
                    pass
                try:
                    self._q.put_nowait(self._sentinel)
                except Full:
                    pass

            if self._worker and self._worker.is_alive():
                self._worker.join(timeout=5.0)
        except Exception as e:
            logger.warning(f"MetricSink close exception: {e}")
        finally:
            try:
                if self._client:
                    self._client.close()
            except Exception:
                pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass