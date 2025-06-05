import asyncio
import threading
from threading import Event

import time
import cv2
import numpy as np
from collections import deque

from inference.core import logger

from av import VideoFrame
from fractions import Fraction
from aiortc.mediastreams import MediaStreamError

from inference.core.interfaces.stream_manager.manager_app.webrtc import (
    VideoStreamTrack,
    RTCPeerConnection,
    RTCIceServer,
    RTCConfiguration,
    RTCSessionDescription,
)

from coral_inference.core.inference.stream_manager.entities import (
    PatchInitialiseWebRTCPipelinePayload
)


class GeneratedVideoStreamTrack(VideoStreamTrack):
    def __init__(self, queue: deque, stop_event: Event):
        super().__init__()
        self.counter = 0
        self.start_time = time.time()
        self.stop_event = stop_event
        self.width = 640
        self.height = 480
        self.fps = 30
        self.frame_delay = 1.0 / self.fps
        self._last_np_frame = None
        self._track_active = True  # 添加活动状态标志
        self.queue = queue

    async def recv(self):
        if not self._track_active:
            raise MediaStreamError("Track is not active")

        print('recv incomming...')
        try:
            # 获取新帧
            np_frame = self.queue.popleft()
            self._last_np_frame = np_frame
            
            # 转换格式
            img_rgb = cv2.cvtColor(np_frame, cv2.COLOR_BGR2RGB)
            new_frame = VideoFrame.from_ndarray(img_rgb, format="rgb24")
            
            self.counter += 1
            new_frame.pts = self.counter
            new_frame.time_base = Fraction(1, self.fps)
            print('frame new get')
            
            return new_frame
            
        except Exception as e:
            print(f"Error in recv: {e}")
            if self._last_np_frame is not None:
                # 使用上一帧
                img_rgb = cv2.cvtColor(self._last_np_frame, cv2.COLOR_BGR2RGB)
                new_frame = VideoFrame.from_ndarray(img_rgb, format="rgb24")
                new_frame.pts = self.counter
                new_frame.time_base = Fraction(1, self.fps)
                return new_frame
            raise

    def stop(self):
        self._track_active = False


async def get_frame_from_buffer_sink(from_inference_queue: deque, stop_event: Event):
    while not stop_event.is_set():
        mock_frame = np.full((480, 640, 3), [0, 255, 0], dtype=np.uint8)
        # 随机生成100个彩色点
        for _ in range(100):
            x = np.random.randint(0, 640)
            y = np.random.randint(0, 480)
            color = np.random.randint(0, 255, 3)
            mock_frame[y:y+5, x:x+5] = color

        from_inference_queue.append(mock_frame)
        await asyncio.sleep(1/30)
    

async def offer(payload: dict) -> None:
    # 创建新的事件循环
    print('enter offer....')
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=lambda: loop.run_forever(), daemon=True)
    t.start()

    stop_event = Event()

    print('xxxxx')

    from_inference_queue = deque(maxlen=50)

    # 在新的事件循环中运行 WebRTC 相关操作
    future = asyncio.run_coroutine_threadsafe(
        _run_webrtc_connection(from_inference_queue, payload, stop_event),
        loop
    )
    print('yyyyy')

    asyncio.run_coroutine_threadsafe(get_frame_from_buffer_sink(from_inference_queue, stop_event), loop)
    
    # 等待连接建立并返回 SDP
    result = future.result()
    print(f'end result: {result}')
    return result

async def _run_webrtc_connection(queue, payload: dict, stop_event: Event):
    parsed_payload = PatchInitialiseWebRTCPipelinePayload.model_validate(payload)

    # 创建 PeerConnection
    if parsed_payload.webrtc_turn_config:
        turn_server = RTCIceServer(
            urls=[parsed_payload.webrtc_turn_config.urls],
            username=parsed_payload.webrtc_turn_config.username,
            credential=parsed_payload.webrtc_turn_config.credential,
        )
        pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[turn_server]))
    else:
        pc = RTCPeerConnection()

    # 创建视频轨道
    generated_video_track = GeneratedVideoStreamTrack(queue, stop_event)
    pc.addTrack(generated_video_track)

    # 设置连接状态变化处理
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"Connection state is {pc.connectionState}")
        if pc.connectionState in {"failed", "closed"}:
            print("PeerConnection closed or failed, cleaning up...")
            await pc.close()
            stop_event.set()

    # 设置远程描述
    await pc.setRemoteDescription(RTCSessionDescription(
        sdp=parsed_payload.webrtc_offer.sdp,
        type=parsed_payload.webrtc_offer.type
    ))

    # 创建应答
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    print({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}