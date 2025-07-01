import asyncio
import json
import os
import time
import shutil
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Deque

from loguru import logger
from inference.core.interfaces.stream_manager.api.stream_manager_client import (
    StreamManagerClient
)

from pipeline_cache import PipelineCache


class StatusCache:
    """状态信息缓存类"""
    def __init__(self, max_size: int = 100):
        self.latency_cache: Deque[Dict] = deque(maxlen=max_size)
        self.throughput_cache: Deque[Dict] = deque(maxlen=max_size)
        self.sources_cache: Deque[Dict] = deque(maxlen=max_size)
        self.max_size = max_size

    def add_status(self, latency: Dict, throughput: Dict, sources: Dict):
        """添加新的状态信息到缓存"""
        timestamp = int(time.time() * 1000)
        
        self.latency_cache.append({"timestamp": timestamp, "data": latency})
        self.throughput_cache.append({"timestamp": timestamp, "data": throughput})
        self.sources_cache.append({"timestamp": timestamp, "data": sources})

    def get_latest_status(self) -> Dict[str, Any]:
        """获取最新的状态信息"""
        return {
            "latency": self.latency_cache[-1] if self.latency_cache else None,
            "throughput": self.throughput_cache[-1] if self.throughput_cache else None,
            "sources": self.sources_cache[-1] if self.sources_cache else None
        }

    def get_history(self, minutes: int = 5) -> Dict[str, List]:
        """获取指定时间范围内的历史数据"""
        now = time.time() * 1000
        time_threshold = now - (minutes * 60 * 1000)
        
        return {
            "latency": [item for item in self.latency_cache 
                       if item["timestamp"] > time_threshold],
            "throughput": [item for item in self.throughput_cache 
                         if item["timestamp"] > time_threshold],
            "sources": [item for item in self.sources_cache 
                       if item["timestamp"] > time_threshold]
        }


class PipelineMonitor:
    def __init__(self, stream_manager_client: StreamManagerClient, pipeline_cache: PipelineCache, 
                 poll_interval: float = 1, output_dir: str = "/tmp/pipeline_results",
                 max_days: int = 7, cleanup_interval: float = 3600,
                 status_interval: float = 5, status_cache_size: int = 100):
        """
        初始化pipeline监控器
        
        参数:
            stream_manager_client: 流管理客户端
            pipeline_cache: 管道缓存
            poll_interval: 轮询间隔(秒)
            output_dir: 结果输出目录
            max_days: 结果保留最大天数
            cleanup_interval: 清理检查间隔(秒)
            status_interval: 状态检查间隔(秒)
            status_cache_size: 状态缓存大小
        """
        self.stream_manager_client = stream_manager_client
        self.pipeline_cache = pipeline_cache
        self.poll_interval = poll_interval
        self.output_dir = Path(output_dir)
        self.running = False
        self.pipeline_ids = {}
        self.max_days = max_days
        self.cleanup_interval = cleanup_interval
        self.last_cleanup_time = 0
        
        # 状态监控相关
        self.status_interval = status_interval
        self.last_status_time = 0
        self.status_cache = StatusCache(max_size=status_cache_size)
        self.status_dir = self.output_dir / "status"
        self.status_dir.mkdir(parents=True, exist_ok=True)

    async def start(self):
        """启动监控进程"""
        self.running = True
        logger.info(f"启动Pipeline监控，轮询间隔: {self.poll_interval}秒, 输出目录: {self.output_dir}")
        logger.info(f"设置自动清理: 保留天数={self.max_days}, 清理间隔={self.cleanup_interval}秒")
        logger.info(f"设置状态监控: 检查间隔={self.status_interval}秒")
        
        while self.running:
            await self.poll_and_save_results()
            await self.cleanup_old_results()
            await self.check_and_save_status()
            await asyncio.sleep(self.poll_interval)

    async def check_and_save_status(self):
        """检查并保存stream manager状态"""
        current_time = time.time()
        
        # 检查是否需要获取状态
        if current_time - self.last_status_time < self.status_interval:
            return
            
        self.last_status_time = current_time
        
        try:
            # 获取状态信息
            status = await self.stream_manager_client.get_status()
            
            if not status:
                return
                
            # 解析状态信息
            latency_reports = status.get("latency_reports", {})
            inference_throughput = status.get("inference_throughput", {})
            sources_metadata = status.get("sources_metadata", {})
            
            # 更新缓存
            self.status_cache.add_status(
                latency_reports,
                inference_throughput,
                sources_metadata
            )
            
            # 创建时间戳目录
            timestamp = int(current_time * 1000)
            status_timestamp_dir = self.status_dir / str(timestamp)
            status_timestamp_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存分离的状态文件
            await self._save_status_files(
                status_timestamp_dir,
                latency_reports,
                inference_throughput,
                sources_metadata
            )
            
            logger.debug("已更新并保存状态信息")
            
        except Exception as e:
            logger.error(f"获取或保存状态信息时出错: {e}")

    async def _save_status_files(self, 
                               dir_path: Path,
                               latency: Dict,
                               throughput: Dict,
                               sources: Dict):
        """保存状态文件"""
        try:
            # 异步保存各个状态文件
            save_tasks = [
                self._save_json_file(dir_path / "latency_reports.json", latency),
                self._save_json_file(dir_path / "inference_throughput.json", throughput),
                self._save_json_file(dir_path / "sources_metadata.json", sources)
            ]
            
            await asyncio.gather(*save_tasks)
            
        except Exception as e:
            logger.error(f"保存状态文件时出错: {e}")

    async def _save_json_file(self, file_path: Path, data: Dict):
        """异步保存JSON文件"""
        try:
            # 使用线程池执行文件写入
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: file_path.write_text(json.dumps(data, indent=2))
            )
        except Exception as e:
            logger.error(f"保存JSON文件 {file_path} 时出错: {e}")

    def get_latest_status(self) -> Dict[str, Any]:
        """获取最新的状态信息"""
        return self.status_cache.get_latest_status()

    def get_status_history(self, minutes: int = 5) -> Dict[str, List]:
        """获取状态历史数据"""
        return self.status_cache.get_history(minutes)

    async def cleanup_old_results(self):
        """清理过期的结果文件夹"""
        current_time = time.time()
        
        # 检查是否需要执行清理
        if current_time - self.last_cleanup_time < self.cleanup_interval:
            return
            
        self.last_cleanup_time = current_time
        logger.info("开始检查并清理过期结果...")
        
        try:
            # 获取所有pipeline目录
            if not self.output_dir.exists():
                return
                
            pipeline_dirs = [d for d in self.output_dir.iterdir() if d.is_dir()]
            cleanup_tasks = []
            
            for pipeline_dir in pipeline_dirs:
                if not pipeline_dir.exists():
                    continue
                    
                # 检查每个pipeline目录下的时间戳目录
                timestamp_dirs = [d for d in pipeline_dir.iterdir() if d.is_dir()]
                
                for timestamp_dir in timestamp_dirs:
                    try:
                        # 从目录名获取时间戳（毫秒）
                        timestamp_ms = int(timestamp_dir.name)
                        dir_time = datetime.fromtimestamp(timestamp_ms / 1000)
                        
                        # 检查是否超过最大保留天数
                        if datetime.now() - dir_time > timedelta(days=self.max_days):
                            cleanup_tasks.append(self.remove_dir(timestamp_dir))
                            
                    except ValueError:
                        logger.warning(f"无效的时间戳目录名: {timestamp_dir}")
                        continue
            
            if cleanup_tasks:
                # 并发执行删除任务
                await asyncio.gather(*cleanup_tasks)
                logger.info(f"清理完成，共删除 {len(cleanup_tasks)} 个过期目录")
            else:
                logger.debug("没有需要清理的过期目录")
                
        except Exception as e:
            logger.error(f"清理过期结果时发生错误: {e}")

    async def remove_dir(self, dir_path: Path):
        """异步删除目录"""
        try:
            # 使用线程池执行删除操作，因为shutil.rmtree是阻塞操作
            await asyncio.get_event_loop().run_in_executor(
                None, shutil.rmtree, str(dir_path), True
            )
            logger.debug(f"已删除过期目录: {dir_path}")
        except Exception as e:
            logger.error(f"删除目录 {dir_path} 时出错: {e}")

    def stop(self):
        """停止监控进程"""
        self.running = False
        logger.info("停止Pipeline监控")
    
    async def get_pipeline_ids(self):
        """获取所有活跃pipeline的ID"""
        pipelines = await self.stream_manager_client.list_pipelines()
        return {pipeline["id"]: self.pipeline_cache.get(pipeline["id"]) for pipeline in pipelines}

    async def poll_and_save_results(self):
        """轮询pipeline并保存结果"""
        try:
            # 获取所有活跃pipeline的ID
            pipeline_ids_mapper = await self.get_pipeline_ids()
            
            if not pipeline_ids_mapper:
                logger.info("没有发现活跃的pipeline")
                return
            
            logger.info(f"发现{len(pipeline_ids_mapper)}个活跃pipeline，开始获取结果")
            
            for pipeline_id, pipeline_cache_id in pipeline_ids_mapper.items():
                try:
                    if not pipeline_cache_id:
                        logger.error(f"Pipeline {pipeline_id} 没有 pipeline_cache_id")
                        continue
                    
                    pipeline_dir = self.output_dir / pipeline_cache_id
                    pipeline_dir.mkdir(parents=True, exist_ok=True)
                    
                    timestamp = int(time.time() * 1000)
                    pipeline_timestamp_dir = pipeline_dir / str(timestamp)
                    
                    # 获取pipeline的推理结果
                    results = await self.stream_manager_client.consume_pipeline_result(pipeline_id)
                    
                    if not results:
                        logger.debug(f"Pipeline {pipeline_cache_id} 没有新的结果")
                        continue
                    
                    await self._save_results(results, pipeline_timestamp_dir)
                    logger.debug(f"已保存Pipeline {pipeline_cache_id}的结果")
                except Exception as e:
                    logger.error(f"获取Pipeline {pipeline_cache_id}结果时出错: {e}")
        
        except Exception as e:
            logger.error(f"轮询过程中发生错误: {e}")

    async def _save_results(self, results: Dict[str, Any], result_dir: Path):
        """保存结果到JSON文件"""
        frames_metadata = results.get("frames_metadata", [])
        outputs = results.get("outputs", [])
        
        if not frames_metadata or not outputs:
            return
            
        for i, metadata in enumerate(frames_metadata):
            try:
                source_id = metadata.get("source_id", "unknown")
                frame_id = metadata.get("frame_id", str(i))
                frame_timestamp = metadata.get("frame_timestamp", int(time.time() * 1000))
                
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


async def setup_monitor(
        stream_manager_client: StreamManagerClient,
        pipeline_cache: PipelineCache,
        poll_interval: float = 0.1,
        output_dir: str = "/tmp/pipeline_results",
        max_days: int = 7,
        cleanup_interval: float = 3600,
        status_interval: float = 5,
        status_cache_size: int = 100
    ):
    """
    设置并启动pipeline监控器
    
    参数:
        stream_manager_client: 流管理客户端
        pipeline_cache: 管道缓存
        poll_interval: 轮询间隔(秒)
        output_dir: 结果输出目录
        max_days: 结果保留最大天数
        cleanup_interval: 清理检查间隔(秒)
        status_interval: 状态检查间隔(秒)
        status_cache_size: 状态缓存大小
    """
    monitor = PipelineMonitor(
        stream_manager_client=stream_manager_client,
        pipeline_cache=pipeline_cache,
        poll_interval=poll_interval,
        output_dir=output_dir,
        max_days=max_days,
        cleanup_interval=cleanup_interval,
        status_interval=status_interval,
        status_cache_size=status_cache_size
    )
    
    # 启动监控器
    asyncio.create_task(monitor.start())
    
    return monitor
