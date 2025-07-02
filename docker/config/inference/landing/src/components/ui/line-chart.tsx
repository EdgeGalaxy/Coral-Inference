import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  ChartOptions,
} from 'chart.js';

// 注册 Chart.js 组件
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

interface LineChartProps {
  data: {
    labels: string[];
    datasets: {
      label: string;
      data: number[];
      borderColor?: string;
      backgroundColor?: string;
      borderWidth?: number;
      pointRadius?: number;
      pointHoverRadius?: number;
      tension?: number;
      fill?: boolean;
    }[];
  };
  className?: string;
}

export function LineChart({ data, className }: LineChartProps) {
  const options: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top' as const,
        labels: {
          boxWidth: 15,
          padding: 10,
          font: {
            size: 12,
          }
        }
      },
      tooltip: {
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        titleFont: {
          size: 13,
        },
        bodyFont: {
          size: 12,
        },
        padding: 8,
        cornerRadius: 4,
        displayColors: true,
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        grid: {
          color: 'rgba(200, 200, 200, 0.2)',
        },
        ticks: {
          font: {
            size: 11,
          }
        }
      },
      x: {
        grid: {
          display: false,
        },
        ticks: {
          maxRotation: 45,
          minRotation: 45,
          autoSkip: true,
          maxTicksLimit: 6,
          font: {
            size: 10,
          }
        }
      }
    },
    elements: {
      line: {
        borderWidth: 2,
        tension: 0.2,
      },
      point: {
        radius: 1.5,
        hitRadius: 8,
        hoverRadius: 3,
        hoverBorderWidth: 2
      }
    },
  };

  // 确保所有数据集的样式正确应用
  const processedData = {
    labels: data.labels,
    datasets: data.datasets.map((dataset, index) => {
      // 合并默认样式和自定义样式
      return {
        ...dataset,
        borderColor: dataset.borderColor || `hsl(${index * 60}, 70%, 50%)`,
        backgroundColor: dataset.backgroundColor || `hsla(${index * 60}, 70%, 50%, 0.5)`,
        tension: dataset.tension !== undefined ? dataset.tension : 0.2,
        borderWidth: dataset.borderWidth !== undefined ? dataset.borderWidth : 2,
        pointRadius: dataset.pointRadius !== undefined ? dataset.pointRadius : 1.5,
        pointHoverRadius: dataset.pointHoverRadius !== undefined ? dataset.pointHoverRadius : 3,
        fill: dataset.fill !== undefined ? dataset.fill : false,
      };
    }),
  };

  return (
    <div className={className}>
      <Line options={options} data={processedData} />
    </div>
  );
} 