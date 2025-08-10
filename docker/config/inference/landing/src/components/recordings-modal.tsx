'use client'

import { useEffect, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { RecordingsViewer } from '@/components/recordings-viewer'
import { Video, Check } from 'lucide-react'

interface RecordingsModalProps {
  isOpen: boolean
  onClose: () => void
  defaultPipelineId: string | null
}

export function RecordingsModal({ isOpen, onClose, defaultPipelineId }: RecordingsModalProps) {
  const [pipelineId, setPipelineId] = useState<string>('')

  useEffect(() => {
    if (isOpen) {
      setPipelineId(defaultPipelineId || '')
    }
  }, [isOpen, defaultPipelineId])

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Video className="h-5 w-5" />
            查看录像
          </DialogTitle>
          {/* <DialogDescription>
            指定 Pipeline ID，选择录像文件并进行播放或下载
          </DialogDescription> */}
        </DialogHeader>

        <div className="space-y-3">
          {/* <div className="flex items-center gap-2">
            <Input
              placeholder="输入或粘贴 Pipeline ID"
              value={pipelineId}
              onChange={(e) => setPipelineId(e.target.value)}
            />
            <Button
              variant="secondary"
              onClick={() => setPipelineId(defaultPipelineId || '')}
              disabled={!defaultPipelineId}
            >
              <Check className="h-4 w-4 mr-2" />
              使用当前选择
            </Button>
          </div> */}

          <RecordingsViewer pipelineId={pipelineId || null} />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


