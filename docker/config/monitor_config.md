# Pipeline Monitor 配置参数说明

## 基础监控配置

### PIPELINE_MONITOR_INTERVAL
- **默认值**: 0.1 (秒)
- **描述**: 监控器轮询间隔，控制监控器多久检查一次pipeline状态
- **建议**: 较小的值提供更实时的监控，但会增加CPU使用率

### PIPELINE_RESULTS_DIR
- **默认值**: `{MODEL_CACHE_DIR}/pipelines`
- **描述**: 监控结果存储目录
- **建议**: 确保有足够的磁盘空间

### PIPELINE_RESULTS_MAX_DAYS
- **默认值**: 7 (天)
- **描述**: 结果文件保留天数，超过此天数的文件会被清理
- **建议**: 根据存储需求和磁盘容量调整

### PIPELINE_CLEANUP_INTERVAL
- **默认值**: 3600 (秒)
- **描述**: 清理任务运行间隔
- **建议**: 对于高频使用的系统，可以缩短间隔

## 性能优化配置

### PIPELINE_STATUS_INTERVAL
- **默认值**: 1 (秒)
- **描述**: 状态监控间隔
- **建议**: 根据监控精度需求调整

### PIPELINE_SAVE_INTERVAL_MINUTES
- **默认值**: 5 (分钟)
- **描述**: 指标数据保存间隔
- **建议**: 较短的间隔提供更好的数据保护，但会增加磁盘I/O

## 缓存优化配置

### PIPELINE_RESULTS_BATCH_SIZE
- **默认值**: 10
- **描述**: 结果缓存批次大小，达到此数量后会触发磁盘写入
- **建议**: 
  - 较大的值减少磁盘I/O频率，但会增加内存使用
  - 较小的值提供更好的实时性

### PIPELINE_RESULTS_FLUSH_INTERVAL
- **默认值**: 30 (秒)
- **描述**: 结果缓存强制刷新间隔，即使未达到批次大小也会刷新
- **建议**: 根据数据丢失容忍度调整

## 磁盘使用监控配置

### PIPELINE_MAX_SIZE_GB
- **默认值**: 10 (GB)
- **描述**: 监控目录最大磁盘使用量阈值
- **建议**: 
  - 根据可用磁盘空间设置
  - 留出足够的缓冲空间

### PIPELINE_SIZE_CHECK_INTERVAL
- **默认值**: 300 (秒)
- **描述**: 磁盘使用检查间隔
- **建议**: 
  - 较短的间隔提供更及时的清理
  - 较长的间隔减少系统开销

## 配置建议

### 高频使用场景
```bash
PIPELINE_MONITOR_INTERVAL=0.05
PIPELINE_RESULTS_BATCH_SIZE=20
PIPELINE_RESULTS_FLUSH_INTERVAL=60
PIPELINE_MAX_SIZE_GB=20
PIPELINE_SIZE_CHECK_INTERVAL=180
```

### 低频使用场景
```bash
PIPELINE_MONITOR_INTERVAL=0.5
PIPELINE_RESULTS_BATCH_SIZE=5
PIPELINE_RESULTS_FLUSH_INTERVAL=15
PIPELINE_MAX_SIZE_GB=5
PIPELINE_SIZE_CHECK_INTERVAL=600
```

### 资源受限环境
```bash
PIPELINE_MONITOR_INTERVAL=1.0
PIPELINE_RESULTS_BATCH_SIZE=3
PIPELINE_RESULTS_FLUSH_INTERVAL=10
PIPELINE_MAX_SIZE_GB=2
PIPELINE_SIZE_CHECK_INTERVAL=300
```

## API端点

### 监控状态查询
- **GET** `/monitor/disk-usage` - 获取磁盘使用情况

### 手动操作
- **POST** `/monitor/flush-cache` - 手动刷新缓存
- **POST** `/monitor/cleanup` - 手动触发磁盘清理

## 监控指标

### 缓存监控
- `cached_metrics_count`: 缓存的指标数量
- `cached_results_count`: 缓存的结果数量

### 磁盘监控
- `total_size_gb`: 当前磁盘使用量
- `max_size_gb`: 最大磁盘使用量阈值
- `usage_percentage`: 磁盘使用率百分比
- `pipeline_count`: 管道数量

## 故障排除

### 磁盘空间不足
1. 检查 `/monitor/disk-usage` 端点
2. 调整 `PIPELINE_MAX_SIZE_GB` 参数
3. 手动触发清理 `/monitor/cleanup`
4. 减少 `PIPELINE_RESULTS_MAX_DAYS` 参数

### 性能问题
1. 增加 `PIPELINE_RESULTS_BATCH_SIZE` 减少磁盘I/O
2. 增加 `PIPELINE_RESULTS_FLUSH_INTERVAL` 延长刷新间隔
3. 增加 `PIPELINE_MONITOR_INTERVAL` 减少监控频率

### 数据丢失风险
1. 减少 `PIPELINE_RESULTS_FLUSH_INTERVAL` 增加刷新频率
2. 减少 `PIPELINE_RESULTS_BATCH_SIZE` 及时写入
3. 确保优雅关闭流程正常工作 