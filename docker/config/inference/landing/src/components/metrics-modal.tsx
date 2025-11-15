'use client'

import { useMemo, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { RefreshCw, TrendingUp, Activity, Clock, AlertCircle, Zap, Timer, BarChart3 } from 'lucide-react'
import { apiUtils, type MetricsResponse } from '@/lib/api'
import { usePipelineMetrics, useInfluxStatus } from '@/features/monitoring/hooks'

interface MetricsModalProps {
  isOpen: boolean
  onClose: () => void
  pipelineId: string | null
}

export function MetricsModal({ isOpen, onClose, pipelineId }: MetricsModalProps) {
  const [timeRange, setTimeRange] = useState<string>('5')
  const minutes = parseInt(timeRange, 10)
  const influxStatusQuery = useInfluxStatus(isOpen)
  const influxDBStatus = influxStatusQuery.data
  const useInfluxDB = Boolean(influxDBStatus?.enabled && influxDBStatus?.connected)
  const metricsQuery = usePipelineMetrics(pipelineId, minutes, {
    enabled: isOpen && Boolean(pipelineId),
  })
  const metricsData = metricsQuery.data ?? null
  const loading = metricsQuery.isLoading
  const refreshing = metricsQuery.isFetching && !metricsQuery.isLoading
  const errorMessage = metricsQuery.error ? apiUtils.formatError(metricsQuery.error) : null
  const flushMutation = useFlushMonitorCache()
  const cleanupMutation = useTriggerMonitorCleanup()
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  const handleRefresh = async () => {
    await Promise.all([metricsQuery.refetch(), influxStatusQuery.refetch()])
  }

  // 转换指标数据为图表格式
  const convertToChartData = (data: MetricsResponse) => {
    if (!data.dates || data.dates.length === 0) return []

    return data.dates.map((date, index) => {
      const dataPoint: any = { time: date }
      
      data.datasets.forEach(dataset => {
        if (dataset.data && dataset.data[index] !== undefined) {
          dataPoint[dataset.name] = dataset.data[index]
        }
      })
      
      return dataPoint
    })
  }

  // 获取延迟相关的数据集
  const getLatencyDatasets = (data: MetricsResponse) => {
    if (!data.datasets) return []
    
    return data.datasets.filter(dataset => 
      dataset.data && dataset.data.length > 0 &&
      (dataset.name.includes('Frame Decoding') || 
       dataset.name.includes('Inference Latency') || 
       dataset.name.includes('E2E Latency'))
    )
  }

  // 获取吞吐量数据集
  const getThroughputDatasets = (data: MetricsResponse) => {
    if (!data.datasets) return []
    
    return data.datasets.filter(dataset => 
      dataset.data && dataset.data.length > 0 &&
      dataset.name.includes('Throughput')
    )
  }

  // 获取状态数据集
  const getStateDatasets = (data: MetricsResponse) => {
    if (!data.datasets) return []
    
    return data.datasets.filter(dataset => 
      dataset.data && dataset.data.length > 0 &&
      dataset.name.includes('State')
    )
  }

  // 获取其他数字类型的数据集
  const getOtherNumericDatasets = (data: MetricsResponse) => {
    if (!data.datasets) return []
    
    return data.datasets.filter(dataset => 
      dataset.data && dataset.data.length > 0 && 
      typeof dataset.data[0] === 'number' &&
      !dataset.name.includes('Frame Decoding') &&
      !dataset.name.includes('Inference Latency') &&
      !dataset.name.includes('E2E Latency') &&
      !dataset.name.includes('Throughput')
    )
  }

  // 转换状态数据为时间线格式
  const convertStateDataToTimeline = (data: MetricsResponse, stateDatasets: any[]) => {
    if (!data.dates || data.dates.length === 0 || stateDatasets.length === 0) return []

    return data.dates.map((date, index) => {
      const dataPoint: any = { time: date }
      
      stateDatasets.forEach(dataset => {
        if (dataset.data && dataset.data[index] !== undefined) {
          const state = dataset.data[index]
          // 将状态转换为数字以便在图表中显示
          let stateValue = 0
          switch (state) {
            case 'NOT_STARTED':
              stateValue = 0
              break
            case 'INITIALISING':
              stateValue = 1
              break
            case 'RESTARTING':
              stateValue = 2
              break
            case 'RUNNING':
              stateValue = 3
              break
            case 'PAUSED':
              stateValue = 4
              break
            case 'MUTED':
              stateValue = 5
              break
            case 'TERMINATING':
              stateValue = 6
              break
            case 'ENDED':
              stateValue = 7
              break
            case 'ERROR':
              stateValue = 8
              break
            default:
              stateValue = 0
          }
          dataPoint[dataset.name] = stateValue
          dataPoint[`${dataset.name}_label`] = state
        }
      })
      
      return dataPoint
    })
  }

  // 自定义状态图表的Tooltip
  const StateTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-lg">
          <p className="font-medium">{`时间: ${label}`}</p>
          {payload.map((entry: any, index: number) => {
            const labelKey = `${entry.dataKey}_label`
            const stateLabel = entry.payload[labelKey] || 'unknown'
            return (
              <p key={index} style={{ color: entry.color }}>
                {`${entry.dataKey.replace(' (', ' (')}: ${stateLabel}`}
              </p>
            )
          })}
        </div>
      )
    }
    return null
  }

  const chartData = useMemo(() => (metricsData ? convertToChartData(metricsData) : []), [metricsData])
  const latencyDatasets = useMemo(
    () => (metricsData ? getLatencyDatasets(metricsData) : []),
    [metricsData],
  )
  const throughputDatasets = useMemo(
    () => (metricsData ? getThroughputDatasets(metricsData) : []),
    [metricsData],
  )
  const stateDatasets = useMemo(
    () => (metricsData ? getStateDatasets(metricsData) : []),
    [metricsData],
  )
  const otherNumericDatasets = useMemo(
    () => (metricsData ? getOtherNumericDatasets(metricsData) : []),
    [metricsData],
  )
  const stateChartData = useMemo(
    () => (metricsData ? convertStateDataToTimeline(metricsData, stateDatasets) : []),
    [metricsData, stateDatasets],
  )

  const colors = [
    '#8884d8', '#82ca9d', '#ffc658', '#ff7c7c', '#8dd1e1', 
    '#d084d0', '#ffb347', '#87ceeb', '#dda0dd', '#98fb98'
  ]

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-6xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            Pipeline 指标监控
            <div className="ml-auto flex items-center gap-2">
              {influxDBStatus && (
                <Badge 
                  variant="outline" 
                  className={`${influxDBStatus.connected ? 'bg-green-50 text-green-700 border-green-200' : 'bg-yellow-50 text-yellow-700 border-yellow-200'}`}
                >
                  InfluxDB: {influxDBStatus.connected ? '已连接' : '未连接'}
                </Badge>
              )}
              <Badge variant="outline">
                {useInfluxDB ? '实时模式' : '文件模式'}
              </Badge>
            </div>
          </DialogTitle>
          <DialogDescription>
            {pipelineId ? `Pipeline: ${pipelineId}` : '未选择Pipeline'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* 控制面板 */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm font-medium">时间范围:</span>
                  <Select value={timeRange} onValueChange={setTimeRange}>
                    <SelectTrigger className="w-32">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">1分钟</SelectItem>
                      <SelectItem value="5">5分钟</SelectItem>
                      <SelectItem value="15">15分钟</SelectItem>
                      <SelectItem value="30">30分钟</SelectItem>
                      <SelectItem value="60">1小时</SelectItem>
                      <SelectItem value="120">2小时</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {influxDBStatus && (
                  <div className="flex items-center gap-2 text-sm">
                    <div className={`w-2 h-2 rounded-full ${
                      influxDBStatus.healthy ? 'bg-green-500' : influxDBStatus.connected ? 'bg-yellow-500' : 'bg-red-500'
                    }`} />
                    <span className="text-muted-foreground">
                      {influxDBStatus.connected ? 
                        (influxDBStatus.healthy ? '健康' : '连接异常') : 
                        '断开连接'
                      }
                    </span>
                    {influxDBStatus.buffer_size !== undefined && (
                      <span className="text-xs text-muted-foreground ml-2">
                        缓冲: {influxDBStatus.buffer_size}
                      </span>
                    )}
                  </div>
                )}
              </div>
              
              <Button
                onClick={handleRefresh}
                disabled={loading || refreshing}
                size="sm"
                variant="outline"
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
                {refreshing ? '刷新中...' : '刷新'}
              </Button>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={async () => {
                  setActionMessage(null)
                  try {
                    const res = await flushMutation.mutateAsync()
                    setActionMessage(res?.message || '已刷新监控缓存')
                  } catch (err) {
                    setActionMessage(apiUtils.formatError(err))
                  }
                }}
                disabled={flushMutation.isPending}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${flushMutation.isPending ? 'animate-spin' : ''}`} />
                刷新缓存
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={async () => {
                  setActionMessage(null)
                  try {
                    const res = await cleanupMutation.mutateAsync()
                    setActionMessage(res?.message || '已触发清理')
                  } catch (err) {
                    setActionMessage(apiUtils.formatError(err))
                  }
                }}
                disabled={cleanupMutation.isPending}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${cleanupMutation.isPending ? 'animate-spin' : ''}`} />
                触发清理
              </Button>
              {actionMessage && (
                <span className="text-xs text-muted-foreground">{actionMessage}</span>
              )}
            </div>
          </div>

          {/* 加载状态 */}
          {loading && (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground mr-2" />
              <span className="text-sm text-muted-foreground">正在加载指标数据...</span>
            </div>
          )}

          {/* 错误状态 */}
          {errorMessage && (
            <Card className="border-red-200">
              <CardContent className="pt-6">
                <div className="flex items-center gap-2 text-red-600">
                  <AlertCircle className="h-5 w-5" />
                  <span className="font-medium">获取指标数据失败</span>
                </div>
                <p className="mt-2 text-sm text-red-500">{errorMessage}</p>
                <Button
                  onClick={() => metricsQuery.refetch()}
                  size="sm"
                  variant="outline"
                  className="mt-3"
                >
                  重试
                </Button>
              </CardContent>
            </Card>
          )}

          {/* 指标数据 */}
          {metricsData && !loading && !errorMessage && (
            <div className="space-y-6">
              {/* 吞吐量图表 */}
              {throughputDatasets.length > 0 && chartData.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <BarChart3 className="h-5 w-5" />
                      吞吐量指标
                    </CardTitle>
                    <CardDescription>
                      过去 {timeRange} 分钟的吞吐量数据趋势
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="h-80">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis 
                            dataKey="time" 
                            tick={{ fontSize: 12 }}
                            angle={-45}
                            textAnchor="end"
                            height={60}
                          />
                          <YAxis tick={{ fontSize: 12 }} />
                          <Tooltip />
                          <Legend />
                          {throughputDatasets.map((dataset, index) => (
                            <Line
                              key={dataset.name}
                              type="monotone"
                              dataKey={dataset.name}
                              stroke={colors[index % colors.length]}
                              strokeWidth={2}
                              dot={false}
                              connectNulls={false}
                            />
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* 延迟指标图表 */}
              {latencyDatasets.length > 0 && chartData.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Timer className="h-5 w-5" />
                      延迟指标
                    </CardTitle>
                    <CardDescription>
                      过去 {timeRange} 分钟的延迟数据趋势（包括帧解码、推理和端到端延迟）
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="h-80">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis 
                            dataKey="time" 
                            tick={{ fontSize: 12 }}
                            angle={-45}
                            textAnchor="end"
                            height={60}
                          />
                          <YAxis tick={{ fontSize: 12 }} />
                          <Tooltip />
                          <Legend />
                          {latencyDatasets.map((dataset, index) => (
                            <Line
                              key={dataset.name}
                              type="monotone"
                              dataKey={dataset.name}
                              stroke={colors[index % colors.length]}
                              strokeWidth={2}
                              dot={false}
                              connectNulls={false}
                            />
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* 状态时间线图表 */}
              {stateDatasets.length > 0 && stateChartData.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Activity className="h-5 w-5" />
                      状态时间线
                    </CardTitle>
                    <CardDescription>
                      过去 {timeRange} 分钟的Pipeline组件状态变化
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="h-80">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={stateChartData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis 
                            dataKey="time" 
                            tick={{ fontSize: 12 }}
                            angle={-45}
                            textAnchor="end"
                            height={60}
                          />
                          <YAxis 
                            tick={{ fontSize: 12 }}
                            domain={[0, 8]}
                            tickFormatter={(value) => {
                              switch (value) {
                                case 0: return 'NOT_STARTED'
                                case 1: return 'INITIALISING'
                                case 2: return 'RESTARTING'
                                case 3: return 'RUNNING'
                                case 4: return 'PAUSED'
                                case 5: return 'MUTED'
                                case 6: return 'TERMINATING'
                                case 7: return 'ENDED'
                                case 8: return 'ERROR'
                                default: return ''
                              }
                            }}
                          />
                          <Tooltip content={<StateTooltip />} />
                          <Legend />
                          {stateDatasets.map((dataset, index) => (
                            <Line
                              key={dataset.name}
                              type="stepAfter"
                              dataKey={dataset.name}
                              stroke={colors[index % colors.length]}
                              strokeWidth={2}
                              dot={{ r: 3 }}
                              connectNulls={false}
                            />
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <Badge variant="outline" className="bg-gray-100">
                        <div className="w-3 h-3 rounded-full bg-gray-500 mr-1"></div>
                        NOT_STARTED
                      </Badge>
                      <Badge variant="outline" className="bg-blue-100">
                        <div className="w-3 h-3 rounded-full bg-blue-500 mr-1"></div>
                        INITIALISING
                      </Badge>
                      <Badge variant="outline" className="bg-orange-100">
                        <div className="w-3 h-3 rounded-full bg-orange-500 mr-1"></div>
                        RESTARTING
                      </Badge>
                      <Badge variant="outline" className="bg-green-100">
                        <div className="w-3 h-3 rounded-full bg-green-500 mr-1"></div>
                        RUNNING
                      </Badge>
                      <Badge variant="outline" className="bg-yellow-100">
                        <div className="w-3 h-3 rounded-full bg-yellow-500 mr-1"></div>
                        PAUSED
                      </Badge>
                      <Badge variant="outline" className="bg-purple-100">
                        <div className="w-3 h-3 rounded-full bg-purple-500 mr-1"></div>
                        MUTED
                      </Badge>
                      <Badge variant="outline" className="bg-pink-100">
                        <div className="w-3 h-3 rounded-full bg-pink-500 mr-1"></div>
                        TERMINATING
                      </Badge>
                      <Badge variant="outline" className="bg-slate-100">
                        <div className="w-3 h-3 rounded-full bg-slate-500 mr-1"></div>
                        ENDED
                      </Badge>
                      <Badge variant="outline" className="bg-red-100">
                        <div className="w-3 h-3 rounded-full bg-red-500 mr-1"></div>
                        ERROR
                      </Badge>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* 其他数值指标图表 */}
              {otherNumericDatasets.length > 0 && chartData.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Zap className="h-5 w-5" />
                      其他性能指标
                    </CardTitle>
                    <CardDescription>
                      过去 {timeRange} 分钟的其他性能数据趋势
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="h-80">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis 
                            dataKey="time" 
                            tick={{ fontSize: 12 }}
                            angle={-45}
                            textAnchor="end"
                            height={60}
                          />
                          <YAxis tick={{ fontSize: 12 }} />
                          <Tooltip />
                          <Legend />
                          {otherNumericDatasets.map((dataset, index) => (
                            <Line
                              key={dataset.name}
                              type="monotone"
                              dataKey={dataset.name}
                              stroke={colors[index % colors.length]}
                              strokeWidth={2}
                              dot={false}
                              connectNulls={false}
                            />
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* 数据统计 */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    数据统计
                    <div className="flex items-center gap-2">
                      {influxDBStatus && (
                        <Badge variant={influxDBStatus.connected ? 'default' : 'secondary'} className="text-xs">
                          {influxDBStatus.connected ? 'InfluxDB' : 'File'}
                        </Badge>
                      )}
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-blue-600">
                        {metricsData.dates.length}
                      </div>
                      <div className="text-sm text-muted-foreground">数据点</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-orange-600">
                        {throughputDatasets.length}
                      </div>
                      <div className="text-sm text-muted-foreground">吞吐量指标</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-green-600">
                        {latencyDatasets.length}
                      </div>
                      <div className="text-sm text-muted-foreground">延迟指标</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-purple-600">
                        {stateDatasets.length}
                      </div>
                      <div className="text-sm text-muted-foreground">状态指标</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-gray-600">
                        {timeRange}min
                      </div>
                      <div className="text-sm text-muted-foreground">时间范围</div>
                    </div>
                  </div>
                  {influxDBStatus && (
                    <div className="mt-4 pt-4 border-t">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                        <div>
                          <span className="text-muted-foreground">数据源:</span>
                          <span className="ml-1 font-medium">
                            {influxDBStatus.connected ? influxDBStatus.url : '本地文件'}
                          </span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">数据库:</span>
                          <span className="ml-1 font-medium">
                            {influxDBStatus.bucket || 'N/A'}
                          </span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">测量表:</span>
                          <span className="ml-1 font-medium">
                            {influxDBStatus.measurement || 'N/A'}
                          </span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">缓冲区:</span>
                          <span className="ml-1 font-medium">
                            {influxDBStatus.buffer_size || 0} 条
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}

          {/* 无数据状态 */}
          {metricsData && !loading && !errorMessage && chartData.length === 0 && (
            <Card>
              <CardContent className="pt-6">
                <div className="text-center py-8">
                  <Activity className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                  <h3 className="text-lg font-medium mb-2">暂无指标数据</h3>
                  <p className="text-sm text-muted-foreground mb-4">
                    所选时间范围内没有找到指标数据
                  </p>
                  <Button onClick={fetchMetrics} size="sm">
                    重新加载
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
} 
