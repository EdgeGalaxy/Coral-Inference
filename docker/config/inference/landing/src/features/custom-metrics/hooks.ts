'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  customMetricsApi,
  type CustomMetric,
  type CustomMetricChartResponse,
  type CustomMetricPayload,
} from '@/lib/api'
import { useApiBaseUrl } from '@/hooks/use-api-base-url'
import { queryKeys } from '@/lib/query-client'

export const useCustomMetrics = () => {
  const apiBaseUrl = useApiBaseUrl()
  return useQuery<CustomMetric[]>({
    queryKey: queryKeys.customMetricsList(apiBaseUrl),
    queryFn: () => customMetricsApi.list(apiBaseUrl),
  })
}

export const useCustomMetricChart = (
  metricId: number | null,
  minutes: number,
  options?: { enabled?: boolean },
) => {
  const apiBaseUrl = useApiBaseUrl()
  return useQuery<CustomMetricChartResponse>({
    queryKey: queryKeys.customMetricChart(metricId, minutes, apiBaseUrl),
    queryFn: () =>
      customMetricsApi.fetchChartData(metricId as number, { minutes }, apiBaseUrl),
    enabled: Boolean(metricId) && (options?.enabled ?? true),
  })
}

export const useCreateCustomMetric = () => {
  const apiBaseUrl = useApiBaseUrl()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CustomMetricPayload) => customMetricsApi.create(payload, apiBaseUrl),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.customMetricsList(apiBaseUrl) })
    },
  })
}

export const useDeleteCustomMetric = () => {
  const apiBaseUrl = useApiBaseUrl()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (metricId: number) => customMetricsApi.remove(metricId, apiBaseUrl),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.customMetricsList(apiBaseUrl) })
    },
  })
}
