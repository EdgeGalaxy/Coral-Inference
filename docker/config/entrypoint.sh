#!/bin/bash

# 设置错误时退出
set -e

# 设置环境变量
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-9001}
ENABLE_STREAM_API=${ENABLE_STREAM_API:-true}

# 检测是否在 Docker 环境中运行
if [ -f /.dockerenv ]; then
    LOG_OUTPUT="> >(tee /proc/1/fd/1) 2>&1"
else
    LOG_OUTPUT="2>&1 | tee -a app.log"
fi

# 启动 start.py 服务
echo "Starting start.py service..."
echo "ENABLE_STREAM_API is set to: $ENABLE_STREAM_API"
eval "ENABLE_STREAM_API=$ENABLE_STREAM_API python3 start.py $LOG_OUTPUT &"
START_PID=$!

# 等待 start.py 服务启动并检查状态
sleep 5
if ! kill -0 $START_PID 2>/dev/null; then
    echo "Error: start.py service failed to start"
    exit 1
fi

# 启动 web.py 服务
echo "Starting web.py service..."
eval "ENABLE_STREAM_API=$ENABLE_STREAM_API uvicorn web:app --host $HOST --port $PORT $LOG_OUTPUT &"
WEB_PID=$!

# 捕获终止信号
trap 'echo "Received termination signal. Shutting down services..."; kill $START_PID $WEB_PID; exit 0' SIGTERM SIGINT

# 保持容器运行并等待信号
wait $START_PID $WEB_PID 