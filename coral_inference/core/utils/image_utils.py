import numpy as np
import cv2
from typing import Dict, List, Union

def merge_frames(frames: Dict[str, np.ndarray], layout: str = 'grid') -> np.ndarray:
    """
    将多个视频帧合并为一张图片
    
    Args:
        frames: 包含多个视频帧的字典，key为source_id，value为numpy数组格式的图像
        layout: 布局方式，支持 'grid'（网格布局）和 'horizontal'（水平布局）
    
    Returns:
        合并后的图像
    """
    if not frames:
        return None
        
    frame_list = list(frames.values())
    if len(frame_list) == 1:
        return frame_list[0]
        
    # 获取所有帧的尺寸
    heights = [frame.shape[0] for frame in frame_list]
    widths = [frame.shape[1] for frame in frame_list]
    
    if layout == 'grid':
        # 计算网格的行列数
        n = len(frame_list)
        cols = int(np.ceil(np.sqrt(n)))
        rows = int(np.ceil(n / cols))
        
        # 计算每个网格的大小
        max_height = max(heights)
        max_width = max(widths)
        
        # 创建画布
        canvas = np.zeros((max_height * rows, max_width * cols, 3), dtype=np.uint8)
        
        # 填充画布
        for idx, frame in enumerate(frame_list):
            i, j = divmod(idx, cols)
            # 调整帧的大小以匹配网格
            resized_frame = cv2.resize(frame, (max_width, max_height))
            canvas[i*max_height:(i+1)*max_height, j*max_width:(j+1)*max_width] = resized_frame
            
    elif layout == 'horizontal':
        # 水平布局
        total_width = sum(widths)
        max_height = max(heights)
        
        # 创建画布
        canvas = np.zeros((max_height, total_width, 3), dtype=np.uint8)
        
        # 填充画布
        x_offset = 0
        for frame in frame_list:
            # 调整帧的高度以匹配最大高度
            resized_frame = cv2.resize(frame, (frame.shape[1], max_height))
            canvas[:, x_offset:x_offset+frame.shape[1]] = resized_frame
            x_offset += frame.shape[1]
            
    else:
        raise ValueError(f"Unsupported layout: {layout}")
        
    return canvas 