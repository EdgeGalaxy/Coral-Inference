from inference.core.models import roboflow
from inference.core.logger import logger
from inference.core.interfaces.stream import sinks
from inference.core.interfaces.stream_manager.api import stream_manager_client
from inference.core.interfaces.stream_manager.manager_app import app
from inference.core.interfaces.stream_manager.manager_app import inference_pipeline_manager

from coral_inference.core.models.utils import get_runtime_platform
from coral_inference.core.models import rknn_base
from coral_inference.core.inference.stream_manager import patch_app
from coral_inference.core.inference.stream_manager import patch_manager_client
from coral_inference.core.inference.stream_manager import patch_pipeline_manager
from coral_inference.core.inference.stream import patch_sinks

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
        f"runtime_platform is {runtime_platform}, using default OnnxRoboflowInferenceModel"
    )

sinks.InMemoryBufferSink.__init__ = patch_sinks.extend_init(sinks.InMemoryBufferSink.__init__)
sinks.InMemoryBufferSink.on_prediction = patch_sinks.extend_on_prediction(sinks.InMemoryBufferSink.on_prediction)
inference_pipeline_manager.InferencePipelineManager._offer = patch_pipeline_manager.offer
inference_pipeline_manager.InferencePipelineManager._handle_command = patch_pipeline_manager.rewrite_handle_command
stream_manager_client.StreamManagerClient.offer = patch_manager_client.offer
app.InferencePipelinesManagerHandler.handle = patch_app.rewrite_handle
app.execute_termination = patch_app.rewrite_execute_termination
