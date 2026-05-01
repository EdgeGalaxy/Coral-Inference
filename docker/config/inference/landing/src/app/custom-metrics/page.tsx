"use client"

import { useCallback, useEffect, useState } from 'react'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ArrowLeft, Database, RefreshCw } from 'lucide-react'

const RANGE_OPTIONS = [
  { label: '最近5分钟', value: 5 },
  { label: '最近15分钟', value: 15 },
  { label: '最近30分钟', value: 30 },
  { label: '最近1小时', value: 60 },
] as const

export default function CustomMetricsPage() {
  const [metrics, setMetrics] = useState<CustomMetric[]>([])
  const [selectedMetric, setSelectedMetric] = useState<CustomMetric | null>(null)
  const [chartResponse, setChartResponse] =
    useState<CustomMetricChartResponse | null>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [chartMinutes, setChartMinutes] = useState(15)
  const [chartLoading, setChartLoading] = useState(false)
  const [chartError, setChartError] = useState<string | null>(null)

  const fetchMetrics = useCallback(async () => {
    try {
      setLoadingList(true)
      setListError(null)
      const list = await customMetricsApi.list()
      setMetrics(list)
      setSelectedMetric((current) => {
        if (current && list.some((item) => item.id === current.id)) {
          return current
        }
        return list[0] || null
      })
    } catch (error) {
      setListError(
        error instanceof Error ? error.message : '获取指标列表失败，请稍后重试'
      )
    } finally {
      setLoadingList(false)
    }
  }, [])

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
    fetchMetrics()
  }, [fetchMetrics])

  useEffect(() => {
    if (selectedMetric) {
      fetchChartData(selectedMetric, chartMinutes)
    } else {
      setChartResponse(null)
    }
  }, [selectedMetric, chartMinutes, fetchChartData])

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="container mx-auto flex flex-col gap-4 px-4 py-5 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-slate-600">
              <Database className="h-4 w-4" />
              Custom Metrics
            </div>
            <h1 className="mt-1 text-2xl font-semibold text-slate-950">
              自定义指标只读视图
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              查看本机后端已有的自定义指标配置、图表数据和执行查询。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button asChild variant="outline">
              <Link href="/">
                <ArrowLeft className="mr-2 h-4 w-4" />
                返回首页
              </Link>
            </Button>
            <Button
              variant="secondary"
              onClick={fetchMetrics}
              disabled={loadingList}
            >
              <RefreshCw className={`mr-2 h-4 w-4 ${loadingList ? 'animate-spin' : ''}`} />
              刷新
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto grid gap-6 px-4 py-8 lg:grid-cols-[360px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>已有配置</CardTitle>
            <CardDescription>
              页面只读取现有配置，不提供新增、更新或删除操作。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {loadingList && (
              <div className="text-sm text-muted-foreground">
                正在加载自定义指标...
              </div>
            )}
            {listError && (
              <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {listError}
              </div>
            )}
            {!loadingList && metrics.length === 0 && !listError && (
              <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                当前后端没有已保存的自定义指标配置。
              </div>
            )}
            {metrics.map((metric) => (
              <button
                key={metric.id}
                type="button"
                onClick={() => setSelectedMetric(metric)}
                className={`w-full rounded-md border p-3 text-left transition hover:border-slate-400 ${
                  selectedMetric?.id === metric.id ? 'border-slate-900 bg-slate-50' : ''
                }`}
              >
                <div className="font-medium text-slate-950">{metric.name}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {metric.measurement} · {metric.fields.join(', ')}
                </div>
                {metric.tag_filters && (
                  <div className="mt-1 text-xs text-slate-500">
                    {Object.entries(metric.tag_filters)
                      .map(([key, value]) => `${key}=${value}`)
                      .join(', ')}
                  </div>
                )}
              </button>
            ))}
          </CardContent>
        </Card>

        <section className="space-y-6">
          {selectedMetric ? (
            <>
              <Card>
                <CardHeader className="gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <CardTitle>{selectedMetric.name}</CardTitle>
                    <CardDescription>
                      Measurement: {selectedMetric.measurement} ·{' '}
                      {selectedMetric.fields.join(', ')}
                    </CardDescription>
                  </div>
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
                    <Button
                      variant="outline"
                      onClick={() => fetchChartData(selectedMetric, chartMinutes)}
                      disabled={chartLoading}
                    >
                      <RefreshCw className={`mr-2 h-4 w-4 ${chartLoading ? 'animate-spin' : ''}`} />
                      刷新数据
                    </Button>
                  </div>
                </CardHeader>
              </Card>

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
                    <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-md bg-slate-950 p-4 text-xs text-slate-100">
                      {chartResponse.executed_query}
                    </pre>
                  </CardContent>
                </Card>
              )}
            </>
          ) : (
            <Card>
              <CardContent className="py-12 text-center text-sm text-muted-foreground">
                请选择一个自定义指标查看图表。
              </CardContent>
            </Card>
          )}
        </section>
      </main>
    </div>
  )
}
