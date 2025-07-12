#!/bin/bash

# 设置错误时退出
set -e

# 设置环境变量
export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-9001}
export ENABLE_STREAM_API=${ENABLE_STREAM_API:-true}
export PWD=${PWD:-/app}

echo "Starting services with supervisor..."
echo "HOST: $HOST"
echo "PORT: $PORT"
echo "ENABLE_STREAM_API: $ENABLE_STREAM_API"

# 创建必要的目录
mkdir -p $PWD/logs

# 优雅关闭函数
graceful_shutdown() {
    echo "Received termination signal. Starting graceful shutdown..."
    
    # 尝试刷新监控器缓存
    echo "Attempting to flush monitor cache..."
    if curl -s -X POST "http://localhost:$PORT/monitor/flush-cache" > /dev/null 2>&1; then
        echo "Monitor cache flushed successfully"
    else
        echo "Failed to flush monitor cache, continuing with shutdown..."
    fi
    
    # 等待一小段时间让缓存刷新完成
    sleep 2
    
    # 停止所有supervisor管理的进程
    echo "Shutting down services..."
    supervisorctl stop all
    
    # 停止supervisor
    supervisorctl shutdown
    
    echo "Graceful shutdown completed"
    exit 0
}

# 捕获终止信号
trap 'graceful_shutdown' SIGTERM SIGINT

# 启动supervisor
exec supervisord -c $PWD/supervisord.conf 