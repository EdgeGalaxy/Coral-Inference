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

export function MetricsModal({ isOpen, onClose, pipelineId }: MetricsModalProps) {
  const apiBaseUrl = getApiBaseUrl();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [metricsData, setMetricsData] = useState<MetricsData | null>(null);


  useEffect(() => {
    if (isOpen && pipelineId) {
      fetchMetrics();
    }
  }, [isOpen, pipelineId]);

  const fetchMetrics = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch(
        `${apiBaseUrl}/inference_pipelines/${pipelineId}/metrics?minutes=5`,
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

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Pipeline 性能指标</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : error ? (
            <div className="text-red-500 text-center">{error}</div>
          ) : metricsData ? (
            <>
              {/* FPS图表 */}
              <Card className="p-4">
                <h3 className="text-lg font-semibold mb-4">FPS</h3>
                <LineChart
                  data={{
                    labels: metricsData.dates,
                    datasets: [
                      {
                        label: "FPS",
                        data: metricsData.datasets.find(d => d.name === "Throughput")?.data || [],
                      },
                    ],
                  }}
                  className="w-full aspect-[2/1]"
                />
              </Card>

              {/* 延迟图表 */}
              <Card className="p-4">
                <h3 className="text-lg font-semibold mb-4">帧解码延迟</h3>
                <LineChart
                  data={{
                    labels: metricsData.dates,
                    datasets: metricsData.datasets
                      .filter(d => d.name.startsWith("Frame Decoding Latency"))
                      .map(d => ({
                        label: d.name,
                        data: d.data,
                      })),
                  }}
                  className="w-full aspect-[2/1]"
                />
              </Card>

              <Card className="p-4">
                <h3 className="text-lg font-semibold mb-4">推理延迟</h3>
                <LineChart
                  data={{
                    labels: metricsData.dates,
                    datasets: metricsData.datasets
                      .filter(d => d.name.startsWith("Inference Latency"))
                      .map(d => ({
                        label: d.name,
                        data: d.data,
                      })),
                  }}
                  className="w-full aspect-[2/1]"
                />
              </Card>

              <Card className="p-4">
                <h3 className="text-lg font-semibold mb-4">E2E延迟</h3>
                <LineChart
                  data={{
                    labels: metricsData.dates,
                    datasets: metricsData.datasets
                      .filter(d => d.name.startsWith("E2E Latency"))
                      .map(d => ({
                        label: d.name,
                        data: d.data,
                      })),
                  }}
                  className="w-full aspect-[2/1]"
                />
              </Card>

              <Card className="p-4">
                <h3 className="text-lg font-semibold mb-4">状态</h3>
                <LineChart
                  data={{
                    labels: metricsData.dates,
                    datasets: metricsData.datasets
                      .filter(d => d.name.startsWith("State"))
                      .map(d => ({
                        label: d.name,
                        data: d.data, 
                      })),
                  }}
                  className="w-full aspect-[2/1]"
                />
              </Card>
            </>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
} 