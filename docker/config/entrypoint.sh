#!/bin/bash

# 设置错误时退出
set -e

# 设置环境变量
export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-9001}
export ENABLE_STREAM_API=${ENABLE_STREAM_API:-true}
export PWD=${PWD:-/app}
# 禁用推理路由
export LEGACY_ROUTE_ENABLED=False
export DISABLE_VERSION_CHECK=True

echo "Starting services with supervisor..."
echo "HOST: $HOST"
echo "PORT: $PORT"
echo "ENABLE_STREAM_API: $ENABLE_STREAM_API"

# 创建必要的目录
mkdir -p $PWD/logs

# 在启动 supervisord 前，强制释放端口 7070 与 9001
kill_port() {
    local port="$1"
    echo "Force closing port ${port}..."
    # 临时关闭 set -e，避免无进程时导致脚本退出
    set +e
    if command -v fuser >/dev/null 2>&1; then
        fuser -k -n tcp "${port}" >/dev/null 2>&1 || true
    fi
    if command -v lsof >/dev/null 2>&1; then
        pids=$(lsof -ti tcp:"${port}")
        if [ -n "${pids}" ]; then
            kill -9 ${pids} >/dev/null 2>&1 || true
        fi
    fi
    if command -v ss >/dev/null 2>&1; then
        pids=$(ss -lptn "sport = :${port}" 2>/dev/null | awk -F 'pid=' 'NR>1{split($2,a,","); print a[1]}' | sort -u)
        if [ -n "${pids}" ]; then
            kill -9 ${pids} >/dev/null 2>&1 || true
        fi
    elif command -v netstat >/dev/null 2>&1; then
        pids=$(netstat -tulpn 2>/dev/null | awk -v p=":${port}" '$4 ~ p {split($7,a,"/"); print a[1]}' | sort -u)
        if [ -n "${pids}" ] && [ "${pids}" != "-" ]; then
            kill -9 ${pids} >/dev/null 2>&1 || true
        fi
    fi
    set -e
}

kill_port 7070
kill_port $PORT

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


echo "Using console-based logging configuration"
CONFIG_FILE="$PWD/supervisord.conf"

# 启动supervisor
exec supervisord -c $CONFIG_FILE
