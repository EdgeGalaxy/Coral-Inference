'use client'

import { useEffect, useMemo, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { recordingApi, apiUtils } from '@/lib/api'
import { Film, RefreshCw, Play, Download, ListFilter, HardDrive } from 'lucide-react'
import { usePipelineRecordings } from '@/features/recordings/hooks'
import { useApiBaseUrl } from '@/hooks/use-api-base-url'

interface RecordingsViewerProps {
  pipelineId: string | null
}

interface SortOption {
  key: 'created_at' | 'modified_at' | 'size_bytes' | 'filename'
  label: string
}

const SORT_OPTIONS: SortOption[] = [
  { key: 'created_at', label: '按创建时间(新→旧)' },
  { key: 'modified_at', label: '按修改时间(新→旧)' },
  { key: 'size_bytes', label: '按大小(大→小)' },
  { key: 'filename', label: '按文件名(A→Z)' },
]

export function RecordingsViewer({ pipelineId }: RecordingsViewerProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const [outputDirectory, setOutputDirectory] = useState<string>('records')
  const [sortKey, setSortKey] = useState<SortOption['key']>('created_at')
  const [search, setSearch] = useState('')
  const apiBaseUrl = useApiBaseUrl()
  const recordingsQuery = usePipelineRecordings(pipelineId, outputDirectory)
  const files = useMemo(() => recordingsQuery.data ?? [], [recordingsQuery.data])
  const loading = recordingsQuery.isLoading
  const refreshing = recordingsQuery.isFetching && !recordingsQuery.isLoading
  const errorMessage = recordingsQuery.error ? apiUtils.formatError(recordingsQuery.error) : null

  useEffect(() => {
    setSelected(null)
  }, [pipelineId, outputDirectory])

  useEffect(() => {
    if (!selected && files.length > 0) {
      setSelected(files[0].filename)
    }
  }, [files, selected])

  const sortedAndFiltered = useMemo(() => {
    const filtered = files.filter(f =>
      f.filename.toLowerCase().includes(search.toLowerCase())
    )
    const sorted = [...filtered].sort((a, b) => {
      switch (sortKey) {
        case 'created_at':
          return b.created_at - a.created_at
        case 'modified_at':
          return b.modified_at - a.modified_at
        case 'size_bytes':
          return b.size_bytes - a.size_bytes
        case 'filename':
          return a.filename.localeCompare(b.filename)
        default:
          return 0
      }
    })
    return sorted
  }, [files, sortKey, search])

  const currentVideoUrl = useMemo(() => {
    if (!pipelineId || !selected) return ''
    return recordingApi.videoUrl(pipelineId, selected, outputDirectory, apiBaseUrl)
  }, [apiBaseUrl, pipelineId, selected, outputDirectory])

  const formatSize = (size: number) => {
    if (size >= 1024 * 1024 * 1024) return `${(size / (1024 * 1024 * 1024)).toFixed(2)} GB`
    if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(2)} MB`
    if (size >= 1024) return `${(size / 1024).toFixed(2)} KB`
    return `${size} B`
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Film className="h-5 w-5" />
          录像回放
          <Badge variant="outline" className="ml-auto">
            <HardDrive className="h-3 w-3 mr-1" />
            本地文件
          </Badge>
        </CardTitle>
        <CardDescription>
          {pipelineId ? `Pipeline: ${pipelineId}` : '请选择Pipeline以查看录像'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 p-3 bg-muted rounded-lg">
          <div className="flex items-center gap-2">
            <Input
              placeholder="搜索文件名..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2">
            <ListFilter className="h-4 w-4" />
            <Select value={sortKey} onValueChange={(v) => setSortKey(v as SortOption['key'])}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="排序" />
              </SelectTrigger>
              <SelectContent>
                {SORT_OPTIONS.map(opt => (
                  <SelectItem key={opt.key} value={opt.key}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            {/* <Input
              placeholder="输出目录，例如 records"
              value={outputDirectory}
              onChange={(e) => setOutputDirectory(e.target.value)}
            /> */}
            <Button
              variant="outline"
              onClick={() => recordingsQuery.refetch()}
              disabled={!pipelineId || loading}
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>

        {errorMessage && (
          <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-600">
            {errorMessage}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-5">
            <div className="border rounded-lg overflow-hidden">
              <div className="max-h-[420px] overflow-auto divide-y">
                {sortedAndFiltered.length === 0 && (
                  <div className="p-4 text-sm text-muted-foreground">{pipelineId ? '暂无录像文件' : '请选择Pipeline'}</div>
                )}
                {sortedAndFiltered.map(item => (
                  <div
                    key={item.filename}
                    onClick={() => setSelected(item.filename)}
                    className={`p-3 cursor-pointer hover:bg-muted/60 ${selected === item.filename ? 'bg-muted' : ''}`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="truncate font-medium">{item.filename}</div>
                      <div className="text-xs text-muted-foreground ml-2">{formatSize(item.size_bytes)}</div>
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      创建: {new Date(item.created_at * 1000).toLocaleString()} | 更新: {new Date(item.modified_at * 1000).toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="lg:col-span-7">
            <div className="relative bg-black rounded-lg overflow-hidden" style={{ aspectRatio: '16/9' }}>
              {currentVideoUrl ? (
                <video
                  key={currentVideoUrl}
                  src={currentVideoUrl}
                  controls
                  controlsList="nodownload noplaybackrate"
                  className="w-full h-full object-contain"
                />
              ) : (
                <div className="absolute inset-0 flex items-center justify-center bg-black/50">
                  <div className="text-center text-white">
                    <Film className="h-12 w-12 mx-auto mb-2 opacity-50" />
                    <p className="text-sm opacity-75">
                      {pipelineId ? '选择左侧文件播放录像' : '请选择Pipeline'}
                    </p>
                  </div>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2 mt-3">
              <Button
                onClick={() => currentVideoUrl && window.open(currentVideoUrl, '_blank')}
                disabled={!currentVideoUrl}
              >
                <Play className="h-4 w-4 mr-2" />
                在新窗口播放
              </Button>
              <a
                href={currentVideoUrl}
                download
                className={`inline-flex items-center justify-center h-10 px-4 py-2 rounded-md border text-sm font-medium ${currentVideoUrl ? 'bg-white hover:bg-gray-50' : 'pointer-events-none opacity-50'}`}
              >
                <Download className="h-4 w-4 mr-2" />
                下载视频
              </a>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
