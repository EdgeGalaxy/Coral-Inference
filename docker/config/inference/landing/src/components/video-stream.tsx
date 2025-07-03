'use client'

import { useState, useEffect, useRef } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { pipelineApi, apiUtils } from '@/lib/api'
import { Play, Square, Video, AlertCircle, Loader2, Wifi, WifiOff } from 'lucide-react'

interface VideoStreamProps {
  pipelineId: string | null
}

export function VideoStream({ pipelineId }: VideoStreamProps) {
  const [isStreaming, setIsStreaming] = useState(false)
  const [connectionState, setConnectionState] = useState<'disconnected' | 'connecting' | 'connected' | 'failed'>('disconnected')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  
  const videoRef = useRef<HTMLVideoElement>(null)
  const peerConnectionRef = useRef<RTCPeerConnection | null>(null)
  const localStreamRef = useRef<MediaStream | null>(null)

  // 清理连接
  const cleanupConnection = () => {
    if (peerConnectionRef.current) {
      peerConnectionRef.current.close()
      peerConnectionRef.current = null
    }
    
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach(track => track.stop())
      localStreamRef.current = null
    }
    
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
    
    setConnectionState('disconnected')
    setIsStreaming(false)
  }

  // 创建WebRTC连接
  const createWebRTCConnection = async () => {
    try {
      setLoading(true)
      setError(null)
      setConnectionState('connecting')
      
      console.log('创建WebRTC连接...')
      
      // 创建RTCPeerConnection
      const peerConnection = new RTCPeerConnection({
        iceServers: [
          { urls: 'stun:stun.l.google.com:19302' },
          { urls: 'stun:stun1.l.google.com:19302' }
        ]
      })
      
      peerConnectionRef.current = peerConnection
      
      // 监听连接状态变化
      peerConnection.onconnectionstatechange = () => {
        console.log('WebRTC连接状态:', peerConnection.connectionState)
        
        switch (peerConnection.connectionState) {
          case 'connected':
            setConnectionState('connected')
            setIsStreaming(true)
            setError(null)
            break
          case 'disconnected':
          case 'failed':
            setConnectionState('failed')
            setError('WebRTC连接失败')
            break
          case 'connecting':
            setConnectionState('connecting')
            break
        }
      }
      
      // 监听ICE连接状态
      peerConnection.oniceconnectionstatechange = () => {
        console.log('ICE连接状态:', peerConnection.iceConnectionState)
      }
      
      // 监听远程流
      peerConnection.ontrack = (event) => {
        console.log('收到远程流:', event.streams[0])
        
        if (videoRef.current && event.streams[0]) {
          videoRef.current.srcObject = event.streams[0]
        }
      }
      
      // 创建offer
      const offer = await peerConnection.createOffer({
        offerToReceiveVideo: true,
        offerToReceiveAudio: false
      })
      
      await peerConnection.setLocalDescription(offer)
      
      console.log('本地SDP Offer:', offer)
      
      // 发送offer到后端
      if (!pipelineId) {
        throw new Error('Pipeline ID为空')
      }
      
      const response = await pipelineApi.createWebRTCOffer(pipelineId, {
        webrtc_offer: {
          sdp: offer.sdp!,
          type: 'offer'
        }
      })
      
      console.log('收到后端SDP Answer:', response)
      
      // 设置远程描述
      await peerConnection.setRemoteDescription({
        type: 'answer',
        sdp: response.sdp
      })
      
      console.log('WebRTC连接建立成功')
      
    } catch (error) {
      console.error('WebRTC连接失败:', error)
      setError(apiUtils.formatError(error))
      setConnectionState('failed')
      cleanupConnection()
    } finally {
      setLoading(false)
    }
  }

  // 开始流传输
  const handleStartStream = async () => {
    if (!pipelineId) {
      setError('请先选择一个Pipeline')
      return
    }
    
    await createWebRTCConnection()
  }

  // 停止流传输
  const handleStopStream = () => {
    console.log('停止视频流')
    cleanupConnection()
    setError(null)
  }

  // 清理资源
  useEffect(() => {
    return () => {
      cleanupConnection()
    }
  }, [])

  // 当pipelineId变化时停止当前流
  useEffect(() => {
    if (isStreaming) {
      handleStopStream()
    }
  }, [pipelineId])

  const getConnectionStatusColor = () => {
    switch (connectionState) {
      case 'connected':
        return 'bg-green-500'
      case 'connecting':
        return 'bg-yellow-500'
      case 'failed':
        return 'bg-red-500'
      default:
        return 'bg-gray-500'
    }
  }

  const getConnectionStatusText = () => {
    switch (connectionState) {
      case 'connected':
        return '已连接'
      case 'connecting':
        return '连接中'
      case 'failed':
        return '连接失败'
      default:
        return '未连接'
    }
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Video className="h-5 w-5" />
          实时视频流
          <Badge variant="outline" className="ml-auto">
            <Wifi className="h-3 w-3 mr-1" />
            WebRTC模式
          </Badge>
        </CardTitle>
        <CardDescription>
          {pipelineId ? `Pipeline: ${pipelineId}` : '请选择Pipeline以开始视频流'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 连接状态 */}
        <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${getConnectionStatusColor()}`} />
            <span className="text-sm font-medium">连接状态:</span>
            <span className="text-sm">{getConnectionStatusText()}</span>
          </div>
          
          <div className="flex items-center gap-2">
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            {connectionState === 'connected' && <Wifi className="h-4 w-4 text-green-600" />}
            {connectionState === 'failed' && <WifiOff className="h-4 w-4 text-red-600" />}
          </div>
        </div>

        {/* 视频容器 */}
        <div className="relative bg-black rounded-lg overflow-hidden" style={{ aspectRatio: '16/9' }}>
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="w-full h-full object-contain"
            style={{ backgroundColor: '#000' }}
          />
          
          {/* 覆盖层 */}
          {!isStreaming && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/50">
              <div className="text-center text-white">
                <Video className="h-12 w-12 mx-auto mb-2 opacity-50" />
                <p className="text-sm opacity-75">
                  {pipelineId ? '点击开始播放视频流' : '请选择Pipeline'}
                </p>
              </div>
            </div>
          )}
          
          {/* 加载状态 */}
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/70">
              <div className="text-center text-white">
                <Loader2 className="h-8 w-8 mx-auto mb-2 animate-spin" />
                <p className="text-sm">正在建立WebRTC连接...</p>
              </div>
            </div>
          )}
        </div>

        {/* 错误信息 */}
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
            <div className="flex items-center gap-2 text-red-600">
              <AlertCircle className="h-4 w-4" />
              <span className="font-medium">连接错误</span>
            </div>
            <p className="text-sm text-red-500 mt-1">{error}</p>
          </div>
        )}

        {/* 控制按钮 */}
        <div className="flex items-center gap-2">
          {!isStreaming ? (
            <Button
              onClick={handleStartStream}
              disabled={!pipelineId || loading}
              className="flex-1"
            >
              <Play className="h-4 w-4 mr-2" />
              {loading ? '连接中...' : '开始播放'}
            </Button>
          ) : (
            <Button
              onClick={handleStopStream}
              variant="destructive"
              className="flex-1"
            >
              <Square className="h-4 w-4 mr-2" />
              停止播放
            </Button>
          )}
          
          {error && (
            <Button
              onClick={handleStartStream}
              variant="outline"
              disabled={!pipelineId || loading}
            >
              重试
            </Button>
          )}
        </div>

        {/* 技术信息 */}
        <div className="text-xs text-gray-500 space-y-1">
          <div>• 使用WebRTC协议进行实时视频传输</div>
          <div>• 支持自适应码率和低延迟播放</div>
          <div>• 需要Pipeline处于运行状态</div>
          {pipelineId && (
            <div>• 当前Pipeline: <code className="bg-gray-100 px-1 rounded">{pipelineId}</code></div>
          )}
        </div>
      </CardContent>
    </Card>
  )
} 