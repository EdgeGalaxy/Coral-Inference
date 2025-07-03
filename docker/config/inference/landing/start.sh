#!/bin/bash

# Coral Inference Dashboard 启动脚本

echo "🚀 启动 Coral Inference Dashboard..."

# 检查Node.js版本
node_version=$(node --version)
echo "Node.js 版本: $node_version"

# 检查npm版本
npm_version=$(npm --version)
echo "npm 版本: $npm_version"

# 检查是否已安装依赖
if [ ! -d "node_modules" ]; then
    echo "📦 安装依赖包..."
    npm install
fi

# 设置环境变量
export NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8080}
export NODE_ENV=${NODE_ENV:-development}

echo "🌐 API基础URL: $NEXT_PUBLIC_API_BASE_URL"
echo "🔧 环境模式: $NODE_ENV"

# 启动开发服务器
echo "🎯 启动开发服务器..."
echo "📱 访问地址: http://localhost:3000"
echo "🛑 按 Ctrl+C 停止服务器"

npm run dev 