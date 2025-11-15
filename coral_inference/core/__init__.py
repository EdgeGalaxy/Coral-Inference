from coral_inference.runtime import init as runtime_init
from coral_inference.core.models.utils import get_runtime_platform

runtime_init()
runtime_platform = get_runtime_platform()
