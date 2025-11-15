import { resolveApiBaseUrl } from '@/config/runtime'

type ApiRequestOptions = RequestInit & {
  baseUrl?: string
}

// API服务 - 连接后端接口
const getApiBaseUrl = (override?: string): string => override || resolveApiBaseUrl()

// 状态枚举
export type PipelineStatus = 'pending' | 'running' | 'warning' | 'failure' | 'muted' | 'stopped' | 'not_found' | 'timeout'

// 类型定义
export interface Pipeline {
  id: string
  name: string
  status: PipelineStatus
}

export interface MetricsResponse {
  dates: string[]
  datasets: Array<{
    name: string
    data: number[] | string[]
  }>
}

export interface WebRTCOfferRequest {
  webrtc_offer: {
    sdp: string
    type: 'offer'
  }
  webrtc_turn_config?: any
  stream_output?: string[]
  data_output?: string[]
  webrtc_peer_timeout?: number
  webcam_fps?: number
  processing_timeout?: number
  fps_probe_frames?: number
  max_consecutive_timeouts?: number
  min_consecutive_on_time?: number
}

export interface WebRTCOfferResponse {
  status: string
  context: {
    request_id: string
    pipeline_id: string
  }
  sdp: string
  type: string
}

// 录像文件类型
export interface VideoFileItem {
  filename: string
  size_bytes: number
  created_at: number
  modified_at: number
}

export interface VideoListResponse {
  status: string
  files?: VideoFileItem[]
  error?: string
}

export interface PipelineStatusResponse {
  status: string
  context: {
    request_id: string
    pipeline_id: string
  }
  report: {
    [key: string]: any
  }
}

export interface PipelineInfoResponse {
  status: string
  data: {
    pipeline_id: string
    restore_pipeline_id: string
    parameters: {
      output_image_fields?: string[]
      [key: string]: any
    }
  }
}

// 自定义指标类型
export type ChartType = 'line' | 'area' | 'bar' | 'pie'

export interface CustomMetricPayload {
  name: string
  chart_type: ChartType
  measurement: string
  fields: string[]
  aggregation?: string | null
  group_by?: string[] | null
  group_by_time?: string | null
  tag_filters?: Record<string, string> | null
  description?: string | null
  time_range_seconds?: number | null
  refresh_interval_seconds?: number | null
}

export interface CustomMetric extends CustomMetricPayload {
  id: number
  created_at: string
  updated_at: string
}

export interface CustomMetricChartPoint {
  timestamp: string | number | Date
  value: number
  label?: string
  tags?: Record<string, string>
  metadata?: Record<string, any>
}

export interface CustomMetricChartResponse {
  metric: CustomMetric
  executed_query: string
  time_window: {
    start: string
    end: string
  }
  series: Array<{
    name: string
    columns: string[]
    values: any[][]
    tags?: Record<string, string>
  }>
  chart_data: CustomMetricChartPoint[]
}

// API错误处理
export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public response?: Response
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

// 通用请求函数
async function apiRequest<T>(
  endpoint: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  const { baseUrl, ...requestInit } = options
  const API_BASE_URL = getApiBaseUrl(baseUrl)
  const url = `${API_BASE_URL}${endpoint}`
  
  const defaultOptions: RequestInit = {
    headers: {
      'Content-Type': 'application/json',
      ...requestInit.headers,
    },
    ...requestInit,
  }

  try {
    console.log(`API请求: ${options.method || 'GET'} ${url}`)
    
    const response = await fetch(url, defaultOptions)
    
    if (!response.ok) {
      const errorText = await response.text()
      throw new ApiError(
        `API请求失败: ${response.status} ${response.statusText}${errorText ? ` - ${errorText}` : ''}`,
        response.status,
        response
      )
    }

    const data = await response.json()
    console.log(`API响应:`, data)
    return data
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }
    
    console.error(`API请求错误:`, error)
    throw new ApiError(
      `网络错误: ${error instanceof Error ? error.message : '未知错误'}`,
      0
    )
  }
}

// Pipeline相关API
export const pipelineApi = {
  // 获取Pipeline列表
  async list(apiBaseUrl?: string): Promise<Pipeline[]> {
    try {
      const response = await apiRequest<{
        pipelines: string[]
        fixed_pipelines: Array<{
          pipeline_id: string
          pipeline_name: string
          created_at: number
        }>
      }>('/inference_pipelines/list', { baseUrl: apiBaseUrl })
      
      // 转换为前端需要的格式
      const pipelines: Pipeline[] = response.fixed_pipelines.map(pipelineInfo => ({
        id: pipelineInfo.pipeline_id,
        name: pipelineInfo.pipeline_name,
        status: 'pending' as const // 默认状态，实际状态需要通过其他接口获取
      }))

      return pipelines
    } catch (error) {
      console.error('获取Pipeline列表失败:', error)
      throw error
    }
  },

  // 获取Pipeline信息
  async getInfo(pipelineId: string, apiBaseUrl?: string): Promise<PipelineInfoResponse> {
    try {
      const response = await apiRequest<PipelineInfoResponse>(
        `/inference_pipelines/${pipelineId}/info`,
        { baseUrl: apiBaseUrl }
      )
      return response
    } catch (error) {
      console.error('获取Pipeline信息失败:', error)
      throw error
    }
  },

  // 获取Pipeline指标数据
  async getMetrics(
    pipelineId: string,
    timeRange: { start?: number; end?: number; minutes?: number } = { minutes: 5 },
    apiBaseUrl?: string
  ): Promise<MetricsResponse> {
    try {
      const params = new URLSearchParams()
      
      if (timeRange.start) params.append('start_time', timeRange.start.toString())
      if (timeRange.end) params.append('end_time', timeRange.end.toString())
      if (timeRange.minutes) params.append('minutes', timeRange.minutes.toString())
      
      const queryString = params.toString()
      const endpoint = `/inference_pipelines/${pipelineId}/metrics${queryString ? `?${queryString}` : ''}`
      
      const response = await apiRequest<MetricsResponse>(endpoint, { baseUrl: apiBaseUrl })
      return response
    } catch (error) {
      console.error('获取Pipeline指标失败:', error)
      throw error
    }
  },

  // 获取带有实际状态的Pipeline列表
  async listWithStatus(apiBaseUrl?: string): Promise<Pipeline[]> {
    try {
      // 首先获取基础的Pipeline列表
      const pipelines = await this.list(apiBaseUrl)
      
      // 并行获取每个Pipeline的状态
      const statusPromises = pipelines.map(async (pipeline: Pipeline) => {
        try {
          const statusResponse = await monitorApi.getStatus(pipeline.id, apiBaseUrl)
          const calculatedStatus = statusUtils.calculatePipelineStatus(
            statusResponse.status,
            statusResponse.report
          )
          return {
            ...pipeline,
            status: calculatedStatus
          }
        } catch (error) {
          console.error(`获取Pipeline ${pipeline.id} 状态失败:`, error)
          // 根据错误类型设置状态
          if (error instanceof ApiError) {
            if (error.status === 404) {
              return { ...pipeline, status: 'not_found' as PipelineStatus }
            } else if (error.status === 0) {
              return { ...pipeline, status: 'timeout' as PipelineStatus }
            }
          }
          return { ...pipeline, status: 'failure' as PipelineStatus }
        }
      })
      
      const pipelinesWithStatus = await Promise.all(statusPromises)
      return pipelinesWithStatus
    } catch (error) {
      console.error('获取Pipeline列表及状态失败:', error)
      throw error
    }
  },

  // 创建WebRTC连接
  async createWebRTCOffer(
    pipelineId: string,
    offer: WebRTCOfferRequest,
    apiBaseUrl?: string
  ): Promise<WebRTCOfferResponse> {
    try {
      const body = JSON.stringify(offer)
      console.log('发送的请求体:', body)
      const response = await apiRequest<WebRTCOfferResponse>(
        `/inference_pipelines/${pipelineId}/offer`,
        {
          method: 'POST',
          body: body,
          baseUrl: apiBaseUrl,
        }
      )
      
      return response
    } catch (error) {
      console.error('创建WebRTC连接失败:', error)
      throw error
    }
  },
}

// 监控相关API
export const monitorApi = {
  // 获取Pipeline状态
  async getStatus(pipelineId: string, apiBaseUrl?: string): Promise<PipelineStatusResponse> {
    try {
      const response = await apiRequest<PipelineStatusResponse>(
        `/inference_pipelines/${pipelineId}/status`,
        { baseUrl: apiBaseUrl }
      )
      
      return response
    } catch (error) {
      console.error('获取Pipeline状态失败:', error)
      throw error
    }
  },

  // 获取磁盘使用情况
  async getDiskUsage(apiBaseUrl?: string) {
    try {
      const response = await apiRequest<{
        status: string
        data: {
          output_dir: string
          current_size_gb: number
          max_size_gb: number
          usage_percentage: number
          free_space_gb: number
        }
      }>('/monitor/disk-usage', { baseUrl: apiBaseUrl })
      
      return response.data
    } catch (error) {
      console.error('获取磁盘使用情况失败:', error)
      throw error
    }
  },

  // 手动刷新缓存
  async flushCache(apiBaseUrl?: string) {
    try {
      const response = await apiRequest<{
        status: string
        message: string
      }>('/monitor/flush-cache', {
        method: 'POST',
        baseUrl: apiBaseUrl,
      })
      
      return response
    } catch (error) {
      console.error('刷新缓存失败:', error)
      throw error
    }
  },

  // 手动触发清理
  async triggerCleanup(apiBaseUrl?: string) {
    try {
      const response = await apiRequest<{
        status: string
        message: string
      }>('/monitor/cleanup', {
        method: 'POST',
        baseUrl: apiBaseUrl,
      })
      
      return response
    } catch (error) {
      console.error('触发清理失败:', error)
      throw error
    }
  },

  // 获取监控器状态
  async getMonitorStatus(apiBaseUrl?: string) {
    try {
      const response = await apiRequest<{
        status: string
        data: {
          running: boolean
          output_dir: string
          poll_interval: number
          pipeline_count: number
          is_healthy: boolean
          performance_metrics: {
            poll_count: number
            poll_duration: number
            last_poll_time: number
            influxdb_enabled: boolean
            error_count: number
            last_error_time: number
            background_queue_size: number
            results_cache_size: number
            influxdb_buffer_size?: number
          }
          influxdb_enabled: boolean
          influxdb_connected: boolean
        }
      }>('/monitor/status', { baseUrl: apiBaseUrl })
      
      return response.data
    } catch (error) {
      console.error('获取监控器状态失败:', error)
      throw error
    }
  },

  // 获取Pipeline指标摘要（从 InfluxDB）
  async getMetricsSummary(
    pipelineId: string,
    timeRange: { start?: number; end?: number; minutes?: number; aggregation_window?: string } = { minutes: 30 },
    apiBaseUrl?: string
  ) {
    try {
      const params = new URLSearchParams()
      
      if (timeRange.start) params.append('start_time', timeRange.start.toString())
      if (timeRange.end) params.append('end_time', timeRange.end.toString())
      if (timeRange.minutes) params.append('minutes', timeRange.minutes.toString())
      if (timeRange.aggregation_window) params.append('aggregation_window', timeRange.aggregation_window)
      
      const queryString = params.toString()
      const endpoint = `/inference_pipelines/${pipelineId}/metrics/summary${queryString ? `?${queryString}` : ''}`
      
      const response = await apiRequest<{
        status: string
        data: {
          pipeline_id: string
          start_time: string
          end_time: string
          aggregation_window: string
          data: Array<{
            time?: string
            source_id?: string
            avg_latency?: number
            max_p99_latency?: number
            avg_fps?: number
            total_frames?: number
            total_dropped?: number
            [key: string]: any
          }>
        }
      }>(endpoint, { baseUrl: apiBaseUrl })
      
      return response.data
    } catch (error) {
      console.error('获取Pipeline指标摘要失败:', error)
      throw error
    }
  },

  // 获取 InfluxDB 连接状态
  async getInfluxDBStatus(apiBaseUrl?: string) {
    try {
      const response = await apiRequest<{
        status: string
        data: {
          enabled: boolean
          connected: boolean
          healthy?: boolean
          url?: string
          bucket?: string
          measurement?: string
          buffer_size?: number
          last_flush_time?: number
          message?: string
        }
      }>('/monitor/influxdb/status', { baseUrl: apiBaseUrl })
      
      return response.data
    } catch (error) {
      console.error('获取InfluxDB状态失败:', error)
      throw error
    }
  },
}

// 自定义指标 API
export const customMetricsApi = {
  async list(apiBaseUrl?: string): Promise<CustomMetric[]> {
    return apiRequest<CustomMetric[]>('/custom-metrics', { baseUrl: apiBaseUrl })
  },

  async create(payload: CustomMetricPayload, apiBaseUrl?: string): Promise<CustomMetric> {
    return apiRequest<CustomMetric>('/custom-metrics', {
      method: 'POST',
      body: JSON.stringify(payload),
      baseUrl: apiBaseUrl,
    })
  },

  async get(metricId: number, apiBaseUrl?: string): Promise<CustomMetric> {
    return apiRequest<CustomMetric>(`/custom-metrics/${metricId}`, { baseUrl: apiBaseUrl })
  },

  async update(
    metricId: number,
    payload: CustomMetricPayload,
    apiBaseUrl?: string
  ): Promise<CustomMetric> {
    return apiRequest<CustomMetric>(`/custom-metrics/${metricId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
      baseUrl: apiBaseUrl,
    })
  },

  async remove(metricId: number, apiBaseUrl?: string): Promise<void> {
    await apiRequest(`/custom-metrics/${metricId}`, { method: 'DELETE', baseUrl: apiBaseUrl })
  },

  async fetchChartData(
    metricId: number,
    params: { minutes?: number; start_time?: number; end_time?: number } = {},
    apiBaseUrl?: string
  ): Promise<CustomMetricChartResponse> {
    return apiRequest<CustomMetricChartResponse>(`/custom-metrics/${metricId}/chart-data`, {
      method: 'POST',
      body: JSON.stringify(params),
      baseUrl: apiBaseUrl,
    })
  },
}

// 录像相关API
export const recordingApi = {
  // 列出录像文件
  async list(
    pipelineId: string,
    outputDirectory: string = 'records',
    apiBaseUrl?: string,
  ): Promise<VideoFileItem[]> {
    const params = new URLSearchParams()
    if (outputDirectory) params.append('output_directory', outputDirectory)
    const endpoint = `/inference_pipelines/${pipelineId}/videos${params.toString() ? `?${params.toString()}` : ''}`
    const res = await apiRequest<VideoListResponse>(endpoint, { baseUrl: apiBaseUrl })
    if (res.status !== 'success') {
      throw new ApiError(res.error || '获取录像列表失败')
    }
    return res.files || []
  },

  // 构造可播放的视频URL（支持Range）
  videoUrl(
    pipelineId: string,
    filename: string,
    outputDirectory: string = 'records',
    apiBaseUrl?: string,
  ): string {
    const API_BASE_URL = getApiBaseUrl(apiBaseUrl)
    const params = new URLSearchParams()
    if (outputDirectory) params.append('output_directory', outputDirectory)
    const query = params.toString()
    return `${API_BASE_URL}/inference_pipelines/${encodeURIComponent(pipelineId)}/videos/${encodeURIComponent(filename)}${query ? `?${query}` : ''}`
  },
}

// 状态计算工具函数
export const statusUtils = {
  // 计算Pipeline状态 - 参考后端deployments.py的get_status方法
  calculatePipelineStatus(status: string, report: any): PipelineStatus {
    if (status === "failure") {
      return 'failure'
    }
    
    if (status === "not_found") {
      return 'not_found'
    }
    
    if (status === "success") {
      if (!report) {
        return 'pending'
      }
      
      const sourcesMetadata = report['sources_metadata']
      if (!sourcesMetadata || !Array.isArray(sourcesMetadata)) {
        return 'pending'
      }
      
      const sourceStates = sourcesMetadata.map(source => source['state'])
      
      if (sourceStates.every(state => state === "RUNNING")) {
        return 'running'
      } else if (sourceStates.every(state => state === "MUTED")) {
        return 'muted'
      } else {
        return 'warning'
      }
    }
    
    return 'pending'
  }
}

// 工具函数
export const apiUtils = {
  // 检查API连接状态
  async checkConnection(options: { pipelineId?: string; apiBaseUrl?: string } = {}): Promise<boolean> {
    const { pipelineId, apiBaseUrl } = options
    try {
      if (pipelineId) {
        await monitorApi.getStatus(pipelineId, apiBaseUrl)
      } else {
        // 如果没有提供pipelineId，尝试获取pipeline列表
        await pipelineApi.list(apiBaseUrl)
      }
      return true
    } catch (error) {
      console.error('API连接检查失败:', error)
      return false
    }
  },

  // 格式化API错误信息
  formatError(error: unknown): string {
    if (error instanceof ApiError) {
      return error.message
    }
    
    if (error instanceof Error) {
      return error.message
    }
    
    return '未知错误'
  },
} 
