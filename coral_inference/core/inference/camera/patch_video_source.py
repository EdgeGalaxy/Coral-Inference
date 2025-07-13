from typing import Union, Dict

import cv2
from inference.core.env import RUNS_ON_JETSON

from inference.core.interfaces.camera.video_source import CV2VideoFrameProducer, _consumes_camera_on_jetson

from coral_inference.core.env import CURRENT_INFERENCE_PLATFORM


def _consumes_camera_on_rknn(video: Union[str, int]) -> bool:
    if CURRENT_INFERENCE_PLATFORM.lower() != "rknn":
        return False
    if isinstance(video, int):
        return True
    return video.startswith("/dev/video")


class PatchedCV2VideoFrameProducer(CV2VideoFrameProducer):
    def __init__(self, video: Union[str, int]):
        self._source_ref = video
        if _consumes_camera_on_jetson(video=video):
            self.stream = cv2.VideoCapture(video, cv2.CAP_V4L2)
        elif _consumes_camera_on_rknn(video=video):
            self.stream = cv2.VideoCapture(video, cv2.CAP_V4L2)
            self.stream.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('Y', 'U', 'Y', 'V'))
        else:
            video = int(video) if isinstance(video, str) and video.isdigit() else video
            self.stream = cv2.VideoCapture(video)
