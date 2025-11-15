'use client'

import { QueryClient, type QueryKey } from '@tanstack/react-query'

export const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: 2,
      },
    },
  })

export const queryKeys = {
  pipelines: (apiBaseUrl: string): QueryKey => ['pipelines', 'with-status', apiBaseUrl],
  pipelineInfo: (pipelineId: string | null, apiBaseUrl: string): QueryKey => [
    'pipelines',
    'info',
    pipelineId,
    apiBaseUrl,
  ],
  pipelineMetrics: (
    pipelineId: string | null,
    minutes: number,
    apiBaseUrl: string,
  ): QueryKey => ['pipelines', 'metrics', pipelineId, minutes, apiBaseUrl],
  influxStatus: (apiBaseUrl: string): QueryKey => ['monitoring', 'influx-status', apiBaseUrl],
  recordings: (pipelineId: string | null, directory: string, apiBaseUrl: string): QueryKey => [
    'recordings',
    pipelineId,
    directory,
    apiBaseUrl,
  ],
  customMetricsList: (apiBaseUrl: string): QueryKey => ['custom-metrics', 'list', apiBaseUrl],
  customMetricChart: (metricId: number | null, minutes: number, apiBaseUrl: string): QueryKey => [
    'custom-metrics',
    'chart',
    metricId,
    minutes,
    apiBaseUrl,
  ],
}
