from time import perf_counter
from typing import Any, Tuple, Union, List, Callable

import numpy as np

from inference.core.cache import cache
from inference.core.logger import logger
from inference.core.exceptions import ModelArtefactError
from inference.core.roboflow_api import (
    ModelEndpointType,
    get_roboflow_model_data,
    get_from_url,
)
from inference.core.cache.model_artifacts import save_bytes_in_cache
from inference.core.models.roboflow import OnnxRoboflowInferenceModel
from inference.core.entities.requests.inference import InferenceRequestImage

from coral_inference.core.models.utils import RknnInferenceSession


def rknn_weights_file(self: OnnxRoboflowInferenceModel) -> str:
    return self.weights_file.replace(".onnx", ".rknn")


def initialize_model(self: OnnxRoboflowInferenceModel, origin_method: Callable) -> None:
    """Initializes the Rknn model, setting up the inference session and other necessary properties."""
    print(f"initialize_rknn_model {self.rknn_weights_file}")

    # Initialize the base onnx model
    origin_method(self)

    model_inputs = self.onnx_session.get_inputs()[0]
    # Delete the onnx session
    del self.onnx_session

    if self.has_model_metadata:
        t1_session = perf_counter()
        try:
            self.rknn_session = RknnInferenceSession(
                model_fp=self.cache_file(self.rknn_weights_file), inputs=model_inputs
            )
        except Exception as e:
            self.clear_cache()
            raise ModelArtefactError(f"Unable to load model Rknn Models. Cause: {e}")
        logger.debug(
            f"Rknn Session creation took {perf_counter() - t1_session:.2f} seconds"
        )
    else:
        raise ModelArtefactError(
            "Rknn initialisation failed! -> No model metadata found!"
        )


def preproc_image(
    self: OnnxRoboflowInferenceModel,
    origin_method: Callable,
    image: Union[Any, InferenceRequestImage],
    disable_preproc_auto_orient: bool = False,
    disable_preproc_contrast: bool = False,
    disable_preproc_grayscale: bool = False,
    disable_preproc_static_crop: bool = False,
) -> Tuple[np.ndarray, Tuple[int, int]]:
    """
    Preprocesses an inference request image by loading it, then applying any pre-processing specified by the Roboflow platform, then scaling it to the inference input dimensions.

    Args:
        image (Union[Any, InferenceRequestImage]): An object containing information necessary to load the image for inference.
        disable_preproc_auto_orient (bool, optional): If true, the auto orient preprocessing step is disabled for this call. Default is False.
        disable_preproc_contrast (bool, optional): If true, the contrast preprocessing step is disabled for this call. Default is False.
        disable_preproc_grayscale (bool, optional): If true, the grayscale preprocessing step is disabled for this call. Default is False.
        disable_preproc_static_crop (bool, optional): If true, the static crop preprocessing step is disabled for this call. Default is False.

    Returns:
        Tuple[np.ndarray, Tuple[int, int]]: A tuple containing a numpy array of the preprocessed image pixel data and a tuple of the images original size.
    """
    img_in, img_dims = origin_method(
        self,
        image,
        disable_preproc_auto_orient=disable_preproc_auto_orient,
        disable_preproc_contrast=disable_preproc_contrast,
        disable_preproc_grayscale=disable_preproc_grayscale,
        disable_preproc_static_crop=disable_preproc_static_crop,
    )

    ## ! FIXME: This is a temporary fix to scale the image to the correct format for Rknn
    # Transpose the image to the correct format for Rknn
    img_in = np.transpose(img_in, (0, 2, 3, 1))
    img_in = np.squeeze(img_in, axis=0)
    # Scale the image
    img_in *= 255.0

    return img_in, img_dims


def get_all_required_infer_bucket_file(
    self: OnnxRoboflowInferenceModel, origin_method: Callable
) -> List[str]:
    infer_bucket_files = origin_method(self)
    infer_bucket_files.append(self.rknn_weights_file)
    return infer_bucket_files


def download_model_artifacts_from_roboflow_api(
    self: OnnxRoboflowInferenceModel, origin_method: Callable
) -> None:
    origin_method(self)

    # rknn model save in cache
    api_data_cache_key = f"roboflow_api_data:{ModelEndpointType.ORT}:{self.endpoint}"
    api_data = cache.get(api_data_cache_key)
    if api_data is not None:
        if "rknn_model" not in api_data:
            raise ModelArtefactError(
                "Could not find `rknn_model` key in roboflow API model description response."
            )
    else:
        api_data = get_roboflow_model_data(
            api_key=self.api_key,
            model_id=self.endpoint,
            endpoint_type=ModelEndpointType.ORT,
            device_id=self.device_id,
        )
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
