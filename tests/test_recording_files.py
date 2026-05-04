import os
import sys
import time
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1] / "docker"))

from config.core.stream.recording_files import list_recording_files


def test_list_recording_files_returns_single_completed_segment(tmp_path):
    video_path = tmp_path / "20260504120000.mp4"
    video_path.write_bytes(b"fake mp4")
    completed_at = time.time() - 10
    os.utime(video_path, (completed_at, completed_at))

    files = list_recording_files(str(tmp_path))

    assert [item["filename"] for item in files] == ["20260504120000.mp4"]


def test_list_recording_files_hides_recently_modified_segment(tmp_path):
    video_path = tmp_path / "20260504120000.mp4"
    video_path.write_bytes(b"fake mp4")

    files = list_recording_files(str(tmp_path), active_write_grace_seconds=60)

    assert files == []
