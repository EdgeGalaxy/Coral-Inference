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
import { MetricsModal } from "@/components/metrics-modal";
import { BarChart } from "lucide-react";
import { getApiBaseUrl } from "@/utils/api";


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


export default function Home() {
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const peerConnection = useRef<RTCPeerConnection | null>(null);
  const apiBaseUrl = getApiBaseUrl();
  const [showMetrics, setShowMetrics] = useState(false);

  // 获取pipeline列表
  const fetchPipelines = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/inference_pipelines/list`, defaultOptions);
      const data = await response.json();
      console.log('data', data)
      setPipelines(data.fixed_pipelines?.map((pipeline: string) => ({ id: pipeline})));
      // 如果有pipeline但没有选中的，默认选择第一个
      if (data.pipelines?.length > 0 && !selectedPipeline) {
        setSelectedPipeline(data.pipelines[0]);
      }
    } catch (error) {
      console.error('Error fetching pipelines:', error);
    }
  };

  // 获取pipeline状态
  const fetchPipelineStatus = async (pipelineId: string) => {
    try {
      const response = await fetch(`${apiBaseUrl}/inference_pipelines/${pipelineId}/status`, defaultOptions);
      const data = await response.json();
      return data.status;
    } catch (error) {
      console.error('Error fetching pipeline status:', error);
      return 'unknown';
    }
  };

  // 定期更新pipeline状态
  useEffect(() => {
    const interval = setInterval(async () => {
      const updatedPipelines = await Promise.all(
        pipelines.map(async (pipeline) => ({
          ...pipeline,
          status: await fetchPipelineStatus(pipeline.id)
        }))
      );
      setPipelines(updatedPipelines);
    }, 5000);

    return () => clearInterval(interval);
  }, [pipelines]);

  // 初始化时获取pipeline列表
  useEffect(() => {
    fetchPipelines();
  }, []);

  // 处理WebRTC连接
  const handleStartStream = async () => {
    if (!selectedPipeline) return; 

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

      const response = await fetch(`${apiBaseUrl}/inference_pipelines/${selectedPipeline}/offer`, {
        ...defaultOptions, 
        method: 'POST',
        body: JSON.stringify({
          webrtc_offer: {
            type: offer.type,
            sdp: offer.sdp
          },
          stream_output: ["output_image"],
          webcam_fps: 30, 
          max_consecutive_timeouts: 10,
          min_consecutive_on_time: 3,
          processing_timeout: 1.0, 
          fps_probe_frames: 30 
        }),
      });

      const data = await response.json();
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
      <div className="flex justify-between mb-8">
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

        {selectedPipeline && (
          <Button
            onClick={() => setShowMetrics(true)}
            className="flex items-center gap-2 border border-gray-200 hover:bg-gray-100"
          >
            <BarChart className="h-4 w-4" />
            查看指标
          </Button>
        )}
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

      {/* 指标Modal */}
      {selectedPipeline && (
        <MetricsModal
          isOpen={showMetrics}
          onClose={() => setShowMetrics(false)}
          pipelineId={selectedPipeline}
          apiBaseUrl={apiBaseUrl}
        />
      )}
    </main>
  );
}
