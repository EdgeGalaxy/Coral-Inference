'use client'

import { useMemo } from 'react'
import {
  LineChart,
  Line,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
} from 'recharts'
import { format } from 'date-fns'

import type {
  CustomMetric,
  CustomMetricChartPoint,
} from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const COLORS = [
  '#2563eb',
  '#0ea5e9',
  '#22c55e',
  '#eab308',
  '#f97316',
  '#ec4899',
  '#8b5cf6',
  '#14b8a6',
]

interface ChartRendererProps {
  metric: CustomMetric
  data: CustomMetricChartPoint[]
  loading?: boolean
  error?: string | null
}

interface PreparedData {
  rows: Array<Record<string, any>>
  seriesKeys: string[]
  pieSeries: Array<{ name: string; value: number }>
}

function formatTimeLabel(date: Date) {
  return format(date, 'MM-dd HH:mm:ss')
}

function getSeriesKey(point: CustomMetricChartPoint, metric: CustomMetric): string {
  const baseLabel =
    point.label ||
    metric.fields?.[0] ||
    metric.name

  const groupTags = (metric.group_by || []).map((tag) => {
    const tags = point.tags || (point.metadata?.current_tags as Record<string, string> | undefined)
    return tags?.[tag]
  }).filter(Boolean)

  if (groupTags.length > 0) {
    return `${baseLabel} (${groupTags.join(', ')})`
  }

  return baseLabel
}

function prepareChartData(
  data: CustomMetricChartPoint[],
  metric: CustomMetric
): PreparedData {
  const timeMap = new Map<number, Record<string, any>>()
  const pieMap = new Map<string, number>()
  const seriesSet = new Set<string>()

  data.forEach((point) => {
    const timestamp = new Date(point.timestamp)
    const timeKey = timestamp.getTime()
    const seriesKey = getSeriesKey(point, metric)
    seriesSet.add(seriesKey)

    if (!timeMap.has(timeKey)) {
      timeMap.set(timeKey, {
        time: formatTimeLabel(timestamp),
        fullTime: timestamp.toISOString(),
      })
    }
    const row = timeMap.get(timeKey)!
    row[seriesKey] = Number(point.value ?? 0)

    pieMap.set(seriesKey, (pieMap.get(seriesKey) ?? 0) + Number(point.value ?? 0))
  })

  const rows = Array.from(timeMap.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([, value]) => value)

  const pieSeries = Array.from(pieMap.entries()).map(([name, value]) => ({
    name,
    value,
  }))

  return {
    rows,
    seriesKeys: Array.from(seriesSet),
    pieSeries,
  }
}

export function ChartRenderer({ metric, data, loading, error }: ChartRendererProps) {
  const prepared = useMemo(() => prepareChartData(data || [], metric), [data, metric])

  const renderContent = () => {
    if (loading) {
      return (
        <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
          指标数据加载中...
        </div>
      )
    }

    if (error) {
      return (
        <div className="flex h-64 items-center justify-center text-sm text-red-600">
          {error}
        </div>
      )
    }

    if (!data || data.length === 0) {
      return (
        <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
          暂无数据，请调整时间范围或稍后重试
        </div>
      )
    }

    if (metric.chart_type === 'pie') {
      return (
        <ResponsiveContainer width="100%" height={320}>
          <PieChart>
            <Pie
              data={prepared.pieSeries}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={110}
              label
            >
              {prepared.pieSeries.map((entry, index) => (
                <Cell
                  key={`cell-${entry.name}`}
                  fill={COLORS[index % COLORS.length]}
                />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      )
    }

    const chartData = prepared.rows
    const series = prepared.seriesKeys

    if (metric.chart_type === 'bar') {
      return (
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" />
            <YAxis />
            <Tooltip />
            <Legend />
            {series.map((key, index) => (
              <Bar
                key={key}
                dataKey={key}
                fill={COLORS[index % COLORS.length]}
                stackId={series.length > 1 ? `stack-${index}` : undefined}
                maxBarSize={48}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )
    }

    if (metric.chart_type === 'area') {
      return (
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" />
            <YAxis />
            <Tooltip />
            <Legend />
            {series.map((key, index) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                stroke={COLORS[index % COLORS.length]}
                fill={COLORS[index % COLORS.length]}
                fillOpacity={0.25}
                strokeWidth={2}
                activeDot={{ r: 4 }}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      )
    }

    return (
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="time" />
          <YAxis />
          <Tooltip />
          <Legend />
          {series.map((key, index) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              stroke={COLORS[index % COLORS.length]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg font-semibold">{metric.name}</CardTitle>
      </CardHeader>
      <CardContent>{renderContent()}</CardContent>
    </Card>
  )
}
