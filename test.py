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
      "type": "roboflow_core/roboflow_object_detection_model@v1",
      "name": "model",
      "images": "$inputs.image",
      "model_id": "yolov8s-640"
    },
    {
      "type": "roboflow_core/bounding_box_visualization@v1",
      "name": "detection_visualization",
      "image": "$inputs.image",
      "predictions": "$steps.model.predictions"
    },
    {
      "type": "roboflow_core/property_definition@v1",
      "name": "count_objects",
      "data": "$steps.model.predictions",
      "operations": [
        {
          "type": "SequenceLength"
        }
      ]
    },
    {
      "type": "roboflow_core/label_visualization@v1",
      "name": "annotated_image",
      "image": "$steps.detection_visualization.image",
      "predictions": "$steps.model.predictions"
    }
  ],
  "outputs": [
    {
      "type": "JsonField",
      "name": "count_objects",
      "coordinates_system": "own",
      "selector": "$steps.count_objects.output"
    },
    {
      "type": "JsonField",
      "name": "output_image",
      "coordinates_system": "own",
      "selector": "$steps.annotated_image.image"
    },
    {
      "type": "JsonField",
      "name": "predictions",
      "coordinates_system": "own",
      "selector": "$steps.model.predictions"
    }
  ]
}

result = client.start_inference_pipeline_with_workflow(
    workspace_name="test-j47p5",
    workflow_specification=data,
    video_reference=0
)

print(result)