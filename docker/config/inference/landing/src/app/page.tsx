'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PipelineSelector } from '@/components/pipeline-selector'
import { VideoStream } from '@/components/video-stream'
import { MetricsModal } from '@/components/metrics-modal'
import { BarChart, Settings, Info } from 'lucide-react'

export default function Home() {
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null)
  const [showMetrics, setShowMetrics] = useState(false)

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      {/* 头部 */}
      <header className="bg-white/80 backdrop-blur-sm border-b border-white/20 sticky top-0 z-40">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                <Settings className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">Coral Inference Dashboard</h1>
                <p className="text-sm text-gray-600">实时推理管道监控与控制面板</p>
              </div>
            </div>
            
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
            />

            {/* 系统信息卡片 */}
            <Card className="bg-white/70 backdrop-blur-sm border-white/20">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Info className="h-5 w-5" />
                  系统信息
                </CardTitle>
                <CardDescription>当前系统状态概览</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">系统状态</span>
                    <span className="text-sm font-medium text-green-600">正常运行</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">API服务</span>
                    <span className="text-sm font-medium text-green-600">已连接</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">WebRTC支持</span>
                    <span className="text-sm font-medium text-green-600">已启用</span>
                  </div>
                  {selectedPipeline && (
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">活动Pipeline</span>
                      <span className="text-sm font-medium text-blue-600">
                        {selectedPipeline}
                      </span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* 快速操作 */}
            <Card className="bg-white/70 backdrop-blur-sm border-white/20">
              <CardHeader>
                <CardTitle>快速操作</CardTitle>
                <CardDescription>常用功能快捷入口</CardDescription>
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
                    disabled={!selectedPipeline}
                  >
                    <Settings className="h-4 w-4 mr-2" />
                    Pipeline设置
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* 右侧视频流区域 */}
          <div className="lg:col-span-8">
            <VideoStream pipelineId={selectedPipeline} />
          </div>
        </div>

        {/* 底部信息 */}
        <div className="mt-12 text-center">
          <p className="text-sm text-gray-500">
            Coral Inference Dashboard - 实时推理管道监控系统
          </p>
          <p className="text-xs text-gray-400 mt-1">
            支持WebRTC视频流、实时性能监控和Pipeline管理
          </p>
        </div>
      </main>

      {/* 指标Modal */}
      <MetricsModal
        isOpen={showMetrics}
        onClose={() => setShowMetrics(false)}
        pipelineId={selectedPipeline}
      />
    </div>
  )
} 