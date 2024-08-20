from functools import partial
import itertools
import platform
from time import perf_counter
from typing import Any, List, Tuple, Union
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from inference.core.env import (
    MAX_BATCH_SIZE,
    MODEL_VALIDATION_DISABLED,
    DISABLE_PREPROC_AUTO_ORIENT,
)
from inference.core.logger import logger
from inference.core.exceptions import ModelArtefactError
from inference.core.models.roboflow import RoboflowInferenceModel
from inference.core.models.utils.batching import create_batches
from inference.core.utils.image_utils import load_image
from inference.core.utils.preprocess import letterbox_image
from inference.core.entities.requests.inference import InferenceRequestImage

from coral_inference.core.models.utils import rknnruntime_session


class RknnCoralInferenceModel(RoboflowInferenceModel):
    def __init__(
        self,
        model_id: str,
        batch_size: int,
        image_size: Tuple[int, int],
        device_platform: str,
        *args,
        **kwargs,
    ):
        """Initializes the OnnxRoboflowInferenceModel instance.

        Args:
            model_id (str): The identifier for the specific ONNX model.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(model_id, *args, **kwargs)

        self.batch_size = batch_size
        self.img_size_h = image_size[0]
        self.img_size_w = image_size[1]
        self.input_name = f"input_{model_id}_{self.img_size_h}x{self.img_size_w}"
        self.platform = device_platform

        self.initialize_model()
        self.image_loader_threadpool = ThreadPoolExecutor(max_workers=None)
        try:
            self.validate_model()
        except ModelArtefactError as e:
            logger.error(f"Unable to validate model artifacts, clearing cache: {e}")
            self.clear_cache()
            raise ModelArtefactError from e

    def infer(self, image: Any, **kwargs) -> Any:
        """Runs inference on given data.
        - image:
            can be a BGR numpy array, filepath, InferenceRequestImage, PIL Image, byte-string, etc.
        """
        input_elements = len(image) if isinstance(image, list) else 1
        max_batch_size = MAX_BATCH_SIZE if self.batching_enabled else self.batch_size
        if (input_elements == 1) or (max_batch_size == float("inf")):
            return super().infer(image, **kwargs)
        logger.debug(
            f"Inference will be executed in batches, as there is {input_elements} input elements and "
            f"maximum batch size for a model is set to: {max_batch_size}"
        )
        inference_results = []
        for batch_input in create_batches(sequence=image, batch_size=max_batch_size):
            batch_inference_results = super().infer(batch_input, **kwargs)
            inference_results.append(batch_inference_results)
        return self.merge_inference_results(inference_results=inference_results)

    def merge_inference_results(self, inference_results: List[Any]) -> Any:
        return list(itertools.chain(*inference_results))

    def validate_model(self) -> None:
        if MODEL_VALIDATION_DISABLED:
            logger.debug("Model validation disabled.")
            return None
        logger.debug("Starting model validation")
        if not self.load_weights:
            return
        try:
            assert self.rknn_session is not None
        except AssertionError as e:
            raise ModelArtefactError(
                "ONNX session not initialized. Check that the model weights are available."
            ) from e
        try:
            self.run_test_inference()
        except Exception as e:
            raise ModelArtefactError(f"Unable to run test inference. Cause: {e}") from e
        try:
            self.validate_model_classes()
        except Exception as e:
            raise ModelArtefactError(
                f"Unable to validate model classes. Cause: {e}"
            ) from e
        logger.debug("Model validation finished")

    def run_test_inference(self) -> None:
        test_image = (np.random.rand(1024, 1024, 3) * 255).astype(np.uint8)
        logger.debug(f"Running test inference. Image size: {test_image.shape}")
        result = self.infer(test_image)
        logger.debug("Test inference finished.")
        return result

    def get_model_output_shape(self) -> Tuple[int, int, int]:
        test_image = (np.random.rand(1024, 1024, 3) * 255).astype(np.uint8)
        logger.debug(f"Getting model output shape. Image size: {test_image.shape}")
        test_image, _ = self.preprocess(test_image)
        output = self.predict(test_image)[0]
        logger.debug("Model output shape test finished.")
        return output.shape

    def validate_model_classes(self) -> None:
        pass

    def get_infer_bucket_file_list(self) -> list:
        """Returns the list of files to be downloaded from the inference bucket for ONNX model.

        Returns:
            list: A list of filenames specific to ONNX models.
        """
        return ["environment.json", "class_names.txt"]

    def initialize_model(self) -> None:
        """Initializes the ONNX model, setting up the inference session and other necessary properties."""
        logger.debug("Getting model artefacts")
        self.get_model_artifacts()
        if self.load_weights or not self.has_model_metadata:
            t1_session = perf_counter()
            try:
                self.rknn_session = rknnruntime_session(
                    model_fp=self.cache_file(self.weights_file),
                    device_id=self.device_id,
                )
            except Exception as e:
                self.clear_cache()
                raise ModelArtefactError(
                    f"Unable to load model Rknn Models. Cause: {e}"
                )
            logger.debug(
                f"Rknn Session creation took {perf_counter() - t1_session:.2f} seconds"
            )

        if isinstance(self.batch_size, str):
            self.batching_enabled = True
            logger.debug(
                f"Model {self.endpoint} is loaded with dynamic batching enabled"
            )
        else:
            self.batching_enabled = False
            logger.debug(
                f"Model {self.endpoint} is loaded with dynamic batching disabled"
            )

        model_metadata = {
            "batch_size": self.batch_size,
            "image_size_h": self.img_size_h,
            "image_size_w": self.img_size_w,
        }
        self.write_model_metadata_to_memcache(model_metadata)
        logger.debug("Model initialisation finished.")

    def preproc_image(
        self,
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
        np_image, is_bgr = load_image(
            image,
            disable_preproc_auto_orient=disable_preproc_auto_orient
            or "auto-orient" not in self.preproc.keys()
            or DISABLE_PREPROC_AUTO_ORIENT,
        )
        preprocessed_image, img_dims = self.preprocess_image(
            np_image,
            disable_preproc_contrast=disable_preproc_contrast,
            disable_preproc_grayscale=disable_preproc_grayscale,
            disable_preproc_static_crop=disable_preproc_static_crop,
        )

        if self.resize_method == "Stretch to":
            resized = cv2.resize(
                preprocessed_image, (self.img_size_w, self.img_size_h), cv2.INTER_CUBIC
            )
        elif self.resize_method == "Fit (black edges) in":
            resized = letterbox_image(
                preprocessed_image, (self.img_size_w, self.img_size_h)
            )
        elif self.resize_method == "Fit (white edges) in":
            resized = letterbox_image(
                preprocessed_image,
                (self.img_size_w, self.img_size_h),
                color=(255, 255, 255),
            )
        elif self.resize_method == "Fit (grey edges) in":
            resized = letterbox_image(
                preprocessed_image,
                (self.img_size_w, self.img_size_h),
                color=(114, 114, 114),
            )

        if is_bgr:
            resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        # img_in = np.transpose(resized, (2, 0, 1))
        img_in = resized.astype(np.float32)
        img_in = np.expand_dims(img_in, axis=0)

        return img_in, img_dims

    def load_image(
        self,
        image: Any,
        disable_preproc_auto_orient: bool = False,
        disable_preproc_contrast: bool = False,
        disable_preproc_grayscale: bool = False,
        disable_preproc_static_crop: bool = False,
    ) -> Tuple[np.ndarray, Tuple[int, int]]:
        if isinstance(image, list):
            preproc_image = partial(
                self.preproc_image,
                disable_preproc_auto_orient=disable_preproc_auto_orient,
                disable_preproc_contrast=disable_preproc_contrast,
                disable_preproc_grayscale=disable_preproc_grayscale,
                disable_preproc_static_crop=disable_preproc_static_crop,
            )
            imgs_with_dims = self.image_loader_threadpool.map(preproc_image, image)
            imgs, img_dims = zip(*imgs_with_dims)
            img_in = np.concatenate(imgs, axis=0)
        else:
            img_in, img_dims = self.preproc_image(
                image,
                disable_preproc_auto_orient=disable_preproc_auto_orient,
                disable_preproc_contrast=disable_preproc_contrast,
                disable_preproc_grayscale=disable_preproc_grayscale,
                disable_preproc_static_crop=disable_preproc_static_crop,
            )
            img_dims = [img_dims]
        return img_in, img_dims

    @property
    def weights_file(self) -> str:
        """Returns the file containing the ONNX model weights.

        Returns:
            str: The file path to the weights file.
        """
        return f"weights_{self.platform}.rknn"
