"""
Local SQLite buffer for uptime segments.
Records status changes offline and flushes to backend when network is available.
"""
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import List, Optional

import aiohttp
from inference.core.env import API_BASE_URL, MODEL_CACHE_DIR
from coral_inference.core.env import CORAL_BACKEND_INTERNAL_SECRET
from coral_inference.core.log import logger


_DB_PATH = os.path.join(MODEL_CACHE_DIR, "uptime_buffer.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=2)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS uptime_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            target_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            source TEXT NOT NULL DEFAULT 'edge',
            created_at INTEGER NOT NULL
        )"""
    )
    conn.commit()
    return conn


def record_segment(
    kind: str,
    target_id: str,
    workspace_id: str,
    status: str,
    started_at: datetime,
    ended_at: Optional[datetime] = None,
) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO uptime_segments (kind, target_id, workspace_id, status, started_at, ended_at, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'edge', ?)",
            (
                kind,
                target_id,
                workspace_id,
                status,
                started_at.isoformat(),
                ended_at.isoformat() if ended_at else None,
                int(time.time()),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("uptime_buffer: failed to record segment: {}", e)


def _pop_pending(workspace_id: str, kind: str, target_id: str, limit: int = 200) -> List[dict]:
    try:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT id, kind, target_id, workspace_id, status, started_at, ended_at, source "
            "FROM uptime_segments WHERE workspace_id=? AND kind=? AND target_id=? "
            "ORDER BY started_at ASC LIMIT ?",
            (workspace_id, kind, target_id, limit),
        )
        rows = cursor.fetchall()
        if not rows:
            conn.close()
            return []
        ids = [r[0] for r in rows]
        segments = [
            {
                "kind": r[1],
                "target_id": r[2],
                "workspace_id": r[3],
                "status": r[4],
                "started_at": r[5],
                "ended_at": r[6],
                "source": r[7],
            }
            for r in rows
        ]
        conn.execute(f"DELETE FROM uptime_segments WHERE id IN ({','.join('?' * len(ids))})", ids)
        conn.commit()
        conn.close()
        return segments
    except Exception as e:
        logger.warning("uptime_buffer: failed to pop pending: {}", e)
        return []


async def flush_to_backend(
    workspace_id: str,
    kind: str,
    target_id: str,
    backend_url: Optional[str] = None,
    backend_secret: Optional[str] = None,
) -> bool:
    segments = _pop_pending(workspace_id, kind, target_id)
    if not segments:
        return True

    resolved_url = (backend_url or API_BASE_URL or "").rstrip("/")
    secret = backend_secret or CORAL_BACKEND_INTERNAL_SECRET
    if not resolved_url or not secret:
        logger.warning("uptime_buffer: no backend URL/secret, re-queuing {} segments", len(segments))
        _requeue(segments)
        return False

    url = f"{resolved_url}/api/reef/workspaces/{workspace_id}/uptime/{kind}/{target_id}/edge-segments"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=segments,
                headers={"X-Internal-Secret": secret},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status < 300:
                    logger.info("uptime_buffer: flushed {} segments for {}/{}", len(segments), kind, target_id)
                    return True
                else:
                    logger.warning("uptime_buffer: backend returned {}, re-queuing", resp.status)
                    _requeue(segments)
                    return False
    except Exception as e:
        logger.warning("uptime_buffer: flush failed ({}), re-queuing {} segments", e, len(segments))
        _requeue(segments)
        return False


def _requeue(segments: List[dict]) -> None:
    try:
        conn = _get_conn()
        for seg in segments:
            conn.execute(
                "INSERT INTO uptime_segments (kind, target_id, workspace_id, status, started_at, ended_at, source, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    seg["kind"], seg["target_id"], seg["workspace_id"],
                    seg["status"], seg["started_at"], seg.get("ended_at"),
                    seg.get("source", "edge"), int(time.time()),
                ),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("uptime_buffer: failed to requeue: {}", e)
