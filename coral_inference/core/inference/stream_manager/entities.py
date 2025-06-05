from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field
from inference.core.interfaces.stream_manager.manager_app.entities import WebRTCOffer, WebRTCTURNConfig



class PatchInitialiseWebRTCPipelinePayload(BaseModel):
    webrtc_offer: WebRTCOffer
    webrtc_turn_config: Optional[WebRTCTURNConfig] = None
    stream_output: Optional[List[Optional[str]]] = Field(default_factory=list)
    data_output: Optional[List[Optional[str]]] = Field(default_factory=list)
    webrtc_peer_timeout: float = 1
    webcam_fps: Optional[float] = None
    processing_timeout: float = 0.1
    fps_probe_frames: int = 10
    max_consecutive_timeouts: int = 30
    min_consecutive_on_time: int = 5



class ExtendCommandType(str, Enum):
    INIT = "init"
    WEBRTC = "webrtc"
    MUTE = "mute"
    RESUME = "resume"
    STATUS = "status"
    TERMINATE = "terminate"
    LIST_PIPELINES = "list_pipelines"
    CONSUME_RESULT = "consume_result"
    OFFER = 'offer'