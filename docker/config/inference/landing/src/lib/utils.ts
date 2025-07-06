import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * 获取API基础URL
 */
export const getApiBaseUrl = () => {
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:9001'
    }
    return `http://${hostname}:9001`
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:9001'
}

/**
 * 格式化延迟时间
 */
export const formatLatency = (latency: number): string => {
  if (latency < 1) {
    return `${(latency * 1000).toFixed(0)}ms`
  }
  return `${latency.toFixed(2)}s`
}

/**
 * 格式化FPS
 */
export const formatFPS = (fps: number): string => {
  return `${fps.toFixed(1)} FPS`
}

/**
 * 获取状态颜色
 */
export const getStatusColor = (status: string): string => {
  switch (status?.toLowerCase()) {
    case 'running':
      return 'bg-green-500'
    case 'pending':
      return 'bg-blue-500'
    case 'warning':
      return 'bg-yellow-500'
    case 'failure':
      return 'bg-red-600'
    case 'muted':
      return 'bg-gray-500'
    case 'stopped':
      return 'bg-red-500'
    case 'not_found':
      return 'bg-red-400'
    case 'timeout':
      return 'bg-orange-500'
    // 保持向后兼容
    case 'paused':
      return 'bg-yellow-500'
    case 'error':
      return 'bg-red-600'
    default:
      return 'bg-gray-400'
  }
}

/**
 * 获取状态文本颜色
 */
export const getStatusTextColor = (status: string): string => {
  switch (status?.toLowerCase()) {
    case 'running':
      return 'text-green-600'
    case 'pending':
      return 'text-blue-600'
    case 'warning':
      return 'text-yellow-600'
    case 'failure':
      return 'text-red-700'
    case 'muted':
      return 'text-gray-600'
    case 'stopped':
      return 'text-red-600'
    case 'not_found':
      return 'text-red-500'
    case 'timeout':
      return 'text-orange-600'
    // 保持向后兼容
    case 'paused':
      return 'text-yellow-600'
    case 'error':
      return 'text-red-700'
    default:
      return 'text-gray-600'
  }
}

/**
 * 防抖函数
 */
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null
  return (...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout)
    timeout = setTimeout(() => func(...args), wait)
  }
}

/**
 * 获取状态显示名称
 */
export const getStatusDisplayName = (status: string): string => {
  switch (status?.toLowerCase()) {
    case 'running':
      return '运行中'
    case 'pending':
      return '等待中'
    case 'warning':
      return '警告'
    case 'failure':
      return '失败'
    case 'muted':
      return '静音'
    case 'stopped':
      return '已停止'
    case 'not_found':
      return '未找到'
    case 'timeout':
      return '超时'
    // 保持向后兼容
    case 'paused':
      return '暂停'
    case 'error':
      return '错误'
    default:
      return '未知'
  }
}

/**
 * 节流函数
 */
export function throttle<T extends (...args: any[]) => any>(
  func: T,
  limit: number
): (...args: Parameters<T>) => void {
  let inThrottle: boolean
  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      func(...args)
      inThrottle = true
      setTimeout(() => (inThrottle = false), limit)
    }
  }
} 