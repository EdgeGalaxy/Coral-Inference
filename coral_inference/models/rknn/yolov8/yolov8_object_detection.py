from typing import Tuple

import numpy as np

from coral_inference.core.models.object_detection_base import (
    ObjectDetectionBaseRknnCoralInferenceModel,
)


class YOLOv8RknnObjectDetection(ObjectDetectionBaseRknnCoralInferenceModel):
    """Coral RKNN Object detection model (Implements an object detection specific infer method).

    This class is responsible for performing object detection using the YOLOv8 model
    with RKNN runtime.

    Attributes:
        weights_file (str): Path to the RKNN weights file.

    Methods:
        predict: Performs object detection on the given image using the RKNN session.
    """

    @property
    def weights_file(self) -> str:
        """Gets the weights file for the YOLOv8 model.

        Returns:
            str: Path to the RKNN weights file.
        """
        return f"weights_{self.platform}.rknn"

    def predict(self, img_in: np.ndarray, **kwargs) -> Tuple[np.ndarray]:
        """Performs object detection on the given image using the RKNN session.

        Args:
            img_in (np.ndarray): Input image as a NumPy array.

        Returns:
            Tuple[np.ndarray]: NumPy array representing the predictions, including boxes, confidence scores, and class confidence scores.
        """
        # img_in = img_in if img_ else img_in[np.newaxis, :, :, :]
        predictions = self.rknn_session.inference(inputs=[img_in])[0]
        predictions = (
            np.squeeze(predictions, axis=-1)
            if len(predictions.shape) > 3
            else predictions
        )

        predictions = predictions.transpose(0, 2, 1)
        boxes = predictions[:, :, :4]
        class_confs = predictions[:, :, 4:]
        confs = np.expand_dims(np.max(class_confs, axis=2), axis=2)
        predictions = np.concatenate([boxes, confs, class_confs], axis=2)
        return (predictions,)
