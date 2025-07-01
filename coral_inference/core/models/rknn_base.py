from time import perf_counter
from typing import Any, Tuple, Union, List

import numpy as np

from inference.core.cache import cache
from inference.core.exceptions import ModelArtefactError
from inference.core.roboflow_api import (
    ModelEndpointType,
    get_roboflow_model_data,
    get_from_url,
)
from inference.core.cache.model_artifacts import save_bytes_in_cache
from inference.core.models.roboflow import OnnxRoboflowInferenceModel
from inference.core.entities.requests.inference import InferenceRequestImage

from coral_inference.core.log import logger
from coral_inference.core.models.utils import RknnInferenceSession
from coral_inference.core.models.decorators import extend_method_after


def rknn_weights_file(self: OnnxRoboflowInferenceModel) -> str:
    return self.weights_file.replace(".onnx", ".rknn")


@extend_method_after
def extend_initialize_model(self, original_result: None, *args, **kwargs) -> None:
    """扩展初始化模型的方法"""
    model_inputs = self.onnx_session.get_inputs()[0]
    del self.onnx_session

    if self.has_model_metadata:
        t1_session = perf_counter()
        try:
            self.onnx_session = RknnInferenceSession(
                model_fp=self.cache_file(self.rknn_weights_file), inputs=model_inputs
            )
        except Exception as e:
            self.clear_cache()
            raise ModelArtefactError(f"Unable to load model Rknn Models. Cause: {e}")
        logger.debug(
            f"Rknn Session creation took {perf_counter() - t1_session:.2f} seconds"
        )
        if "resize" in self.preproc:
            self.img_size_h = int(self.preproc["resize"]["height"])
            self.img_size_w = int(self.preproc["resize"]["width"])
        logger.debug(f"img_size_h: {self.img_size_h}, img_size_w: {self.img_size_w}")
    else:
        raise ModelArtefactError(
            "Rknn initialisation failed! -> No model metadata found!"
        )


@extend_method_after
def extend_preproc_image(
    self,
    original_result: Tuple[np.ndarray, Tuple[int, int]],
    image: Union[Any, InferenceRequestImage],
    **kwargs,
) -> Tuple[np.ndarray, Tuple[int, int]]:
    """扩展图像预处理方法"""
    img_in, img_dims = original_result
    img_in = np.transpose(img_in, (0, 2, 3, 1))
    img_in = np.squeeze(img_in, axis=0)
    img_in *= 255.0
    return img_in, img_dims


@extend_method_after
def extend_get_all_required_infer_bucket_file(
    self, original_result: List[str], *args, **kwargs
) -> List[str]:
    """扩展获取所需推理文件的方法"""
    original_result.append(self.rknn_weights_file)
    return original_result


@extend_method_after
def extend_download_model_artifacts(
    self, original_result: None, *args, **kwargs
) -> None:
    """扩展下载模型文件的方法"""
    api_data_cache_key = f"roboflow_api_data:{ModelEndpointType.ORT}:{self.endpoint}"
    api_data = cache.get(api_data_cache_key)

    if api_data is None:
        api_data = get_roboflow_model_data(
            api_key=self.api_key,
            model_id=self.endpoint,
            endpoint_type=ModelEndpointType.ORT,
            device_id=self.device_id,
        )
        if 'ort' not in api_data:
            raise ModelArtefactError(
                "Could not find `ort` key in roboflow API model description response."
            )
        api_data = api_data['ort']

    if "rknn_model" not in api_data:
        raise ModelArtefactError(
            "Could not find `rknn_model` key in roboflow API model description response."
        )

    model_weights_response = get_from_url(api_data["rknn_model"], json_response=False)
    save_bytes_in_cache(
        content=model_weights_response.content,
        file=self.rknn_weights_file,
        model_id=self.endpoint,
    )
