import asyncio
import json
import os
import time
import shutil
import threading
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

from loguru import logger
from inference.core.interfaces.stream_manager.api.stream_manager_client import (
    StreamManagerClient
)
from inference.core.interfaces.stream_manager.api.entities import ConsumePipelineResponse
from pipeline_cache import PipelineCache


class ResultsCollector:
    """负责收集和保存pipeline结果的组件"""
    def __init__(self, stream_manager_client: StreamManagerClient, output_dir: Path, 
                 batch_size: int = 50, flush_interval: float = 30):
        self.stream_manager_client = stream_manager_client
        self.output_dir = output_dir
        self.batch_size = batch_size  # 批量写入大小
        self.flush_interval = flush_interval  # 强制刷新间隔（秒）
        self.results_cache: Dict[str, List[Dict]] = {}  # 结果缓存
        self.last_flush_time: Dict[str, float] = {}  # 上次刷新时间

    async def poll_and_save_results(self, pipeline_ids_mapper: Dict[str, str]):
        """轮询pipeline并保存结果"""
        try:
            if not pipeline_ids_mapper:
                return
            
            for pipeline_id, pipeline_cache_id in pipeline_ids_mapper.items():
                try:
                    # 获取pipeline的推理结果
                    results = await self.stream_manager_client.consume_pipeline_result(pipeline_id, excluded_fields=[])
                    
                    if not results.frames_metadata or not results.outputs:
                        continue

                    # # 缓存结果而不是立即写入
                    # await self._cache_results(pipeline_cache_id, results)
                    
                    # # 检查是否需要刷新缓存
                    # await self._check_and_flush_cache(pipeline_cache_id)
                    
                except Exception as e:
                    logger.error(f"获取Pipeline {pipeline_cache_id}结果时出错: {e}")
        
        except Exception as e:
            logger.error(f"轮询过程中发生错误: {e}")

    async def _cache_results(self, pipeline_cache_id: str, results: ConsumePipelineResponse):
        """缓存结果数据"""
        frames_metadata = results.frames_metadata
        outputs = results.outputs
        
        if not frames_metadata or not outputs:
            return
            
        if pipeline_cache_id not in self.results_cache:
            self.results_cache[pipeline_cache_id] = []
            
        for i, metadata in enumerate(frames_metadata):
            try:
                source_id = metadata.source_id
                frame_id = metadata.frame_id
                frame_timestamp = int(metadata.frame_timestamp.timestamp() * 1000)
                
                # 如果索引有效，获取对应的输出
                if i < len(outputs):
                    output_data = outputs[i]
                else:
                    output_data = {}
                
                # 添加到缓存
                self.results_cache[pipeline_cache_id].append({
                    "source_id": source_id,
                    "frame_id": frame_id,
                    "frame_timestamp": frame_timestamp,
                    "output_data": output_data
                })
                    
            except Exception as e:
                logger.error(f"缓存结果数据时出错: {e}")

    async def _check_and_flush_cache(self, pipeline_cache_id: str):
        """检查并刷新缓存"""
        current_time = time.time()
        
        if pipeline_cache_id not in self.results_cache:
            return
            
        cache_size = len(self.results_cache[pipeline_cache_id])
        last_flush = self.last_flush_time.get(pipeline_cache_id, 0)
        
        # 达到批量大小或超过刷新间隔时刷新
        if cache_size >= self.batch_size or (current_time - last_flush) >= self.flush_interval:
            await self._flush_cache_to_files(pipeline_cache_id)

    async def _flush_cache_to_files(self, pipeline_cache_id: str):
        """将缓存数据刷新到文件"""
        if pipeline_cache_id not in self.results_cache or not self.results_cache[pipeline_cache_id]:
            return
            
        try:
            pipeline_dir = self.output_dir / pipeline_cache_id
            pipeline_dir.mkdir(parents=True, exist_ok=True)
            
            pipeline_timestamp_dir = pipeline_dir / 'results'
            pipeline_timestamp_dir.mkdir(parents=True, exist_ok=True)
            
            # 批量写入文件
            cached_results = self.results_cache[pipeline_cache_id]
            for result in cached_results:
                filename = f"{result['source_id']}-{result['frame_id']}-{result['frame_timestamp']}.json"
                file_path = pipeline_timestamp_dir / filename
                
                with open(file_path, "w") as f:
                    json.dump(result['output_data'], f, indent=2)
            
            # 清空缓存并更新时间
            self.results_cache[pipeline_cache_id] = []
            self.last_flush_time[pipeline_cache_id] = time.time()
            
            logger.debug(f"已批量写入 {len(cached_results)} 个结果文件到 {pipeline_timestamp_dir}")
            
        except Exception as e:
            logger.error(f"刷新结果缓存到文件时出错: {e}")

    async def flush_all_caches(self):
        """刷新所有缓存数据"""
        for pipeline_cache_id in list(self.results_cache.keys()):
            await self._flush_cache_to_files(pipeline_cache_id)

    async def _save_results(self, pipeline_cache_id: str, results: ConsumePipelineResponse, result_dir: Path):
        """保存结果到JSON文件 - 保留原方法以兼容"""
        frames_metadata = results.frames_metadata
        outputs = results.outputs
        
        if not frames_metadata or not outputs:
            logger.debug(f"Pipeline {pipeline_cache_id} 没有结果")
            return
            
        for i, metadata in enumerate(frames_metadata):
            try:
                source_id = metadata.source_id
                frame_id = metadata.frame_id
                frame_timestamp = int(metadata.frame_timestamp.timestamp() * 1000)
                
                # 创建文件名
                filename = f"{source_id}-{frame_id}-{frame_timestamp}.json"
                file_path = result_dir / filename
                
                # 如果索引有效，获取对应的输出
                if i < len(outputs):
                    output_data = outputs[i]
                else:
                    output_data = {}
                    
                # 保存到JSON文件
                with open(file_path, "w") as f:
                    json.dump(output_data, f, indent=2)
                    
            except Exception as e:
                logger.error(f"保存结果文件时出错: {e}")


class MetricsCollector:
    """负责收集和保存metrics数据的组件"""
    def __init__(self, stream_manager_client: StreamManagerClient, output_dir: Path, 
                 status_interval: float = 5, save_interval: int = 5):
        self.stream_manager_client = stream_manager_client
        self.output_dir = output_dir
        self.status_interval = status_interval
        self.save_interval = save_interval
        self.last_status_time = 0
        self.metrics_cache: Dict[str, List[Dict]] = {}
        self.metrics_last_save_time: Dict[str, float] = {}

    def _get_time_slot(self, timestamp: float) -> str:
        """获取时间槽标识符"""
        dt = datetime.fromtimestamp(timestamp)
        slot = (dt.minute // self.save_interval) + 1
        return f"{dt.strftime('%Y%m%d_%H')}{int(slot):02d}"

    def _get_metrics_filename(self, pipeline_cache_id: str, time_slot: str) -> Path:
        """生成指标文件路径"""
        return self.output_dir / pipeline_cache_id / 'metrics' / f"{time_slot}.json"

    async def check_and_save_report(self, pipeline_ids_mapper: Dict[str, str]):
        """检查并保存stream manager状态"""
        current_time = time.time()
        
        if current_time - self.last_status_time < self.status_interval:
            return
            
        self.last_status_time = current_time
        
        for pipeline_id, pipeline_cache_id in pipeline_ids_mapper.items():
            try:
                response = await self.stream_manager_client.get_status(pipeline_id)
                report = response.report
                
                latency_reports = report.get("latency_reports", [])
                sources_metadata = report.get("sources_metadata", [])
                inference_throughput = report.get("inference_throughput", 0)
                metrics = await self._combine_metrics(latency_reports, inference_throughput, sources_metadata)

                if pipeline_cache_id not in self.metrics_cache:
                    self.metrics_cache[pipeline_cache_id] = []
                self.metrics_cache[pipeline_cache_id].append(metrics)

                current_slot = self._get_time_slot(current_time)
                last_save_time = self.metrics_last_save_time.get(pipeline_cache_id, 0)
                
                # 修复：如果 last_save_time 为 0，使用当前时间作为基准
                if last_save_time == 0:
                    # 初始化时，将上次保存时间设置为当前时间槽的开始时间
                    self.metrics_last_save_time[pipeline_cache_id] = current_time
                    last_save_slot = current_slot
                else:
                    last_save_slot = self._get_time_slot(last_save_time)

                # 检查是否需要保存数据（时间槽发生变化）
                if current_slot != last_save_slot:
                    # 保存到上一个时间槽的文件中
                    await self._save_metrics_to_file(pipeline_cache_id, last_save_slot)
                    self.metrics_last_save_time[pipeline_cache_id] = current_time

                # logger.debug(f"已更新Pipeline {pipeline_cache_id}的指标数据")
                
            except Exception as e:
                logger.exception(f"获取或保存状态信息时出错: {e}")

    async def _combine_metrics(self, latency_reports: List[Dict], inference_throughput: float, sources_metadata: List[Dict]) -> Dict:
        """合并指标数据"""
        combined_metrics = []
        for source_metadata in sources_metadata:
            source_metrics = {
                "source_id": source_metadata.get("source_id", ""),
                "state": source_metadata.get("state", ""),
            }
            for latency_report in latency_reports:
                if latency_report.get("source_id", "") == source_metadata.get("source_id", ""):
                    source_metrics.update(latency_report)
                    break
            combined_metrics.append(source_metrics)

        return {
            "timestamp": int(time.time() * 1000),
            "throughput": inference_throughput,
            "sources": combined_metrics
        }

    async def _save_metrics_to_file(self, pipeline_cache_id: str, time_slot: str):
        """保存指标数据到文件"""
        if pipeline_cache_id not in self.metrics_cache:
            return

        metrics_data = self.metrics_cache[pipeline_cache_id]
        if not metrics_data:
            return

        file_path = self._get_metrics_filename(pipeline_cache_id, time_slot)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            existing_data = []
            if file_path.exists():
                with open(file_path, 'r') as f:
                    existing_data = json.load(f)

            all_data = existing_data + metrics_data
            all_data.sort(key=lambda x: x['timestamp'])

            with open(file_path, 'w') as f:
                json.dump(all_data, f, indent=2)

            self.metrics_cache[pipeline_cache_id] = []
            logger.debug(f"已保存指标数据到文件: {file_path}")

        except Exception as e:
            logger.error(f"保存指标数据到文件时出错: {e}")

    async def flush_cache_to_files(self):
        """将缓存中的所有数据刷新到文件中"""
        for pipeline_cache_id, metrics_data in self.metrics_cache.items():
            if not metrics_data:
                continue
                
            try:
                # 根据最新的数据时间戳确定时间槽
                latest_timestamp = max(m['timestamp'] for m in metrics_data) / 1000
                time_slot = self._get_time_slot(latest_timestamp)
                
                file_path = self._get_metrics_filename(pipeline_cache_id, time_slot)
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                existing_data = []
                if file_path.exists():
                    with open(file_path, 'r') as f:
                        existing_data = json.load(f)
                
                all_data = existing_data + metrics_data
                all_data.sort(key=lambda x: x['timestamp'])
                
                with open(file_path, 'w') as f:
                    json.dump(all_data, f, indent=2)
                
                logger.debug(f"已刷新缓存数据到文件: {file_path}")
                
            except Exception as e:
                logger.error(f"刷新缓存数据到文件时出错: {e}")
        
        # 清空缓存
        self.metrics_cache.clear()
        logger.info("已将所有缓存数据刷新到文件")

    async def get_metrics_by_timerange(self, pipeline_cache_id: str, start_time: float, end_time: float) -> List[Dict]:
        """获取指定时间范围内的指标数据"""
        start_dt = datetime.fromtimestamp(start_time)
        end_dt = datetime.fromtimestamp(end_time)
        logger.info(f"start_dt: {start_dt}, end_dt: {end_dt}")
        current_dt = start_dt
        
        all_metrics = []
        while current_dt <= end_dt:
            slot = self._get_time_slot(current_dt.timestamp())
            file_path = self._get_metrics_filename(pipeline_cache_id, slot)
            logger.info(f"file_path: {file_path}")
            
            if file_path.exists():
                try:
                    with open(file_path, 'r') as f:
                        metrics = json.load(f)
                        filtered_metrics = [
                            m for m in metrics 
                            if start_time * 1000 <= m['timestamp'] <= end_time * 1000
                        ]
                        all_metrics.extend(filtered_metrics)
                except Exception as e:
                    logger.error(f"读取指标文件时出错: {file_path}, {e}")
            
            current_dt += timedelta(minutes=self.save_interval)
        
        # 包含缓存中的数据
        if pipeline_cache_id in self.metrics_cache:
            cached_metrics = [
                m for m in self.metrics_cache[pipeline_cache_id]
                if start_time * 1000 <= m['timestamp'] <= end_time * 1000
            ]
            all_metrics.extend(cached_metrics)
        
        all_metrics.sort(key=lambda x: x['timestamp'])
        return all_metrics


class CleanupManager:
    """负责清理旧数据的组件"""
    def __init__(self, output_dir: Path, max_days: int = 7, cleanup_interval: float = 3600,
                 max_size_gb: float = 10.0, size_check_interval: float = 300):
        self.output_dir = output_dir
        self.max_days = max_days
        self.cleanup_interval = cleanup_interval
        self.max_size_gb = max_size_gb  # 最大磁盘使用量（GB）
        self.size_check_interval = size_check_interval  # 磁盘大小检查间隔（秒）
        self.last_cleanup_time = 0
        self.last_size_check_time = 0

    def get_directory_size(self, path: Path) -> float:
        """获取目录大小（GB）"""
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except (OSError, FileNotFoundError):
                        continue
            return total_size / (1024 ** 3)  # 转换为GB
        except Exception as e:
            logger.error(f"获取目录大小时出错: {e}")
            return 0.0

    async def check_disk_usage_and_cleanup(self):
        """检查磁盘使用量并在必要时触发清理"""
        current_time = time.time()
        
        # 检查是否需要进行磁盘大小检查
        if current_time - self.last_size_check_time < self.size_check_interval:
            return False
            
        self.last_size_check_time = current_time
        
        if not self.output_dir.exists():
            return False
            
        # 获取当前磁盘使用量
        current_size = await asyncio.get_event_loop().run_in_executor(
            None, self.get_directory_size, self.output_dir
        )
        
        logger.debug(f"当前磁盘使用量: {current_size:.2f} GB, 阈值: {self.max_size_gb} GB")
        
        # 如果超过阈值，触发清理
        if current_size > self.max_size_gb:
            logger.warning(f"磁盘使用量 {current_size:.2f} GB 超过阈值 {self.max_size_gb} GB，触发清理")
            await self.cleanup_by_size()
            return True
            
        return False

    async def cleanup_by_size(self):
        """基于磁盘使用量进行清理"""
        try:
            if not self.output_dir.exists():
                return
                
            # 获取所有pipeline目录及其大小和最后修改时间
            pipeline_dirs = []
            for pipeline_dir in self.output_dir.iterdir():
                if not pipeline_dir.is_dir():
                    continue
                    
                try:
                    dir_size = await asyncio.get_event_loop().run_in_executor(
                        None, self.get_directory_size, pipeline_dir
                    )
                    
                    # 获取目录最后修改时间
                    last_modified = max(
                        (f.stat().st_mtime for f in pipeline_dir.rglob('*') if f.is_file()),
                        default=pipeline_dir.stat().st_mtime
                    )
                    
                    pipeline_dirs.append({
                        'path': pipeline_dir,
                        'size': dir_size,
                        'last_modified': last_modified
                    })
                    
                except Exception as e:
                    logger.error(f"处理目录 {pipeline_dir} 时出错: {e}")
                    continue
            
            # 按最后修改时间排序（最旧的在前）
            pipeline_dirs.sort(key=lambda x: x['last_modified'])
            
            # 计算需要清理的大小
            current_total_size = sum(d['size'] for d in pipeline_dirs)
            target_size = self.max_size_gb * 0.8  # 清理到80%阈值
            size_to_cleanup = current_total_size - target_size
            
            if size_to_cleanup <= 0:
                logger.info("无需清理磁盘空间")
                return
                
            # 清理最旧的目录直到达到目标大小
            cleaned_size = 0
            cleanup_tasks = []
            
            for dir_info in pipeline_dirs:
                if cleaned_size >= size_to_cleanup:
                    break
                    
                cleanup_tasks.append(self.remove_dir(dir_info['path']))
                cleaned_size += dir_info['size']
                logger.info(f"计划清理目录: {dir_info['path']}, 大小: {dir_info['size']:.2f} GB")
            
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks)
                logger.info(f"基于磁盘使用量清理完成，共清理 {len(cleanup_tasks)} 个目录，释放约 {cleaned_size:.2f} GB")
                
        except Exception as e:
            logger.error(f"基于磁盘使用量清理时发生错误: {e}")

    async def cleanup_old_results(self):
        """清理过期的结果文件夹"""
        current_time = time.time()
        
        if current_time - self.last_cleanup_time < self.cleanup_interval:
            return
            
        self.last_cleanup_time = current_time
        logger.info("开始检查并清理过期结果...")
        
        try:
            if not self.output_dir.exists():
                return
                
            pipeline_dirs = [d for d in self.output_dir.iterdir() if d.is_dir()]
            cleanup_tasks = []
            
            for pipeline_dir in pipeline_dirs:
                if not pipeline_dir.exists():
                    continue
                    
                # 检查pipeline目录的子目录
                subdirs = [d for d in pipeline_dir.iterdir() if d.is_dir()]
                
                for subdir in subdirs:
                    try:
                        # 尝试解析时间戳目录名
                        if subdir.name.isdigit():
                            timestamp_ms = int(subdir.name)
                            dir_time = datetime.fromtimestamp(timestamp_ms / 1000)
                            
                            if datetime.now() - dir_time > timedelta(days=self.max_days):
                                cleanup_tasks.append(self.remove_dir(subdir))
                        else:
                            # 对于非时间戳目录，检查文件的修改时间
                            try:
                                dir_mtime = subdir.stat().st_mtime
                                dir_time = datetime.fromtimestamp(dir_mtime)
                                
                                if datetime.now() - dir_time > timedelta(days=self.max_days):
                                    cleanup_tasks.append(self.remove_dir(subdir))
                            except Exception:
                                continue
                                
                    except ValueError:
                        logger.warning(f"无效的时间戳目录名: {subdir}")
                        continue
            
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks)
                logger.info(f"按时间清理完成，共删除 {len(cleanup_tasks)} 个过期目录")
            else:
                logger.debug("没有需要清理的过期目录")
                
        except Exception as e:
            logger.error(f"清理过期结果时发生错误: {e}")

    async def remove_dir(self, dir_path: Path):
        """异步删除目录"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, shutil.rmtree, str(dir_path), True
            )
            logger.debug(f"已删除目录: {dir_path}")
        except Exception as e:
            logger.error(f"删除目录 {dir_path} 时出错: {e}")

    async def get_disk_usage_info(self) -> Dict:
        """获取磁盘使用情况信息"""
        try:
            if not self.output_dir.exists():
                return {
                    "total_size_gb": 0.0,
                    "max_size_gb": self.max_size_gb,
                    "usage_percentage": 0.0,
                    "pipeline_count": 0
                }
                
            total_size = await asyncio.get_event_loop().run_in_executor(
                None, self.get_directory_size, self.output_dir
            )
            
            pipeline_count = len([d for d in self.output_dir.iterdir() if d.is_dir()])
            
            return {
                "total_size_gb": round(total_size, 2),
                "max_size_gb": self.max_size_gb,
                "usage_percentage": round((total_size / self.max_size_gb) * 100, 2),
                "pipeline_count": pipeline_count
            }
        except Exception as e:
            logger.error(f"获取磁盘使用信息时出错: {e}")
            return {
                "total_size_gb": 0.0,
                "max_size_gb": self.max_size_gb,
                "usage_percentage": 0.0,
                "pipeline_count": 0,
                "error": str(e)
            }


class PipelineMonitor:
    """Pipeline监控器，协调各个组件的工作"""
    def __init__(self, stream_manager_client: StreamManagerClient, pipeline_cache: PipelineCache, 
                 poll_interval: float = 1, output_dir: str = "/tmp/pipeline_results",
                 max_days: int = 7, cleanup_interval: float = 3600,
                 status_interval: float = 5, save_interval_minutes: int = 5,
                 # 新增参数
                 results_batch_size: int = 50, results_flush_interval: float = 30,
                 max_size_gb: float = 10.0, size_check_interval: float = 300):
        self.stream_manager_client = stream_manager_client
        self.pipeline_cache = pipeline_cache
        self.poll_interval = poll_interval
        self.output_dir = Path(output_dir)
        self.running = False
        self.pipeline_ids_mapper = {}
        self._task = None  # 存储运行任务的引用

        # 初始化各个组件
        self.results_collector = ResultsCollector(
            stream_manager_client, self.output_dir, 
            results_batch_size, results_flush_interval
        )
        self.metrics_collector = MetricsCollector(
            stream_manager_client, self.output_dir, 
            status_interval, save_interval_minutes
        )
        self.cleanup_manager = CleanupManager(
            self.output_dir, max_days, cleanup_interval,
            max_size_gb, size_check_interval
        )

    async def _run_monitor_loop(self):
        """实际的监控循环实现"""
        retry_count = 0
        max_retries = 3
        retry_delay = 5  # 初始重试延迟（秒）

        while self.running:
            try:
                pipeline_ids_mapper = await self.get_pipeline_ids()
                
                # 调用各个组件的功能
                await self.results_collector.poll_and_save_results(pipeline_ids_mapper)
                await self.metrics_collector.check_and_save_report(pipeline_ids_mapper)
                
                # 首先检查磁盘使用量，如果超过阈值则触发清理
                disk_cleanup_triggered = await self.cleanup_manager.check_disk_usage_and_cleanup()
                
                # 如果没有触发磁盘清理，则按正常间隔进行时间清理
                if not disk_cleanup_triggered:
                    await self.cleanup_manager.cleanup_old_results()

                # 重置重试计数
                retry_count = 0
                retry_delay = 5

            except Exception as e:
                retry_count += 1
                logger.error(f"监控过程中发生错误 (重试 {retry_count}/{max_retries}): {e}")
                
                if retry_count >= max_retries:
                    logger.error("达到最大重试次数，等待更长时间后继续...")
                    retry_count = 0
                    retry_delay = min(retry_delay * 2, 300)  # 最大等待5分钟
                
                await asyncio.sleep(retry_delay)
                continue

            await asyncio.sleep(self.poll_interval)

    async def start(self):
        """启动监控进程"""
        if self.running:
            logger.warning("监控器已经在运行中")
            return

        self.running = True
        logger.info(f"启动Pipeline监控，轮询间隔: {self.poll_interval}秒, 输出目录: {self.output_dir}")
        
        try:
            await self._run_monitor_loop()
        except asyncio.CancelledError:
            logger.info("监控任务被取消")
        except Exception as e:
            logger.error(f"监控任务异常退出: {e}")
            raise
        finally:
            self.running = False
            # 在监控结束时刷新所有缓存数据
            try:
                await self.metrics_collector.flush_cache_to_files()
                await self.results_collector.flush_all_caches()
            except Exception as e:
                logger.error(f"监控结束时刷新缓存失败: {e}")
            logger.info("监控任务结束")

    def stop(self):
        """停止监控进程"""
        if not self.running:
            return

        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("停止Pipeline监控")

    async def stop_async(self):
        """异步停止监控进程并刷新缓存"""
        if not self.running:
            return

        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
        
        # 刷新所有缓存中的数据到文件
        try:
            await self.metrics_collector.flush_cache_to_files()
            await self.results_collector.flush_all_caches()
        except Exception as e:
            logger.error(f"停止监控时刷新缓存失败: {e}")
        
        logger.info("停止Pipeline监控并已刷新所有缓存数据")

    async def flush_cache(self):
        """手动刷新缓存数据到文件"""
        try:
            await self.metrics_collector.flush_cache_to_files()
            await self.results_collector.flush_all_caches()
            logger.info("手动刷新所有缓存数据完成")
        except Exception as e:
            logger.error(f"手动刷新缓存数据失败: {e}")
            raise

    async def get_disk_usage_info(self) -> Dict:
        """获取磁盘使用情况信息"""
        return await self.cleanup_manager.get_disk_usage_info()

    async def force_cleanup(self):
        """强制触发清理"""
        try:
            await self.cleanup_manager.cleanup_by_size()
            await self.cleanup_manager.cleanup_old_results()
            logger.info("强制清理完成")
        except Exception as e:
            logger.error(f"强制清理失败: {e}")
            raise

    async def get_pipeline_ids(self):
        """获取所有活跃pipeline的ID"""
        pipelines = (await self.stream_manager_client.list_pipelines()).pipelines
        pipeline_ids_mapper = {}
        for pipeline_id in pipelines:
            if pipeline_id in self.pipeline_ids_mapper:
                pipeline_ids_mapper[pipeline_id] = self.pipeline_ids_mapper[pipeline_id]
                continue
            restore_pipeline_id = self.pipeline_cache.get_restore_pipeline_id(pipeline_id)
            if restore_pipeline_id is None:
                logger.warning(f"Monitor Pipeline {pipeline_id} not found in cache")
                continue
            self.pipeline_ids_mapper[pipeline_id] = restore_pipeline_id
            pipeline_ids_mapper[pipeline_id] = restore_pipeline_id
        return pipeline_ids_mapper

    async def get_metrics_by_timerange(self, pipeline_cache_id: str, start_time: float, end_time: float) -> List[Dict]:
        """获取指定时间范围内的指标数据"""
        return await self.metrics_collector.get_metrics_by_timerange(pipeline_cache_id, start_time, end_time)


async def setup_monitor(
        stream_manager_client: StreamManagerClient,
        pipeline_cache: PipelineCache,
        poll_interval: float = 0.1,
        output_dir: str = "/tmp/pipeline_results",
        max_days: int = 7,
        cleanup_interval: float = 3600,
        status_interval: float = 5,
        save_interval_minutes: int = 5,
        # 新增参数
        results_batch_size: int = 50,
        results_flush_interval: float = 30,
        max_size_gb: float = 10.0,
        size_check_interval: float = 300
    ):
    """设置并启动pipeline监控器"""
    monitor = PipelineMonitor(
        stream_manager_client=stream_manager_client,
        pipeline_cache=pipeline_cache,
        poll_interval=poll_interval,
        output_dir=output_dir,
        max_days=max_days,
        cleanup_interval=cleanup_interval,
        status_interval=status_interval,
        save_interval_minutes=save_interval_minutes,
        results_batch_size=results_batch_size,
        results_flush_interval=results_flush_interval,
        max_size_gb=max_size_gb,
        size_check_interval=size_check_interval
    )

    def start_loop(loop: asyncio.AbstractEventLoop):
        asyncio.set_event_loop(loop)
        loop.run_forever()
    
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_loop, args=(loop,), daemon=True)
    t.start()
    
    # 在当前事件循环中启动监控器
    asyncio.run_coroutine_threadsafe(monitor.start(), loop)
    
    return monitor
