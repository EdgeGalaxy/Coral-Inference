import os
import subprocess
from typing import Any, Union

import numpy as np
from requests import Response
from inference.core.exceptions import ModelArtefactError
from inference.core.models import roboflow
from inference.core.roboflow_api import (
    wrap_roboflow_api_errors,
    _get_from_url,
)
from coral_inference.core.log import logger

from coral_inference.core.env import CURRENT_INFERENCE_PLATFORM


class RknnInferenceSession:
    def __init__(self, model_fp: str, inputs: Any, device_id: int = 0):
        try:
            from rknnlite.api import RKNNLite as RKNN
        except ImportError:
            raise ImportError("Please install rknnlite first!")

        self.input_name = inputs.name
        self.input_shape = inputs.shape

        self.rknn_session = RKNN(verbose=False)
        self.rknn_session.load_rknn(model_fp)
        ret = self.rknn_session.init_runtime(core_mask=int(device_id))
        if ret != 0:
            raise ModelArtefactError(f"Unable to initialize RKNN session. Cause: {ret}")

    def run(self, output_names, input_feed: dict, run_options=None) -> np.ndarray:
        _inputs = input_feed[self.input_name]
        inputs = (
            np.array(_inputs)
            if isinstance(_inputs, list)
            else _inputs[np.newaxis, :, :, :]
        )
        outputs = self.rknn_session.inference(inputs=inputs)[0]
        predictions = (
            np.squeeze(outputs, axis=-1) if len(outputs.shape) > 3 else outputs
        )
        return [predictions]


def get_runtime_platform():
    """
    获取当前的推理平台
    """
    manual_platform = CURRENT_INFERENCE_PLATFORM
    if manual_platform and manual_platform.lower() in ["rknn", "onnx"]:
        logger.info(
            f"CURRENT_INFERENCE_PLATFORM is {manual_platform}, using {manual_platform} runtime"
        )
        return manual_platform
    try:
        subprocess.check_output("rknn-server")
        logger.info("rknn-server is installed, using rknn runtime")
        return "rknn"
    except:
        logger.info("rknn-server is not installed, using onnx runtime")
        return "onnx"


@wrap_roboflow_api_errors()
def get_from_url(
    url: str,
    json_response: bool = True,
    verify_content_length: bool = False,
) -> Union[Response, dict]:
    print(f'request: {url} {verify_content_length}')
    return _get_from_url(
        url=url,
        json_response=json_response,
        # verify_content_length=verify_content_length,
    )
