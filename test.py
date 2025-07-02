import requests

from inference_sdk import InferenceHTTPClient

client = InferenceHTTPClient(
    api_url="http://localhost:9001", # use local inference server
    api_key="jDmVpLRLlwVHOafDapSi"
)

# data = {
#   "version": "1.0",
#   "inputs": [
#     {
#       "type": "InferenceImage",
#       "name": "image"
#     }
#   ],
#   "steps": [
#     {
#       "type": "roboflow_core/roboflow_object_detection_model@v1",
#       "name": "model",
#       "images": "$inputs.image",
#       "model_id": "yolov8s-640"
#     },
#     {
#       "type": "roboflow_core/bounding_box_visualization@v1",
#       "name": "detection_visualization",
#       "image": "$inputs.image",
#       "predictions": "$steps.model.predictions"
#     },
#     {
#       "type": "roboflow_core/property_definition@v1",
#       "name": "count_objects",
#       "data": "$steps.model.predictions",
#       "operations": [
#         {
#           "type": "SequenceLength"
#         }
#       ]
#     },
#     {
#       "type": "roboflow_core/label_visualization@v1",
#       "name": "annotated_image",
#       "image": "$steps.detection_visualization.image",
#       "predictions": "$steps.model.predictions"
#     }
#   ],
#   "outputs": [
#     {
#       "type": "JsonField",
#       "name": "count_objects",
#       "coordinates_system": "own",
#       "selector": "$steps.count_objects.output"
#     },
#     {
#       "type": "JsonField",
#       "name": "output_image",
#       "coordinates_system": "own",
#       "selector": "$steps.annotated_image.image"
#     },
#     {
#       "type": "JsonField",
#       "name": "predictions",
#       "coordinates_system": "own",
#       "selector": "$steps.model.predictions"
#     }
#   ]
# }

# result = client.start_inference_pipeline_with_workflow(
#     workspace_name="test-j47p5",
#     workflow_specification=data,
#     video_reference=0
# )

# print(result)

print(client.list_inference_pipelines())
# r = client.pause_inference_pipeline(pipeline_id="d8620d8b-f7ec-4649-83df-9525573cbfc5")
# print(r)

# print(client.get_inference_pipeline_status(pipeline_id="0f85a17f-99cc-45d7-bfba-84314f236bcf"))
# print(client.consume_inference_pipeline_result(pipeline_id="bcb55e80-611a-4f54-8019-160ecf060b10"))
# print(client.resume_inference_pipeline(pipeline_id="d39943ab-c019-4adb-bf0c-5e3513a21fb9"))
# print(client.terminate_inference_pipeline(pipeline_id="bcb55e80-611a-4f54-8019-160ecf060b10"))
# print(client.consume_inference_pipeline_result(pipeline_id="0f85a17f-99cc-45d7-bfba-84314f236bcf"))