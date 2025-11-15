import type { WebAppConfig } from '@/config/types'

export const DEFAULT_CONFIG: WebAppConfig = {
  app: {
    name: 'Coral Inference Dashboard',
    tagline: '实时推理管道监控与控制面板',
  },
  api: {
    baseUrl: 'runtime-default',
    timeoutMs: 10_000,
    headers: {},
  },
  features: {
    pipelines: { enabled: true, order: 1 },
    streams: { enabled: true, order: 2 },
    monitoring: { enabled: true, order: 3 },
    recordings: { enabled: true, order: 4 },
    customMetrics: { enabled: true, order: 5 },
    plugins: { enabled: false, order: 99 },
  },
  streams: {
    iceServers: [],
    defaultFps: 30,
    peerConfig: {},
  },
  monitoring: {
    disk: { maxSizeGb: 20, warnPercentage: 85 },
    metrics: { provider: 'influxdb', refreshIntervalSeconds: 10 },
  },
  plugins: { web: [] },
  ui: {
    theme: { mode: 'system', primaryColor: '#0f172a' },
    layout: {},
  },
  build: {
    version: 'dev',
    generatedAt: new Date(0).toISOString(),
  },
}
