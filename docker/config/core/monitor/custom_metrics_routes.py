import asyncio
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Literal

from fastapi import FastAPI, HTTPException, Path
from fastapi import Body
from pydantic import BaseModel, Field, validator

from inference.core.env import MODEL_CACHE_DIR
from inference.core.interfaces.http.http_api import with_route_exceptions_async

from .influxdb_service import influx_client, metrics_processor, InfluxQueryParams

# =============================================================================
# SQLite 存储
# =============================================================================


ChartTypeLiteral = Literal["line", "area", "bar", "pie"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CustomMetricBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="指标名称")
    chart_type: ChartTypeLiteral = Field(
        "line", description="图表类型：line/area/bar/pie"
    )
    measurement: str = Field(..., description="Influx measurement 名称")
    fields: List[str] = Field(..., min_items=1, description="需要查询的字段")
    aggregation: Optional[str] = Field(
        "mean", description="聚合函数，例如 mean/max/min/sum"
    )
    group_by: Optional[List[str]] = Field(
        default=None, description="分组标签列表，对应 Influx tag"
    )
    group_by_time: Optional[str] = Field(
        default="5s", description="时间分组粒度，例如 5s/1m/1h"
    )
    tag_filters: Optional[Dict[str, str]] = Field(
        default=None, description="查询时附加的 tag 过滤条件"
    )
    description: Optional[str] = Field(default=None, max_length=512)
    time_range_seconds: Optional[int] = Field(
        default=900, ge=60, le=86400 * 7, description="默认查询时间范围（秒）"
    )
    refresh_interval_seconds: Optional[int] = Field(
        default=60, ge=5, le=3600, description="默认刷新间隔（秒）"
    )

    @validator("fields", pre=True)
    def validate_fields(cls, value: List[str]) -> List[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if not cleaned:
            raise ValueError("fields 不能为空")
        return cleaned


class CustomMetricCreate(CustomMetricBase):
    pass


class CustomMetricUpdate(BaseModel):
    name: Optional[str] = None
    chart_type: Optional[ChartTypeLiteral] = None
    measurement: Optional[str] = None
    fields: Optional[List[str]] = None
    aggregation: Optional[str] = None
    group_by: Optional[List[str]] = None
    group_by_time: Optional[str] = None
    tag_filters: Optional[Dict[str, str]] = None
    description: Optional[str] = None
    time_range_seconds: Optional[int] = Field(default=None, ge=60, le=86400 * 7)
    refresh_interval_seconds: Optional[int] = Field(default=None, ge=5, le=3600)


class CustomMetricResponse(CustomMetricBase):
    id: int
    created_at: str
    updated_at: str


class ChartDataPoint(BaseModel):
    timestamp: datetime
    value: float
    label: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: Dict[str, str] = Field(default_factory=dict)


class CustomMetricChartQuery(BaseModel):
    start_time: Optional[float] = Field(
        default=None, description="起始时间，Unix 时间戳（秒）"
    )
    end_time: Optional[float] = Field(
        default=None, description="结束时间，Unix 时间戳（秒）"
    )
    minutes: Optional[int] = Field(default=None, ge=1, le=24 * 60)
    group_by_time: Optional[str] = None
    aggregation: Optional[str] = None
    tag_filters: Optional[Dict[str, str]] = None

    @validator("end_time")
    def validate_range(cls, v, values):
        start = values.get("start_time")
        if v is not None and start is not None and v <= start:
            raise ValueError("end_time must be greater than start_time")
        return v


class CustomMetricChartResponse(BaseModel):
    metric: CustomMetricResponse
    executed_query: str
    time_window: Dict[str, str]
    series: List[Dict[str, Any]]
    chart_data: List[ChartDataPoint]


class CustomMetricStore:
    """负责在 SQLite 中存储自定义指标配置"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS custom_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    chart_type TEXT NOT NULL,
                    measurement TEXT NOT NULL,
                    fields_json TEXT NOT NULL,
                    aggregation TEXT,
                    group_by_json TEXT,
                    group_by_time TEXT,
                    tag_filters_json TEXT,
                    description TEXT,
                    time_range_seconds INTEGER,
                    refresh_interval_seconds INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    # -------------------- helpers --------------------

    @staticmethod
    def _loads(value: Optional[str], default):
        if value in (None, "", "null"):
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default

    def _row_to_metric(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "chart_type": row["chart_type"],
            "measurement": row["measurement"],
            "fields": self._loads(row["fields_json"], []),
            "aggregation": row["aggregation"],
            "group_by": self._loads(row["group_by_json"], None),
            "group_by_time": row["group_by_time"],
            "tag_filters": self._loads(row["tag_filters_json"], None),
            "description": row["description"],
            "time_range_seconds": row["time_range_seconds"],
            "refresh_interval_seconds": row["refresh_interval_seconds"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # -------------------- CRUD APIs --------------------

    def _list_sync(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM custom_metrics ORDER BY updated_at DESC"
            ).fetchall()
        return [self._row_to_metric(row) for row in rows]

    def _get_sync(self, metric_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM custom_metrics WHERE id = ?", (metric_id,)
            ).fetchone()
        return self._row_to_metric(row) if row else None

    def _create_sync(self, data: CustomMetricCreate) -> Dict[str, Any]:
        now = _now_iso()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO custom_metrics (
                    name, chart_type, measurement, fields_json, aggregation,
                    group_by_json, group_by_time, tag_filters_json, description,
                    time_range_seconds, refresh_interval_seconds, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.name,
                    data.chart_type,
                    data.measurement,
                    json.dumps(data.fields),
                    data.aggregation,
                    json.dumps(data.group_by) if data.group_by else None,
                    data.group_by_time,
                    json.dumps(data.tag_filters) if data.tag_filters else None,
                    data.description,
                    data.time_range_seconds,
                    data.refresh_interval_seconds,
                    now,
                    now,
                ),
            )
            metric_id = cursor.lastrowid
            conn.commit()
        return self._get_sync(metric_id)

    def _update_sync(
        self, metric_id: int, data: CustomMetricUpdate
    ) -> Optional[Dict[str, Any]]:
        existing = self._get_sync(metric_id)
        if not existing:
            return None

        payload = existing.copy()
        payload.update(data.dict(exclude_unset=True))
        updated = CustomMetricCreate(
            name=payload["name"],
            chart_type=payload["chart_type"],
            measurement=payload["measurement"],
            fields=payload["fields"],
            aggregation=payload.get("aggregation"),
            group_by=payload.get("group_by"),
            group_by_time=payload.get("group_by_time"),
            tag_filters=payload.get("tag_filters"),
            description=payload.get("description"),
            time_range_seconds=payload.get("time_range_seconds"),
            refresh_interval_seconds=payload.get("refresh_interval_seconds"),
        )
        now = _now_iso()

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE custom_metrics
                SET name=?, chart_type=?, measurement=?, fields_json=?, aggregation=?,
                    group_by_json=?, group_by_time=?, tag_filters_json=?, description=?,
                    time_range_seconds=?, refresh_interval_seconds=?, updated_at=?
                WHERE id=?
                """,
                (
                    updated.name,
                    updated.chart_type,
                    updated.measurement,
                    json.dumps(updated.fields),
                    updated.aggregation,
                    json.dumps(updated.group_by) if updated.group_by else None,
                    updated.group_by_time,
                    json.dumps(updated.tag_filters) if updated.tag_filters else None,
                    updated.description,
                    updated.time_range_seconds,
                    updated.refresh_interval_seconds,
                    now,
                    metric_id,
                ),
            )
            conn.commit()
        return self._get_sync(metric_id)

    def _delete_sync(self, metric_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM custom_metrics WHERE id = ?", (metric_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    # -------------------- async wrappers --------------------

    async def list_metrics(self) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_sync)

    async def get_metric(self, metric_id: int) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._get_sync, metric_id)

    async def create_metric(self, data: CustomMetricCreate) -> Dict[str, Any]:
        return await asyncio.to_thread(self._create_sync, data)

    async def update_metric(
        self, metric_id: int, data: CustomMetricUpdate
    ) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._update_sync, metric_id, data)

    async def delete_metric(self, metric_id: int) -> bool:
        return await asyncio.to_thread(self._delete_sync, metric_id)


# =============================================================================
# Route Registration
# =============================================================================


def _resolve_time_window(
    metric: Dict[str, Any], query: CustomMetricChartQuery
) -> Tuple[datetime, datetime]:
    if query.start_time and query.end_time:
        start = datetime.fromtimestamp(query.start_time, tz=timezone.utc)
        end = datetime.fromtimestamp(query.end_time, tz=timezone.utc)
        return start, end

    minutes = query.minutes
    if minutes is not None:
        delta = timedelta(minutes=minutes)
    else:
        seconds = metric.get("time_range_seconds") or 900
        delta = timedelta(seconds=seconds)

    end_time = datetime.now(timezone.utc)
    start_time = end_time - delta
    return start_time, end_time


def _merge_filters(
    metric_filters: Optional[Dict[str, str]], override_filters: Optional[Dict[str, str]]
) -> Optional[Dict[str, str]]:
    if not metric_filters and not override_filters:
        return None
    combined = dict(metric_filters or {})
    combined.update(override_filters or {})
    return combined


async def _execute_chart_query(
    payload: Dict[str, Any], group_by: Optional[List[str]]
) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    query = influx_client.build_query(
        measurement=payload["measurement"],
        fields=payload["fields"],
        start_time=payload.get("start_time"),
        end_time=payload.get("end_time"),
        aggregation=payload.get("aggregation"),
        group_by=group_by,
        group_by_time=payload.get("group_by_time", "5s"),
        tag_filters=payload.get("tag_filters"),
    )

    params = InfluxQueryParams(db=influx_client.database, q=query)
    response = await influx_client.query(params, group_by or [])

    series: List[Dict[str, Any]] = []
    if response.results:
        first = response.results[0]
        if first.series:
            for s in first.series:
                series.append(
                    {
                        "name": s.name,
                        "columns": s.columns,
                        "values": s.values,
                        "tags": s.tags or {},
                    }
                )

    chart_data = metrics_processor.convert_to_chart_data(
        response, payload["fields"], group_by or []
    )
    return query, series, chart_data


def register_custom_metrics_routes(app: FastAPI) -> None:
    db_path = os.environ.get(
        "CUSTOM_METRICS_DB_PATH", os.path.join(MODEL_CACHE_DIR, "custom_metrics.db")
    )
    store = CustomMetricStore(db_path=db_path)

    @app.get(
        "/custom-metrics",
        response_model=List[CustomMetricResponse],
        summary="获取自定义指标列表",
        description="返回所有已保存的自定义指标配置",
    )
    @with_route_exceptions_async
    async def list_custom_metrics():
        return await store.list_metrics()

    @app.post(
        "/custom-metrics",
        response_model=CustomMetricResponse,
        summary="创建自定义指标",
        description="保存新的指标配置",
    )
    @with_route_exceptions_async
    async def create_custom_metric(payload: CustomMetricCreate):
        return await store.create_metric(payload)

    @app.get(
        "/custom-metrics/{metric_id}",
        response_model=CustomMetricResponse,
        summary="获取自定义指标详情",
    )
    @with_route_exceptions_async
    async def get_custom_metric(metric_id: int = Path(..., ge=1)):
        metric = await store.get_metric(metric_id)
        if not metric:
            raise HTTPException(status_code=404, detail="Custom metric not found")
        return metric

    @app.put(
        "/custom-metrics/{metric_id}",
        response_model=CustomMetricResponse,
        summary="更新自定义指标",
    )
    @with_route_exceptions_async
    async def update_custom_metric(
        payload: CustomMetricUpdate, metric_id: int = Path(..., ge=1)
    ):
        metric = await store.update_metric(metric_id, payload)
        if not metric:
            raise HTTPException(status_code=404, detail="Custom metric not found")
        return metric

    @app.delete(
        "/custom-metrics/{metric_id}",
        summary="删除自定义指标",
        description="删除指定的自定义指标配置",
    )
    @with_route_exceptions_async
    async def delete_custom_metric(metric_id: int = Path(..., ge=1)):
        deleted = await store.delete_metric(metric_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Custom metric not found")
        return {"status": "success"}

    @app.post(
        "/custom-metrics/{metric_id}/chart-data",
        response_model=CustomMetricChartResponse,
        summary="获取自定义指标的图表数据",
        description="根据保存的配置查询 Influx 指标数据",
    )
    @with_route_exceptions_async
    async def get_custom_metric_chart_data(
        metric_id: int = Path(..., ge=1),
        query: CustomMetricChartQuery = Body(default_factory=CustomMetricChartQuery),
    ):
        metric = await store.get_metric(metric_id)
        if not metric:
            raise HTTPException(status_code=404, detail="Custom metric not found")

        start_time, end_time = _resolve_time_window(metric, query)
        tag_filters = _merge_filters(metric.get("tag_filters"), query.tag_filters)

        payload = {
            "measurement": metric["measurement"],
            "fields": metric["fields"],
            "start_time": start_time,
            "end_time": end_time,
            "aggregation": query.aggregation or metric.get("aggregation") or "mean",
            "group_by_time": query.group_by_time or metric.get("group_by_time") or "5s",
            "tag_filters": tag_filters,
        }

        query_str, series, chart_data = await _execute_chart_query(
            payload, metric.get("group_by")
        )

        return CustomMetricChartResponse(
            metric=CustomMetricResponse(**metric),
            executed_query=query_str,
            time_window={
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            series=series,
            chart_data=[ChartDataPoint(**point) for point in chart_data],
        )
