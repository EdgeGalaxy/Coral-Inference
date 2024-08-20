import cv2
import supervision as sv
from coral_inference import get_model

model = get_model(model_id="yolov8n-640")
image = cv2.imread("test.jpg")
results = model.infer(image)[0]
detections = sv.Detections.from_inference(results)

box_annotator = sv.BoxAnnotator()
label_annotator = sv.LabelAnnotator()

annotated_image = box_annotator.annotate(scene=image, detections=detections)
annotated_image = label_annotator.annotate(scene=annotated_image, detections=detections)

cv2.imwrite("annotated.jpg", annotated_image)
# print(results)
