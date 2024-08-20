from inference.models.utils import ROBOFLOW_MODEL_TYPES

from coral_inference.core.env import CURRENT_INFERENCE_PLATFORM
from coral_inference.models.rknn.yolov8 import YOLOv8RknnObjectDetection


if CURRENT_INFERENCE_PLATFORM == "rknn":
    # !MONKEY PATCH
    # 通过自己实现的rknn推理代码, 新增或替换掉ROBOFLOW_MODEL_TYPES中的模型类
    rknn_model_types = {
        ("object-detection", "yolov8"): YOLOv8RknnObjectDetection,
        ("object-detection", "yolov8s"): YOLOv8RknnObjectDetection,
        ("object-detection", "yolov8n"): YOLOv8RknnObjectDetection,
        ("object-detection", "yolov8s"): YOLOv8RknnObjectDetection,
        ("object-detection", "yolov8m"): YOLOv8RknnObjectDetection,
        ("object-detection", "yolov8l"): YOLOv8RknnObjectDetection,
        ("object-detection", "yolov8x"): YOLOv8RknnObjectDetection,
    }

    ROBOFLOW_MODEL_TYPES.update(rknn_model_types)


__all__ = ["YOLOv8RknnObjectDetection"]
