'use client'

import { useQuery } from '@tanstack/react-query'

import { pipelineApi, type Pipeline, type PipelineInfoResponse } from '@/lib/api'
import { queryKeys } from '@/lib/query-client'
import { useApiBaseUrl } from '@/hooks/use-api-base-url'

export const usePipelinesWithStatus = () => {
  const apiBaseUrl = useApiBaseUrl()
  return useQuery<Pipeline[]>({
    queryKey: queryKeys.pipelines(apiBaseUrl),
    queryFn: () => pipelineApi.listWithStatus(apiBaseUrl),
    refetchInterval: 60_000,
  })
}

export const usePipelineInfo = (pipelineId: string | null) => {
  const apiBaseUrl = useApiBaseUrl()
  return useQuery<PipelineInfoResponse>({
    queryKey: queryKeys.pipelineInfo(pipelineId, apiBaseUrl),
    queryFn: () => pipelineApi.getInfo(pipelineId as string, apiBaseUrl),
    enabled: Boolean(pipelineId),
  })
}
