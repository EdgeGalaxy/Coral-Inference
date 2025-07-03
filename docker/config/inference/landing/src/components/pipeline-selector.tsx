'use client'

import { useState, useEffect } from 'react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { getStatusColor, getStatusTextColor } from '@/lib/utils'
import { pipelineApi, apiUtils, Pipeline } from '@/lib/api'
import { RefreshCw, Zap, Wifi, WifiOff } from 'lucide-react'

interface PipelineSelectorProps {
  selectedPipeline: string | null
  onPipelineChange: (pipelineId: string) => void
  onStatusUpdate?: (pipelines: Pipeline[]) => void
}

export function PipelineSelector({
  selectedPipeline,
  onPipelineChange,
  onStatusUpdate,
}: PipelineSelectorProps) {
  const [pipelines, setPipelines] = useState<Pipeline[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isConnected, setIsConnected] = useState(true)

  // 获取pipeline列表
  const fetchPipelines = async () => {
    try {
      setLoading(true)
      setError(null)
      
      console.log('正在获取Pipeline列表...')
      
      const pipelineList = await pipelineApi.list()
      console.log('获取到Pipeline列表:', pipelineList)
      
      setPipelines(pipelineList)
      setIsConnected(true)
      
      // 如果有pipeline但没有选中的，默认选择第一个
      if (pipelineList.length > 0 && !selectedPipeline) {
        onPipelineChange(pipelineList[0].id)
      }
    } catch (error) {
      console.error('获取Pipeline列表失败:', error)
      setError(apiUtils.formatError(error))
      setIsConnected(false)
    } finally {
      setLoading(false)
    }
  }

  // 检查API连接状态
  const checkConnection = async () => {
    try {
      const connected = await apiUtils.checkConnection()
      setIsConnected(connected)
      
      if (!connected) {
        setError('无法连接到后端API服务')
      }
    } catch (error) {
      setIsConnected(false)
      setError('API连接检查失败')
    }
  }

  // 定期检查连接状态和更新pipeline列表
  useEffect(() => {
    // 初始化时检查连接并获取数据
    const initialize = async () => {
      await checkConnection()
      if (isConnected) {
        await fetchPipelines()
      }
    }
    
    initialize()

    // 设置定期检查
    const interval = setInterval(async () => {
      await checkConnection()
      if (isConnected) {
        await fetchPipelines()
      }
    }, 10000) // 每10秒检查一次

    return () => clearInterval(interval)
  }, [])

  // 当pipelines更新时，通知父组件
  useEffect(() => {
    if (pipelines.length > 0) {
      onStatusUpdate?.(pipelines)
    }
  }, [pipelines, onStatusUpdate])

  if (loading) {
    return (
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            Pipeline选择器
            <Badge variant="outline" className="ml-auto">
              API模式
            </Badge>
          </CardTitle>
          <CardDescription>选择要监控的推理管道</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
            <span className="ml-2 text-sm text-muted-foreground">连接API中...</span>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className="w-full max-w-md border-red-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-red-600">
            <Zap className="h-5 w-5" />
            Pipeline选择器
            <Badge variant="destructive" className="ml-auto">
              {isConnected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
              {isConnected ? '已连接' : '连接失败'}
            </Badge>
          </CardTitle>
          <CardDescription className="text-red-500">{error}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <button
              onClick={fetchPipelines}
              disabled={loading}
              className="w-full px-4 py-2 text-sm bg-red-50 text-red-600 rounded-md hover:bg-red-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '重试中...' : '重试'}
            </button>
            <div className="text-xs text-gray-500 text-center">
              请确保后端API服务正在运行
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (pipelines.length === 0) {
    return (
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            Pipeline选择器
            <Badge variant="outline" className="ml-auto">
              <Wifi className="h-3 w-3 mr-1" />
              已连接
            </Badge>
          </CardTitle>
          <CardDescription>选择要监控的推理管道</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8">
            <div className="text-sm text-muted-foreground">
              暂无可用的Pipeline
            </div>
            <button
              onClick={fetchPipelines}
              className="mt-2 px-4 py-2 text-sm bg-blue-50 text-blue-600 rounded-md hover:bg-blue-100 transition-colors"
            >
              刷新列表
            </button>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Zap className="h-5 w-5" />
          Pipeline选择器
          <Badge variant="outline" className="ml-auto">
            <Wifi className="h-3 w-3 mr-1" />
            API模式
          </Badge>
        </CardTitle>
        <CardDescription>
          选择要监控的推理管道 ({pipelines.length} 个可用)
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Select value={selectedPipeline || ''} onValueChange={onPipelineChange}>
          <SelectTrigger>
            <SelectValue placeholder="选择Pipeline" />
          </SelectTrigger>
          <SelectContent>
            {pipelines.map((pipeline) => (
              <SelectItem key={pipeline.id} value={pipeline.id}>
                <div className="flex items-center justify-between w-full">
                  <span className="font-medium">{pipeline.id}</span>
                  <Badge
                    variant="secondary"
                    className={`ml-2 ${getStatusColor(pipeline.status)} ${getStatusTextColor(pipeline.status)}`}
                  >
                    {pipeline.status}
                  </Badge>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {selectedPipeline && (
          <div className="p-3 bg-muted rounded-lg">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">当前选择:</span>
              <button
                onClick={fetchPipelines}
                className="text-xs text-blue-600 hover:text-blue-800 transition-colors"
              >
                刷新
              </button>
            </div>
            <div className="mt-1 text-sm text-muted-foreground">
              {selectedPipeline}
            </div>
            {pipelines.find(p => p.id === selectedPipeline) && (
              <Badge
                variant="secondary"
                className={`mt-2 ${getStatusColor(pipelines.find(p => p.id === selectedPipeline)!.status)} ${getStatusTextColor(pipelines.find(p => p.id === selectedPipeline)!.status)}`}
              >
                {pipelines.find(p => p.id === selectedPipeline)!.status}
              </Badge>
            )}
          </div>
        )}

        <div className="text-xs text-gray-500 text-center">
          数据每10秒自动刷新
        </div>
      </CardContent>
    </Card>
  )
} 