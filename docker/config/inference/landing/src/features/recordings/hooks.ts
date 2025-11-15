'use client'

import { useQuery } from '@tanstack/react-query'

import { recordingApi, type VideoFileItem } from '@/lib/api'
import { useApiBaseUrl } from '@/hooks/use-api-base-url'
import { queryKeys } from '@/lib/query-client'

export const usePipelineRecordings = (
  pipelineId: string | null,
  outputDirectory: string,
) => {
  const apiBaseUrl = useApiBaseUrl()
  return useQuery<VideoFileItem[]>({
    queryKey: queryKeys.recordings(pipelineId, outputDirectory, apiBaseUrl),
    queryFn: () => recordingApi.list(pipelineId as string, outputDirectory, apiBaseUrl),
    enabled: Boolean(pipelineId),
  })
}
