import type { WebAppConfig } from '@/config/types'

declare global {
  interface Window {
    __CORAL_CONFIG__?: WebAppConfig
  }
}

export {}
