"use client"

import * as React from "react"
import { format, startOfDay, endOfDay, getUnixTime } from "date-fns"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { DatePicker } from "@/components/ui/date-picker"
import { Separator } from "@/components/ui/separator"

interface TimeRangePickerProps {
  onTimeRangeChange: (params: { minutes?: number, start_time?: number, end_time?: number }) => void
  className?: string
}

type PresetRange = {
  label: string
  minutes: number
}

export function TimeRangePicker({ onTimeRangeChange, className }: TimeRangePickerProps) {
  const [selectedPreset, setSelectedPreset] = React.useState<number>(5)
  const [startDate, setStartDate] = React.useState<Date | undefined>(undefined)
  const [endDate, setEndDate] = React.useState<Date | undefined>(undefined)

  const presetRanges: PresetRange[] = [
    { label: "5分钟", minutes: 5 },
    { label: "15分钟", minutes: 15 },
    { label: "30分钟", minutes: 30 },
    { label: "60分钟", minutes: 60 },
  ]

  const handlePresetClick = (minutes: number) => {
    setSelectedPreset(minutes)
    setStartDate(undefined)
    setEndDate(undefined)
    onTimeRangeChange({ minutes })
  }

  const handleCustomDateChange = () => {
    if (startDate && endDate) {
      setSelectedPreset(0)
      // 转换为时间戳（秒）
      const start_time = getUnixTime(startOfDay(startDate))
      const end_time = getUnixTime(endOfDay(endDate))
      onTimeRangeChange({ start_time, end_time })
    }
  }

  React.useEffect(() => {
    if (startDate && endDate) {
      handleCustomDateChange()
    }
  }, [startDate, endDate])

  return (
    <div className={cn("flex flex-wrap items-center gap-3", className)}>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">预设:</span>
        <div className="flex gap-1">
          {presetRanges.map((preset) => (
            <Button
              key={preset.minutes}
              variant={selectedPreset === preset.minutes ? "default" : "outline"}
              size="sm"
              onClick={() => handlePresetClick(preset.minutes)}
              className="px-2 py-0 h-8"
            >
              {preset.label}
            </Button>
          ))}
        </div>
      </div>
      
      <Separator orientation="vertical" className="h-8" />
      
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">自定义:</span>
        <div className="flex gap-2 items-center">
          <DatePicker
            date={startDate}
            setDate={setStartDate}
            placeholder="开始日期"
            className="w-36"
          />
          <span className="text-sm">至</span>
          <DatePicker
            date={endDate}
            setDate={setEndDate}
            placeholder="结束日期"
            className="w-36"
          />
        </div>
      </div>
    </div>
  )
} 