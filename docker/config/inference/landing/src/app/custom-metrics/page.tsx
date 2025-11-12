"use client"

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  customMetricsApi,
  type CustomMetric,
  type CustomMetricChartResponse,
} from '@/lib/api'
import { ChartRenderer } from '@/components/custom-metrics/chart-renderer'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const CHART_TYPES = [
  { label: '折线图', value: 'line' },
  { label: '面积图', value: 'area' },
  { label: '柱状图', value: 'bar' },
  { label: '饼图', value: 'pie' },
] as const

const RANGE_OPTIONS = [
  { label: '最近5分钟', value: 5 },
  { label: '最近15分钟', value: 15 },
  { label: '最近30分钟', value: 30 },
  { label: '最近1小时', value: 60 },
] as const

interface TagFilterItem {
  key: string
  value: string
}

export default function CustomMetricsPage() {
  const [metrics, setMetrics] = useState<CustomMetric[]>([])
  const [selectedMetric, setSelectedMetric] = useState<CustomMetric | null>(null)
  const [chartResponse, setChartResponse] =
    useState<CustomMetricChartResponse | null>(null)
  const [formState, setFormState] = useState({
    name: '',
    measurement: '',
    fields: '',
    aggregation: 'mean',
    groupBy: '',
    groupByTime: '5s',
    chartType: 'line',
    timeRangeMinutes: 15,
    refreshInterval: 60,
    description: '',
  })
  const [tagFilters, setTagFilters] = useState<TagFilterItem[]>([
    { key: '', value: '' },
  ])

  const [loadingList, setLoadingList] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [chartMinutes, setChartMinutes] = useState(15)
  const [chartLoading, setChartLoading] = useState(false)
  const [chartError, setChartError] = useState<string | null>(null)

  const fetchMetrics = useCallback(async () => {
    try {
      setLoadingList(true)
      setListError(null)
      const list = await customMetricsApi.list()
      setMetrics(list)
      if (list.length > 0 && !selectedMetric) {
        setSelectedMetric(list[0])
      }
    } catch (error) {
      setListError(
        error instanceof Error ? error.message : '获取指标列表失败，请稍后重试'
      )
    } finally {
      setLoadingList(false)
    }
  }, [selectedMetric])

  useEffect(() => {
    fetchMetrics()
  }, [fetchMetrics])

  const fetchChartData = useCallback(
    async (metric: CustomMetric, minutes: number) => {
      try {
        setChartLoading(true)
        setChartError(null)
        const response = await customMetricsApi.fetchChartData(metric.id, {
          minutes,
        })
        setChartResponse(response)
      } catch (error) {
        setChartError(
          error instanceof Error ? error.message : '获取指标数据失败'
        )
      } finally {
        setChartLoading(false)
      }
    },
    []
  )

  useEffect(() => {
    if (selectedMetric) {
      fetchChartData(selectedMetric, chartMinutes)
    } else {
      setChartResponse(null)
    }
  }, [selectedMetric, chartMinutes, fetchChartData])

  const handleFormChange = (
    key: keyof typeof formState,
    value: string | number
  ) => {
    setFormState((prev) => ({
      ...prev,
      [key]: value,
    }))
  }

  const handleTagFilterChange = (
    index: number,
    field: keyof TagFilterItem,
    value: string
  ) => {
    setTagFilters((prev) => {
      const next = [...prev]
      next[index] = { ...next[index], [field]: value }
      return next
    })
  }

  const addTagFilterRow = () => {
    setTagFilters((prev) => [...prev, { key: '', value: '' }])
  }

  const normalizedTagFilters = useMemo(() => {
    const filters: Record<string, string> = {}
    tagFilters.forEach((item) => {
      if (item.key.trim() && item.value.trim()) {
        filters[item.key.trim()] = item.value.trim()
      }
    })
    return filters
  }, [tagFilters])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!formState.name.trim() || !formState.measurement.trim()) {
      return
    }

    const fields = formState.fields
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)

    if (fields.length === 0) {
      alert('请填写至少一个指标字段')
      return
    }

    const payload = {
      name: formState.name.trim(),
      chart_type: formState.chartType as CustomMetric['chart_type'],
      measurement: formState.measurement.trim(),
      fields,
      aggregation: formState.aggregation.trim() || undefined,
      group_by: formState.groupBy
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
      group_by_time: formState.groupByTime.trim() || undefined,
      tag_filters:
        Object.keys(normalizedTagFilters).length > 0
          ? normalizedTagFilters
          : undefined,
      description: formState.description.trim() || undefined,
      time_range_seconds: Math.max(formState.timeRangeMinutes, 1) * 60,
      refresh_interval_seconds: Math.max(formState.refreshInterval, 5),
    }

    try {
      setSaving(true)
      const created = await customMetricsApi.create(payload)
      setMetrics((prev) => [created, ...prev])
      setSelectedMetric(created)
      setFormState((prev) => ({
        ...prev,
        name: '',
        fields: '',
        measurement: '',
        description: '',
      }))
      setTagFilters([{ key: '', value: '' }])
    } catch (error) {
      alert(error instanceof Error ? error.message : '创建指标失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (metricId: number) => {
    if (!confirm('确定要删除该自定义指标吗？')) {
      return
    }
    try {
      await customMetricsApi.remove(metricId)
      setMetrics((prev) => prev.filter((item) => item.id !== metricId))
      if (selectedMetric?.id === metricId) {
        setSelectedMetric(null)
        setChartResponse(null)
      }
    } catch (error) {
      alert(error instanceof Error ? error.message : '删除失败，请稍后重试')
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      <header className="border-b bg-white/80 backdrop-blur-sm">
        <div className="container mx-auto px-4 py-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-semibold text-blue-600">Custom Metrics</p>
            <h1 className="text-3xl font-bold text-gray-900 mt-1">
              自定义指标中心
            </h1>
            <p className="text-sm text-muted-foreground mt-2">
              定义你关心的指标来源，直接调用后台 Inference API 渲染图表
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button asChild variant="outline">
              <Link href="/">返回首页</Link>
            </Button>
            <Button
              variant="secondary"
              onClick={fetchMetrics}
              disabled={loadingList}
            >
              刷新列表
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8 space-y-8">
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>新建自定义指标</CardTitle>
              <CardDescription>
                选择 measurement、字段、聚合与标签，快速创建一个图表
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={handleSubmit}>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="metric-name">指标名称</Label>
                    <Input
                      id="metric-name"
                      placeholder="例如：Pipeline Throughput"
                      value={formState.name}
                      onChange={(event) =>
                        handleFormChange('name', event.target.value)
                      }
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>图表类型</Label>
                    <Select
                      value={formState.chartType}
                      onValueChange={(value) => handleFormChange('chartType', value)}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="选择图表类型" />
                      </SelectTrigger>
                      <SelectContent>
                        {CHART_TYPES.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="measurement">Measurement</Label>
                    <Input
                      id="measurement"
                      placeholder="例如：pipeline_system_metrics"
                      value={formState.measurement}
                      onChange={(event) =>
                        handleFormChange('measurement', event.target.value)
                      }
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="fields">字段（逗号分隔）</Label>
                    <Input
                      id="fields"
                      placeholder="throughput, e2e_latency"
                      value={formState.fields}
                      onChange={(event) =>
                        handleFormChange('fields', event.target.value)
                      }
                    />
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-3">
                  <div className="space-y-2">
                    <Label htmlFor="aggregation">聚合方式</Label>
                    <Input
                      id="aggregation"
                      placeholder="mean"
                      value={formState.aggregation}
                      onChange={(event) =>
                        handleFormChange('aggregation', event.target.value)
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="group-by">Group By 标签</Label>
                    <Input
                      id="group-by"
                      placeholder="source_id, pipeline_id"
                      value={formState.groupBy}
                      onChange={(event) =>
                        handleFormChange('groupBy', event.target.value)
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="group-by-time">时间聚合</Label>
                    <Input
                      id="group-by-time"
                      placeholder="例如：10s / 1m"
                      value={formState.groupByTime}
                      onChange={(event) =>
                        handleFormChange('groupByTime', event.target.value)
                      }
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Tag 过滤条件</Label>
                  <div className="space-y-2 rounded-md border p-3">
                    {tagFilters.map((item, index) => (
                      <div key={`${index}-${item.key}`} className="grid gap-2 md:grid-cols-2">
                        <Input
                          placeholder="标签名，例如 pipeline_id"
                          value={item.key}
                          onChange={(event) =>
                            handleTagFilterChange(index, 'key', event.target.value)
                          }
                        />
                        <Input
                          placeholder="标签值，例如 123456"
                          value={item.value}
                          onChange={(event) =>
                            handleTagFilterChange(index, 'value', event.target.value)
                          }
                        />
                      </div>
                    ))}
                    <Button
                      type="button"
                      variant="ghost"
                      className="text-sm"
                      onClick={addTagFilterRow}
                    >
                      添加过滤条件
                    </Button>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="time-range">默认时间范围（分钟）</Label>
                    <Input
                      id="time-range"
                      type="number"
                      min={1}
                      value={formState.timeRangeMinutes}
                      onChange={(event) =>
                        handleFormChange(
                          'timeRangeMinutes',
                          Number(event.target.value)
                        )
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="refresh-interval">刷新间隔（秒）</Label>
                    <Input
                      id="refresh-interval"
                      type="number"
                      min={5}
                      value={formState.refreshInterval}
                      onChange={(event) =>
                        handleFormChange(
                          'refreshInterval',
                          Number(event.target.value)
                        )
                      }
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="description">描述</Label>
                  <textarea
                    id="description"
                    className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    placeholder="简单介绍该指标用途"
                    value={formState.description}
                    onChange={(event) =>
                      handleFormChange('description', event.target.value)
                    }
                  />
                </div>

                <Button type="submit" disabled={saving} className="w-full">
                  {saving ? '创建中...' : '保存指标'}
                </Button>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>配置列表</CardTitle>
              <CardDescription>
                管理已经创建的自定义指标，点击即可查看数据
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {loadingList && (
                <div className="text-sm text-muted-foreground">
                  正在加载自定义指标...
                </div>
              )}
              {listError && (
                <div className="text-sm text-red-600">{listError}</div>
              )}
              {!loadingList && metrics.length === 0 && (
                <div className="text-sm text-muted-foreground">
                  还没有自定义指标，先在左侧创建一个吧。
                </div>
              )}
              {metrics.map((metric) => (
                <div
                  key={metric.id}
                  className="rounded-lg border p-3 transition hover:border-blue-200"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-gray-900">{metric.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {metric.measurement} · {metric.fields.join(', ')}
                      </p>
                      {metric.tag_filters && (
                        <p className="mt-1 text-xs text-slate-500">
                          过滤：{' '}
                          {Object.entries(metric.tag_filters)
                            .map(([key, value]) => `${key}=${value}`)
                            .join(', ')}
                        </p>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => setSelectedMetric(metric)}
                      >
                        查看
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => handleDelete(metric.id)}
                      >
                        删除
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        {selectedMetric && (
          <section className="space-y-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="text-2xl font-semibold text-gray-900">
                  {selectedMetric.name}
                </h2>
                <p className="text-sm text-muted-foreground">
                  Measurement：{selectedMetric.measurement} ·{' '}
                  {selectedMetric.fields.join(', ')}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span>时间范围</span>
                  <Select
                    value={String(chartMinutes)}
                    onValueChange={(value) => setChartMinutes(Number(value))}
                  >
                    <SelectTrigger className="w-32">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {RANGE_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={String(option.value)}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button
                  variant="outline"
                  onClick={() =>
                    selectedMetric && fetchChartData(selectedMetric, chartMinutes)
                  }
                  disabled={chartLoading}
                >
                  {chartLoading ? '加载中...' : '刷新数据'}
                </Button>
              </div>
            </div>

            <ChartRenderer
              metric={selectedMetric}
              data={chartResponse?.chart_data || []}
              loading={chartLoading}
              error={chartError}
            />

            {chartResponse?.executed_query && (
              <Card>
                <CardHeader>
                  <CardTitle>执行的查询</CardTitle>
                  <CardDescription>
                    {chartResponse.time_window.start} ~ {chartResponse.time_window.end}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <pre className="whitespace-pre-wrap rounded-md bg-slate-950 p-4 text-xs text-slate-100">
                    {chartResponse.executed_query}
                  </pre>
                </CardContent>
              </Card>
            )}
          </section>
        )}
      </main>
    </div>
  )
}
