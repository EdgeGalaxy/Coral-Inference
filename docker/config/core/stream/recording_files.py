import os
import time
from typing import Any, Dict, List


def list_recording_files(
    base_dir: str,
    *,
    active_write_grace_seconds: float = 3.0,
) -> List[Dict[str, Any]]:
    if not os.path.isdir(base_dir):
        return []

    now = time.time()
    files: List[Dict[str, Any]] = []
    for name in os.listdir(base_dir):
        if not name.lower().endswith(".mp4"):
            continue
        file_path = os.path.join(base_dir, name)
        if not os.path.isfile(file_path):
            continue
        stat = os.stat(file_path)
        if now - stat.st_mtime < active_write_grace_seconds:
            continue
        files.append(
            {
                "filename": name,
                "size_bytes": stat.st_size,
                "created_at": int(stat.st_ctime),
                "modified_at": int(stat.st_mtime),
            }
        )

    files.sort(key=lambda item: item["created_at"], reverse=True)
    return files
