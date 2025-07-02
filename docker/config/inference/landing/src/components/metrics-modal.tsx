import { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Card } from "@/components/ui/card";
import { LineChart } from "@/components/ui/line-chart";
import { Loader2 } from "lucide-react";
import { getApiBaseUrl } from "@/utils/api";
import { TimeRangePicker } from "@/components/time-range-picker";
import { differenceInMinutes, format, isAfter, isBefore, parseISO } from "date-fns";

interface MetricsModalProps {
  isOpen: boolean;
  onClose: () => void;
  pipelineId: string;
  apiBaseUrl: string;
}

interface MetricsData {
  dates: string[];
  datasets: {
    name: string;
    data: number[];
  }[];
}

interface TimeRangeParams {
  minutes?: number;
  start_time?: number;
  end_time?: number;
}

export function MetricsModal({ isOpen, onClose, pipelineId }: MetricsModalProps) {
  const apiBaseUrl = getApiBaseUrl();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [metricsData, setMetricsData] = useState<MetricsData | null>(null);
  const [timeRange, setTimeRange] = useState<TimeRangeParams>({ minutes: 5 });

  useEffect(() => {
    if (isOpen && pipelineId) {
      fetchMetrics();
    }
  }, [isOpen, pipelineId, timeRange]);

  const handleTimeRangeChange = (params: TimeRangeParams) => {
    setTimeRange(params);
  };

  const fetchMetrics = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // 构建查询参数
      const queryParams = new URLSearchParams();
      if (timeRange.minutes) {
        queryParams.append('minutes', timeRange.minutes.toString());
      }
      if (timeRange.start_time) {
        queryParams.append('start_time', timeRange.start_time.toString());
      }
      if (timeRange.end_time) {
        queryParams.append('end_time', timeRange.end_time.toString());
      }
      
      const response = await fetch(
        `${apiBaseUrl}/inference_pipelines/${pipelineId}/metrics?${queryParams.toString()}`,
        {
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to fetch metrics data');
      }

      const data = await response.json();
      setMetricsData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  // 创建图表配置，优化线条粗细和可见性
  const createChartConfig = (datasets: any[]) => {
    return datasets.map(d => ({
      ...d,
      borderWidth: 2, // 减小线条宽度
      pointRadius: 1.5, // 减小点的大小
      pointHoverRadius: 3,
      tension: 0.2,
      fill: false,
      borderColor: '#FF3A29',
    }));
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="flex h-full w-full flex-col sm:max-h-[90vh] sm:max-w-[70vw]">
        <DialogHeader className="pb-2">
          <DialogTitle>Pipeline 性能指标</DialogTitle>
        </DialogHeader>

        <div className="mb-4 p-2 bg-muted/20 border rounded-md">
          <TimeRangePicker onTimeRangeChange={handleTimeRangeChange} />
        </div>

        <div className="space-y-4">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : error ? (
            <div className="text-red-500 text-center">{error}</div>
          ) : metricsData ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {/* FPS图表 */}
              <Card className="p-4">
                <h3 className="text-lg font-semibold mb-2">FPS</h3>
                <LineChart
                  data={{
                    labels: metricsData.dates,
                    datasets: createChartConfig([
                      {
                        label: "FPS",
                        data: metricsData.datasets.find(d => d.name === "Throughput")?.data || [],
                      },
                    ]),
                  }}
                  className="w-full aspect-[3/2]"
                />
              </Card>

              {/* 延迟图表 */}
              <Card className="p-4">
                <h3 className="text-lg font-semibold mb-2">帧解码延迟</h3>
                <LineChart
                  data={{
                    labels: metricsData.dates,
                    datasets: createChartConfig(metricsData.datasets
                      .filter(d => d.name.startsWith("Frame Decoding Latency"))
                      .map(d => ({
                        label: d.name,
                        data: d.data,
                      }))),
                  }}
                  className="w-full aspect-[3/2]"
                />
              </Card>

              <Card className="p-4">
                <h3 className="text-lg font-semibold mb-2">推理延迟</h3>
                <LineChart
                  data={{
                    labels: metricsData.dates,
                    datasets: createChartConfig(metricsData.datasets
                      .filter(d => d.name.startsWith("Inference Latency"))
                      .map(d => ({
                        label: d.name,
                        data: d.data,
                      }))),
                  }}
                  className="w-full aspect-[3/2]"
                />
              </Card>

              <Card className="p-4">
                <h3 className="text-lg font-semibold mb-2">E2E延迟</h3>
                <LineChart
                  data={{
                    labels: metricsData.dates,
                    datasets: createChartConfig(metricsData.datasets
                      .filter(d => d.name.startsWith("E2E Latency"))
                      .map(d => ({
                        label: d.name,
                        data: d.data,
                      }))),
                  }}
                  className="w-full aspect-[3/2]"
                />
              </Card>

              <Card className="p-4">
                <h3 className="text-lg font-semibold mb-2">状态</h3>
                <LineChart
                  data={{
                    labels: metricsData.dates,
                    datasets: createChartConfig(metricsData.datasets
                      .filter(d => d.name.startsWith("State"))
                      .map(d => ({
                        label: d.name,
                        data: d.data, 
                      }))),
                  }}
                  className="w-full aspect-[3/2]"
                />
              </Card>
            </div>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
} 