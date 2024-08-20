import os

from inference.core.utils.environment import safe_split_value

# 当前运行的环境
CURRENT_INFERENCE_PLATFORM = os.getenv("CURRENT_INFERENCE_PLATFORM", "onnx").lower()

# 支持的平台
_DEFAULT_RKNN_PLATFORMS = [
    "rk3562",
    "rk3566",
    "rk3568",
    "rk3576",
    "rk3588",
    "rk1808",
    "rv1109",
    "rv1126",
]
DEFAULT__RKNN_PLATFORMS = (
    safe_split_value(os.getenv("DEFAULT_RKNN_PLATFORMS", "").lower() or None)
    or _DEFAULT_RKNN_PLATFORMS
)

# Rknn 平台型号，rk3588、rk3399...
CURRENT_RKNN_PLATFORM = os.getenv("CURRENT_RKNN_PLATFORM", "rk3588").lower()
assert (
    CURRENT_RKNN_PLATFORM in DEFAULT__RKNN_PLATFORMS
), "RKNN_PLATFORM must in {}".format(DEFAULT__RKNN_PLATFORMS)

# Rknn inference default Image size
DEFAULT_RKNN_IMAGE_SIZE = [
    int(size)
    for size in safe_split_value(os.getenv("DEFAULT_RKNN_IMAGE_SIZE", "640,640"))
]
