# 监控器配置文档

## 概述

本系统现已升级为使用优化的监控器 `OptimizedPipelineMonitorWithInfluxDB`，集成了 InfluxDB3 时序数据库存储，提供更强大的监控和分析能力。

## 环境变量配置

### 基础监控配置

| 环境变量 | 默认值 | 描述 |
|---------|--------|------|
| `PIPELINE_MONITOR_INTERVAL` | `0.1` | 监控轮询间隔（秒） |
| `PIPELINE_RESULTS_DIR` | `${MODEL_CACHE_DIR}/pipelines` | 结果文件存储目录 |
| `PIPELINE_RESULTS_MAX_DAYS` | `7` | 结果文件最大保留天数 |
| `PIPELINE_CLEANUP_INTERVAL` | `3600` | 清理检查间隔（秒） |
| `PIPELINE_STATUS_INTERVAL` | `5` | 状态收集间隔（秒） |
| `PIPELINE_MAX_SIZE_GB` | `10` | 最大磁盘使用空间（GB） |
| `PIPELINE_SIZE_CHECK_INTERVAL` | `300` | 磁盘使用检查间隔（秒） |

### 批量处理配置

| 环境变量 | 默认值 | 描述 |
|---------|--------|------|
| `PIPELINE_RESULTS_BATCH_SIZE` | `100` | 结果缓存批量大小 |
| `PIPELINE_RESULTS_FLUSH_INTERVAL` | `30` | 结果刷新间隔（秒） |
| `PIPELINE_MAX_BACKGROUND_WORKERS` | `5` | 后台工作线程数量 |

### InfluxDB 配置

| 环境变量 | 默认值 | 描述 |
|---------|--------|------|
| `ENABLE_INFLUXDB` | `true` | 是否启用 InfluxDB |
| `INFLUXDB_METRICS_URL` | - | InfluxDB 服务器地址 |
| `INFLUXDB_METRICS_TOKEN` | - | InfluxDB 认证令牌 |
| `INFLUXDB_METRICS_ORG` | - | InfluxDB 组织名 |
| `INFLUXDB_METRICS_BUCKET` | - | InfluxDB 数据库/桶名称 |
| `METRICS_BATCH_SIZE` | `100` | 指标批量写入大小 |
| `METRICS_FLUSH_INTERVAL` | `10` | 指标刷新间隔（秒） |

## InfluxDB 配置示例

### Docker Compose 配置

```yaml
environment:
  # 启用 InfluxDB
  - ENABLE_INFLUXDB=true
  
  # InfluxDB 连接信息
  - INFLUXDB_METRICS_URL=http://influxdb:8086
  - INFLUXDB_METRICS_TOKEN=your-influxdb-token-here
  - INFLUXDB_METRICS_ORG=coral-inference
  - INFLUXDB_METRICS_BUCKET=pipeline_metrics
  
  # 性能调优
  - METRICS_BATCH_SIZE=200
  - METRICS_FLUSH_INTERVAL=5
  - PIPELINE_MAX_BACKGROUND_WORKERS=8
```

### 环境变量文件 (.env)

```bash
# 基础监控配置
PIPELINE_MONITOR_INTERVAL=0.5
PIPELINE_STATUS_INTERVAL=3
PIPELINE_RESULTS_BATCH_SIZE=200
PIPELINE_MAX_BACKGROUND_WORKERS=8

# InfluxDB 配置
ENABLE_INFLUXDB=true
INFLUXDB_METRICS_URL=http://localhost:8086
INFLUXDB_METRICS_TOKEN=your-token
INFLUXDB_METRICS_ORG=your-org
INFLUXDB_METRICS_BUCKET=metrics
METRICS_BATCH_SIZE=100
METRICS_FLUSH_INTERVAL=10

# 磁盘管理
PIPELINE_MAX_SIZE_GB=50
PIPELINE_RESULTS_MAX_DAYS=30
```

## 新增 API 接口

### 监控器状态

```
GET /monitor/status
```

**响应格式：**
```json
{
  "status": "success",
  "data": {
    "running": true,
    "output_dir": "/path/to/results",
    "poll_interval": 1.0,
    "pipeline_count": 3,
    "is_healthy": true,
    "performance_metrics": {
      "poll_count": 12345,
      "poll_duration": 0.123,
      "last_poll_time": 1692345678.9,
      "influxdb_enabled": true,
      "error_count": 0,
      "last_error_time": 0,
      "background_queue_size": 2,
      "results_cache_size": 150,
      "influxdb_buffer_size": 45
    },
    "influxdb_enabled": true,
    "influxdb_connected": true
  }
}
```

### InfluxDB 指标摘要

```
GET /inference_pipelines/{pipeline_id}/metrics/summary?minutes=30&aggregation_window=1m
```

**响应格式：**
```json
{
  "status": "success",
  "data": {
    "pipeline_id": "pipeline_123",
    "start_time": "2024-01-01T12:00:00Z",
    "end_time": "2024-01-01T12:30:00Z",
    "aggregation_window": "1m",
    "data": [
      {
        "time": "2024-01-01T12:00:00Z",
        "source_id": "source_1",
        "avg_latency": 25.5,
        "max_p99_latency": 45.2,
        "avg_fps": 29.8,
        "total_frames": 1780,
        "total_dropped": 2
      }
    ]
  }
}
```

### InfluxDB 连接状态

```
GET /monitor/influxdb/status
```

**响应格式：**
```json
{
  "status": "success",
  "data": {
    "enabled": true,
    "connected": true,
    "healthy": true,
    "url": "http://influxdb:8086",
    "bucket": "pipeline_metrics",
    "measurement": "pipeline_metrics",
    "buffer_size": 45,
    "last_flush_time": 1692345678.9
  }
}
```

## 性能调优建议

### 高负载环境

对于高负载环境，建议以下配置：

```bash
# 增加批处理大小
PIPELINE_RESULTS_BATCH_SIZE=500
METRICS_BATCH_SIZE=300

# 增加工作线程
PIPELINE_MAX_BACKGROUND_WORKERS=12

# 减少轮询间隔以提高响应性
PIPELINE_MONITOR_INTERVAL=0.05
PIPELINE_STATUS_INTERVAL=2

# 减少刷新间隔以提高实时性
PIPELINE_RESULTS_FLUSH_INTERVAL=15
METRICS_FLUSH_INTERVAL=5
```

### 低资源环境

对于资源受限环境，建议以下配置：

```bash
# 减少批处理大小
PIPELINE_RESULTS_BATCH_SIZE=50
METRICS_BATCH_SIZE=50

# 减少工作线程
PIPELINE_MAX_BACKGROUND_WORKERS=2

# 增加轮询间隔以减少负载
PIPELINE_MONITOR_INTERVAL=1.0
PIPELINE_STATUS_INTERVAL=10

# 增加刷新间隔以减少 I/O
PIPELINE_RESULTS_FLUSH_INTERVAL=60
METRICS_FLUSH_INTERVAL=30
```

## 故障排除

### InfluxDB 连接问题

1. 检查 InfluxDB 服务是否运行
2. 验证连接参数（URL、Token、组织、桶）
3. 查看监控器日志中的错误信息
4. 使用 `/monitor/influxdb/status` 接口检查连接状态

### 性能问题

1. 监控后台队列大小：`background_queue_size`
2. 检查缓冲区大小：`results_cache_size`, `influxdb_buffer_size`
3. 调整批处理大小和刷新间隔
4. 增加后台工作线程数量

### 磁盘空间问题

1. 检查当前磁盘使用：`GET /monitor/disk-usage`
2. 调整 `PIPELINE_MAX_SIZE_GB` 设置
3. 减少 `PIPELINE_RESULTS_MAX_DAYS` 保留天数
4. 手动触发清理：`POST /monitor/cleanup`

## 迁移指南

### 从旧版监控器迁移

1. 更新环境变量配置
2. 添加 InfluxDB 相关配置（如需要）
3. 重启应用程序
4. 验证新接口工作正常
5. 更新前端组件以使用新的数据格式

### 数据兼容性

- 新监控器保持向后兼容
- 文件存储结构保持不变
- 新增 InfluxDB 存储选项
- 前端自动检测数据源类型

## 监控和告警

建议监控以下关键指标：

- `performance_metrics.error_count` - 错误计数
- `performance_metrics.background_queue_size` - 队列积压
- `is_healthy` - 监控器健康状态
- `influxdb_connected` - InfluxDB 连接状态
- 磁盘使用百分比

可以通过 `/monitor/status` 接口定期检查这些指标，并设置相应的告警阈值。
