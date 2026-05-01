'use client'

import { useState } from 'react'
import { useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { PipelineSelector } from '@/components/pipeline-selector'
import { VideoStream } from '@/components/video-stream'
import { MetricsModal } from '@/components/metrics-modal'
import { RecordingsModal } from '@/components/recordings-modal'
import {
  BarChart,
  Clock,
  Database,
  HardDrive,
  Info,
  RefreshCw,
  Settings,
} from 'lucide-react'
import {
  apiUtils,
  monitorApi,
  pipelineApi,
  type Pipeline,
  type PipelineInfoResponse,
  type PipelineStatusResponse,
} from '@/lib/api'

const formatTime = (value?: number) => {
  if (!value) return 'N/A'
  return new Date(value * 1000).toLocaleString()
}

const formatPercent = (value?: number) => {
  if (typeof value !== 'number') return 'N/A'
  return `${value.toFixed(1)}%`
}

export default function Home() {
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null)
  const [showMetrics, setShowMetrics] = useState(false)
  const [showRecordings, setShowRecordings] = useState(false)
  const [pipelines, setPipelines] = useState<Pipeline[]>([])
  const [monitorStatus, setMonitorStatus] = useState<any>(null)
  const [diskUsage, setDiskUsage] = useState<any>(null)
  const [influxDBStatus, setInfluxDBStatus] = useState<any>(null)
  const [pipelineInfo, setPipelineInfo] = useState<PipelineInfoResponse['data'] | null>(null)
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatusResponse | null>(null)
  const [overviewError, setOverviewError] = useState<string | null>(null)
  const [lastPoll, setLastPoll] = useState<number | null>(null)
  const [loadingOverview, setLoadingOverview] = useState(false)

  const fetchOverview = async () => {
    try {
      setLoadingOverview(true)
      setOverviewError(null)
      const [monitor, disk, influx] = await Promise.all([
        monitorApi.getMonitorStatus(),
        monitorApi.getDiskUsage(),
        monitorApi.getInfluxDBStatus(),
      ])
      setMonitorStatus(monitor)
      setDiskUsage(disk)
      setInfluxDBStatus(influx)
      setLastPoll(Date.now())
    } catch (error) {
      setOverviewError(apiUtils.formatError(error))
    } finally {
      setLoadingOverview(false)
    }
  }

  useEffect(() => {
    fetchOverview()
    const interval = window.setInterval(fetchOverview, 30000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    const fetchSelectedPipeline = async () => {
      if (!selectedPipeline) {
        setPipelineInfo(null)
        setPipelineStatus(null)
        return
      }

      try {
        const [info, status] = await Promise.all([
          pipelineApi.getInfo(selectedPipeline),
          monitorApi.getStatus(selectedPipeline),
        ])
        setPipelineInfo(info.data)
        setPipelineStatus(status)
      } catch (error) {
        setPipelineInfo(null)
        setPipelineStatus(null)
        console.error('获取Pipeline详情失败:', error)
      }
    }

    fetchSelectedPipeline()
  }, [selectedPipeline])

  const selectedSources = Array.isArray(pipelineStatus?.report?.sources_metadata)
    ? pipelineStatus.report.sources_metadata
    : []

  return (
    <div className="min-h-screen bg-slate-50">
      {/* 头部 */}
      <header className="bg-white border-b sticky top-0 z-40">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-slate-900 rounded-lg flex items-center justify-center">
                <Settings className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">Coral Inference Dashboard</h1>
                <p className="text-sm text-gray-600">离线只读监控面板</p>
              </div>
            </div>
            
            <div className="flex items-center gap-3">
              <Button asChild variant="outline">
                <Link href="/custom-metrics">自定义指标</Link>
              </Button>
              {selectedPipeline && (
                <Button
                  onClick={() => setShowMetrics(true)}
                  className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg"
                >
                  <BarChart className="h-4 w-4 mr-2" />
                  查看指标
                </Button>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* 主要内容 */}
      <main className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* 左侧控制面板 */}
          <div className="lg:col-span-4 space-y-6">
            {/* Pipeline选择器 */}
            <PipelineSelector
              selectedPipeline={selectedPipeline}
              onPipelineChange={setSelectedPipeline}
              onStatusUpdate={setPipelines}
            />

            {/* 系统信息卡片 */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Info className="h-5 w-5" />
                  系统总览
                  {loadingOverview && <RefreshCw className="ml-auto h-4 w-4 animate-spin text-muted-foreground" />}
                </CardTitle>
                <CardDescription>本机 Coral-Inference 后端状态</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3 text-sm">
                  {overviewError && (
                    <div className="rounded-md border border-red-200 bg-red-50 p-2 text-red-700">
                      {overviewError}
                    </div>
                  )}
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">API 连接</span>
                    <Badge variant={overviewError ? 'destructive' : 'outline'}>
                      {overviewError ? '异常' : lastPoll ? '已连接' : '检查中'}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Monitor</span>
                    <span className="font-medium">
                      {monitorStatus
                        ? `${monitorStatus.running ? '运行中' : '已停止'} / ${monitorStatus.is_healthy ? '健康' : '异常'}`
                        : 'N/A'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Pipeline 数量</span>
                    <span className="font-medium">
                      {monitorStatus?.pipeline_count ?? pipelines.length}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">轮询间隔</span>
                    <span className="font-medium">
                      {monitorStatus?.poll_interval ? `${monitorStatus.poll_interval}s` : 'N/A'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">最近轮询</span>
                    <span className="font-medium">
                      {lastPoll ? new Date(lastPoll).toLocaleTimeString() : 'N/A'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">错误计数</span>
                    <span className="font-medium">
                      {monitorStatus?.performance_metrics?.error_count ?? 'N/A'}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Database className="h-5 w-5" />
                  InfluxDB / 磁盘
                </CardTitle>
                <CardDescription>指标存储与录像目录状态</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">InfluxDB</span>
                  <span className="font-medium">
                    {influxDBStatus
                      ? `${influxDBStatus.enabled ? '启用' : '未启用'} / ${influxDBStatus.connected ? '已连接' : '未连接'}`
                      : 'N/A'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">健康状态</span>
                  <span className="font-medium">{influxDBStatus?.healthy ? '健康' : 'N/A'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">数据库</span>
                  <span className="max-w-[180px] truncate font-medium">
                    {influxDBStatus?.database || 'N/A'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">磁盘使用</span>
                  <span className="font-medium">
                    {diskUsage
                      ? `${diskUsage.current_size_gb} / ${diskUsage.max_size_gb} GB (${formatPercent(diskUsage.usage_percentage)})`
                      : 'N/A'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <HardDrive className="h-4 w-4" />
                    剩余空间
                  </span>
                  <span className="font-medium">
                    {diskUsage?.free_space_gb !== undefined ? `${diskUsage.free_space_gb} GB` : 'N/A'}
                  </span>
                </div>
              </CardContent>
            </Card>

            {/* 快速操作 */}
            <Card>
              <CardHeader>
                <CardTitle>只读视图</CardTitle>
                <CardDescription>查看指标、录像和自定义图表</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    onClick={() => setShowMetrics(true)}
                    disabled={!selectedPipeline}
                  >
                    <BarChart className="h-4 w-4 mr-2" />
                    查看性能指标
                  </Button>
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    onClick={() => setShowRecordings(true)}
                    disabled={!selectedPipeline}
                  >
                    <Settings className="h-4 w-4 mr-2" />
                    查看录像
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* 右侧视频流 */}
          <div className="lg:col-span-8 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Clock className="h-5 w-5" />
                  Pipeline 详情
                </CardTitle>
                <CardDescription>
                  {selectedPipeline ? `Pipeline: ${selectedPipeline}` : '请选择Pipeline'}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {selectedPipeline ? (
                  <>
                    <div className="grid gap-3 text-sm md:grid-cols-2">
                      <div>
                        <div className="text-muted-foreground">名称</div>
                        <div className="font-medium">{pipelineInfo?.pipeline_name || pipelines.find((item) => item.id === selectedPipeline)?.name || 'N/A'}</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">创建时间</div>
                        <div className="font-medium">{formatTime(pipelineInfo?.created_at)}</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">恢复 ID</div>
                        <div className="break-all font-mono text-xs">{pipelineInfo?.restore_pipeline_id || 'N/A'}</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Auto Restart</div>
                        <div className="font-medium">{pipelineInfo?.auto_restart === undefined ? 'N/A' : pipelineInfo.auto_restart ? '启用' : '关闭'}</div>
                      </div>
                    </div>
                    <div>
                      <div className="mb-2 text-sm text-muted-foreground">输出字段</div>
                      <div className="flex flex-wrap gap-2">
                        {(pipelineInfo?.parameters?.output_image_fields || ['source_image']).map((field: string) => (
                          <Badge key={field} variant="secondary">{field}</Badge>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div className="mb-2 text-sm text-muted-foreground">Source 状态</div>
                      <div className="space-y-2">
                        {selectedSources.length === 0 && (
                          <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                            暂无 sources_metadata
                          </div>
                        )}
                        {selectedSources.map((source: any, index: number) => (
                          <div key={`${source.source_id || index}`} className="rounded-md border p-3 text-sm">
                            <div className="flex items-center justify-between gap-3">
                              <span className="font-medium">{source.source_id || `source-${index + 1}`}</span>
                              <Badge variant="outline">{source.state || 'unknown'}</Badge>
                            </div>
                            <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
                              {JSON.stringify(source, null, 2)}
                            </pre>
                          </div>
                        ))}
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                    从左侧选择一个 Pipeline 查看详情。
                  </div>
                )}
              </CardContent>
            </Card>
            <VideoStream pipelineId={selectedPipeline} />
          </div>
        </div>

        {/* 底部信息 */}
        <div className="mt-12 text-center">
          <p className="text-sm text-gray-500">
            Coral Inference Dashboard - 离线只读监控系统
          </p>
          <p className="text-xs text-gray-400 mt-1">
            仅连接本机 Coral-Inference API，不调用外部 CoralReefBackend 服务
          </p>
        </div>
      </main>

      {/* 指标Modal */}
      <MetricsModal
        isOpen={showMetrics}
        onClose={() => setShowMetrics(false)}
        pipelineId={selectedPipeline}
      />

      <RecordingsModal
        isOpen={showRecordings}
        onClose={() => setShowRecordings(false)}
        defaultPipelineId={selectedPipeline}
      />
    </div>
  )
} 
