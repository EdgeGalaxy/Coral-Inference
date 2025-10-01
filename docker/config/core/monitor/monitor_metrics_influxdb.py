"""
优化版 Metrics 收集器 - 支持 InfluxDB3 存储
将 Pipeline 监控指标实时写入 InfluxDB3 时序数据库
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor
from typing import Set, Tuple

from loguru import logger
from influxdb_client_3 import InfluxDBClient3, Point

from inference.core.interfaces.stream_manager.api.stream_manager_client import (
    StreamManagerClient,
)

from ..cache import PipelineCache


class DataValidator:
    """数据验证器，验证 Pipeline 指标数据的有效性"""

    @staticmethod
    def validate_latency_report(report: Dict) -> bool:
        """验证延迟报告数据"""
        required_fields = ["source_id"]
        numeric_fields = [
            "inference_latency",
            "e2e_latency",
            "frame_decoding_latency",
            "frames_processed",
            "fps",
            "dropped_frames",
            "queue_size",
        ]

        # 检查必须字段
        for field in required_fields:
            if field not in report:
                return False

        # 检查数值字段
        for field in numeric_fields:
            if field in report and report[field] is not None:
                try:
                    value = float(report[field])
                    if value < 0:  # 负数检查
                        logger.warning(f"检测到负数值 {field}: {value}")
                        return False
                except (ValueError, TypeError):
                    logger.warning(f"无效的数值字段 {field}: {report[field]}")
                    return False

        return True

    @staticmethod
    def validate_source_metadata(metadata: Dict) -> bool:
        """验证源元数据"""
        required_fields = ["source_id"]

        for field in required_fields:
            if field not in metadata:
                return False

        # 验证 source_id 不为空
        if not str(metadata["source_id"]).strip():
            return False

        return True

    @staticmethod
    def validate_pipeline_report(report: Dict) -> bool:
        """验证 pipeline 报告数据"""
        if not isinstance(report, dict):
            return False

        # 检查必要的字段
        latency_reports = report.get("latency_reports", [])
        sources_metadata = report.get("sources_metadata", [])

        if not isinstance(latency_reports, list) or not isinstance(
            sources_metadata, list
        ):
            return False

        # 验证各个子报告
        for latency_report in latency_reports:
            if not DataValidator.validate_latency_report(latency_report):
                return False

        for source_meta in sources_metadata:
            if not DataValidator.validate_source_metadata(source_meta):
                return False

        return True


class ConnectionManager:
    """
    InfluxDB 连接管理器，处理连接重试和健康检查
    """

    def __init__(
        self,
        client: InfluxDBClient3,
        max_retries: int = 3,
        retry_delay: float = 5,
        health_check_interval: float = 60,
    ):
        self.client = client
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.health_check_interval = health_check_interval
        self.last_health_check = 0
        self.is_healthy = True

    async def execute_with_retry(self, operation, *args, **kwargs):
        """带重试机制的操作执行"""
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_exception = e
                logger.warning(f"操作失败，尝试 {attempt + 1}/{self.max_retries}: {e}")

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2**attempt))  # 指数退避

        # 所有重试失败
        self.is_healthy = False
        raise last_exception

    async def health_check(self) -> bool:
        """检查 InfluxDB 连接健康状态"""
        current_time = time.time()
        if current_time - self.last_health_check < self.health_check_interval:
            return self.is_healthy

        try:
            # InfluxDB3 使用 SQL 语法进行健康检查
            # 查询系统表来验证连接
            await asyncio.get_event_loop().run_in_executor(
                None, self.client.query, "SELECT 1 as health_check"
            )
            self.is_healthy = True
            logger.debug("InfluxDB 健康检查通过")
        except Exception as e:
            self.is_healthy = False
            logger.error(f"InfluxDB 健康检查失败: {e}")

        self.last_health_check = current_time
        return self.is_healthy


class InfluxDBMetricsCollector:
    """
    优化的指标收集器，直接写入 InfluxDB3

    数据结构设计：
    - Measurement: pipeline_system_metrics
    - Tags:
        - pipeline_id: Pipeline 的唯一标识
        - pipeline_name: Pipeline 名称（从缓存获取）
        - source_id: 数据源 ID
        - source_state: 数据源状态
    - Fields:
        - throughput: 推理吞吐量 (fps)
        - latency_mean: 平均延迟 (ms)
        - frames_processed: 已处理帧数
        - fps: 每个源的实时 FPS
        - queue_size: 队列大小
        - dropped_frames: 丢帧数
    """

    def __init__(
        self,
        stream_manager_client: StreamManagerClient,
        pipeline_cache: Optional[PipelineCache] = None,
        status_interval: float = 5,
        measurement: str = "pipeline_system_metrics",
        influxdb_url: Optional[str] = None,
        influxdb_token: Optional[str] = None,
        influxdb_database: Optional[str] = None,
        batch_size: int = 100,
        flush_interval: float = 10,
        enable_file_backup: bool = True,
        backup_dir: Optional[Path] = None,
    ):
        """
        初始化 InfluxDB Metrics 收集器

        Args:
            stream_manager_client: Stream Manager 客户端
            pipeline_cache: Pipeline 缓存（用于获取 pipeline 名称等信息）
            status_interval: 状态收集间隔（秒）
            measurement: InfluxDB measurement 名称
            influxdb_url: InfluxDB 服务器 URL
            influxdb_token: InfluxDB 认证 token
            influxdb_database: InfluxDB 数据库名
            batch_size: 批量写入大小
            flush_interval: 强制刷新间隔（秒）
            enable_file_backup: 是否启用文件备份（InfluxDB 不可用时）
            backup_dir: 备份目录
        """
        self.stream_manager_client = stream_manager_client
        self.pipeline_cache = pipeline_cache
        self.status_interval = status_interval
        self.measurement = measurement
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.enable_file_backup = enable_file_backup
        self.backup_dir = backup_dir or Path("/tmp/metrics_backup")

        self.last_status_time = 0
        self.enabled = False
        self.client: Optional[InfluxDBClient3] = None
        self.connection_manager: Optional[ConnectionManager] = None

        # 指标缓冲区
        self.metrics_buffer: List[Point] = []
        self.buffer_lock = asyncio.Lock()
        self.last_flush_time = time.time()

        # 并发控制
        self.semaphore = asyncio.Semaphore(10)

        # 数据验证器
        self.validator = DataValidator()

        # 从环境变量或参数获取 InfluxDB 配置
        self.influxdb_url = influxdb_url
        self.influxdb_token = influxdb_token
        self.influxdb_database = influxdb_database

        # 初始化 InfluxDB 客户端
        self._init_influxdb_client()

        # 用于异步写入的线程池
        self._executor = ThreadPoolExecutor(max_workers=2)

        # 列缓存（用于动态构建查询，避免首次无列导致的查询报错）
        self._columns_cache: Tuple[Set[str], float] = (set(), 0.0)
        self._columns_cache_ttl: float = 60.0

    def _init_influxdb_client(self):
        """初始化 InfluxDB3 客户端"""
        if not all([self.influxdb_url, self.influxdb_token, self.influxdb_database]):
            logger.warning(
                "InfluxDB 配置不完整 (需要 URL/TOKEN/DATABASE)。"
                "Metrics 将保存到本地文件。"
            )
            self.enabled = False
            return

        # 连接重试机制
        max_retries = 3
        retry_delay = 5

        for retry in range(max_retries):
            try:
                self.client = InfluxDBClient3(
                    host=self.influxdb_url,
                    token=self.influxdb_token,
                    database=self.influxdb_database,
                )

                # 测试连接并验证数据库
                try:
                    # InfluxDB3 中数据库在首次写入时自动创建
                    # 这里通过一个简单的查询来验证连接和数据库访问权限
                    test_result = self.client.query("SELECT 1 as connection_test")
                    logger.info("InfluxDB 连接测试成功")
                except Exception as test_error:
                    logger.warning(
                        f"InfluxDB 连接测试失败，但这可能是正常的 (数据库可能尚未存在): {test_error}"
                    )
                    # 对于 InfluxDB3，数据库会在首次写入时创建，所以连接测试失败是可以接受的

                self.enabled = True
                # 初始化连接管理器
                self.connection_manager = ConnectionManager(self.client)
                logger.info(
                    f"InfluxDB3 客户端初始化成功: "
                    f"host={self.influxdb_url}, database={self.influxdb_database}"
                )
                return

            except Exception as e:
                logger.error(
                    f"初始化 InfluxDB3 客户端失败 (重试 {retry + 1}/{max_retries}): {e}"
                )
                if retry < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避

        self.enabled = False
        logger.error("InfluxDB3 客户端初始化最终失败，启用文件备份模式")

    async def collect_and_store_metrics_concurrent(
        self, pipeline_ids_mapper: Dict[str, str]
    ):
        """并发收集多个 pipeline 的指标并存储到 InfluxDB"""
        current_time = time.time()

        if current_time - self.last_status_time < self.status_interval:
            return

        self.last_status_time = current_time

        if not pipeline_ids_mapper:
            return

        # 并发收集所有 pipeline 的指标
        tasks = []
        for pipeline_id, pipeline_cache_id in pipeline_ids_mapper.items():
            task = self._collect_and_store_single_pipeline(
                pipeline_id, pipeline_cache_id, current_time
            )
            tasks.append(task)

        # 并发执行，忽略单个失败
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 记录失败的任务
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pipeline_id = list(pipeline_ids_mapper.keys())[i]
                logger.error(f"Pipeline {pipeline_id} 指标收集失败: {result}")

        # 检查是否需要刷新缓冲区
        await self._check_and_flush_buffer()

    async def _collect_and_store_single_pipeline(
        self, pipeline_id: str, pipeline_cache_id: str, current_time: float
    ):
        """收集单个 pipeline 的指标并创建 InfluxDB Point"""
        async with self.semaphore:
            try:
                # 获取 pipeline 状态
                response = await self.stream_manager_client.get_status(pipeline_id)
                report = response.report
                logger.info(f"Pipeline {pipeline_cache_id} 状态报告: {report}")

                # 验证数据有效性
                if not self.validator.validate_pipeline_report(report):
                    logger.warning(f"Pipeline {pipeline_cache_id} 的报告数据验证失败")
                    return

                # 提取指标数据
                latency_reports = report.get("latency_reports", [])
                sources_metadata = report.get("sources_metadata", [])
                inference_throughput = report.get("inference_throughput", 0)

                # 过滤无效数据
                valid_latency_reports = [
                    r
                    for r in latency_reports
                    if self.validator.validate_latency_report(r)
                ]
                valid_sources_metadata = [
                    m
                    for m in sources_metadata
                    if self.validator.validate_source_metadata(m)
                ]

                if not valid_sources_metadata:
                    logger.debug(f"Pipeline {pipeline_cache_id} 没有有效的源元数据")
                    return

                # 获取 pipeline 名称（如果有缓存）
                pipeline_name = pipeline_cache_id
                if self.pipeline_cache:
                    cache_info = self.pipeline_cache.get(pipeline_cache_id)
                    if cache_info:
                        pipeline_name = cache_info.get(
                            "pipeline_name", pipeline_cache_id
                        )

                # 为每个数据源创建指标点
                points = self._create_influxdb_points(
                    pipeline_id=pipeline_cache_id,
                    pipeline_name=pipeline_name,
                    latency_reports=valid_latency_reports,
                    sources_metadata=valid_sources_metadata,
                    inference_throughput=inference_throughput,
                    timestamp=current_time,
                )

                # 添加到缓冲区
                async with self.buffer_lock:
                    self.metrics_buffer.extend(points)

                logger.debug(
                    f"收集 Pipeline {pipeline_cache_id} 的 {len(points)} 个指标点"
                )

            except Exception as e:
                logger.error(f"收集 Pipeline {pipeline_cache_id} 指标失败: {e}")
                raise

    def _create_influxdb_points(
        self,
        pipeline_id: str,
        pipeline_name: str,
        latency_reports: List[Dict],
        sources_metadata: List[Dict],
        inference_throughput: float,
        timestamp: float,
    ) -> List[Point]:
        """创建 InfluxDB Point 对象"""
        points = []
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        # 创建 pipeline 级别的指标点
        pipeline_point = Point(self.measurement)
        pipeline_point = pipeline_point.tag("pipeline_id", pipeline_id)
        pipeline_point = pipeline_point.tag("pipeline_name", pipeline_name)
        pipeline_point = pipeline_point.tag("level", "pipeline")  # 标记为 pipeline 级别
        pipeline_point = pipeline_point.field(
            "throughput", int(round(float(inference_throughput)))
        )
        pipeline_point = pipeline_point.field("source_count", len(sources_metadata))
        # 计算 pipeline 级 e2e_latency（取各源最大值，单位 ms）
        try:
            e2e_values_ms = []
            for lr in latency_reports:
                v = lr.get("e2e_latency")
                if v is not None:
                    e2e_values_ms.append(float(v) * 1000.0)
            if e2e_values_ms:
                pipeline_point = pipeline_point.field(
                    "e2e_latency", int(round(max(e2e_values_ms)))
                )
        except Exception as _:
            pass
        pipeline_point = pipeline_point.time(dt)
        points.append(pipeline_point)

        # 为每个数据源创建指标点
        for source_metadata in sources_metadata:
            source_id = source_metadata.get("source_id", None)
            # 允许 0 作为有效的 source_id，只有 None 或空字符串才跳过
            if source_id is None or (
                isinstance(source_id, str) and source_id.strip() == ""
            ):
                continue

            # 创建 Point
            point = Point(self.measurement)

            # 设置 Tags
            point = point.tag("pipeline_id", pipeline_id)
            point = point.tag("pipeline_name", pipeline_name)
            point = point.tag("source_id", str(source_id))
            point = point.tag("level", "source")  # 标记为 source 级别

            # 源状态作为 tag
            source_state = source_metadata.get("state", "unknown")
            point = point.tag("state", source_state)

            # 查找对应的延迟报告
            latency_data = None
            for latency_report in latency_reports:
                if latency_report.get("source_id", "") == source_id:
                    latency_data = latency_report
                    break

            # 设置 Fields（仅写入延迟，单位 ms）
            if latency_data:
                try:
                    if latency_data.get("frame_decoding_latency") is not None:
                        v = float(latency_data["frame_decoding_latency"]) * 1000.0
                        point = point.field("frame_decoding_latency", int(round(v)))
                except Exception:
                    pass
                try:
                    if latency_data.get("inference_latency") is not None:
                        v = float(latency_data["inference_latency"]) * 1000.0
                        point = point.field("inference_latency", int(round(v)))
                except Exception:
                    pass
                try:
                    if latency_data.get("e2e_latency") is not None:
                        v = float(latency_data["e2e_latency"]) * 1000.0
                        point = point.field("e2e_latency", int(round(v)))
                except Exception:
                    pass

            # 设置时间戳
            point = point.time(dt)
            points.append(point)

        return points

    async def _check_and_flush_buffer(self):
        """检查并刷新缓冲区到 InfluxDB"""
        current_time = time.time()

        async with self.buffer_lock:
            buffer_size = len(self.metrics_buffer)
            time_since_flush = current_time - self.last_flush_time

            # 达到批量大小或超过刷新间隔时刷新
            should_flush = (
                buffer_size >= self.batch_size
                or time_since_flush >= self.flush_interval
            )

            if should_flush and self.metrics_buffer:
                # 复制缓冲区内容
                points_to_write = self.metrics_buffer.copy()
                self.metrics_buffer.clear()
                self.last_flush_time = current_time

                # 异步写入 InfluxDB
                asyncio.create_task(self._write_to_influxdb(points_to_write))

    async def _write_to_influxdb(self, points: List[Point]):
        """异步写入数据到 InfluxDB"""
        if not points:
            return

        try:
            if self.enabled and self.client:
                # 在线程池中执行同步的 InfluxDB 写入
                await asyncio.get_event_loop().run_in_executor(
                    self._executor, self._write_points_sync, points
                )
                logger.debug(f"成功写入 {len(points)} 个指标点到 InfluxDB")
            else:
                # InfluxDB 不可用，保存到文件
                if self.enable_file_backup:
                    await self._save_to_backup_file(points)

        except Exception as e:
            logger.error(f"写入 InfluxDB 失败: {e}")
            # 失败时尝试保存到文件
            if self.enable_file_backup:
                await self._save_to_backup_file(points)

    def _write_points_sync(self, points: List[Point]):
        """同步写入 Points 到 InfluxDB（在线程池中执行）"""
        if not self.client:
            return

        try:
            # InfluxDB3 支持批量写入
            self.client.write(points)
        except Exception as e:
            logger.error(f"InfluxDB 写入错误: {e}")
            raise

    async def _save_to_backup_file(self, points: List[Point]):
        """将指标保存到备份文件（当 InfluxDB 不可用时）"""
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)

            # 按时间创建备份文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = self.backup_dir / f"metrics_backup_{timestamp}.json"

            # 转换 Points 为 JSON 格式
            data = []
            for point in points:
                point_dict = {
                    "measurement": self.measurement,
                    "tags": {},
                    "fields": {},
                    "timestamp": None,
                }

                # 改进的 Point 数据提取方法
                try:
                    # 使用 Point 的 to_line_protocol() 方法获取数据
                    line_protocol = point.to_line_protocol()
                    point_dict["line_protocol"] = line_protocol

                    # 尝试解析 line protocol 格式
                    parts = line_protocol.split()
                    if len(parts) >= 2:
                        # 解析 measurement,tag=value field=value timestamp
                        measurement_tags = parts[0]
                        fields_str = parts[1]
                        timestamp = parts[2] if len(parts) > 2 else None

                        # 分离 measurement 和 tags
                        if "," in measurement_tags:
                            measurement, tags_str = measurement_tags.split(",", 1)
                            # 解析 tags
                            for tag in tags_str.split(","):
                                if "=" in tag:
                                    key, value = tag.split("=", 1)
                                    point_dict["tags"][key] = value
                        else:
                            measurement = measurement_tags

                        point_dict["measurement"] = measurement

                        # 解析 fields
                        if "=" in fields_str:
                            for field in fields_str.split(","):
                                if "=" in field:
                                    key, value = field.split("=", 1)
                                    # 尝试转换为数值
                                    try:
                                        if value.endswith("i"):
                                            point_dict["fields"][key] = int(value[:-1])
                                        elif "." in value:
                                            point_dict["fields"][key] = float(value)
                                        else:
                                            point_dict["fields"][key] = value.strip('"')
                                    except ValueError:
                                        point_dict["fields"][key] = value.strip('"')

                        point_dict["timestamp"] = timestamp

                except Exception as parse_error:
                    logger.warning(f"解析 Point 失败: {parse_error}，保存原始数据")
                    # 回退到原始方法
                    try:
                        if hasattr(point, "_tags"):
                            point_dict["tags"] = dict(point._tags)
                        if hasattr(point, "_fields"):
                            point_dict["fields"] = dict(point._fields)
                        if hasattr(point, "_time"):
                            point_dict["timestamp"] = str(point._time)
                        point_dict["raw"] = str(point)
                    except:
                        point_dict["raw"] = str(point)

                data.append(point_dict)

            # 异步写入文件
            import aiofiles

            async with aiofiles.open(backup_file, "w") as f:
                await f.write(json.dumps(data, indent=2, default=str))

            logger.info(f"指标已备份到文件: {backup_file} ({len(points)} 个点)")

        except Exception as e:
            logger.error(f"保存备份文件失败: {e}")

    async def flush_buffer(self):
        """强制刷新缓冲区"""
        async with self.buffer_lock:
            if self.metrics_buffer:
                points_to_write = self.metrics_buffer.copy()
                self.metrics_buffer.clear()
                self.last_flush_time = time.time()

                await self._write_to_influxdb(points_to_write)

    async def restore_from_backup(self):
        """从备份文件恢复数据到 InfluxDB（当服务恢复后）"""
        if not self.enabled or not self.client:
            logger.warning("InfluxDB 客户端未启用，无法恢复备份")
            return

        if not self.backup_dir.exists():
            return

        backup_files = sorted(self.backup_dir.glob("metrics_backup_*.json"))

        for backup_file in backup_files:
            try:
                with open(backup_file, "r") as f:
                    data = json.load(f)

                points = []
                for item in data:
                    if "raw" in item:
                        # 跳过无法解析的原始数据
                        continue

                    point = Point(item.get("measurement", self.measurement))

                    # 恢复 tags
                    for tag_key, tag_value in item.get("tags", {}).items():
                        point = point.tag(tag_key, str(tag_value))

                    # 恢复 fields
                    for field_key, field_value in item.get("fields", {}).items():
                        if isinstance(field_value, float):
                            field_value = int(field_value)
                        point = point.field(field_key, field_value)

                    # 恢复时间戳
                    if item.get("timestamp"):
                        # 尝试解析时间戳
                        try:
                            dt = datetime.fromisoformat(item["timestamp"])
                            point = point.time(dt)
                        except:
                            pass

                    points.append(point)

                if points:
                    self._write_points_sync(points)
                    logger.info(f"从 {backup_file} 恢复了 {len(points)} 个指标点")

                # 成功恢复后删除备份文件
                backup_file.unlink()

            except Exception as e:
                logger.error(f"恢复备份文件 {backup_file} 失败: {e}")

    def close(self):
        """关闭 InfluxDB 客户端连接"""
        try:
            if self.client:
                self.client.close()
                logger.info("InfluxDB 客户端已关闭")
        except Exception as e:
            logger.error(f"关闭 InfluxDB 客户端失败: {e}")

    async def get_metrics_summary(
        self,
        pipeline_id: str,
        start_time: datetime,
        end_time: datetime,
        aggregation_window: str = "1m",
        level: str = "source",
    ) -> Dict[str, Any]:
        """
        从 InfluxDB 查询指标摘要

        Args:
            pipeline_id: Pipeline ID
            start_time: 开始时间
            end_time: 结束时间
            aggregation_window: 聚合窗口（如 "1m", "5m", "1h"）

        Returns:
            指标摘要字典
        """
        if not self.enabled or not self.client:
            logger.warning("InfluxDB 客户端未启用")
            return {}

        try:
            # 构建 SQL 查询 (InfluxDB3 使用 SQL) - 动态选择已存在的列
            available = self._get_available_columns()
            # 通用的时间桶表达式
            bucket_expr = f"date_bin(INTERVAL '{aggregation_window}', time, TIMESTAMP '1970-01-01 00:00:00Z') as bucket"
            if level == "pipeline":
                select_parts = [
                    bucket_expr,
                    "AVG(CAST(throughput AS DOUBLE)) as avg_throughput",
                    "AVG(CAST(source_count AS DOUBLE)) as avg_source_count",
                ]
                if "e2e_latency" in available:
                    select_parts.append(
                        "AVG(CAST(e2e_latency AS DOUBLE)) as avg_e2e_latency"
                    )
                select_parts.append("COUNT(*) as data_points")
                select_clause = ",\n                        ".join(select_parts)
                query = f"""
                    SELECT
                        {select_clause}
                    FROM {self.measurement}
                    WHERE
                        pipeline_id = '{pipeline_id}'
                        AND time >= TIMESTAMP '{start_time.isoformat()}'
                        AND time <= TIMESTAMP '{end_time.isoformat()}'
                    GROUP BY bucket
                    ORDER BY bucket
                """
            else:
                select_parts = [
                    bucket_expr,
                    "source_id",
                ]
                if "frame_decoding_latency" in available:
                    select_parts.append(
                        "AVG(CAST(frame_decoding_latency AS DOUBLE)) as avg_frame_decoding_latency"
                    )
                if "inference_latency" in available:
                    select_parts.append(
                        "AVG(CAST(inference_latency AS DOUBLE)) as avg_inference_latency"
                    )
                if "e2e_latency" in available:
                    select_parts.append(
                        "AVG(CAST(e2e_latency AS DOUBLE)) as avg_e2e_latency"
                    )
                select_parts.append("COUNT(*) as data_points")
                select_clause = ",\n                        ".join(select_parts)
                query = f"""
                    SELECT 
                        {select_clause}
                    FROM {self.measurement}
                    WHERE 
                        pipeline_id = '{pipeline_id}'
                        AND time >= TIMESTAMP '{start_time.isoformat()}'
                        AND time <= TIMESTAMP '{end_time.isoformat()}'
                        AND level = 'source'
                    GROUP BY bucket, source_id
                    ORDER BY bucket
                """

            # 执行查询
            result = await asyncio.get_event_loop().run_in_executor(
                self._executor, self._execute_query, query
            )

            # 处理结果
            summary = {
                "pipeline_id": pipeline_id,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "aggregation_window": aggregation_window,
                "data": [],
            }

            if result:
                # InfluxDB3 返回 pyarrow 格式的数据
                try:
                    import pandas as pd

                    df = (
                        result.to_pandas()
                        if hasattr(result, "to_pandas")
                        else pd.DataFrame(result)
                    )
                    for _, row in df.iterrows():
                        item = {
                            "time": str(row.get("bucket"))
                            if row.get("bucket") is not None
                            else None,
                            "data_points": int(row.get("data_points"))
                            if row.get("data_points") is not None
                            else None,
                        }
                        if level == "pipeline":
                            item.update(
                                {
                                    "avg_throughput": float(row.get("avg_throughput"))
                                    if row.get("avg_throughput") is not None
                                    else None,
                                    "avg_source_count": float(
                                        row.get("avg_source_count")
                                    )
                                    if row.get("avg_source_count") is not None
                                    else None,
                                    "avg_latency_mean": float(
                                        row.get("avg_latency_mean")
                                    )
                                    if row.get("avg_latency_mean") is not None
                                    else None,
                                    "total_frames": float(row.get("total_frames"))
                                    if row.get("total_frames") is not None
                                    else None,
                                    "total_dropped": float(row.get("total_dropped"))
                                    if row.get("total_dropped") is not None
                                    else None,
                                }
                            )
                        else:
                            item.update(
                                {
                                    "source_id": str(row.get("source_id"))
                                    if row.get("source_id") is not None
                                    else None,
                                    "avg_latency": float(row.get("avg_latency"))
                                    if row.get("avg_latency") is not None
                                    else None,
                                    "avg_fps": float(row.get("avg_fps"))
                                    if row.get("avg_fps") is not None
                                    else None,
                                    "total_frames": float(row.get("total_frames"))
                                    if row.get("total_frames") is not None
                                    else None,
                                    "total_dropped": float(row.get("total_dropped"))
                                    if row.get("total_dropped") is not None
                                    else None,
                                }
                            )
                        summary["data"].append(item)
                except Exception as parse_error:
                    logger.warning(f"解析查询结果失败: {parse_error}")
                    # 尝试直接遍历结果
                    try:
                        for record in result:
                            record_dict = (
                                record.to_dict()
                                if hasattr(record, "to_dict")
                                else (
                                    dict(record) if hasattr(record, "__iter__") else {}
                                )
                            )
                            item = {
                                "time": str(record_dict.get("bucket"))
                                if record_dict.get("bucket") is not None
                                else None,
                                "data_points": int(record_dict.get("data_points"))
                                if record_dict.get("data_points") is not None
                                else None,
                            }
                            if level == "pipeline":
                                item.update(
                                    {
                                        "avg_throughput": float(
                                            record_dict.get("avg_throughput")
                                        )
                                        if record_dict.get("avg_throughput") is not None
                                        else None,
                                        "avg_source_count": float(
                                            record_dict.get("avg_source_count")
                                        )
                                        if record_dict.get("avg_source_count")
                                        is not None
                                        else None,
                                    }
                                )
                            else:
                                item.update(
                                    {
                                        "source_id": str(record_dict.get("source_id"))
                                        if record_dict.get("source_id") is not None
                                        else None,
                                        "avg_latency": float(
                                            record_dict.get("avg_latency")
                                        )
                                        if record_dict.get("avg_latency") is not None
                                        else None,
                                        "avg_fps": float(record_dict.get("avg_fps"))
                                        if record_dict.get("avg_fps") is not None
                                        else None,
                                        "total_frames": float(
                                            record_dict.get("total_frames")
                                        )
                                        if record_dict.get("total_frames") is not None
                                        else None,
                                        "total_dropped": float(
                                            record_dict.get("total_dropped")
                                        )
                                        if record_dict.get("total_dropped") is not None
                                        else None,
                                    }
                                )
                            summary["data"].append(item)
                    except Exception as fallback_error:
                        logger.error(f"结果处理失败: {fallback_error}")
                        logger.debug(f"结果类型: {type(result)}")
                        if hasattr(result, "__dict__"):
                            logger.debug(f"结果属性: {result.__dict__}")

            return summary

        except Exception as e:
            logger.error(f"查询 InfluxDB 失败: {e}")
            return {}

    def _execute_query(self, query: str):
        """同步执行查询（在线程池中运行）"""
        try:
            return self.client.query(query)
        except Exception as e:
            logger.error(f"执行查询失败: {e}")
            return None

    def _get_available_columns(self) -> Set[str]:
        """查询 measurement 已存在的列（包含 field 与 tag），带缓存。"""
        try:
            import time as _time

            columns, ts = self._columns_cache
            if _time.time() - ts < self._columns_cache_ttl and columns:
                return columns

            # information_schema 查询
            info_query = (
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{self.measurement}'"
            )
            result = self._execute_query(info_query)
            cols: Set[str] = set()
            if result is not None:
                try:
                    # pyarrow 表 → pandas
                    import pandas as pd

                    df = (
                        result.to_pandas()
                        if hasattr(result, "to_pandas")
                        else pd.DataFrame(result)
                    )
                    for _, row in df.iterrows():
                        cn = (
                            row.get("column_name")
                            if "column_name" in row
                            else row.get(0)
                        )
                        if cn:
                            cols.add(str(cn))
                except Exception:
                    try:
                        for rec in result:
                            d = rec.to_dict() if hasattr(rec, "to_dict") else dict(rec)
                            cn = d.get("column_name")
                            if cn:
                                cols.add(str(cn))
                    except Exception:
                        pass

            self._columns_cache = (cols, _time.time())
            return cols
        except Exception as e:
            logger.warning(f"读取 measurement 列失败，使用空集: {e}")
            return set()


# 使用示例和集成函数
async def setup_influxdb_metrics_collector(
    stream_manager_client: StreamManagerClient,
    pipeline_cache: Optional[PipelineCache] = None,
    status_interval: float = 5,
    **kwargs,
) -> InfluxDBMetricsCollector:
    """
    设置 InfluxDB Metrics 收集器

    Example:
        collector = await setup_influxdb_metrics_collector(
            stream_manager_client=client,
            pipeline_cache=cache,
            status_interval=5,
            influxdb_url="http://localhost:8086",
            influxdb_token="your-token",
            influxdb_bucket="metrics"
        )
    """
    collector = InfluxDBMetricsCollector(
        stream_manager_client=stream_manager_client,
        pipeline_cache=pipeline_cache,
        status_interval=status_interval,
        **kwargs,
    )

    # 尝试恢复备份数据
    if collector.enabled:
        await collector.restore_from_backup()

    return collector
