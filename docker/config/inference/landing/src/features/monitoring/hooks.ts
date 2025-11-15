'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { monitorApi, pipelineApi, type MetricsResponse } from '@/lib/api'
import { useApiBaseUrl } from '@/hooks/use-api-base-url'
import { queryKeys } from '@/lib/query-client'

export const usePipelineMetrics = (
  pipelineId: string | null,
  minutes: number,
  options?: { enabled?: boolean },
) => {
  const apiBaseUrl = useApiBaseUrl()
  return useQuery<MetricsResponse>({
    queryKey: queryKeys.pipelineMetrics(pipelineId, minutes, apiBaseUrl),
    queryFn: () => pipelineApi.getMetrics(pipelineId as string, { minutes }, apiBaseUrl),
    enabled: Boolean(pipelineId) && (options?.enabled ?? true),
  })
}

export const useInfluxStatus = (enabled: boolean) => {
  const apiBaseUrl = useApiBaseUrl()
  return useQuery({
    queryKey: queryKeys.influxStatus(apiBaseUrl),
    queryFn: () => monitorApi.getInfluxDBStatus(apiBaseUrl),
    enabled,
    staleTime: 30_000,
  })
}

export const useFlushMonitorCache = () => {
  const apiBaseUrl = useApiBaseUrl()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => monitorApi.flushCache(apiBaseUrl),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['monitoring'] })
      queryClient.invalidateQueries({ queryKey: ['pipelines', 'metrics'], exact: false })
    },
  })
}

export const useTriggerMonitorCleanup = () => {
  const apiBaseUrl = useApiBaseUrl()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => monitorApi.triggerCleanup(apiBaseUrl),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['monitoring'] })
      queryClient.invalidateQueries({ queryKey: ['pipelines', 'metrics'], exact: false })
    },
  })
}
