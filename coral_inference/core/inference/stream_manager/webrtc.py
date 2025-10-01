import asyncio
import time
from threading import Event
from typing import List, Optional

import cv2 as cv
import numpy as np
from fractions import Fraction
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
)
from aiortc.rtcrtpreceiver import RemoteStreamTrack
from av import VideoFrame
from av import logging as av_logging
from loguru import logger

from inference.core.interfaces.stream_manager.manager_app.entities import (
    WebRTCOffer,
    WebRTCTURNConfig,
)
from inference.core.utils.async_utils import Queue as SyncAsyncQueue


def overlay_text_on_np_frame(frame: np.ndarray, text: List[str]):
    for i, l in enumerate(text):
        frame = cv.putText(
            frame,
            l,
            (10, 20 + 30 * i),
            cv.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )
    return frame


class VideoTransformTrack(VideoStreamTrack):
    def __init__(
        self,
        from_inference_queue: "SyncAsyncQueue[np.ndarray]",
        processing_timeout: float,
        min_consecutive_on_time: int,
        webcam_fps: Optional[float] = None,
        max_consecutive_timeouts: Optional[int] = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.processing_timeout: float = processing_timeout

        self.track: Optional[RemoteStreamTrack] = None
        self._track_active: bool = True

        self._id = time.time_ns()
        self._processed = 0

        self.fps = int(webcam_fps)

        self.from_inference_queue: "SyncAsyncQueue[np.ndarray]" = from_inference_queue

        self._last_frame: Optional[VideoFrame] = None
        self._consecutive_timeouts: int = 0
        self._consecutive_on_time: int = 0
        self._max_consecutive_timeouts: Optional[int] = max_consecutive_timeouts
        self._min_consecutive_on_time: int = min_consecutive_on_time

        self._av_logging_set: bool = False

    def close(self):
        self._track_active = False

    async def recv(self):
        # Silencing swscaler warnings in multi-threading environment
        if not self._av_logging_set:
            av_logging.set_libav_level(av_logging.ERROR)
            self._av_logging_set = True
        self._processed += 1

        np_frame: Optional[np.ndarray] = None
        try:
            np_frame = await self.from_inference_queue.async_get(
                timeout=self.processing_timeout
            )
            new_frame = VideoFrame.from_ndarray(np_frame, format="bgr24")
            self._last_frame = new_frame

            if self._max_consecutive_timeouts:
                self._consecutive_on_time += 1
                if self._consecutive_on_time >= self._min_consecutive_on_time:
                    self._consecutive_timeouts = 0
        except asyncio.TimeoutError:
            if self._last_frame:
                if self._max_consecutive_timeouts:
                    self._consecutive_timeouts += 1
                    if self._consecutive_timeouts >= self._max_consecutive_timeouts:
                        self._consecutive_on_time = 0

        workflow_too_slow_message = [
            "Workflow is too heavy to process all frames on time..."
        ]
        if np_frame is None:
            if not self._last_frame:
                np_frame = overlay_text_on_np_frame(
                    np.zeros((480, 640, 3), dtype=np.uint8),
                    ["wait inference streaming..."],
                )
                new_frame = VideoFrame.from_ndarray(np_frame, format="bgr24")
            elif (
                self._max_consecutive_timeouts
                and self._consecutive_timeouts >= self._max_consecutive_timeouts
            ):
                np_frame = overlay_text_on_np_frame(
                    self._last_frame.to_ndarray(format="bgr24"),
                    workflow_too_slow_message,
                )
                new_frame = VideoFrame.from_ndarray(np_frame, format="bgr24")
            else:
                new_frame = self._last_frame
        else:
            if (
                self._max_consecutive_timeouts
                and self._consecutive_timeouts >= self._max_consecutive_timeouts
            ):
                np_frame = overlay_text_on_np_frame(
                    self._last_frame.to_ndarray(format="bgr24"),
                    workflow_too_slow_message,
                )
                new_frame = VideoFrame.from_ndarray(np_frame, format="bgr24")
            else:
                new_frame = VideoFrame.from_ndarray(np_frame, format="bgr24")

        try:
            new_frame.pts = self._processed
            new_frame.time_base = Fraction(1, int(self.fps))
        except Exception as e:
            logger.error(f"Error setting frame time: {e} {self.fps}")
            new_frame.pts = self._processed
            new_frame.time_base = Fraction(1, 30)

        return new_frame


class RTCPeerConnectionWithFPS(RTCPeerConnection):
    def __init__(self, video_transform_track: VideoTransformTrack, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.video_transform_track: VideoTransformTrack = video_transform_track


async def init_rtc_peer_connection(
    webrtc_offer: WebRTCOffer,
    from_inference_queue: "SyncAsyncQueue[np.ndarray]",
    feedback_stop_event: Event,
    processing_timeout: float,
    max_consecutive_timeouts: int,
    min_consecutive_on_time: int,
    webrtc_turn_config: Optional[WebRTCTURNConfig] = None,
    webcam_fps: Optional[float] = 30,
) -> RTCPeerConnectionWithFPS:
    video_transform_track = VideoTransformTrack(
        from_inference_queue=from_inference_queue,
        webcam_fps=webcam_fps,
        processing_timeout=processing_timeout,
        max_consecutive_timeouts=max_consecutive_timeouts,
        min_consecutive_on_time=min_consecutive_on_time,
    )

    if webrtc_turn_config:
        turn_server = RTCIceServer(
            urls=[webrtc_turn_config.urls],
            username=webrtc_turn_config.username,
            credential=webrtc_turn_config.credential,
        )
        peer_connection = RTCPeerConnectionWithFPS(
            video_transform_track=video_transform_track,
            configuration=RTCConfiguration(iceServers=[turn_server]),
        )
    else:
        peer_connection = RTCPeerConnectionWithFPS(
            video_transform_track=video_transform_track,
        )

    peer_connection.addTrack(video_transform_track)

    @peer_connection.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info("Connection state is %s", peer_connection.connectionState)
        if peer_connection.connectionState in {"failed", "closed"}:
            logger.info("Stopping WebRTC peer")
            video_transform_track.close()
            logger.info("Signalling WebRTC termination to the caller")
            feedback_stop_event.set()
            await peer_connection.close()

    await peer_connection.setRemoteDescription(
        RTCSessionDescription(sdp=webrtc_offer.sdp, type=webrtc_offer.type)
    )
    answer = await peer_connection.createAnswer()
    await peer_connection.setLocalDescription(answer)
    logger.info(f"WebRTC connection status: {peer_connection.connectionState}")

    return peer_connection
