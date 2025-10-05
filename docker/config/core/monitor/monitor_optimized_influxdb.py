"""
完整优化版 Pipeline 监控模块 - 集成 InfluxDB3
结合了性能优化和 InfluxDB 时序数据库存储
"""

import asyncio
import json
import os
import time
import shutil
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from concurrent.futures import ThreadPoolExecutor
import aiofiles

from loguru import logger

from inference.core.interfaces.stream_manager.api.stream_manager_client import (
    StreamManagerClient,
)
from inference.core.interfaces.stream_manager.api.entities import (
    ConsumePipelineResponse,
)

from ..cache import PipelineCache
from .monitor_metrics_influxdb import InfluxDBMetricsCollector


class BackgroundTaskQueue:
    """后台任务队列，处理非关键的异步任务"""

    def __init__(self, max_workers: int = 5):
        self.queue = asyncio.Queue()  # 延迟创建
        self.workers = []
        self.max_workers = max_workers
        self.running = False
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    async def start(self):
        """启动工作线程"""
        if self.running:
            return

        self.running = True
        self.workers = [
            asyncio.create_task(self._worker(i)) for i in range(self.max_workers)
        ]
        logger.info(f"启动 {self.max_workers} 个后台工作线程")

    async def stop(self):
        """停止工作线程"""
        self.running = False

        # 等待队列清空
        await self.queue.join()

        # 取消所有工作线程
        for worker in self.workers:
            worker.cancel()

        await asyncio.gather(*self.workers, return_exceptions=True)
        self._executor.shutdown(wait=True)
        logger.info("后台工作线程已停止")

    async def _worker(self, worker_id: int):
        """工作线程主循环"""
        logger.debug(f"Worker {worker_id} 启动")
        while self.running:
            try:
                # 获取任务，设置超时避免永久阻塞
                task = await asyncio.wait_for(self.queue.get(), timeout=1.0)

                if asyncio.iscoroutinefunction(task):
                    await task()
                elif callable(task):
                    # 在线程池中执行同步任务
                    await asyncio.get_event_loop().run_in_executor(self._executor, task)
                else:
                    logger.warning(f"无效的任务类型: {type(task)}")

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} 执行任务失败: {e}")
            finally:
                self.queue.task_done()

        logger.debug(f"Worker {worker_id} 停止")

    async def add_task(self, task: Callable):
        """添加任务到队列"""
        await self.queue.put(task)

    def add_task_nowait(self, task: Callable):
        """非阻塞添加任务"""
        try:
            self.queue.put_nowait(task)
        except asyncio.QueueFull:
            logger.warning("后台任务队列已满，丢弃任务")


class OptimizedResultsCollector:
    """优化的结果收集器，使用批量写入和异步 I/O"""

    def __init__(
        self,
        stream_manager_client: Optional[StreamManagerClient],
        output_dir: Path,
        batch_size: int = 100,
        flush_interval: float = 30,
        background_queue: Optional[BackgroundTaskQueue] = None,
    ):
        self.stream_manager_client = stream_manager_client
        self.output_dir = output_dir
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.background_queue = background_queue

        # 使用线程安全的缓存
        self.results_cache: Dict[str, List[Dict]] = {}
        self.cache_lock = asyncio.Lock()
        self.last_flush_time: Dict[str, float] = {}

        # 并发控制
        self.semaphore = asyncio.Semaphore(10)  # 限制并发数

    async def poll_and_save_results_concurrent(
        self, pipeline_ids_mapper: Dict[str, str]
    ):
        """并发轮询多个 pipeline 的结果"""
        if not pipeline_ids_mapper:
            return

        tasks = []
        for pipeline_id, pipeline_cache_id in pipeline_ids_mapper.items():
            task = self._poll_single_pipeline(pipeline_id, pipeline_cache_id)
            tasks.append(task)

        # 并发执行，忽略单个失败
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 记录失败的任务
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pipeline_id = list(pipeline_ids_mapper.keys())[i]
                logger.error(f"Pipeline {pipeline_id} 轮询失败: {result}")

    async def _poll_single_pipeline(self, pipeline_id: str, pipeline_cache_id: str):
        """轮询单个 pipeline"""
        async with self.semaphore:  # 限制并发
            try:
                # 获取结果
                results = await self.stream_manager_client.consume_pipeline_result(
                    pipeline_id, excluded_fields=[]
                )

                if not results.frames_metadata or not results.outputs:
                    return

                # 缓存结果
                await self._cache_results(pipeline_cache_id, results)

                # 检查是否需要刷新
                await self._check_and_flush_cache(pipeline_cache_id)

            except Exception as e:
                logger.error(f"获取 Pipeline {pipeline_cache_id} 结果失败: {e}")
                raise

    async def _cache_results(
        self, pipeline_cache_id: str, results: ConsumePipelineResponse
    ):
        """缓存结果数据"""
        frames_metadata = results.frames_metadata
        outputs = results.outputs

        if not frames_metadata or not outputs:
            return

        async with self.cache_lock:
            if pipeline_cache_id not in self.results_cache:
                self.results_cache[pipeline_cache_id] = []

            for i, metadata in enumerate(frames_metadata):
                try:
                    source_id = metadata.source_id
                    frame_id = metadata.frame_id
                    frame_timestamp = int(metadata.frame_timestamp.timestamp() * 1000)

                    output_data = outputs[i] if i < len(outputs) else {}

                    self.results_cache[pipeline_cache_id].append(
                        {
                            "source_id": source_id,
                            "frame_id": frame_id,
                            "frame_timestamp": frame_timestamp,
                            "output_data": output_data,
                        }
                    )

                except Exception as e:
                    logger.error(f"缓存结果数据失败: {e}")

    async def _check_and_flush_cache(self, pipeline_cache_id: str):
        """检查并刷新缓存"""
        current_time = time.time()

        async with self.cache_lock:
            if pipeline_cache_id not in self.results_cache:
                return

            cache_size = len(self.results_cache[pipeline_cache_id])
            last_flush = self.last_flush_time.get(pipeline_cache_id, 0)

            # 达到批量大小或超过刷新间隔时刷新
            should_flush = (
                cache_size >= self.batch_size
                or (current_time - last_flush) >= self.flush_interval
            )

            if should_flush:
                # 复制数据用于后台写入
                data_to_flush = self.results_cache[pipeline_cache_id].copy()
                self.results_cache[pipeline_cache_id] = []
                self.last_flush_time[pipeline_cache_id] = current_time

                # 在后台队列中执行写入
                if self.background_queue:
                    task = self._create_flush_task(pipeline_cache_id, data_to_flush)
                    self.background_queue.add_task_nowait(task)
                else:
                    # 如果没有后台队列，直接异步写入
                    asyncio.create_task(
                        self._flush_to_files_async(pipeline_cache_id, data_to_flush)
                    )

    def _create_flush_task(self, pipeline_cache_id: str, data: List[Dict]):
        """创建刷新任务"""

        async def task():
            await self._flush_to_files_async(pipeline_cache_id, data)

        return task

    async def _flush_to_files_async(self, pipeline_cache_id: str, data: List[Dict]):
        """异步批量写入文件"""
        if not data:
            return

        try:
            pipeline_dir = self.output_dir / pipeline_cache_id
            pipeline_dir.mkdir(parents=True, exist_ok=True)

            results_dir = pipeline_dir / "results"
            results_dir.mkdir(parents=True, exist_ok=True)

            # 按时间戳分组，每组写入一个文件
            timestamp = int(time.time() * 1000)
            batch_file = results_dir / f"batch_{timestamp}.json"

            # 使用 aiofiles 异步写入
            async with aiofiles.open(batch_file, "w") as f:
                await f.write(json.dumps(data, indent=2))

            logger.debug(f"批量写入 {len(data)} 条结果到 {batch_file}")

        except Exception as e:
            logger.error(f"异步写入文件失败: {e}")

    async def flush_all_caches(self):
        """刷新所有缓存"""
        async with self.cache_lock:
            for pipeline_cache_id, data in self.results_cache.items():
                if data:
                    # 在后台执行刷新
                    asyncio.create_task(
                        self._flush_to_files_async(pipeline_cache_id, data)
                    )
            self.results_cache.clear()


class OptimizedCleanupManager:
    """优化的清理管理器，在后台执行清理操作"""

    def __init__(
        self,
        output_dir: Path,
        max_days: int = 7,
        cleanup_interval: float = 3600,
        max_size_gb: float = 10.0,
        size_check_interval: float = 300,
        background_queue: Optional[BackgroundTaskQueue] = None,
    ):
        self.output_dir = output_dir
        self.max_days = max_days
        self.cleanup_interval = cleanup_interval
        self.max_size_gb = max_size_gb
        self.size_check_interval = size_check_interval
        self.background_queue = background_queue

        self.last_cleanup_time = 0
        self.last_size_check_time = 0
        self._executor = ThreadPoolExecutor(max_workers=2)

    async def check_and_cleanup_async(self):
        """异步检查并触发清理（不阻塞主循环）"""
        current_time = time.time()

        # 磁盘大小检查
        if current_time - self.last_size_check_time >= self.size_check_interval:
            self.last_size_check_time = current_time

            # 在后台检查磁盘使用
            if self.background_queue:
                self.background_queue.add_task_nowait(self._check_disk_usage_task)
            else:
                asyncio.create_task(self._check_disk_usage_background())

        # 定期清理
        if current_time - self.last_cleanup_time >= self.cleanup_interval:
            self.last_cleanup_time = current_time

            # 在后台执行清理
            if self.background_queue:
                self.background_queue.add_task_nowait(self._cleanup_old_task)
            else:
                asyncio.create_task(self._cleanup_old_background())

    async def _check_disk_usage_task(self):
        """磁盘使用检查任务"""
        await self._check_disk_usage_background()

    async def _cleanup_old_task(self):
        """清理旧文件任务"""
        await self._cleanup_old_background()

    async def _check_disk_usage_background(self):
        """后台检查磁盘使用"""
        try:
            if not self.output_dir.exists():
                return

            # 在线程池中计算目录大小
            current_size = await asyncio.get_event_loop().run_in_executor(
                self._executor, self._get_directory_size_sync, self.output_dir
            )

            logger.debug(f"磁盘使用: {current_size:.2f} GB / {self.max_size_gb} GB")

            if current_size > self.max_size_gb:
                logger.warning(f"磁盘使用超限，触发清理: {current_size:.2f} GB")
                await self._cleanup_by_size_async()

        except Exception as e:
            logger.error(f"检查磁盘使用失败: {e}")

    async def _cleanup_old_background(self):
        """后台清理旧文件"""
        try:
            await self._cleanup_old_results_async()
        except Exception as e:
            logger.error(f"清理旧文件失败: {e}")

    def _get_directory_size_sync(self, path: Path) -> float:
        """同步获取目录大小（在线程池中执行）"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, FileNotFoundError):
                    continue
        return total_size / (1024**3)  # 转换为 GB

    async def _cleanup_by_size_async(self):
        """异步清理磁盘空间"""
        try:
            if not self.output_dir.exists():
                return

            # 收集目录信息
            pipeline_dirs = []
            for pipeline_dir in self.output_dir.iterdir():
                if not pipeline_dir.is_dir():
                    continue

                # 在线程池中计算大小
                dir_size = await asyncio.get_event_loop().run_in_executor(
                    self._executor, self._get_directory_size_sync, pipeline_dir
                )

                # 获取最后修改时间
                last_modified = pipeline_dir.stat().st_mtime

                pipeline_dirs.append(
                    {
                        "path": pipeline_dir,
                        "size": dir_size,
                        "last_modified": last_modified,
                    }
                )

            # 按最后修改时间排序
            pipeline_dirs.sort(key=lambda x: x["last_modified"])

            # 计算需要清理的大小
            current_total_size = sum(d["size"] for d in pipeline_dirs)
            target_size = self.max_size_gb * 0.8
            size_to_cleanup = current_total_size - target_size

            if size_to_cleanup <= 0:
                return

            # 清理最旧的目录
            cleaned_size = 0
            for dir_info in pipeline_dirs:
                if cleaned_size >= size_to_cleanup:
                    break

                # 在线程池中删除目录
                await asyncio.get_event_loop().run_in_executor(
                    self._executor, shutil.rmtree, str(dir_info["path"]), True
                )
                cleaned_size += dir_info["size"]
                logger.info(
                    f"清理目录: {dir_info['path']}, 释放 {dir_info['size']:.2f} GB"
                )

            logger.info(f"磁盘清理完成，释放 {cleaned_size:.2f} GB")

        except Exception as e:
            logger.error(f"磁盘清理失败: {e}")

    async def _cleanup_old_results_async(self):
        """异步清理过期结果"""
        try:
            if not self.output_dir.exists():
                return

            cutoff_time = datetime.now() - timedelta(days=self.max_days)
            cleanup_tasks = []

            for pipeline_dir in self.output_dir.iterdir():
                if not pipeline_dir.is_dir():
                    continue

                for subdir in pipeline_dir.iterdir():
                    if not subdir.is_dir():
                        continue

                    try:
                        # 检查目录时间
                        dir_mtime = datetime.fromtimestamp(subdir.stat().st_mtime)

                        if dir_mtime < cutoff_time:
                            # 在线程池中删除
                            task = asyncio.get_event_loop().run_in_executor(
                                self._executor, shutil.rmtree, str(subdir), True
                            )
                            cleanup_tasks.append(task)

                    except Exception as e:
                        logger.error(f"检查目录 {subdir} 失败: {e}")

            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
                logger.info(f"清理了 {len(cleanup_tasks)} 个过期目录")

        except Exception as e:
            logger.error(f"清理过期结果失败: {e}")


class OptimizedPipelineMonitorWithInfluxDB:
    """
    优化的 Pipeline 监控器 - 集成 InfluxDB3
    结合了所有性能优化和时序数据库存储
    """

    def __init__(
        self,
        stream_manager_client: StreamManagerClient,
        pipeline_cache: PipelineCache,
        poll_interval: float = 1,
        output_dir: str = "/tmp/pipeline_results",
        max_days: int = 7,
        cleanup_interval: float = 3600,
        status_interval: float = 5,
        results_batch_size: int = 100,
        results_flush_interval: float = 30,
        max_size_gb: float = 10.0,
        size_check_interval: float = 300,
        max_background_workers: int = 5,
        # InfluxDB 配置
        enable_influxdb: bool = True,
        influxdb_url: Optional[str] = None,
        influxdb_token: Optional[str] = None,
        influxdb_database: Optional[str] = None,
        metrics_batch_size: int = 100,
        metrics_flush_interval: float = 10,
    ):
        # 参数验证
        self._validate_parameters(
            poll_interval,
            max_days,
            cleanup_interval,
            results_batch_size,
            max_size_gb,
            max_background_workers,
        )

        self.stream_manager_client = stream_manager_client
        self.pipeline_cache = pipeline_cache
        self.poll_interval = poll_interval
        self.output_dir = Path(output_dir)
        self.running = False
        self.pipeline_ids_mapper = {}
        self._task = None
        self.enable_influxdb = enable_influxdb

        # 创建后台任务队列
        self.background_queue = BackgroundTaskQueue(max_workers=max_background_workers)

        # 初始化优化的组件
        self.results_collector = OptimizedResultsCollector(
            stream_manager_client,
            self.output_dir,
            results_batch_size,
            results_flush_interval,
            self.background_queue,
        )

        # 初始化 InfluxDB Metrics 收集器（如果启用）
        self.influxdb_collector = None
        if self.enable_influxdb:
            self.influxdb_collector = InfluxDBMetricsCollector(
                stream_manager_client=stream_manager_client,
                pipeline_cache=pipeline_cache,
                status_interval=status_interval,
                influxdb_url=influxdb_url,
                influxdb_token=influxdb_token,
                influxdb_database=influxdb_database,
                batch_size=metrics_batch_size,
                flush_interval=metrics_flush_interval,
                enable_file_backup=True,
                backup_dir=self.output_dir / "metrics_backup",
            )
            logger.info("InfluxDB Metrics 收集器已启用")
        else:
            logger.info("InfluxDB Metrics 收集器未启用，使用文件存储")

        self.cleanup_manager = OptimizedCleanupManager(
            self.output_dir,
            max_days,
            cleanup_interval,
            max_size_gb,
            size_check_interval,
            self.background_queue,
        )

        # 性能监控
        self.performance_metrics = {
            "poll_count": 0,
            "poll_duration": 0,
            "last_poll_time": 0,
            "influxdb_enabled": self.enable_influxdb,
            "error_count": 0,
            "last_error_time": 0,
        }

        # 监控状态
        self._is_healthy = True
        self._last_pipeline_count = 0

    def _validate_parameters(
        self,
        poll_interval: float,
        max_days: int,
        cleanup_interval: float,
        batch_size: int,
        max_size_gb: float,
        max_workers: int,
    ):
        """验证初始化参数"""
        if poll_interval <= 0:
            raise ValueError("poll_interval 必须大于 0")
        if max_days <= 0:
            raise ValueError("max_days 必须大于 0")
        if cleanup_interval <= 0:
            raise ValueError("cleanup_interval 必须大于 0")
        if batch_size <= 0:
            raise ValueError("results_batch_size 必须大于 0")
        if max_size_gb <= 0:
            raise ValueError("max_size_gb 必须大于 0")
        if max_workers <= 0:
            raise ValueError("max_background_workers 必须大于 0")

    def is_healthy(self) -> bool:
        """检查监控器健康状态"""
        return self._is_healthy

    async def _run_monitor_loop(self):
        """优化的监控循环"""
        retry_count = 0
        max_retries = 3
        retry_delay = 5

        # 启动后台任务队列
        await self.background_queue.start()

        # 如果启用了 InfluxDB，尝试恢复备份数据
        if self.influxdb_collector and self.influxdb_collector.enabled:
            await self.influxdb_collector.restore_from_backup()

        while self.running:
            try:
                start_time = time.time()

                # 获取 pipeline 映射
                pipeline_ids_mapper = await self.get_pipeline_ids()

                # 构建并发任务列表
                tasks = [
                    # # 结果收集
                    # self.results_collector.poll_and_save_results_concurrent(
                    #     pipeline_ids_mapper
                    # ),
                    # 清理管理
                    self.cleanup_manager.check_and_cleanup_async(),
                ]

                # 如果启用了 InfluxDB，添加指标收集任务
                if self.influxdb_collector:
                    tasks.append(
                        self.influxdb_collector.collect_and_store_metrics_concurrent(
                            pipeline_ids_mapper
                        )
                    )

                # 并发执行所有任务
                await asyncio.gather(*tasks, return_exceptions=True)

                # 更新性能指标
                self.performance_metrics["poll_count"] += 1
                self.performance_metrics["poll_duration"] = time.time() - start_time
                self.performance_metrics["last_poll_time"] = time.time()

                # 重置重试计数
                retry_count = 0
                retry_delay = 5

            except Exception as e:
                retry_count += 1
                logger.error(f"监控循环错误 (重试 {retry_count}/{max_retries}): {e}")

                if retry_count >= max_retries:
                    logger.error("达到最大重试次数，延长等待时间")
                    retry_count = 0
                    retry_delay = min(retry_delay * 2, 300)

                await asyncio.sleep(retry_delay)
                continue

            # 动态调整轮询间隔
            elapsed = time.time() - start_time
            sleep_time = max(0, self.poll_interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    async def start(self):
        """启动监控"""
        if self.running:
            logger.warning("监控器已在运行")
            return

        self.running = True
        logger.info(f"启动优化的 Pipeline 监控器 (InfluxDB: {self.enable_influxdb})")
        logger.info(f"轮询间隔: {self.poll_interval}秒")
        logger.info(f"输出目录: {self.output_dir}")

        try:
            await self._run_monitor_loop()
        except asyncio.CancelledError:
            logger.info("监控任务被取消")
        except Exception as e:
            logger.error(f"监控任务异常: {e}")
            raise
        finally:
            await self._cleanup()

    async def _cleanup(self):
        """清理资源"""
        self.running = False

        # 停止后台队列
        await self.background_queue.stop()

        # 刷新所有缓存
        cleanup_tasks = [self.results_collector.flush_all_caches()]

        if self.influxdb_collector:
            cleanup_tasks.append(self.influxdb_collector.flush_buffer())

        try:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"刷新缓存失败: {e}")

        # 关闭 InfluxDB 连接
        if self.influxdb_collector:
            self.influxdb_collector.close()

        logger.info("监控器已停止")

    async def stop_async(self):
        """异步停止监控"""
        if not self.running:
            return

        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()

        await self._cleanup()

    async def get_pipeline_ids(self):
        """获取 pipeline ID 映射"""
        list_resp = await self.stream_manager_client.list_pipelines()
        pipelines = getattr(list_resp, "pipelines", []) or []
        pipeline_ids_mapper = {}

        for pipeline_id in pipelines:
            if not isinstance(pipeline_id, str) or not pipeline_id:
                continue

            if pipeline_id in self.pipeline_ids_mapper:
                pipeline_ids_mapper[pipeline_id] = self.pipeline_ids_mapper[pipeline_id]
                continue

            restore_info = self.pipeline_cache.get_restore_pipeline_id(pipeline_id)
            if not restore_info:
                logger.warning(f"Pipeline {pipeline_id} 未在缓存中找到")
                continue

            restore_pipeline_id = restore_info.get("pipeline_id")
            if not restore_pipeline_id:
                logger.warning(f"Pipeline {pipeline_id} 缺少 pipeline_id")
                continue

            self.pipeline_ids_mapper[pipeline_id] = restore_pipeline_id
            pipeline_ids_mapper[pipeline_id] = restore_pipeline_id

        return pipeline_ids_mapper

    async def get_performance_metrics(self) -> Dict:
        """获取性能指标"""
        metrics = {
            **self.performance_metrics,
            "background_queue_size": self.background_queue.queue.qsize(),
            "results_cache_size": sum(
                len(v) for v in self.results_collector.results_cache.values()
            ),
        }

        if self.influxdb_collector:
            metrics["influxdb_buffer_size"] = len(
                self.influxdb_collector.metrics_buffer
            )
            metrics["influxdb_enabled"] = self.influxdb_collector.enabled

        return metrics

    async def get_metrics_summary(
        self,
        pipeline_id: str,
        start_time: datetime,
        end_time: datetime,
        aggregation_window: str = "10s",
        level: str = "pipeline",
    ) -> Dict[str, Any]:
        """
        获取指定时间范围的指标摘要
        如果启用了 InfluxDB，从 InfluxDB 查询；否则返回空
        """
        if self.influxdb_collector and self.influxdb_collector.enabled:
            return await self.influxdb_collector.get_metrics_summary(
                pipeline_id, start_time, end_time, aggregation_window, level
            )
        else:
            logger.warning("InfluxDB 未启用，无法查询指标摘要")
            return {}


def setup_optimized_monitor_with_influxdb(
    stream_manager_client: StreamManagerClient,
    pipeline_cache: PipelineCache,
    poll_interval: float = 0.1,
    output_dir: str = "/tmp/pipeline_results",
    max_days: int = 7,
    cleanup_interval: float = 3600,
    status_interval: float = 5,
    results_batch_size: int = 100,
    results_flush_interval: float = 30,
    max_size_gb: float = 10.0,
    size_check_interval: float = 300,
    max_background_workers: int = 5,
    # InfluxDB 配置
    enable_influxdb: bool = True,
    influxdb_url: Optional[str] = None,
    influxdb_token: Optional[str] = None,
    influxdb_database: Optional[str] = None,
    metrics_batch_size: int = 100,
    metrics_flush_interval: float = 10,
    auto_start: bool = True,
) -> OptimizedPipelineMonitorWithInfluxDB:
    """
    设置优化的监控器（集成 InfluxDB）

    Args:
        auto_start: 是否自动启动监控器（在单独线程中）

    Example:
        # 自动启动
        monitor = setup_optimized_monitor_with_influxdb(
            stream_manager_client=client,
            pipeline_cache=cache,
            enable_influxdb=True,
            influxdb_url="http://localhost:8086",
            influxdb_token="your-token",
            influxdb_bucket="metrics"
        )

        # 手动管理
        monitor = setup_optimized_monitor_with_influxdb(
            stream_manager_client=client,
            pipeline_cache=cache,
            auto_start=False
        )
        # 在你的 asyncio 事件循环中启动
        await monitor.start()
    """

    monitor = OptimizedPipelineMonitorWithInfluxDB(
        stream_manager_client=stream_manager_client,
        pipeline_cache=pipeline_cache,
        poll_interval=poll_interval,
        output_dir=output_dir,
        max_days=max_days,
        cleanup_interval=cleanup_interval,
        status_interval=status_interval,
        results_batch_size=results_batch_size,
        results_flush_interval=results_flush_interval,
        max_size_gb=max_size_gb,
        size_check_interval=size_check_interval,
        max_background_workers=max_background_workers,
        enable_influxdb=enable_influxdb,
        influxdb_url=influxdb_url,
        influxdb_token=influxdb_token,
        influxdb_database=influxdb_database,
        metrics_batch_size=metrics_batch_size,
        metrics_flush_interval=metrics_flush_interval,
    )

    if auto_start:
        # 在新线程中运行监控器
        def start_monitor_thread():
            """在新线程中启动监控器"""
            try:
                # 创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # 运行监控器
                loop.run_until_complete(monitor.start())
            except Exception as e:
                logger.error(f"监控器线程异常: {e}")
            finally:
                try:
                    loop.close()
                except Exception as e:
                    logger.error(f"关闭事件循环失败: {e}")

        monitor_thread = threading.Thread(
            target=start_monitor_thread, name="PipelineMonitor", daemon=True
        )
        monitor_thread.start()
        monitor._monitor_thread = monitor_thread  # 保存线程引用

        logger.info("监控器已在后台线程中启动")

    return monitor


async def setup_optimized_monitor_async(
    stream_manager_client: StreamManagerClient, pipeline_cache: PipelineCache, **kwargs
) -> OptimizedPipelineMonitorWithInfluxDB:
    """
    异步设置并启动监控器（在当前事件循环中）

    Example:
        monitor = await setup_optimized_monitor_async(
            stream_manager_client=client,
            pipeline_cache=cache,
            enable_influxdb=True
        )
    """
    # 移除 auto_start 参数，因为这个函数总是手动启动
    kwargs.pop("auto_start", None)

    monitor = OptimizedPipelineMonitorWithInfluxDB(
        stream_manager_client=stream_manager_client,
        pipeline_cache=pipeline_cache,
        **kwargs,
    )

    # 在当前事件循环中启动
    asyncio.create_task(monitor.start())

    return monitor
