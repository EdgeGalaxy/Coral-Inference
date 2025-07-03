// Mock数据文件
export interface MockPipeline {
  id: string
  status: 'running' | 'stopped' | 'paused' | 'error'
}

export interface MockMetricsData {
  dates: string[]
  datasets: {
    name: string
    data: number[]
  }[]
}

// Mock Pipeline列表
export const mockPipelines: MockPipeline[] = [
  { id: 'yolo-detection-v1', status: 'running' },
  { id: 'face-recognition-v2', status: 'running' },
  { id: 'object-tracking-v1', status: 'paused' },
  { id: 'pose-estimation-v1', status: 'stopped' },
  { id: 'semantic-segmentation-v1', status: 'running' },
]

// 生成时间序列数据
const generateTimeSeriesData = (minutes: number = 5) => {
  const now = new Date()
  const dates: string[] = []
  const dataPoints = Math.min(minutes * 2, 60) // 每30秒一个数据点，最多60个点
  
  for (let i = dataPoints - 1; i >= 0; i--) {
    const time = new Date(now.getTime() - i * 30 * 1000)
    dates.push(time.toISOString())
  }
  
  return dates
}

// 生成随机数据
const generateRandomData = (length: number, min: number, max: number) => {
  return Array.from({ length }, () => Math.random() * (max - min) + min)
}

// Mock指标数据
export const generateMockMetrics = (pipelineId: string, minutes: number = 5): MockMetricsData => {
  const dates = generateTimeSeriesData(minutes)
  const dataLength = dates.length
  
  return {
    dates,
    datasets: [
      {
        name: 'Throughput (FPS)',
        data: generateRandomData(dataLength, 25, 35)
      },
      {
        name: 'Frame Decoding Latency (ms)',
        data: generateRandomData(dataLength, 10, 25)
      },
      {
        name: 'Inference Latency (ms)',
        data: generateRandomData(dataLength, 15, 35)
      },
      {
        name: 'E2E Latency (ms)',
        data: generateRandomData(dataLength, 30, 60)
      },
      {
        name: 'GPU Utilization (%)',
        data: generateRandomData(dataLength, 70, 95)
      },
      {
        name: 'Memory Usage (MB)',
        data: generateRandomData(dataLength, 2048, 4096)
      }
    ]
  }
}

// Mock API响应延迟
export const mockDelay = (ms: number = 500) => {
  return new Promise(resolve => setTimeout(resolve, ms))
}

// Mock WebRTC SDP响应
export const mockWebRTCAnswer = {
  sdp: `v=0
o=- 4611731400430051336 2 IN IP4 127.0.0.1
s=-
t=0 0
a=group:BUNDLE 0
a=extmap-allow-mixed
a=msid-semantic: WMS
m=video 9 UDP/TLS/RTP/SAVPF 96 97 98 99 100 101 102 121 127 120 125 107 108 109 124 119 123 118 114 115 116
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=ice-ufrag:4ZcD
a=ice-pwd:2/1muCWoOi3uLifh0NuRBZRP
a=ice-options:trickle
a=fingerprint:sha-256 75:74:5A:A6:A4:E5:52:F4:A7:67:4C:01:C7:EE:91:3F:21:3D:A2:E3:53:7B:6F:30:86:F2:30:FF:A6:22:D9:35
a=setup:active
a=mid:0
a=extmap:1 urn:ietf:params:rtp-hdrext:toffset
a=extmap:2 http://www.webrtc.org/experiments/rtp-hdrext/abs-send-time
a=extmap:3 urn:3gpp:video-orientation
a=extmap:4 http://www.ietf.org/id/draft-holmer-rmcat-transport-wide-cc-extensions-01
a=extmap:5 http://www.webrtc.org/experiments/rtp-hdrext/playout-delay
a=extmap:6 http://www.webrtc.org/experiments/rtp-hdrext/video-content-type
a=extmap:7 http://www.webrtc.org/experiments/rtp-hdrext/video-timing
a=extmap:8 http://www.webrtc.org/experiments/rtp-hdrext/color-space
a=extmap:9 urn:ietf:params:rtp-hdrext:sdes:mid
a=extmap:10 urn:ietf:params:rtp-hdrext:sdes:rtp-stream-id
a=extmap:11 urn:ietf:params:rtp-hdrext:sdes:repaired-rtp-stream-id
a=sendonly
a=msid:- 
a=rtcp-mux
a=rtcp-rsize
a=rtpmap:96 VP8/90000
a=rtcp-fb:96 goog-remb
a=rtcp-fb:96 transport-cc
a=rtcp-fb:96 ccm fir
a=rtcp-fb:96 nack
a=rtcp-fb:96 nack pli
a=rtpmap:97 rtx/90000
a=fmtp:97 apt=96
a=rtpmap:98 VP9/90000
a=rtcp-fb:98 goog-remb
a=rtcp-fb:98 transport-cc
a=rtcp-fb:98 ccm fir
a=rtcp-fb:98 nack
a=rtcp-fb:98 nack pli
a=rtpmap:99 rtx/90000
a=fmtp:99 apt=98
a=rtpmap:100 AV1/90000
a=rtcp-fb:100 goog-remb
a=rtcp-fb:100 transport-cc
a=rtcp-fb:100 ccm fir
a=rtcp-fb:100 nack
a=rtcp-fb:100 nack pli
a=rtpmap:101 rtx/90000
a=fmtp:101 apt=100
a=rtpmap:102 H264/90000
a=rtcp-fb:102 goog-remb
a=rtcp-fb:102 transport-cc
a=rtcp-fb:102 ccm fir
a=rtcp-fb:102 nack
a=rtcp-fb:102 nack pli
a=fmtp:102 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42001f
a=rtpmap:121 rtx/90000
a=fmtp:121 apt=102
a=rtpmap:127 H264/90000
a=rtcp-fb:127 goog-remb
a=rtcp-fb:127 transport-cc
a=rtcp-fb:127 ccm fir
a=rtcp-fb:127 nack
a=rtcp-fb:127 nack pli
a=fmtp:127 level-asymmetry-allowed=1;packetization-mode=0;profile-level-id=42001f
a=rtpmap:120 rtx/90000
a=fmtp:120 apt=127
a=rtpmap:125 H264/90000
a=rtcp-fb:125 goog-remb
a=rtcp-fb:125 transport-cc
a=rtcp-fb:125 ccm fir
a=rtcp-fb:125 nack
a=rtcp-fb:125 nack pli
a=fmtp:125 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=640032
a=rtpmap:107 rtx/90000
a=fmtp:107 apt=125
a=rtpmap:108 red/90000
a=rtpmap:109 rtx/90000
a=fmtp:109 apt=108
a=rtpmap:124 ulpfec/90000
a=rtpmap:119 H264/90000
a=rtcp-fb:119 goog-remb
a=rtcp-fb:119 transport-cc
a=rtcp-fb:119 ccm fir
a=rtcp-fb:119 nack
a=rtcp-fb:119 nack pli
a=fmtp:119 level-asymmetry-allowed=1;packetization-mode=0;profile-level-id=640032
a=rtpmap:123 rtx/90000
a=fmtp:123 apt=119
a=rtpmap:118 H264/90000
a=rtcp-fb:118 goog-remb
a=rtcp-fb:118 transport-cc
a=rtcp-fb:118 ccm fir
a=rtcp-fb:118 nack
a=rtcp-fb:118 nack pli
a=fmtp:118 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f
a=rtpmap:114 rtx/90000
a=fmtp:114 apt=118
a=rtpmap:115 H264/90000
a=rtcp-fb:115 goog-remb
a=rtcp-fb:115 transport-cc
a=rtcp-fb:115 ccm fir
a=rtcp-fb:115 nack
a=rtcp-fb:115 nack pli
a=fmtp:115 level-asymmetry-allowed=1;packetization-mode=0;profile-level-id=42e01f
a=rtpmap:116 rtx/90000
a=fmtp:116 apt=115
a=ssrc-group:FID 1 2
a=ssrc:1 cname:4TOk42mSjMCkjuBh
a=ssrc:1 msid:- 
a=ssrc:1 mslabel:-
a=ssrc:1 label:
a=ssrc:2 cname:4TOk42mSjMCkjuBh
a=ssrc:2 msid:- 
a=ssrc:2 mslabel:-
a=ssrc:2 label:`
}

// 模拟视频流URL（用于测试）
export const mockVideoStreamUrl = 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4' 