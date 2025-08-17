
import os
import subprocess
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
        resolution: int = 480
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
            resolution
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
        resolution: int = 360  # 默认360p，最高支持1080p
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
        # 预加载已存在的视频文件，纳入统一清理逻辑
        self._load_existing_video_files()
        
        logger.info(f"TimeBasedVideoSink initialized for pipeline {pipeline_id}, video_info: {self.video_info}")
        
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
            
            # 记录文件信息
            if self.current_segment_path and os.path.exists(self.current_segment_path):
                file_size = os.path.getsize(self.current_segment_path)
                self.video_files.append({
                    'path': self.current_segment_path,
                    'size': file_size,
                    'created_time': self.segment_start_time,
                    'frame_count': self.frame_count
                })
                self.total_size += file_size
                logger.info(f"Video segment created: {self.current_segment_path}, size: {file_size} bytes")
        
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
        """处理预测结果"""
        try:
            if video_frames is None:
                logger.warning(f"pipeline {self.pipeline_id} catch video_frames is None")
                return
                
            # 处理单帧或多帧
            if isinstance(video_frames, list):
                frames = video_frames
                preds = predictions if isinstance(predictions, list) else [predictions] * len(frames)
            else:
                frames = [video_frames]
                preds = [predictions]
            
            current_time = datetime.now()
            
            # 检查是否需要创建新分段
            if self._should_create_new_segment(current_time):
                self._create_new_segment(current_time)
            
            # 处理每一帧
            for frame, prediction in zip(frames, preds):
                # logger.info(f"frame {frame} prediction: {prediction}")
                if frame is None and prediction is None:
                    continue

                # 从预测结果中提取图像
                image = self._extract_image_from_prediction(prediction)
                image = image if isinstance(image, np.ndarray) else frame.image

                # 动态 FPS 统计：按秒累计计数
                now = datetime.now()
                if self._fps_window_start is None:
                    self._fps_window_start = now
                elapsed = (now - self._fps_window_start).total_seconds()
                if elapsed >= 1.0:
                    # 完成一个整秒窗口，更新测得 fps
                    self.measured_fps = float(self._frames_in_current_second)
                    self._fps_window_start = now
                    self._frames_in_current_second = 0
                self._frames_in_current_second += 1

                # 确保VideoWriter已初始化
                self._ensure_writer_initialized(image)
                
                # 调整图像尺寸到目标分辨率
                if self.target_resolution and image is not None:
                    image = cv2.resize(image, self.actual_resolution)
                    image = render_statistics(image, frame_timestamp=frame.frame_timestamp, fps=self.actual_fps)
                
                # 写入视频
                if self.current_writer is not None and image is not None:
                    self.current_writer.write(image)
                    self.frame_count += 1
            # 定期检查磁盘空间
            if self.frame_count % 100 == 0:  # 每100帧检查一次
                self._check_disk_space()
                
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
        """释放资源"""
        try:
            # 关闭当前视频写入器
            if self.current_writer is not None:
                self.current_writer.release()
                self.current_writer = None
                
                # 记录最后一个分段
                if self.current_segment_path and os.path.exists(self.current_segment_path):
                    file_size = os.path.getsize(self.current_segment_path)
                    self.video_files.append({
                        'path': self.current_segment_path,
                        'size': file_size,
                        'created_time': self.segment_start_time,
                        'frame_count': self.frame_count
                    })
                    self.total_size += file_size
                    logger.info(f"Final video segment saved: {self.current_segment_path}")
                    
                    # 步骤 2: 使用 FFmpeg 强制重新编码为 Web 兼容格式
                    self._optimize_video_for_web(self.current_segment_path)
                    
        except Exception as e:
            logger.error(f"Error releasing TimeBasedVideoSink: {e}")
    
    def _optimize_video_for_web(self, video_path: str):
        """使用 FFmpeg 优化视频为 Web 兼容格式"""
        try:
            temp_output_path = video_path + ".temp.mp4"
            final_output_path = video_path
            
            # 先重命名原文件为临时文件
            os.rename(video_path, temp_output_path)
            
            print(f"\n步骤 2/2: 强制重新编码为 Web 兼容格式...")
            command = [
                'ffmpeg',
                '-i', temp_output_path,
                '-c:v', 'libx264',        # 使用 H.264 编码器
                '-pix_fmt', 'yuv420p',    # 强制使用兼容的像素格式
                '-movflags', '+faststart',# 将 moov 移到头部
                '-y',
                final_output_path
            ]
            
            subprocess.run(command, check=True, capture_output=True, text=True)
            logger.info(f"视频优化成功！文件保存在: {final_output_path}")
            os.remove(temp_output_path)
            
        except subprocess.CalledProcessError as e:
            logger.error("FFmpeg 优化失败:")
            logger.error(f"错误信息: {e.stderr}")
            logger.error(f"临时文件 {temp_output_path} 已保留，供调试使用。")
            # 如果优化失败，恢复原文件
            if os.path.exists(temp_output_path):
                os.rename(temp_output_path, final_output_path)
        except Exception as e:
            logger.error(f"视频优化过程中发生错误: {e}")
            # 如果优化失败，恢复原文件
            if os.path.exists(temp_output_path):
                os.rename(temp_output_path, final_output_path)
    
    def get_video_files_info(self) -> List[Dict[str, Any]]:
        """获取所有视频文件的信息"""
        return self.video_files.copy()
    
    def __del__(self):
        """析构函数"""
        self.release()
