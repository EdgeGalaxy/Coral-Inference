'use client'

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import type { WebAppConfig } from '@/config/types'
import { DEFAULT_CONFIG } from '@/config/default-config'
import { ensureRuntimeConfig, setRuntimeConfig } from '@/config/runtime'

type ConfigStatus = 'loading' | 'ready' | 'error'

type ConfigContextValue = {
  config: WebAppConfig
  status: ConfigStatus
  error: Error | null
  refresh: () => void
}

const ConfigContext = createContext<ConfigContextValue>({
  config: DEFAULT_CONFIG,
  status: 'loading',
  error: null,
  refresh: () => {},
})

export const ConfigProvider = ({ children }: { children: ReactNode }) => {
  const [config, setConfig] = useState<WebAppConfig>(DEFAULT_CONFIG)
  const [status, setStatus] = useState<ConfigStatus>('loading')
  const [error, setError] = useState<Error | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    let cancelled = false

    const loadConfig = async () => {
      setStatus('loading')
      setError(null)

      try {
        const existing = ensureRuntimeConfig()
        if (existing) {
          if (!cancelled) {
            setConfig(existing)
            setRuntimeConfig(existing)
            setStatus('ready')
          }
          return
        }

        const response = await fetch('/config.json', { cache: 'no-store' })
        if (!response.ok) {
          throw new Error(`Failed to load config: ${response.status} ${response.statusText}`)
        }
        const payload = (await response.json()) as WebAppConfig
        if (cancelled) {
          return
        }
        setRuntimeConfig(payload)
        setConfig(payload)
        setStatus('ready')
      } catch (err) {
        if (cancelled) {
          return
        }
        setStatus('error')
        setError(err instanceof Error ? err : new Error('Unknown config error'))
        setConfig(DEFAULT_CONFIG)
      }
    }

    loadConfig()

    return () => {
      cancelled = true
    }
  }, [reloadToken])

  const value = useMemo<ConfigContextValue>(
    () => ({
      config,
      status,
      error,
      refresh: () => setReloadToken((token) => token + 1),
    }),
    [config, status, error],
  )

  if (status === 'loading') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 text-slate-600">
        <p className="text-sm tracking-wide">加载配置中...</p>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-red-50 text-red-600">
        <p className="text-sm font-medium">无法加载配置文件</p>
        {error && <p className="mt-2 text-xs text-red-500">{error.message}</p>}
        <button
          onClick={() => setReloadToken((token) => token + 1)}
          className="mt-4 rounded-md bg-red-600 px-4 py-2 text-sm text-white shadow-sm hover:bg-red-700"
        >
          重试
        </button>
      </div>
    )
  }

  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>
}

export const useConfig = (): ConfigContextValue => {
  const context = useContext(ConfigContext)
  if (!context) {
    throw new Error('useConfig must be used within ConfigProvider')
  }
  return context
}
