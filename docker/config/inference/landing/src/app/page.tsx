'use client';

import { useEffect, useState, useRef } from 'react';
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface Pipeline {
  id: string;
  status?: string;
}

// 通用请求配置
const defaultHeaders = {
  'Content-Type': 'application/json',
  'Accept': 'application/json',
};

// 通用请求选项
const defaultOptions = {
  headers: defaultHeaders,
};

// 获取API基础URL
const getApiBaseUrl = () => {
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:9001';
    }
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:9001';
};

export default function Home() {
  const [pipelines, setPipelines] = useState<Pipeline[]>([{"id": "xxxxxx", "status": "success"}]);
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const peerConnection = useRef<RTCPeerConnection | null>(null);
  const apiBaseUrl = getApiBaseUrl();

  // 获取pipeline列表
  // const fetchPipelines = async () => {
  //   try {
  //     const response = await fetch(`${apiBaseUrl}/inference_pipelines/list`, defaultOptions);
  //     const data = await response.json();
  //     console.log('data', data)
  //     setPipelines(data.pipelines?.map((pipeline: string) => ({ id: pipeline})));
  //     // 如果有pipeline但没有选中的，默认选择第一个
  //     if (data.pipelines?.length > 0 && !selectedPipeline) {
  //       setSelectedPipeline(data.pipelines[0]);
  //     }
  //   } catch (error) {
  //     console.error('Error fetching pipelines:', error);
  //   }
  // };

  // 获取pipeline状态
  // const fetchPipelineStatus = async (pipelineId: string) => {
  //   try {
  //     const response = await fetch(`${apiBaseUrl}/inference_pipelines/${pipelineId}/status`, defaultOptions);
  //     const data = await response.json();
  //     return data.status;
  //   } catch (error) {
  //     console.error('Error fetching pipeline status:', error);
  //     return 'unknown';
  //   }
  // };

  // 定期更新pipeline状态
  // useEffect(() => {
  //   const interval = setInterval(async () => {
  //     const updatedPipelines = await Promise.all(
  //       pipelines.map(async (pipeline) => ({
  //         ...pipeline,
  //         status: await fetchPipelineStatus(pipeline.id)
  //       }))
  //     );
  //     setPipelines(updatedPipelines);
  //   }, 5000);

  //   return () => clearInterval(interval);
  // }, [pipelines]);

  // 初始化时获取pipeline列表
  // useEffect(() => {
  //   fetchPipelines();
  // }, []);

  // 处理WebRTC连接
  const handleStartStream = async () => {
    if (!selectedPipeline) return; // 确保 selectedPipeline 不为空，尽管你的 URL 是硬编码的

    try {
      
      peerConnection.current = new RTCPeerConnection(); // 使用 current 引用

      // 2. 添加空的音视频轨道并设置为 recvonly
      // stream = new MediaStream() is not needed here
      peerConnection.current.addTransceiver('video', {
        direction: 'recvonly' // 前端只接收视频
      });
      // 注意: 不需要 addTransceiver('audio', { direction: 'recvonly' }); 如果你只关心视频

      // 3. 设置视频流处理 (ontrack)
      // 这是将远程流附加到 <video> 元素的关键
      peerConnection.current.ontrack = (event) => {
        // 确保 event.streams[0] 是有效的，并且 videoRef.current 存在
        if (event.streams && event.streams.length > 0 && event.track.kind === 'video') {
            console.log('Received remote stream:', event.streams[0]);
            if (videoRef.current) {
                videoRef.current.srcObject = event.streams[0];
                console.log('Video srcObject set.');
            }
        }
      };

      // 4. ICE 协商事件处理 (可选但推荐)
      peerConnection.current.onicecandidate = (event) => {
          if (event.candidate) {
              // 对于单向流，通常后端不会主动发送 ICE 候选给前端。
              // 但如果前端是发起者，它可能会有本地候选。
              // 理论上，这些候选需要通过信令服务器发送给后端。
              // 在你的简化场景中，如果 STUN/TURN 工作良好，可能不需要显式发送。
              // 如果遇到连接问题，这里是排查点。
              console.log('Frontend ICE candidate:', event.candidate);
          }
      };
      
      // 5. 连接状态变化监听 (重要)
      peerConnection.current.onconnectionstatechange = () => {
        console.log('Frontend Connection state:', peerConnection.current?.connectionState);
        console.log('Frontend ICE Connection state:', peerConnection.current?.iceConnectionState);
        if (peerConnection.current?.connectionState === 'failed' || peerConnection.current?.connectionState === 'disconnected') {
          console.error('WebRTC connection failed or disconnected');
          setIsStreaming(false);
          if (peerConnection.current) {
            peerConnection.current.close();
            peerConnection.current = null;
          }
        }
      };
      // 6. 创建 offer
      const offer = await peerConnection.current.createOffer();
      await peerConnection.current.setLocalDescription(offer);
      console.log('Frontend generated offer:', offer);

      // 7. 发送 offer 到服务器
      // 检查你的 `apiBaseUrl` 和路由是否匹配后端 `app.router.add_post("/inference_pipelines/offer/test", handle_offer_request)`
      // const response = await fetch(`${apiBaseUrl}/inference_pipelines/${selectedPipeline}/offer`, {
      const response = await fetch(`${apiBaseUrl}/inference_pipelines/offer/test`, {
        // ...defaultOptions, // 确保 defaultOptions 包含正确的 headers (e.g., 'Content-Type': 'application/json')
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }, // 显式设置 Content-Type
        body: JSON.stringify({
          webrtc_offer: {
            type: offer.type,
            sdp: offer.sdp
          },
          // 确保这些参数与后端 PatchInitialiseWebRTCPipelinePayload 的预期匹配
          stream_output: ["image"],
          webcam_fps: 30, // 后端代码目前也忽略了
          max_consecutive_timeouts: 10,
          min_consecutive_on_time: 3,
          processing_timeout: 1.0, // 后端 GeneratedVideoStreamTrack 中使用的 timeout
          fps_probe_frames: 30 // 后端代码 currently ignores this
        }),
      });

      const data = await response.json();
      console.log('Frontend received answer data:', data);
      
      // 8. 检查和验证 SDP answer
      if (!data || !data.sdp) {
        throw new Error('Invalid response from server: missing SDP');
      }
      const answerSdp = data.sdp;

      if (typeof answerSdp !== 'string') {
        throw new Error('Invalid SDP format: not a string');
      }
      if (!answerSdp.includes('v=') || !answerSdp.includes('o=') || !answerSdp.includes('s=')) {
        console.error('Invalid SDP format:', answerSdp);
        throw new Error('Invalid SDP format: missing required fields');
      }

      // 9. 设置远程描述
      try {
        const answer = new RTCSessionDescription({
          type: 'answer',
          sdp: answerSdp
        });
        
        await peerConnection.current.setRemoteDescription(answer);
        console.log('Frontend set remote description (answer).');
        setIsStreaming(true); // 更新 UI 状态
      } catch (error) {
        console.error('Error setting remote description:', error);
        throw new Error('Failed to set remote description: ' + (error as Error).message);
      }
    } catch (error) {
      console.error('Error starting stream:', error);
      // 清理连接
      if (peerConnection.current) {
        peerConnection.current.close();
        peerConnection.current = null;
      }
      setIsStreaming(false);
    }
  };

  // 停止流
  const handleStopStream = () => {
    if (peerConnection.current) {
      peerConnection.current.close();
      peerConnection.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsStreaming(false);
  };

  // 获取状态对应的颜色
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'bg-green-500';
      case 'stopped':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  return (
    <main className="min-h-screen p-8">
      {/* 顶部导航栏 */}
      <div className="flex justify-start mb-8">
        <Select
          value={selectedPipeline || ''}
          onValueChange={(value: string) => setSelectedPipeline(value)}
        >
          <SelectTrigger className="w-[300px]">
            <SelectValue placeholder="选择 Pipeline" />
          </SelectTrigger>
          <SelectContent>
            {pipelines?.length === 0
              ? null
              : pipelines.map((pipeline) => (
                  <SelectItem key={pipeline.id} value={pipeline.id}>
                    <div className="flex items-center justify-between w-full">
                      <span className="truncate">{pipeline.id}</span>
                      <Badge variant="secondary" className={`ml-2 ${getStatusColor(pipeline.status || '')}`}>
                        {pipeline.status}
                      </Badge>
                    </div>
                  </SelectItem>
                ))}
          </SelectContent>
        </Select>
      </div>

      {/* 主要内容区域 */}
      <div className="max-w-4xl mx-auto">
        {!selectedPipeline ? (
          <Alert>
            <AlertDescription>
              请从左上角选择一个 Pipeline 开始
            </AlertDescription>
          </Alert>
        ) : (
          <>
            {/* 视频流显示区域 */}
            <div className="aspect-video bg-black rounded-lg overflow-hidden mb-4">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                className="w-full h-full object-contain"
              />
            </div>

            {/* 控制按钮 */}
            <div className="flex justify-center gap-4">
              <Button
                onClick={handleStartStream}
                disabled={!selectedPipeline || isStreaming}
                className="bg-green-500 hover:bg-green-600"
              >
                开始
              </Button>
              <Button
                onClick={handleStopStream}
                disabled={!isStreaming}
                className="bg-red-500 hover:bg-red-600"
              >
                停止
              </Button>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
