from enum import Enum
from typing import List, Optional

import supervision as sv

from pydantic import BaseModel, Field
from inference.core.interfaces.stream_manager.manager_app.entities import (
    WebRTCOffer,
    WebRTCTURNConfig,
)


class PatchInitialiseWebRTCPipelinePayload(BaseModel):
    webrtc_offer: WebRTCOffer
    webrtc_turn_config: Optional[WebRTCTURNConfig] = None
    stream_output: Optional[List[Optional[str]]] = Field(default_factory=list)
    data_output: Optional[List[Optional[str]]] = Field(default_factory=list)
    webrtc_peer_timeout: float = 1
    webcam_fps: Optional[float] = 30
    processing_timeout: float = 0.1
    fps_probe_frames: int = 10
    max_consecutive_timeouts: int = 30
    min_consecutive_on_time: int = 5


class VideoRecordSinkConfiguration(BaseModel):
    output_directory: str = Field(default="records")
    video_info: Optional[sv.VideoInfo] = None
    segment_duration: int = 100
    max_disk_usage: float = 0.8
    max_total_size: int = 10 * 1024 * 1024 * 1024
    image_input_name: Optional[str] = None
    resolution: int = Field(
        default=360, ge=1, le=1080, description="视频分辨率，默认360p，最高支持1080p"
    )
    is_open: bool = Field(default=True, description="是否启用录像功能")
    queue_size: int = Field(default=1000, ge=1, description="异步处理队列大小")


class ExtendCommandType(str, Enum):
    INIT = "init"
    WEBRTC = "webrtc"
    MUTE = "mute"
    RESUME = "resume"
    STATUS = "status"
    TERMINATE = "terminate"
    LIST_PIPELINES = "list_pipelines"
    CONSUME_RESULT = "consume_result"
    OFFER = "offer"
