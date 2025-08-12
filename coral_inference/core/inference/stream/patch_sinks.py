
from collections import deque
from typing import Union, List, Optional


from inference.core.interfaces.stream.sinks import InMemoryBufferSink
from inference.core.interfaces.camera.entities import VideoFrame

from coral_inference.core.models.decorators import extend_method_after



@extend_method_after
def extend_init(self: InMemoryBufferSink, result, queue_size: int):
    self._webrtc_buffer = deque(maxlen=queue_size)


@extend_method_after
def extend_on_prediction(
    self: InMemoryBufferSink, 
    result, 
    predictions: Union[dict, List[Optional[dict]]], 
    video_frame: Union[VideoFrame, List[Optional[VideoFrame]]]
):
    self._webrtc_buffer.append((predictions, video_frame))

