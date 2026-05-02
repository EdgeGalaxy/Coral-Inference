import multiprocessing as mp

try:
    mp.set_start_method("spawn")
except RuntimeError:
    # The start method can only be set once per interpreter.
    pass

from coral_inference.core.env import apply_runtime_default_backend_env

apply_runtime_default_backend_env()

from coral_inference.core import runtime_platform, logger  # noqa
from inference.core.interfaces.stream_manager.manager_app.app import start


if __name__ == "__main__":
    start()
