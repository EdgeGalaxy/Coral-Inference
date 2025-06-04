import requests

from inference_sdk import InferenceHTTPClient

client = InferenceHTTPClient(
    api_url="http://localhost:9001", # use local inference server
    api_key="jDmVpLRLlwVHOafDapSi"
)

data = {
  "version": "1.0",
  "inputs": [
    {
      "type": "InferenceImage",
      "name": "image"
    }
  ],
  "steps": [
    {
      "type": "ObjectDetectionModel",
      "name": "model",
      "image": "$inputs.image",
      "model_id": "yolov8n-640",
      "confidence": 0.4,
      "iou_threshold": 0.4,
      "class_agnostic_nms": True,
      "images": "$inputs.image"
    }
  ],
  "outputs": [
    {
      "type": "JsonField",
      "name": "image",
      "coordinates_system": "own",
      "selector": "$inputs.image"
    },
    {
      "type": "JsonField",
      "name": "predictions",
      "selector": "$steps.model.predictions"
    }
  ]
}

result = client.start_inference_pipeline_with_workflow(
    workspace_name="test-j47p5",
    workflow_specification=data,
    video_reference=['https://media.roboflow.com/supervision/video-examples/people-walking.mp4']
)

print(result)