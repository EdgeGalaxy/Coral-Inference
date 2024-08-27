import cv2
import supervision as sv
from coral_inference import get_model

model = get_model(model_id="yolov8n-640")
image = cv2.imread("test.jpg")
results = model.infer(image)[0]

print(results)
