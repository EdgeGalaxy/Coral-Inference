"""
InfluxDB 查询服务
完整迁移自 CoralReefBackend/reef/utlis/influxdb.py
提供独立的 InfluxDB3 查询能力，不依赖 monitor_metrics_influxdb.py
"""

from collections import defaultdict
import re
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum
from loguru import logger

from influxdb_client_3 import InfluxDBClient3
from asyncer import asyncify

from coral_inference.core.env import (
    INFLUXDB_METRICS_URL,
    INFLUXDB_METRICS_TOKEN,
    INFLUXDB_METRICS_DATABASE,
)


# ==================== Enums ====================

class TimePrecision(str, Enum):
    """时间精度枚举"""
    NANOSECONDS = "ns"
    MICROSECONDS = "u"
    MILLISECONDS = "ms"
    SECONDS = "s"
    MINUTES = "m"
    HOURS = "h"


class AggregationType(str, Enum):
    """聚合类型枚举"""
    MEAN = "mean"
    SUM = "sum"
    MAX = "max"
    MIN = "min"
    COUNT = "count"
    FIRST = "first"
    LAST = "last"
    MEDIAN = "median"


# ==================== Data Classes ====================

@dataclass
class InfluxQueryParams:
    """InfluxDB 查询参数"""
    db: str
    q: str
    epoch: TimePrecision = TimePrecision.MILLISECONDS
    chunked: bool = False
    pretty: bool = False


@dataclass
class InfluxSeries:
    """InfluxDB 数据系列"""
    name: str
    columns: List[str]
    values: List[List[Any]]
    tags: Optional[Dict[str, str]] = None
    tags_metadata: Optional[Dict[str, list]] = None


@dataclass
class InfluxQueryResult:
    """InfluxDB 查询结果"""
    series: Optional[List[InfluxSeries]] = None
    messages: Optional[List[Any]] = None
    partial: bool = False


@dataclass
class InfluxResponse:
    """InfluxDB 响应"""
    results: List[InfluxQueryResult]
    error: Optional[str] = None


# ==================== InfluxDB Client ====================

class InfluxDBClient:
    """InfluxDB3 客户端工具类（仅查询，从 reef 完整迁移）"""

    def __init__(self):
        self.database = INFLUXDB_METRICS_DATABASE
        self.precision = TimePrecision.MILLISECONDS
        self.token = INFLUXDB_METRICS_TOKEN
        self.host = INFLUXDB_METRICS_URL

        # v3 客户端
        self._v3: Optional[InfluxDBClient3] = None
        if self.host and self.token and self.database:
            try:
                self._v3 = InfluxDBClient3(
                    token=self.token,
                    host=self.host,
                    database=self.database,
                )
                logger.info(
                    f"Initialized InfluxDB3 client host={self.host}, database={self.database}"
                )
            except Exception as error:
                logger.error(f"Failed to initialize InfluxDB3 client: {error}")
                self._v3 = None

    def _arrow_table_to_series(
        self, table, tag_fields: List[str], measurement_fallback: str
    ) -> List[InfluxSeries]:
        """将 PyArrow 表转换为 InfluxSeries 列表"""
        try:
            data_dict: Dict[str, List[Any]] = table.to_pydict()
            columns: List[str] = list(data_dict.keys())
            length = len(next(iter(data_dict.values()), []))
            values: List[List[Any]] = []

            # 收集所有标签的不重复值（元数据）
            tags_metadata: Dict[str, List[str]] = defaultdict(list)

            for i in range(length):
                row = []
                for col in columns:
                    if tag_fields and col in tag_fields:
                        tags_metadata[col].append(str(data_dict[col][i]))
                    row.append(data_dict[col][i])
                values.append(row)

            # 去重标签元数据
            tags_metadata = {
                tag: list(set(tag_values)) for tag, tag_values in tags_metadata.items()
            }

            # 解析 measurement 名称
            measurement = measurement_fallback

            # 如果有标签分组，按标签分组创建多个 series
            if tag_fields:
                series_list = []
                # 按标签值的组合分组数据
                groups = defaultdict(list)
                for i, row in enumerate(values):
                    # 构建当前行的标签组合
                    tag_combo = tuple(
                        str(row[columns.index(tag)])
                        for tag in tag_fields
                        if tag in columns
                    )
                    groups[tag_combo].append(row)

                for tag_combo, group_values in groups.items():
                    # 构建当前系列的具体标签值
                    current_tags = {
                        tag_fields[i]: tag_combo[i]
                        for i in range(len(tag_combo))
                        if i < len(tag_fields)
                    }

                    series_list.append(
                        InfluxSeries(
                            name=measurement,
                            columns=columns,
                            values=group_values,
                            tags=current_tags,
                            tags_metadata=tags_metadata,
                        )
                    )
                return series_list
            else:
                # 无分组，返回单个 series
                series = [
                    InfluxSeries(
                        name=measurement,
                        columns=columns,
                        values=values,
                        tags=None,
                        tags_metadata=tags_metadata,
                    )
                ]
                return series
        except Exception as error:
            logger.error(f"Failed to convert Arrow table to series: {error}")
            return []

    async def query(
        self, params: InfluxQueryParams, group_by: List[str] = None
    ) -> InfluxResponse:
        """执行查询（InfluxDB3）"""
        if self._v3 is None:
            logger.error(
                "InfluxDB3 client not initialized; missing host/token/database"
            )
            return InfluxResponse(results=[], error="influx_client_unavailable")

        try:
            query_upper = params.q.upper().strip()
            if query_upper.startswith("SHOW"):
                # InfluxQL SHOW 语句
                language = "influxql"
                logger.info(
                    f"Querying InfluxDB3 ({language}) host={self.host}, db={self.database}: {params.q}"
                )
                table = await asyncify(self._v3.query)(params.q, language=language)
                measurement = self._parse_influx_ql(params.q).get(
                    "measurement", "metrics"
                )
            elif query_upper.startswith("SELECT") and (
                "FROM" in query_upper and "GROUP BY" in query_upper
            ):
                # SQL 查询 - 用于聚合和时间分组
                language = "sql"
                logger.info(
                    f"Querying InfluxDB3 ({language}) host={self.host}, db={self.database}: {params.q}"
                )
                table = await asyncify(self._v3.query)(params.q, language=language)
                measurement = self._parse_sql_measurement(params.q)
            else:
                # 默认使用 InfluxQL
                language = "influxql"
                logger.info(
                    f"Querying InfluxDB3 ({language}) host={self.host}, db={self.database}: {params.q}"
                )
                table = await asyncify(self._v3.query)(params.q, language=language)
                measurement = self._parse_influx_ql(params.q).get(
                    "measurement", "metrics"
                )

            series = self._arrow_table_to_series(
                table, group_by or [], measurement_fallback=measurement
            )
            return InfluxResponse(
                results=[InfluxQueryResult(series=series, messages=[])]
            )
        except Exception as error:
            logger.exception(f"InfluxDB3 query error: {error}")
            return InfluxResponse(results=[], error=str(error))

    def _parse_influx_ql(self, query: str) -> Dict[str, Any]:
        """解析 InfluxQL 查询"""
        select_match = re.search(r"SELECT\s+(.*?)\s+FROM", query, re.IGNORECASE)
        from_match = re.search(r'FROM\s+"?(\w+)"?', query, re.IGNORECASE)
        where_match = re.search(
            r"WHERE\s+(.*?)(?:\s+GROUP\s+BY|$)", query, re.IGNORECASE
        )
        group_by_match = re.search(
            r"GROUP\s+BY\s+(.*?)(?:\s+ORDER\s+BY|$)", query, re.IGNORECASE
        )
        data = {
            "fields": re.findall(r"AS\s+(\w+)", select_match.group(1), re.IGNORECASE)
            if select_match
            else [],
            "measurement": from_match.group(1) if from_match else "metrics",
            "conditions": where_match.group(1) if where_match else "",
            "groupBy": group_by_match.group(1).split(",") if group_by_match else [],
        }
        return data

    def _parse_sql_measurement(self, query: str) -> str:
        """从 SQL 查询中提取 measurement 名称"""
        match = re.search(r"FROM\s+(\w+)", query, re.IGNORECASE)
        return match.group(1) if match else "metrics"

    def _parse_time_interval_to_seconds(self, time_str: str) -> int:
        """解析时间间隔字符串为秒数"""
        match = re.match(r"(\d+)([smh])", time_str.strip())
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            if unit == "s":
                return value
            elif unit == "m":
                return value * 60
            elif unit == "h":
                return value * 3600
        return 300  # 默认5分钟

    def build_query(
        self,
        measurement: str,
        fields: List[str],
        tags: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        aggregation: Union[AggregationType, str] = AggregationType.MEAN,
        group_by: Optional[List[str]] = None,
        group_by_time: str = "5s",
        tag_filters: Optional[Dict[str, str]] = None,
    ) -> str:
        """构建查询语句（SQL for InfluxDB 3）"""
        # 兼容字符串聚合参数
        if isinstance(aggregation, str):
            try:
                aggregation_enum = AggregationType(aggregation.lower())
            except Exception:
                aggregation_enum = AggregationType.MEAN
        else:
            aggregation_enum = aggregation

        # 构建 SELECT 子句 - 使用 SQL 语法
        select_parts = []
        # 时间窗口聚合需要使用 date_bin 函数
        if group_by_time:
            interval_seconds = self._parse_time_interval_to_seconds(group_by_time)
            select_parts.append(
                f"date_bin(INTERVAL '{interval_seconds} seconds', time) as time_window"
            )

        # 添加聚合字段
        for field in fields:
            if aggregation_enum == AggregationType.MEAN:
                select_parts.append(f"AVG({field}) as {field}")
            elif aggregation_enum == AggregationType.SUM:
                select_parts.append(f"SUM({field}) as {field}")
            elif aggregation_enum == AggregationType.MAX:
                select_parts.append(f"MAX({field}) as {field}")
            elif aggregation_enum == AggregationType.MIN:
                select_parts.append(f"MIN({field}) as {field}")
            elif aggregation_enum == AggregationType.COUNT:
                select_parts.append(f"COUNT({field}) as {field}")
            elif aggregation_enum == AggregationType.FIRST:
                select_parts.append(f"FIRST_VALUE({field}) as {field}")
            elif aggregation_enum == AggregationType.LAST:
                select_parts.append(f"LAST_VALUE({field}) as {field}")
            elif aggregation_enum == AggregationType.MEDIAN:
                select_parts.append(f"MEDIAN({field}) as {field}")
            else:
                select_parts.append(f"AVG({field}) as {field}")

        # 添加分组标签
        if group_by:
            select_parts.extend(group_by)

        select_clause = ", ".join(select_parts)

        # 构建 WHERE 子句 - 使用 SQL 语法
        where_conditions = []
        if start_time:
            where_conditions.append(f"time >= '{start_time}'")
        if end_time:
            where_conditions.append(f"time <= '{end_time}'")
        if tag_filters:
            for k, v in tag_filters.items():
                where_conditions.append(f"{k} = '{v}'")

        where_clause = " AND ".join(where_conditions) if where_conditions else ""

        # 构建 GROUP BY 子句 - 使用 SQL 语法
        group_by_clause = []
        if group_by_time:
            group_by_clause.append("time_window")
        if group_by:
            group_by_clause.extend(group_by)

        # 构建完整查询
        query = f"SELECT {select_clause} FROM {measurement}"
        if where_clause:
            query += f" WHERE {where_clause}"
        if group_by_clause:
            query += f" GROUP BY {', '.join(group_by_clause)}"
        if group_by_time:
            query += " ORDER BY time_window"

        return query


# ==================== Metrics Data Processor ====================

class MetricsDataProcessor:
    """指标数据处理器（从 reef 完整迁移）"""

    @staticmethod
    def convert_to_chart_data(
        influx_response: InfluxResponse,
        fields: List[str],
        group_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """将 InfluxDB 数据转换为图表数据点"""
        data_points = []
        if not influx_response.results or not influx_response.results[0].series:
            return data_points

        for series in influx_response.results[0].series:
            # 兼容 v1/v2/v3 不同时间列命名，包括 SQL 查询中的 time_window
            time_col = None
            if "time" in series.columns:
                time_col = "time"
            elif "_time" in series.columns:
                time_col = "_time"
            elif "time_window" in series.columns:
                time_col = "time_window"
            else:
                # 默认使用第一列作为时间列
                time_col = series.columns[0]

            if time_col not in series.columns:
                continue

            time_index = series.columns.index(time_col)

            # 获取分组标签列（从 group_by 参数中）
            group_by_tags = group_by or []

            for row in series.values:
                raw_t = row[time_index]
                # 处理不同的时间格式
                if isinstance(raw_t, (int, float)):
                    # 毫秒时间戳
                    if raw_t > 1e12:  # 毫秒时间戳
                        timestamp = datetime.fromtimestamp(raw_t / 1000)
                    else:  # 秒时间戳
                        timestamp = datetime.fromtimestamp(raw_t)
                else:
                    # ISO 时间字符串或其他格式
                    try:
                        timestamp = datetime.fromisoformat(
                            str(raw_t).replace("Z", "+00:00")
                        )
                    except ValueError:
                        # 如果无法解析，跳过这个数据点
                        continue

                # 构建当前数据点的标签值
                current_tags = {}
                if group_by_tags:
                    # 优先使用 series.tags 中的标签值（当前系列的具体标签值）
                    if series.tags:
                        for tag in group_by_tags:
                            if tag in series.tags:
                                current_tags[tag] = str(series.tags[tag])
                    # 如果 series.tags 中没有，再从数据列中获取
                    if not current_tags:
                        for tag in group_by_tags:
                            if tag in series.columns:
                                tag_index = series.columns.index(tag)
                                current_tags[tag] = str(row[tag_index])

                for field in fields:
                    if field in series.columns:
                        value_index = series.columns.index(field)
                        value = row[value_index]
                        if value is not None:
                            data_points.append(
                                {
                                    "timestamp": timestamp,
                                    "value": float(value),
                                    "label": field,
                                    "tags": current_tags,
                                    "metadata": {
                                        "tags": series.tags_metadata
                                        or {},  # 所有可能的标签值
                                        "current_tags": current_tags,  # 当前数据点的具体标签值
                                        "metric": field,
                                        "series": series.name,
                                    },
                                }
                            )
        return data_points

    @staticmethod
    async def get_available_metrics_via_influx(
        client: InfluxDBClient, measurement: str
    ) -> List[Dict[str, Any]]:
        """通过 SHOW FIELD KEYS 获取指定 measurement 的字段列表"""
        q = f'SHOW FIELD KEYS FROM "{measurement}"'
        params = InfluxQueryParams(db=client.database, q=q)
        resp = await client.query(params)
        fields: List[Dict[str, Any]] = []
        if resp.results and resp.results[0].series:
            for s in resp.results[0].series:
                try:
                    key_index = s.columns.index("fieldKey")
                except ValueError:
                    key_index = 0
                for row in s.values:
                    field_name = row[key_index]
                    fields.append(
                        {
                            "field": field_name,
                            "display_name": str(field_name).replace("_", " ").title(),
                            "unit": "",
                            "description": f"{field_name} metric",
                        }
                    )
        return fields

    @staticmethod
    async def get_tag_values_via_influx(
        client: InfluxDBClient, measurement: str, tag: str
    ) -> List[str]:
        """通过 SHOW TAG VALUES 获取标签值"""
        q = f'SHOW TAG VALUES FROM "{measurement}" WITH KEY = "{tag}"'
        params = InfluxQueryParams(db=client.database, q=q)
        resp = await client.query(params)
        values: List[str] = []
        if resp.results and resp.results[0].series:
            for s in resp.results[0].series:
                try:
                    key_index = s.columns.index("value")
                except ValueError:
                    key_index = 0
                for row in s.values:
                    values.append(str(row[key_index]))
        return values

    @staticmethod
    async def get_tag_keys_via_influx(
        client: InfluxDBClient, measurement: str
    ) -> List[str]:
        """通过 SHOW TAG KEYS 获取标签键列表"""
        q = f'SHOW TAG KEYS FROM "{measurement}"'
        params = InfluxQueryParams(db=client.database, q=q)
        resp = await client.query(params)
        keys: List[str] = []
        if resp.results and resp.results[0].series:
            for s in resp.results[0].series:
                try:
                    key_index = s.columns.index("tagKey")
                except ValueError:
                    key_index = 0
                for row in s.values:
                    keys.append(str(row[key_index]))
        return keys


# ==================== 全局实例 ====================

# 注意：实际使用时应该通过依赖注入传入配置
metrics_processor = MetricsDataProcessor()
influx_client = InfluxDBClient()
