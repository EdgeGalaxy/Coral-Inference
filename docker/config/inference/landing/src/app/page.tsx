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
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const peerConnection = useRef<RTCPeerConnection | null>(null);
  const apiBaseUrl = getApiBaseUrl();

  // 获取pipeline列表
  const fetchPipelines = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/inference_pipelines/list`, defaultOptions);
      const data = await response.json();
      console.log('data', data)
      setPipelines(data.pipelines?.map((pipeline: string) => ({ id: pipeline})));
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
      // 创建新的 RTCPeerConnection
      peerConnection.current = new RTCPeerConnection({
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
      });

      // 设置视频流处理
      if (videoRef.current) {
        peerConnection.current.ontrack = (event) => {
          if (videoRef.current) {
            videoRef.current.srcObject = event.streams[0];
          }
        };
      }

      // 创建 offer
      const offer = await peerConnection.current.createOffer();
      await peerConnection.current.setLocalDescription(offer);

      // 发送 offer 到服务器
      const response = await fetch(`${apiBaseUrl}/inference_pipelines/${selectedPipeline}/offer`, {
        ...defaultOptions,
        method: 'POST',
        body: JSON.stringify({
          webrtc_offer: {
            type: offer.type,
            sdp: offer.sdp
          },
          stream_output: "image"
        }),
      });

      const data = await response.json();
      
      // 检查响应格式
      if (!data || !data.sdp) {
        throw new Error('Invalid response from server: missing SDP');
      }

      const answerSdp = data.sdp;

      // 验证 SDP 格式
      if (typeof answerSdp !== 'string') {
        throw new Error('Invalid SDP format: not a string');
      }

      // 检查 SDP 是否包含必要的字段
      if (!answerSdp.includes('v=') || !answerSdp.includes('o=') || !answerSdp.includes('s=')) {
        console.error('Invalid SDP format:', answerSdp);
        throw new Error('Invalid SDP format: missing required fields');
      }

      // 设置远程描述
      try {
        const answer = new RTCSessionDescription({
          type: 'answer',
          sdp: answerSdp
        });
        
        await peerConnection.current.setRemoteDescription(answer);
        setIsStreaming(true);
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
