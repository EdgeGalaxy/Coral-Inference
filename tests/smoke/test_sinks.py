import datetime
from queue import Queue
from unittest import mock

import numpy as np
import pytest

from coral_inference.core.inference.stream.video_sink import TimeBasedVideoSink


class DummyFrame:
    def __init__(self):
        self.image = np.zeros((32, 32, 3), dtype=np.uint8)
        self.frame_timestamp = datetime.datetime.now()
        self.source_id = "cam-1"


def test_time_based_video_sink_processes_frames(tmp_path, monkeypatch):
    """Verify TimeBasedVideoSink can enqueue and process frames without touching disk."""

    # Redirect MODEL_CACHE_DIR to a temporary folder
    monkeypatch.setattr(
        "inference.core.env.MODEL_CACHE_DIR", tmp_path.as_posix(), raising=False
    )

    written_frames = []

    class DummyWriter:
        def __init__(self, *_args, **_kwargs):
            pass

        def write(self, image):
            written_frames.append(image.copy())

        def release(self):
            pass

    # Prevent background thread & heavy operations
    monkeypatch.setattr(
        TimeBasedVideoSink,
        "_start_worker_thread",
        lambda self: None,
    )
    monkeypatch.setattr(
        TimeBasedVideoSink,
        "_optimize_video_for_web",
        lambda self, path: None,
    )
    monkeypatch.setattr(
        "coral_inference.core.inference.stream.video_sink.cv2.VideoWriter",
        DummyWriter,
    )

    sink = TimeBasedVideoSink.init(
        pipeline_id="pipe-1",
        output_directory="records",
        video_info=None,
        segment_duration=1,
        queue_size=10,
    )

    # Replace queue with controllable instance
    sink._prediction_queue = Queue()

    sink.on_prediction(predictions=None, video_frames=DummyFrame())
    queue_item = sink._prediction_queue.get(timeout=1)
    sink._process_batch_predictions([queue_item])

    assert len(written_frames) >= 1

