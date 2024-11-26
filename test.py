import cv2
import sys
import supervision as sv

sys.path.append(".")

from coral_inference import get_model

# from inference_sdk import InferenceHTTPClient

model = get_model(model_id="yolov8s-640", api_key="jDmVpLRLlwVHOafDapSi")

image = cv2.imread("test.jpg")
results = model.infer(image)[0]
sv.Detections.from_inference(results)


# client = InferenceHTTPClient(
#     api_url="http://localhost:8000",
#     api_key="dfasdfads",
# )

# with client.use_model(model_id='yolov8n-640'):
#     predictions = client.infer(image)
#     print(predictions)


# print(client.list_inference_pipelines())

# # # workflow definition
# OBJECT_DETECTION_WORKFLOW = {
#     "version": "1.0",
#     "inputs": [
#         {"type": "WorkflowImage", "name": "image"},
#         {
#             "type": "WorkflowParameter",
#             "name": "model_id",
#             "default_value": "yolov8n-640",
#         },
#         {"type": "WorkflowParameter", "name": "confidence", "default_value": 0.3},
#     ],
#     "steps": [
#         {
#             "type": "RoboflowObjectDetectionModel",
#             "name": "detection",
#             "image": "$inputs.image",
#             "model_id": "$inputs.model_id",
#             "confidence": "$inputs.confidence",
#         }
#     ],
#     "outputs": [
#         {"type": "JsonField", "name": "result", "selector": "$steps.detection.*"}
#     ],
# }


# data = client.start_inference_pipeline_with_workflow(
#     video_reference="/Users/zhaokefei/Downloads/test.mov",
#     workflow_specification=OBJECT_DETECTION_WORKFLOW,
# )
# print(data)

# print(client.get_inference_pipeline_status(pipeline_id='3c103cac-dd35-40f3-8cdd-f5798fcd875a'))
# print(client.list_inference_pipelines())
