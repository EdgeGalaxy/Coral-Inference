
import os
import queue
import subprocess
import threading
from datetime import datetime
from typing import Union, List, Optional, Dict, Any

import cv2
import numpy as np
import supervision as sv
from loguru import logger

from inference.core.interfaces.camera.entities import VideoFrame
from inference.core.interfaces.stream.sinks import render_statistics
from inference.core.env import MODEL_CACHE_DIR
from inference.core.workflows.execution_engine.entities.base import WorkflowImageData

from coral_inference.core.utils.image_utils import merge_frames


class TimeBasedVideoSink:
    """
    基于时间分段的视频录制Sink，支持磁盘空间监控和滚动删除
    """
    @classmethod    
    def init(
        cls, 
        pipeline_id: str,
        output_directory: str, 
        video_info: sv.VideoInfo = None, 
        segment_duration: int = 300, 
        max_disk_usage: float = 0.8, 
        max_total_size: int = 10 * 1024 * 1024 * 1024, 
        video_field_name: str = None, 
        codec: str = "mp4v", 
        resolution: int = 480,
        queue_size: int = 1000
    ):
        return cls(
            pipeline_id,
            output_directory, 
            video_info, 
            segment_duration, 
            max_disk_usage, 
            max_total_size, 
            video_field_name, 
            codec, 
            resolution,
            queue_size
        )
    
    def __init__(
        self,
        pipeline_id: str,
        output_directory: str,
        video_info: sv.VideoInfo = None,
        segment_duration: int = 300,  # 5分钟一个分段
        max_disk_usage: float = 0.8,  # 最大磁盘使用率 80%
        max_total_size: int = 10 * 1024 * 1024 * 1024,  # 最大总大小 10GB
        video_field_name: str = None,
        codec: str = "mp4v",
        resolution: int = 360,  # 默认360p，最高支持1080p
        queue_size: int = 1000  # 异步处理队列大小
    ):
        output_directory = os.path.join(MODEL_CACHE_DIR, "pipelines", pipeline_id, output_directory)
        os.makedirs(output_directory, exist_ok=True)

        self.output_directory = os.path.join(output_directory)
        self.video_info = video_info
        self.segment_duration = segment_duration
        self.max_disk_usage = max_disk_usage
        self.max_total_size = max_total_size
        self.video_field_name = video_field_name
        self.codec = codec
        self.pipeline_id = pipeline_id
        # 限制分辨率，超过1080则使用1080
        self.target_resolution = min(resolution, 1080)
        
        # 创建输出目录
        os.makedirs(self.output_directory, exist_ok=True)
        
        # 状态变量
        self.current_writer = None
        self.current_segment_path = None
        self.segment_start_time = None
        self.frame_count = 0
        self.total_size = 0
        self.actual_fps = None
        self.actual_resolution = None
        # FPS 动态估计相关状态
        self.measured_fps = 10.0
        self._fps_window_start: Optional[datetime] = None
        self._frames_in_current_second: int = 0
        
        # 文件管理
        self.video_files = []
        # 当前进程内已创建的分段数量（用于判断是否为首段）
        self.created_segment_count = 0
        # 异步处理队列和线程管理
        self._prediction_queue = queue.Queue(maxsize=queue_size)
        self._worker_thread = None
        self._shutdown_event = threading.Event()
        
        # 性能优化相关
        self._batch_size = min(32, max(1, queue_size // 50))  # 批处理大小
        self._disk_check_interval = 500  # 磁盘检查间隔帧数
        self._frames_since_disk_check = 0
        self._last_queue_size_log = 0
        
        # 预加载已存在的视频文件，纳入统一清理逻辑
        self._load_existing_video_files()
        
        # 启动后台工作线程
        self._start_worker_thread()
        
        logger.info(f"TimeBasedVideoSink initialized for pipeline {pipeline_id}, video_info: {self.video_info}, queue_size: {queue_size}")
        
    def _get_segment_path(self, timestamp: datetime) -> str:
        """生成当前分段视频文件路径"""
        timestamp_str = timestamp.strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp_str}.mp4"
        return os.path.join(self.output_directory, filename)
    
    def _create_new_segment(self, timestamp: datetime):
        """创建新的视频分段"""
        # 关闭当前分段
        if self.current_writer is not None:
            self.current_writer.release()
            self.current_writer = None
            
            # 记录文件信息并优化视频
            if self.current_segment_path and os.path.exists(self.current_segment_path):
                # 先优化视频为Web兼容格式
                self._optimize_video_for_web(self.current_segment_path)
                
                # 重新获取优化后的文件大小
                file_size = os.path.getsize(self.current_segment_path)
                self.video_files.append({
                    'path': self.current_segment_path,
                    'size': file_size,
                    'created_time': self.segment_start_time,
                    'frame_count': self.frame_count
                })
                self.total_size += file_size
                logger.info(f"Video segment created and optimized: {self.current_segment_path}, size: {file_size} bytes")
        
        # 创建新分段路径
        self.current_segment_path = self._get_segment_path(timestamp)
        self.segment_start_time = timestamp
        self.frame_count = 0
        
        logger.info(f"New video segment prepared: {self.current_segment_path}")
        # 更新分段计数
        self.created_segment_count += 1
    
    def _ensure_writer_initialized(self, image: np.ndarray):
        """确保VideoWriter已初始化，使用实际图像尺寸"""
        if self.current_writer is not None:
            return
            
        if self.current_segment_path is None:
            logger.error("Cannot initialize writer: no segment path set")
            return
            
        # 从实际图像获取尺寸，并根据目标分辨率调整
        height, width = image.shape[:2]
        
        # 根据目标分辨率计算实际尺寸
        if self.target_resolution:
            # 保持宽高比，以较短边为准调整到目标分辨率
            if height <= width:
                new_height = self.target_resolution
                new_width = int(width * self.target_resolution / height)
            else:
                new_width = self.target_resolution  
                new_height = int(height * self.target_resolution / width)
            
            # 确保是偶数，避免编码问题
            new_width = new_width if new_width % 2 == 0 else new_width + 1
            new_height = new_height if new_height % 2 == 0 else new_height + 1
            
            self.actual_resolution = (new_width, new_height)
        else:
            self.actual_resolution = (width, height)
        
        # 优先使用 video_info 中的 fps，如果没有则使用动态测得的 fps
        if self.video_info and hasattr(self.video_info, 'fps') and self.video_info.fps > 0:
            # 使用 video_info 中的 fps
            self.actual_fps = float(self.video_info.fps)
        elif self.created_segment_count == 1:
            # 第一段视频固定 10fps
            self.actual_fps = 10.0
        else:
            # 其后根据测得的每秒帧数动态设置
            dynamic_fps = self.measured_fps if self.measured_fps and self.measured_fps > 0 else 10.0
            # 合理约束范围，避免编码器异常
            self.actual_fps = float(max(1.0, min(dynamic_fps, 60.0)))
        
        # 创建视频写入器
        def _select_fourcc(preferred: str):
            candidates = [preferred, "avc1", "H264", "mp4v", "XVID"]
            for c in candidates:
                try:
                    return c, cv2.VideoWriter_fourcc(*c)
                except Exception as e:
                    logger.warning(f"use VideoWriter_fourcc: {c} raise error: {e}")
                    continue
            # 理论上不会到这
            return "mp4v", cv2.VideoWriter_fourcc(*"mp4v")

        selected_codec, fourcc = _select_fourcc(self.codec)
        if selected_codec != self.codec:
            logger.warning(f"Codec {self.codec} not available, using {selected_codec}")
            
        self.current_writer = cv2.VideoWriter(
            self.current_segment_path,
            fourcc,
            self.actual_fps,
            self.actual_resolution
        )
        
        logger.info(f"VideoWriter initialized: {self.actual_resolution} @ {self.actual_fps}fps")
    
    def _check_disk_space(self):
        """检查磁盘空间并清理旧文件"""
        try:
            # 检查总大小限制
            if self.total_size > self.max_total_size:
                self._cleanup_oldest_files()
                
            # 检查磁盘使用率
            stat = os.statvfs(self.output_directory)
            total_space = stat.f_blocks * stat.f_frsize
            free_space = stat.f_bavail * stat.f_frsize
            used_space = total_space - free_space
            usage_ratio = used_space / total_space
            
            if usage_ratio > self.max_disk_usage:
                self._cleanup_oldest_files()
                
        except Exception as e:
            logger.error(f"Error checking disk space: {e}")
    
    def _parse_created_time_from_filename(self, filename: str) -> Optional[datetime]:
        """从文件名解析创建时间（期望格式：YYYYmmddHHMMSS.mp4），失败返回 None"""
        try:
            name, _ = os.path.splitext(filename)
            return datetime.strptime(name, "%Y%m%d%H%M%S")
        except Exception:
            return None

    def _load_existing_video_files(self) -> None:
        """扫描输出目录，将已存在的视频加入 video_files，并累加 total_size"""
        try:
            if not os.path.isdir(self.output_directory):
                return
            loaded_count = 0
            for filename in os.listdir(self.output_directory):
                if not filename.lower().endswith(".mp4"):
                    continue
                path = os.path.join(self.output_directory, filename)
                if not os.path.isfile(path):
                    continue
                try:
                    size = os.path.getsize(path)
                    created_time = self._parse_created_time_from_filename(filename)
                    if created_time is None:
                        created_time = datetime.fromtimestamp(os.path.getctime(path))
                    self.video_files.append({
                        'path': path,
                        'size': size,
                        'created_time': created_time,
                        'frame_count': 0,
                    })
                    self.total_size += size
                    loaded_count += 1
                except Exception as e:
                    logger.warning(f"Skip existing video file due to error: {path}, err: {e}")
            if loaded_count:
                logger.info(f"Loaded {loaded_count} existing video files from {self.output_directory}")
        except Exception as e:
            logger.error(f"Error loading existing video files: {e}")
    
    def _cleanup_oldest_files(self):
        """清理最旧的视频文件"""
        if not self.video_files:
            return
            
        # 按创建时间排序
        self.video_files.sort(key=lambda x: x['created_time'])
        
        while self.video_files and (
            self.total_size > self.max_total_size * 0.9 or  # 清理到90%以下
            len(self.video_files) > 100  # 最多保留100个文件
        ):
            oldest_file = self.video_files.pop(0)
            
            try:
                if os.path.exists(oldest_file['path']):
                    os.remove(oldest_file['path'])
                    self.total_size -= oldest_file['size']
                    logger.info(f"Deleted old video file: {oldest_file['path']}")
            except Exception as e:
                logger.error(f"Error deleting file {oldest_file['path']}: {e}")
    
    def _should_create_new_segment(self, timestamp: datetime) -> bool:
        """检查是否应该创建新的分段"""
        if self.segment_start_time is None:
            return True
            
        time_diff = (timestamp - self.segment_start_time).total_seconds()
        return time_diff >= self.segment_duration
    
    def on_prediction(
        self,
        predictions: Union[Optional[dict], List[Optional[dict]]],
        video_frames: Union[Optional[VideoFrame], List[Optional[VideoFrame]]],
    ) -> None:
        """异步推送预测结果到处理队列"""
        try:
            if video_frames is None:
                logger.warning(f"pipeline {self.pipeline_id} catch video_frames is None")
                return
            
            # 将数据打包推送到队列
            queue_item = {
                'predictions': predictions,
                'video_frames': video_frames,
                'timestamp': datetime.now()
            }
            
            # 非阻塞推送，如果队列满了就丢弃（避免阻塞主线程）
            try:
                self._prediction_queue.put_nowait(queue_item)
            except queue.Full:
                logger.warning(f"Prediction queue full, dropping frame for pipeline {self.pipeline_id}")
                
        except Exception as e:
            logger.error(f"Error in TimeBasedVideoSink.on_prediction: {e}")
    
    def _extract_image_from_prediction(self, prediction: dict) -> Optional[np.ndarray]:
        """从预测结果中提取图像"""
        try:
            # 查找指定的视频字段
            if self.video_field_name and self.video_field_name in prediction:
                field_value = prediction[self.video_field_name]
                if isinstance(field_value, WorkflowImageData):
                    return field_value.numpy_image
            
            # 如果没有找到指定字段，查找任何base64图像
            for key, value in prediction.items():
                if isinstance(value, WorkflowImageData):
                    return value.numpy_image
                    
            return None
            
        except Exception as e:
            logger.error(f"Error extracting image from prediction: {e}")
            return None
    
    def release(self):
        """优雅释放资源"""
        try:
            # 设置关闭信号
            logger.info(f"TimeBasedVideoSink releasing for pipeline {self.pipeline_id}")
            self._shutdown_event.set()
            
            # 等待工作线程处理完队列中的数据
            if self._worker_thread and self._worker_thread.is_alive():
                logger.info(f"Waiting for worker thread to finish processing queue...")
                self._worker_thread.join(timeout=10.0)  # 最多等待10秒
                if self._worker_thread.is_alive():
                    logger.warning(f"Worker thread did not finish within timeout")
            
            # 关闭当前视频写入器
            if self.current_writer is not None:
                self.current_writer.release()
                self.current_writer = None
                
                # 记录最后一个分段并优化
                if self.current_segment_path and os.path.exists(self.current_segment_path):
                    # 优化最后一个分段
                    self._optimize_video_for_web(self.current_segment_path)
                    
                    # 重新获取优化后的文件大小
                    file_size = os.path.getsize(self.current_segment_path)
                    self.video_files.append({
                        'path': self.current_segment_path,
                        'size': file_size,
                        'created_time': self.segment_start_time,
                        'frame_count': self.frame_count
                    })
                    self.total_size += file_size
                    logger.info(f"Final video segment saved and optimized: {self.current_segment_path}")
                    
        except Exception as e:
            logger.error(f"Error releasing TimeBasedVideoSink: {e}")
    
    def _optimize_video_for_web(self, video_path: str):
        """使用 FFmpeg 优化视频为 Web 兼容格式 - 后台执行不阻塞"""
        def _optimize_worker(video_path: str):
            """后台优化工作线程"""
            if not os.path.exists(video_path):
                logger.error(f"Video file not found: {video_path}")
                return
                
            try:
                temp_output_path = video_path + ".temp.mp4"
                final_output_path = video_path
                
                # 先重命名原文件为临时文件
                os.rename(video_path, temp_output_path)
                
                logger.info(f"Background optimizing video for web compatibility: {video_path}")
                command = [
                    'ffmpeg',
                    '-i', temp_output_path,
                    '-c:v', 'libx264',        # 使用 H.264 编码器
                    '-pix_fmt', 'yuv420p',    # 强制使用兼容的像素格式
                    '-movflags', '+faststart',# 将 moov 移到头部
                    '-y',                     # 覆盖输出文件
                    final_output_path
                ]
                
                subprocess.run(command, check=True, capture_output=True, text=True)
                logger.info(f"Background video optimization successful: {final_output_path}")
                
                # 删除临时文件
                if os.path.exists(temp_output_path):
                    os.remove(temp_output_path)
                    
            except subprocess.CalledProcessError as e:
                logger.error("Background FFmpeg optimization failed:")
                logger.error(f"Command: {' '.join(command)}")
                logger.error(f"Error output: {e.stderr}")
                # 如果优化失败，恢复原文件
                if os.path.exists(temp_output_path):
                    os.rename(temp_output_path, final_output_path)
                    logger.info(f"Restored original file: {final_output_path}")
            except Exception as e:
                logger.error(f"Error during background video optimization: {e}")
                # 如果优化失败，恢复原文件
                if os.path.exists(temp_output_path):
                    os.rename(temp_output_path, final_output_path)
                    logger.info(f"Restored original file: {final_output_path}")
        
        # 启动后台线程执行优化，不阻塞当前进程
        optimization_thread = threading.Thread(
            target=_optimize_worker, 
            args=(video_path,),
            daemon=True,  # 设置为守护线程，主进程退出时自动结束
            name=f"VideoOptimizer-{os.path.basename(video_path)}"
        )
        optimization_thread.start()
        logger.info(f"Started background video optimization thread for: {video_path}")
    
    def get_video_files_info(self) -> List[Dict[str, Any]]:
        """获取所有视频文件的信息"""
        return self.video_files.copy()
    
    def _start_worker_thread(self):
        """启动后台工作线程"""
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=False,
            name=f"VideoSink-{self.pipeline_id}"
        )
        self._worker_thread.start()
        logger.info(f"Started video sink worker thread for pipeline {self.pipeline_id}")
    
    def _worker_loop(self):
        """后台工作线程主循环 - 优化版本支持批处理"""
        logger.info(f"Video sink worker thread started for pipeline {self.pipeline_id}")
        
        while not self._shutdown_event.is_set():
            try:
                # 批量获取队列项以提升吞吐量
                batch_items = self._get_batch_items()
                if not batch_items:
                    continue
                
                # 批量处理队列数据
                self._process_batch_predictions(batch_items)
                
                # 批量标记任务完成
                for _ in batch_items:
                    self._prediction_queue.task_done()
                
                # 队列监控和告警
                self._monitor_queue_health()
                
            except Exception as e:
                logger.error(f"Error in video sink worker loop: {e}")
                
        # 处理剩余队列中的数据
        logger.info(f"Processing remaining queue items for pipeline {self.pipeline_id}...")
        remaining_items = []
        while True:
            try:
                queue_item = self._prediction_queue.get_nowait()
                remaining_items.append(queue_item)
            except queue.Empty:
                break
        
        if remaining_items:
            self._process_batch_predictions(remaining_items)
            for _ in remaining_items:
                self._prediction_queue.task_done()
                
        logger.info(f"Video sink worker thread finished for pipeline {self.pipeline_id}")
    
    def _get_batch_items(self) -> List[Dict]:
        """批量获取队列项，提升处理效率"""
        batch_items = []
        
        # 至少获取一个项目，带超时
        try:
            first_item = self._prediction_queue.get(timeout=1.0)
            batch_items.append(first_item)
        except queue.Empty:
            return batch_items
        
        # 尽量获取更多项目组成批次，但不阻塞
        for _ in range(self._batch_size - 1):
            try:
                item = self._prediction_queue.get_nowait()
                batch_items.append(item)
            except queue.Empty:
                break
                
        return batch_items
    
    def _process_batch_predictions(self, batch_items: List[Dict]) -> None:
        """批量处理预测结果，提升性能"""
        if not batch_items:
            return
            
        try:
            for queue_item in batch_items:
                self._process_prediction_optimized(
                    predictions=queue_item['predictions'],
                    video_frames=queue_item['video_frames'],
                    timestamp=queue_item['timestamp']
                )
        except Exception as e:
            logger.error(f"Error in batch prediction processing: {e}")
    
    def _monitor_queue_health(self) -> None:
        """监控队列健康状态"""
        current_queue_size = self._prediction_queue.qsize()
        
        # 队列使用率告警
        queue_usage = current_queue_size / self._prediction_queue.maxsize
        if queue_usage > 0.8:  # 超过80%使用率
            if current_queue_size - self._last_queue_size_log > 100:
                logger.warning(f"Pipeline {self.pipeline_id} queue usage high: {current_queue_size}/{self._prediction_queue.maxsize} ({queue_usage:.1%})")
                self._last_queue_size_log = current_queue_size
        elif queue_usage < 0.2:  # 低于20%重置日志计数
            self._last_queue_size_log = 0
    
    def _process_prediction_optimized(
        self,
        predictions: Union[Optional[dict], List[Optional[dict]]],
        video_frames: Union[Optional[VideoFrame], List[Optional[VideoFrame]]],
        timestamp: datetime
    ) -> None:
        """优化版本的预测结果处理 - 支持多帧拼接"""
        try:
            if video_frames is None:
                return
                
            # 处理单帧或多帧
            if isinstance(video_frames, list):
                frames = video_frames
                preds = predictions if isinstance(predictions, list) else [predictions] * len(frames)
            else:
                frames = [video_frames]
                preds = [predictions]
            
            # 检查是否需要创建新分段
            if self._should_create_new_segment(timestamp):
                self._create_new_segment(timestamp)
            
            # 处理多帧拼接 - 参考 webrtc_manager.py 的逻辑
            if len(frames) > 1:
                # 多帧情况：创建拼接帧字典
                show_frames = {}
                for frame, prediction in zip(frames, preds):
                    if frame is None:
                        continue
                    
                    # 从预测结果中提取图像
                    image = self._extract_image_from_prediction(prediction)
                    if image is None:
                        image = frame.image
                    
                    # 添加统计信息渲染
                    if image is not None:
                        image = render_statistics(image, frame_timestamp=frame.frame_timestamp, fps=self.actual_fps)
                        show_frames[frame.source_id or f"source_{len(show_frames)}"] = image
                
                # 合并所有帧为一个拼接帧
                if show_frames:
                    try:
                        merged_frame = merge_frames(show_frames, layout='grid')
                        if merged_frame is not None:
                            # 将合并的帧作为单帧处理
                            processed_frames = [(merged_frame, frames[0])]  # 使用第一帧的元数据
                        else:
                            processed_frames = []
                    except Exception as merge_error:
                        logger.warning(f"Frame merging failed, using individual frames: {merge_error}")
                        # 回退到单独处理每帧
                        processed_frames = []
                        for frame, prediction in zip(frames, preds):
                            if frame is None:
                                continue
                            image = self._extract_image_from_prediction(prediction)
                            image = image if isinstance(image, np.ndarray) else frame.image
                            if image is not None:
                                processed_frames.append((image, frame))
                else:
                    processed_frames = []
            else:
                # 单帧情况：保持原有逻辑
                processed_frames = []
                for frame, prediction in zip(frames, preds):
                    if frame is None and prediction is None:
                        continue

                    # 从预测结果中提取图像
                    image = self._extract_image_from_prediction(prediction)
                    image = image if isinstance(image, np.ndarray) else frame.image
                    
                    if image is not None:
                        processed_frames.append((image, frame))
            
            # 批量写入视频帧
            if processed_frames:
                self._write_frames_batch(processed_frames)
                
            # 优化磁盘检查频率
            self._frames_since_disk_check += len(processed_frames)
            if self._frames_since_disk_check >= self._disk_check_interval:
                self._check_disk_space()
                self._frames_since_disk_check = 0
                
        except Exception as e:
            logger.error(f"Error in TimeBasedVideoSink._process_prediction_optimized: {e}")
    
    def _write_frames_batch(self, frames_batch: List[tuple]) -> None:
        """批量写入视频帧，减少频繁的VideoWriter初始化 - 支持拼接帧"""
        try:
            if not frames_batch:
                return
                
            # 使用第一帧初始化VideoWriter（如果需要）
            first_image = frames_batch[0][0]
            self._ensure_writer_initialized(first_image)
            
            if self.current_writer is None:
                logger.warning("VideoWriter initialization failed, skipping batch")
                return
            
            # 批量处理和写入帧
            for image, frame in frames_batch:
                # 动态 FPS 统计
                self._update_fps_measurement()
                
                # 调整图像尺寸（复用已计算的分辨率）
                # 注意：对于拼接帧，图像可能已经经过 render_statistics 处理
                if self.target_resolution and self.actual_resolution:
                    # 检查图像是否已经是目标尺寸
                    current_height, current_width = image.shape[:2]
                    target_width, target_height = self.actual_resolution
                    
                    if current_width != target_width or current_height != target_height:
                        image = cv2.resize(image, self.actual_resolution)
                    
                    # # 对于单帧（非拼接帧），添加统计信息
                    # if len(frames_batch) == 1:
                    #     image = render_statistics(image, frame_timestamp=frame.frame_timestamp, fps=self.actual_fps)
                
                # 写入视频
                self.current_writer.write(image)
                self.frame_count += 1
                
        except Exception as e:
            logger.error(f"Error in batch frame writing: {e}")
    
    def _update_fps_measurement(self) -> None:
        """优化的FPS测量，减少datetime.now()调用"""
        now = datetime.now()
        if self._fps_window_start is None:
            self._fps_window_start = now
        elapsed = (now - self._fps_window_start).total_seconds()
        if elapsed >= 1.0:
            self.measured_fps = float(self._frames_in_current_second)
            self._fps_window_start = now
            self._frames_in_current_second = 0
        self._frames_in_current_second += 1
    
    def __del__(self):
        """析构函数"""
        self.release()
