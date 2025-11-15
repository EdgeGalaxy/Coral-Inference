export type FeatureToggle = {
  enabled: boolean
  order?: number
  label?: string
  description?: string
  maxCharts?: number
}

export type IceServerConfig = {
  urls: string | string[]
  username?: string
  credential?: string
}

export type WebPluginSpec = {
  id: string
  displayName: string
  description?: string
  mountPath: string
  entrypoint: string
  sandbox?: 'iframe' | 'module'
  permissions?: string[]
  config?: Record<string, unknown>
}

export type MonitoringConfig = {
  disk?: {
    maxSizeGb?: number
    warnPercentage?: number
  }
  metrics?: {
    provider?: 'influxdb' | 'prometheus' | 'stdout'
    refreshIntervalSeconds?: number
  }
}

export type UIConfig = {
  theme?: {
    mode?: 'light' | 'dark' | 'system'
    primaryColor?: string
  }
  layout?: {
    sidebarCollapsed?: boolean
    hideRecordingTab?: boolean
  }
}

export interface WebAppConfig {
  app: {
    name: string
    tagline?: string
    logoUrl?: string
    docsUrl?: string
    supportEmail?: string
  }
  api: {
    baseUrl: string
    websocketUrl?: string
    timeoutMs: number
    headers?: Record<string, string>
  }
  features: {
    pipelines: FeatureToggle
    streams: FeatureToggle & { defaultPipelineId?: string }
    monitoring: FeatureToggle & { sinks?: string[] }
    recordings: FeatureToggle
    customMetrics: FeatureToggle
    plugins: FeatureToggle
  }
  streams?: {
    iceServers?: IceServerConfig[]
    peerConfig?: Record<string, unknown>
    maxResolution?: `${number}x${number}`
    defaultFps?: number
  }
  monitoring?: MonitoringConfig
  plugins?: {
    web?: WebPluginSpec[]
  }
  ui?: UIConfig
  build: {
    version: string
    gitCommit?: string
    generatedAt: string
  }
}
