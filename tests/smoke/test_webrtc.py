import asyncio
import datetime
from collections import deque
from threading import Event

import numpy as np
from coral_inference.core.inference.camera.webrtc_manager import WebRTCManager


class DummyFrame:
    def __init__(self):
        self.image = np.zeros((16, 16, 3), dtype=np.uint8)
        self.frame_timestamp = datetime.datetime.now()
        self.source_id = "cam-1"


class DummyImageData:
    def __init__(self, image):
        self.numpy_image = image


class DummyQueue:
    def __init__(self):
        self.items = []

    async def async_put(self, item):
        self.items.append(item)


def test_webrtc_manager_processes_buffer(monkeypatch):
    manager = WebRTCManager()
    manager.stop_event = Event()
    manager.from_inference_queue = DummyQueue()

    def fake_render_statistics(image, frame_timestamp, fps):  # noqa: ARG001
        return image

    def fake_merge_frames(show_frames, layout="grid"):  # noqa: ARG001
        # Return merged placeholder
        assert "cam-1" in show_frames
        return np.zeros((10, 10, 3), dtype=np.uint8)

    monkeypatch.setattr(
        "coral_inference.core.inference.camera.webrtc_manager.render_statistics",
        fake_render_statistics,
    )
    monkeypatch.setattr(
        "coral_inference.core.inference.camera.webrtc_manager.merge_frames",
        fake_merge_frames,
    )

    webrtc_buffer = deque()
    webrtc_buffer.append(({"main": DummyImageData(np.zeros((16, 16, 3)) )}, DummyFrame()))
    
    async def runner():
        task = asyncio.create_task(
            manager._process_video_frames(webrtc_buffer, lambda pred, frame: frame.image)
        )
        await asyncio.sleep(0.1)
        manager.stop_event.set()
        await task

    asyncio.run(runner())

    assert len(manager.from_inference_queue.items) >= 1
