import inference.models.utils as models_utils

from coral_inference.core.env import CURRENT_INFERENCE_PLATFORM
from coral_inference.models.rknn import RKNN_MODEL_TYPES
from coral_inference.models.onnx import ONNX_MODEL_TYPES


MODEL_TYPES_MAPPER = {"rknn": RKNN_MODEL_TYPES, "onnx": ONNX_MODEL_TYPES}


# !MONKEY PATCH
# 替换掉ROBOFLOW_MODEL_TYPES中的模型类
if CURRENT_INFERENCE_PLATFORM in MODEL_TYPES_MAPPER:
    models_utils.ROBOFLOW_MODEL_TYPES = MODEL_TYPES_MAPPER[CURRENT_INFERENCE_PLATFORM]
