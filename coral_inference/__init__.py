from inference import get_model, get_roboflow_model, InferencePipeline, Stream

from coral_inference.core import *
from coral_inference.plugins import *
from coral_inference.runtime import init as runtime_init, get_current_context

_AUTO_INIT_ENV = "CI_RUNTIME_AUTOINIT"

import os  # noqa

if os.environ.get(_AUTO_INIT_ENV, "1") == "1" and get_current_context() is None:
    runtime_init()
