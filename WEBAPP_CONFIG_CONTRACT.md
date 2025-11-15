# Coral WebAppConfig Contract

The frontend (Next.js dashboard) and backend (FastAPI `coral_inference.webapp`) now share a single `WebAppConfig` payload. This file records the schema, defaulting rules, and responsibilities so both sides can iterate in lockstep throughout Phase A of the refactor.

## Delivery pipeline

1. **Source** – `RuntimeDescriptor.services.webapp` (YAML/JSON or env overrides) defines cluster-specific values. Backend owns validation & defaults.
2. **Generation** – `coral-runtime web serve` materializes a typed `WebAppConfig` object and serializes it at startup.
3. **Distribution** – FastAPI exposes the payload via:
   - `GET /config.json` (static JSON, cached aggressively), and
   - `<script>window.__CORAL_CONFIG__ = {…}</script>` injected into `/index.html` for static export compatibility.
4. **Consumption** – The Next.js app loads config through `ConfigProvider` which falls back to the global script when SSR/static rendering.

The payload is immutable at runtime; hot updates require restarting the backend or reloading the JSON file.

## Schema overview

| Field | Type | Required | Producer | Consumer |
| --- | --- | --- | --- | --- |
| `app` | object | ✅ | Backend | Frontend branding (title/logo) |
| `api` | object | ✅ | Backend | `apiClient` base URLs/timeouts |
| `features` | object | ✅ | Backend | Frontend Feature toggles/order |
| `streams` | object | ⚪ | Backend | WebRTC defaults |
| `monitoring` | object | ⚪ | Backend | Metrics & disk panels |
| `plugins` | object | ⚪ | Backend | Web plugins exposed to frontend |
| `ui` | object | ⚪ | Backend | Theme/layout defaults |
| `build` | object | ✅ | Backend | Footer/debug info |

## Type definitions (TypeScript-style)

```ts
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
    customMetrics: FeatureToggle & { maxCharts?: number }
    plugins: FeatureToggle
  }
  streams?: {
    iceServers: IceServer[]
    peerConfig?: Record<string, unknown>
    maxResolution?: `${number}x${number}`
    defaultFps?: number
  }
  monitoring?: {
    disk: {
      maxSizeGb: number
      warnPercentage: number
    }
    metrics: {
      provider: "influxdb" | "prometheus" | "stdout"
      refreshIntervalSeconds: number
    }
  }
  plugins?: {
    web: WebPluginSpec[]
  }
  ui?: {
    theme: {
      mode: "light" | "dark" | "system"
      primaryColor?: string
    }
    layout?: {
      sidebarCollapsed?: boolean
      hideRecordingTab?: boolean
    }
  }
  build: {
    version: string
    gitCommit?: string
    generatedAt: string
  }
}

type FeatureToggle = {
  enabled: boolean
  label?: string
  order?: number
  description?: string
}

type IceServer = {
  urls: string | string[]
  username?: string
  credential?: string
}

type WebPluginSpec = {
  id: string
  displayName: string
  description?: string
  mountPath: string
  entrypoint: string
  sandbox?: "iframe" | "module"
  permissions?: string[]
  config?: Record<string, unknown>
}
```

## Sample payload

```json
{
  "app": { "name": "Coral Runtime", "tagline": "Realtime pipelines", "docsUrl": "https://docs.coral" },
  "api": { "baseUrl": "https://coral.example.com", "timeoutMs": 8000 },
  "features": {
    "pipelines": { "enabled": true, "order": 1 },
    "streams": { "enabled": true, "order": 2 },
    "monitoring": { "enabled": true, "order": 3, "description": "InfluxDB metrics" },
    "recordings": { "enabled": false },
    "customMetrics": { "enabled": true, "order": 4, "maxCharts": 6 },
    "plugins": { "enabled": true, "order": 99 }
  },
  "streams": {
    "iceServers": [
      { "urls": "stun:stun.l.google.com:19302" },
      {
        "urls": ["turn:turn.internal:3478"],
        "username": "user",
        "credential": "secret"
      }
    ],
    "defaultFps": 30
  },
  "monitoring": {
    "disk": { "maxSizeGb": 20, "warnPercentage": 85 },
    "metrics": { "provider": "influxdb", "refreshIntervalSeconds": 10 }
  },
  "plugins": {
    "web": [
      {
        "id": "custom-metrics",
        "displayName": "Custom Metrics",
        "mountPath": "/custom-metrics",
        "entrypoint": "https://cdn.example.com/custom-metrics/index.js",
        "sandbox": "module"
      }
    ]
  },
  "ui": {
    "theme": { "mode": "system", "primaryColor": "#00B2A9" },
    "layout": { "sidebarCollapsed": false }
  },
  "build": { "version": "0.4.0", "gitCommit": "abc1234", "generatedAt": "2024-05-03T12:00:00Z" }
}
```

## Ownership checklist

- **Backend**
  1. Validate `RuntimeDescriptor.services.webapp` against this schema.
  2. Serialize configs to `/config.json` and inline script.
  3. Keep git history of schema updates (edit this contract + relevant doc).

- **Frontend**
  1. Load config using `ConfigProvider` before rendering feature modules.
  2. Keep `types/webapp-config.ts` synced with this document.
  3. Gate all feature surfaces through `config.features.*`.

- **Shared**
  1. Update this file whenever new fields are added/removed.
  2. Tag releases where config schema changes (semver minor if additive).
  3. Coordinate rollout via `WEBAPP_FRONTEND_ROADMAP.md` & `WEBAPP_ROADMAP.md` status rows.
