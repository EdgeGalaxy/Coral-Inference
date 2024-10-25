from functools import partialmethod

import inference.core.models.roboflow as roboflow
from inference.core.logger import logger

from coral_inference.core.env import CURRENT_INFERENCE_PLATFORM
from coral_inference.core.models import rknn_base


if CURRENT_INFERENCE_PLATFORM == "rknn":
    print(f"CURRENT_INFERENCE_PLATFORM is {CURRENT_INFERENCE_PLATFORM}")
    roboflow.OnnxRoboflowInferenceModel.initialize_model = partialmethod(
        rknn_base.initialize_model,
        origin_method=roboflow.OnnxRoboflowInferenceModel.initialize_model,
    )
    roboflow.OnnxRoboflowInferenceModel.preproc_image = partialmethod(
        rknn_base.preproc_image,
        origin_method=roboflow.OnnxRoboflowInferenceModel.preproc_image,
    )
    roboflow.OnnxRoboflowInferenceModel.get_all_required_infer_bucket_file = partialmethod(
        rknn_base.get_all_required_infer_bucket_file,
        origin_method=roboflow.OnnxRoboflowInferenceModel.get_all_required_infer_bucket_file,
    )
    roboflow.OnnxRoboflowInferenceModel.download_model_artifacts_from_roboflow_api = partialmethod(
        rknn_base.download_model_artifacts_from_roboflow_api,
        origin_method=roboflow.OnnxRoboflowInferenceModel.download_model_artifacts_from_roboflow_api,
    )
    roboflow.OnnxRoboflowInferenceModel.rknn_weights_file = property(
        rknn_base.rknn_weights_file
    )

    logger.info(
        f"CURRENT_INFERENCE_PLATFORM is {CURRENT_INFERENCE_PLATFORM}, useing RknnCoralInferenceModel replace OnnxRoboflowInferenceModel"
    )
else:
    logger.info(
        f"CURRENT_INFERENCE_PLATFORM is {CURRENT_INFERENCE_PLATFORM}, useing default OnnxRoboflowInferenceModel"
    )
