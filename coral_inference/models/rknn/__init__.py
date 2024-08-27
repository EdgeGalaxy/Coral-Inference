from coral_inference.models.rknn.yolov8 import YOLOv8RknnObjectDetection


RKNN_MODEL_TYPES = {
    ("object-detection", "yolov8"): YOLOv8RknnObjectDetection,
    ("object-detection", "yolov8s"): YOLOv8RknnObjectDetection,
    ("object-detection", "yolov8n"): YOLOv8RknnObjectDetection,
    ("object-detection", "yolov8s"): YOLOv8RknnObjectDetection,
    ("object-detection", "yolov8m"): YOLOv8RknnObjectDetection,
    ("object-detection", "yolov8l"): YOLOv8RknnObjectDetection,
    ("object-detection", "yolov8x"): YOLOv8RknnObjectDetection,
}
