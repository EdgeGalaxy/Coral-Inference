from inference.core.models import roboflow
from inference.core.logger import logger
from coral_inference.core.models.utils import get_runtime_platform
from coral_inference.core.models import rknn_base

runtime_platform = get_runtime_platform()

if runtime_platform == "rknn":
    roboflow.OnnxRoboflowInferenceModel.initialize_model = (
        rknn_base.extend_initialize_model(
            roboflow.OnnxRoboflowInferenceModel.initialize_model
        )
    )
    roboflow.OnnxRoboflowInferenceModel.preproc_image = rknn_base.extend_preproc_image(
        roboflow.OnnxRoboflowInferenceModel.preproc_image
    )
    roboflow.OnnxRoboflowInferenceModel.get_all_required_infer_bucket_file = (
        rknn_base.extend_get_all_required_infer_bucket_file(
            roboflow.OnnxRoboflowInferenceModel.get_all_required_infer_bucket_file
        )
    )
    roboflow.OnnxRoboflowInferenceModel.download_model_artifacts_from_roboflow_api = rknn_base.extend_download_model_artifacts(
        roboflow.OnnxRoboflowInferenceModel.download_model_artifacts_from_roboflow_api
    )

    roboflow.OnnxRoboflowInferenceModel.rknn_weights_file = property(
        rknn_base.rknn_weights_file
    )

    logger.info(
        "runtime_platform is rknn, using RknnCoralInferenceModel replace OnnxRoboflowInferenceModel"
    )
else:
    logger.info(
        "runtime_platform is {runtime_platform}, using default OnnxRoboflowInferenceModel"
    )
