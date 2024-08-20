import numpy as np
import pytest

from inference.core.entities.responses.inference import (
    ObjectDetectionInferenceResponse,
)
from coral_inference.models import (
    YOLOv8RknnObjectDetection,
)


def assert_yolov8_detection_prediction_matches_reference(
    prediction: ObjectDetectionInferenceResponse,
) -> None:
    assert (
        len(prediction.predictions) == 1
    ), "Example model is expected to predict 1 bbox, as this is the result obtained while test creation"
    assert (
        prediction.predictions[0].class_name == "dog"
    ), "Dog class was predicted by exported model"
    assert (
        abs(prediction.predictions[0].confidence - 0.892430) < 1e-3
    ), "Confidence while test creation was 0.892430"
    xywh = [
        prediction.predictions[0].x,
        prediction.predictions[0].y,
        prediction.predictions[0].width,
        prediction.predictions[0].height,
    ]
    assert np.allclose(
        xywh, [360.0, 215.5, 558.0, 411.0], atol=0.6
    ), "while test creation, box coordinates was [360.0, 215.5, 558.0, 411.0]"


@pytest.mark.slow
def test_yolov8_detection_single_image_inference(
    yolov8_det_model: str,
    example_image: np.ndarray,
) -> None:
    # given
    model = YOLOv8RknnObjectDetection(model_id=yolov8_det_model, api_key="DUMMY")

    # when
    result = model.infer(example_image)

    # then
    assert len(result) == 1, "Batch size=1 hence 1 result expected"
    assert_yolov8_detection_prediction_matches_reference(prediction=result[0])
