from coral_inference.core.env import apply_runtime_default_backend_env

apply_runtime_default_backend_env()

from inference.core.logger import logger

from coral_inference.core.patches import (
    get_runtime_patch_installation_state,
    install_business_runtime_patches,
    install_default_runtime_patches,
    runtime_platform,
)


install_default_runtime_patches()

__all__ = [
    "install_business_runtime_patches",
    "install_default_runtime_patches",
    "get_runtime_patch_installation_state",
    "logger",
    "runtime_platform",
]
