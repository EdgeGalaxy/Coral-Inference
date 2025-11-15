'use client'

import { useMemo } from 'react'

import { resolveApiBaseUrl } from '@/config/runtime'
import { useConfig } from '@/providers/config-provider'

export const useApiBaseUrl = (): string => {
  const { config } = useConfig()
  return useMemo(() => resolveApiBaseUrl(config), [config])
}
