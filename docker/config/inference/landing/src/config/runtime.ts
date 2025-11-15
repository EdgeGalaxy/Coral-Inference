'use client'

import type { WebAppConfig } from '@/config/types'
import { DEFAULT_CONFIG } from '@/config/default-config'

const DEFAULT_FALLBACK_API_BASE_URL = 'http://localhost:9001'
const RUNTIME_PLACEHOLDER_BASE_URL = 'runtime-default'

let runtimeConfig: WebAppConfig | null = null

const isIpAddress = (host: string): boolean => {
  const ipv4Pattern = /^(\d{1,3}\.){3}\d{1,3}$/
  const ipv6Pattern = /^([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}$/
  return ipv4Pattern.test(host) || ipv6Pattern.test(host)
}

const buildBrowserBaseUrl = (): string => {
  if (typeof window === 'undefined') {
    return DEFAULT_FALLBACK_API_BASE_URL
  }
  return `${window.location.protocol}//${window.location.hostname}${
    isIpAddress(window.location.hostname) ? ':9001' : window.location.port ? `:${window.location.port}` : ''
  }`
}

export const ensureRuntimeConfig = (): WebAppConfig | null => {
  if (runtimeConfig) {
    return runtimeConfig
  }
  if (typeof window !== 'undefined' && window.__CORAL_CONFIG__) {
    runtimeConfig = window.__CORAL_CONFIG__
    return runtimeConfig
  }
  return null
}

export const setRuntimeConfig = (config: WebAppConfig): void => {
  runtimeConfig = config
  if (typeof window !== 'undefined') {
    window.__CORAL_CONFIG__ = config
  }
}

export const getRuntimeConfig = (): WebAppConfig | null => runtimeConfig

export const resolveApiBaseUrl = (providedConfig?: WebAppConfig | null): string => {
  const activeConfig = providedConfig ?? getRuntimeConfig() ?? ensureRuntimeConfig()
  const configuredBase = activeConfig?.api?.baseUrl
  if (configuredBase && configuredBase !== RUNTIME_PLACEHOLDER_BASE_URL) {
    return configuredBase
  }
  if (process.env.NEXT_PUBLIC_API_BASE_URL) {
    return process.env.NEXT_PUBLIC_API_BASE_URL
  }
  if (typeof window !== 'undefined') {
    return buildBrowserBaseUrl()
  }
  return DEFAULT_FALLBACK_API_BASE_URL
}

export const getInitialConfig = (): WebAppConfig => {
  return (
    getRuntimeConfig() ??
    ensureRuntimeConfig() ?? {
      ...DEFAULT_CONFIG,
      app: { ...DEFAULT_CONFIG.app },
      api: { ...DEFAULT_CONFIG.api },
      features: { ...DEFAULT_CONFIG.features },
    }
  )
}
