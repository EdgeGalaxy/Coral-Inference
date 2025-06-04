
from collections import deque
from typing import Union, List, Optional

from inference.core.interfaces.stream.sinks import InMemoryBufferSink
from inference.core.interfaces.camera.entities import VideoFrame


class InMemoryBufferSinkPatch(InMemoryBufferSink):
    def __init__(self, queue_size: int):
        super().__init__(queue_size)
        self._webrtc_buffer = deque(maxlen=queue_size)
    
    def on_prediction(
        self,
        predictions: Union[dict, List[Optional[dict]]],
        video_frame: Union[VideoFrame, List[Optional[VideoFrame]]],
    ) -> None:
        self._webrtc_buffer.append((predictions, video_frame))
        super().on_prediction(predictions, video_frame)
