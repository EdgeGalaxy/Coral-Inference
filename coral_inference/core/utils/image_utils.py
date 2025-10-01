import numpy as np
import cv2
from typing import Dict, List, Union


def merge_frames(
    frames: Dict[str, np.ndarray], layout: str = "grid", target_height: int = None
) -> np.ndarray:
    """
    将多个视频帧合并为一张图片

    Args:
        frames: 包含多个视频帧的字典，key为source_id，value为numpy数组格式的图像
        layout: 布局方式，支持 'grid'（网格布局）和 'horizontal'（水平布局）
        target_height: 目标高度，如果为None则使用默认值

    Returns:
        合并后的图像
    """
    if not frames:
        return None

    frame_list = list(frames.values())
    n_frames = len(frame_list)

    # 设置默认分辨率（高度）
    if target_height is None:
        if n_frames == 1:
            # 单个视频，默认480p
            target_height = 720
        elif n_frames == 2 and layout == "horizontal":
            # 两个视频在一排，默认520p
            target_height = 960
        else:
            # 多个视频（grid布局），默认720p
            target_height = 1080

    if n_frames == 1:
        # 单个视频，调整到目标分辨率
        frame = frame_list[0]
        height, width = frame.shape[:2]
        # 保持宽高比
        aspect_ratio = width / height
        target_width = int(target_height * aspect_ratio)
        return cv2.resize(frame, (target_width, target_height))

    # 获取所有帧的尺寸
    heights = [frame.shape[0] for frame in frame_list]
    widths = [frame.shape[1] for frame in frame_list]

    if layout == "grid":
        # 计算网格的行列数
        n = len(frame_list)
        cols = int(np.ceil(np.sqrt(n)))
        rows = int(np.ceil(n / cols))

        # 计算每个网格单元的大小
        # 根据目标高度和行数计算每个单元的高度
        cell_height = target_height // rows if rows > 0 else target_height

        # 计算平均宽高比
        aspect_ratios = [w / h for w, h in zip(widths, heights)]
        avg_aspect_ratio = sum(aspect_ratios) / len(aspect_ratios)
        cell_width = int(cell_height * avg_aspect_ratio)

        # 创建画布
        canvas = np.zeros((target_height, cell_width * cols, 3), dtype=np.uint8)

        # 填充画布
        for idx, frame in enumerate(frame_list):
            i, j = divmod(idx, cols)
            # 调整帧的大小以匹配网格单元
            resized_frame = cv2.resize(frame, (cell_width, cell_height))
            canvas[
                i * cell_height : (i + 1) * cell_height,
                j * cell_width : (j + 1) * cell_width,
            ] = resized_frame

    elif layout == "horizontal":
        # 水平布局
        # 调整所有帧到目标高度，保持宽高比
        resized_frames = []
        total_width = 0

        for frame in frame_list:
            height, width = frame.shape[:2]
            # 保持宽高比
            aspect_ratio = width / height
            new_width = int(target_height * aspect_ratio)
            resized_frame = cv2.resize(frame, (new_width, target_height))
            resized_frames.append(resized_frame)
            total_width += new_width

        # 创建画布
        canvas = np.zeros((target_height, total_width, 3), dtype=np.uint8)

        # 填充画布
        x_offset = 0
        for resized_frame in resized_frames:
            width = resized_frame.shape[1]
            canvas[:, x_offset : x_offset + width] = resized_frame
            x_offset += width

    else:
        raise ValueError(f"Unsupported layout: {layout}")

    return canvas
