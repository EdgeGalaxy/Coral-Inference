'use client'

import { useEffect } from 'react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { getStatusColor, getStatusTextColor, getStatusDisplayName } from '@/lib/utils'
import { apiUtils, type Pipeline } from '@/lib/api'
import { RefreshCw, Zap, Wifi, WifiOff } from 'lucide-react'

import { usePipelinesWithStatus } from '@/features/pipelines/hooks'

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
  const {
    data: pipelines = [],
    error,
    isPending,
    isFetching,
    refetch,
  } = usePipelinesWithStatus()
  const errorMessage = error ? apiUtils.formatError(error) : null
  const isConnected = !error

  useEffect(() => {
    if (!selectedPipeline && pipelines.length > 0) {
      onPipelineChange(pipelines[0].id)
    }
  }, [pipelines, selectedPipeline, onPipelineChange])

  useEffect(() => {
    if (pipelines.length > 0) {
      onStatusUpdate?.(pipelines)
    }
  }, [pipelines, onStatusUpdate])

  const selectedPipelineInfo = selectedPipeline
    ? pipelines.find((pipeline) => pipeline.id === selectedPipeline)
    : null

  if (isPending && pipelines.length === 0) {
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

  if (errorMessage) {
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
          <CardDescription className="text-red-500">{errorMessage}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <button
              onClick={() => refetch()}
              className="w-full px-4 py-2 text-sm bg-red-50 text-red-600 rounded-md hover:bg-red-100 transition-colors"
            >
              重试
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
            <div className="text-sm text-muted-foreground">暂无可用的Pipeline</div>
            <button
              onClick={() => refetch()}
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
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5" />
              Pipeline选择器
            </CardTitle>
            <CardDescription>选择要监控的推理管道 ({pipelines.length} 个可用)</CardDescription>
          </div>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1 rounded-lg border px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        <Badge variant="outline" className="ml-auto w-fit">
          <Wifi className="h-3 w-3 mr-1" />
          API模式
        </Badge>
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
                  <span className="font-medium">{pipeline.name || pipeline.id}</span>
                  <Badge
                    variant="secondary"
                    className={`ml-2 ${getStatusColor(pipeline.status)} ${getStatusTextColor(pipeline.status)}`}
                  >
                    {getStatusDisplayName(pipeline.status)}
                  </Badge>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {selectedPipeline && selectedPipelineInfo && (
          <div className="p-3 bg-muted rounded-lg">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">当前选择:</span>
            </div>
            <div className="mt-1 text-sm text-muted-foreground">
              {selectedPipelineInfo.name || selectedPipelineInfo.id}
            </div>
            <div className="mt-1 text-xs text-gray-500">ID: {selectedPipelineInfo.id}</div>
            <Badge
              variant="secondary"
              className={`mt-2 ${getStatusColor(selectedPipelineInfo.status)} ${getStatusTextColor(selectedPipelineInfo.status)}`}
            >
              {getStatusDisplayName(selectedPipelineInfo.status)}
            </Badge>
          </div>
        )}

        <div className="text-xs text-gray-500 text-center">
          数据每60秒自动刷新
        </div>
      </CardContent>
    </Card>
  )
} 
