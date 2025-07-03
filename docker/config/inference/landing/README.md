# Coral Inference Dashboard

一个现代化的推理管道监控与控制面板，支持实时视频流、性能指标监控和Pipeline管理。

## 🌟 主要特性

- **实时视频流**: 基于WebRTC的低延迟视频传输
- **性能监控**: 实时指标数据可视化和历史趋势分析
- **Pipeline管理**: 支持多个推理管道的选择和状态监控
- **现代化UI**: 响应式设计，支持深色模式和动画效果
- **API集成**: 完整的后端API集成，支持实时数据更新

## 🚀 快速开始

### 环境要求

- Node.js 18+ 
- npm 或 yarn
- 后端API服务运行在 `http://localhost:8080`

### 安装和运行

1. **快速启动**（推荐）:
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

2. **手动启动**:
   ```bash
   # 安装依赖
   npm install
   
   # 启动开发服务器
   npm run dev
   
   # 或构建生产版本
   npm run build
   npm run start
   
   # 构建静态版本（包含static文件夹）
   npm run build:static
   ```

3. **API连接测试**:
   ```bash
   # 测试后端API连接
   node test-api.js
   ```

### 访问应用

- 开发模式: http://localhost:3000
- 生产模式: http://localhost:3000

## 🏗️ 构建说明

### 标准构建

```bash
npm run build
```

标准构建会生成：
- `.next/` - Next.js构建输出
- `out/` - 静态导出文件

### 静态构建（推荐用于部署）

```bash
npm run build:static
# 或直接运行
./build-static.sh
```

静态构建会额外生成：
- `out/_next/static/` - Next.js标准静态资源路径
- `out/static/` - 备用静态资源路径（方便部署）

构建完成后的文件结构：
```
out/
├── _next/
│   ├── static/          # Next.js标准静态资源
│   │   ├── chunks/      # JavaScript chunks
│   │   ├── css/         # CSS文件
│   │   └── media/       # 媒体文件
│   └── [buildId]/       # 构建相关文件
├── static/              # 静态资源副本
│   ├── chunks/          # JavaScript chunks副本
│   ├── css/             # CSS文件副本
│   └── media/           # 媒体文件副本
├── index.html           # 主页面
└── 404.html             # 404页面
```

### 清理构建文件

```bash
npm run clean
```

### 验证构建结果

```bash
npm run test-static
```

## 🚀 部署指南

### 静态文件部署

1. **构建静态版本**:
   ```bash
   npm run build:static
   ```

2. **验证构建结果**:
   ```bash
   npm run test-static
   ```

3. **部署到Web服务器**:
   将 `out/` 目录的内容复制到Web服务器的根目录。

### Nginx配置示例

项目包含了 `nginx.conf.example` 文件，提供了完整的Nginx配置示例：

```bash
# 复制并修改Nginx配置
cp nginx.conf.example /etc/nginx/sites-available/coral-inference-dashboard
# 编辑配置文件，修改域名和路径
sudo nano /etc/nginx/sites-available/coral-inference-dashboard
# 启用站点
sudo ln -s /etc/nginx/sites-available/coral-inference-dashboard /etc/nginx/sites-enabled/
# 重载Nginx配置
sudo nginx -t && sudo systemctl reload nginx
```

### 静态资源访问路径

构建完成后，静态资源可通过以下路径访问：

- **标准路径**: `/_next/static/*` (Next.js标准路径)
- **备用路径**: `/static/*` (方便部署和CDN配置)

### 部署检查清单

- [ ] 构建成功完成
- [ ] 静态文件验证通过
- [ ] Web服务器配置正确
- [ ] 静态资源路径可访问
- [ ] 环境变量配置正确
- [ ] API服务正常运行

## 🔧 配置说明

### 环境变量

在项目根目录创建 `.env.local` 文件：

```bash
# API基础URL - 后端服务地址
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080

# 开发环境配置
NODE_ENV=development

# 其他配置
NEXT_PUBLIC_APP_NAME=Coral Inference Dashboard
NEXT_PUBLIC_APP_VERSION=1.0.0
```

### API接口说明

应用连接到以下后端API接口：

#### Pipeline管理
- `GET /inference_pipelines/list` - 获取Pipeline列表
- `POST /inference_pipelines/{pipeline_id}/offer` - 创建WebRTC连接
- `GET /inference_pipelines/{pipeline_id}/metrics` - 获取Pipeline指标

#### 监控接口
- `GET /monitor/disk-usage` - 获取磁盘使用情况
- `POST /monitor/flush-cache` - 手动刷新缓存
- `POST /monitor/cleanup` - 手动触发清理

## 📁 项目结构

```
src/
├── app/                    # Next.js 应用路由
│   ├── globals.css        # 全局样式
│   ├── layout.tsx         # 应用布局
│   └── page.tsx           # 主页面
├── components/            # React组件
│   ├── ui/               # 基础UI组件
│   │   ├── badge.tsx
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── dialog.tsx
│   │   └── select.tsx
│   ├── metrics-modal.tsx  # 指标模态框
│   ├── pipeline-selector.tsx # Pipeline选择器
│   └── video-stream.tsx   # 视频流组件
└── lib/                   # 工具库
    ├── api.ts            # API服务
    ├── mock-data.ts      # Mock数据（备用）
    └── utils.ts          # 工具函数
```

## 🔄 API集成模式

### 数据流

1. **Pipeline选择**: 从后端获取可用的Pipeline列表
2. **视频流**: 通过WebRTC协议建立实时视频连接
3. **指标监控**: 定期获取性能指标数据并可视化
4. **状态更新**: 实时监控连接状态和系统状态

### 错误处理

- 自动重连机制
- 友好的错误提示
- 降级到Mock模式（开发调试）

## 🎨 UI特性

- **响应式设计**: 支持桌面和移动设备
- **现代化界面**: 基于Tailwind CSS和shadcn/ui
- **动画效果**: 平滑的过渡和加载动画
- **状态指示**: 清晰的连接状态和加载状态
- **主题支持**: 支持浅色和深色模式

## 📊 性能监控

### 支持的指标

- **吞吐量**: 实时FPS数据
- **延迟指标**: 
  - 帧解码延迟
  - 推理延迟  
  - 端到端延迟
- **系统资源**: GPU使用率、内存使用
- **状态信息**: Pipeline各组件状态

### 可视化功能

- 实时图表更新
- 历史趋势分析
- 多时间范围选择
- 交互式图表

## 🔧 开发说明

### 技术栈

- **前端框架**: Next.js 14 (App Router)
- **UI组件**: React + TypeScript
- **样式**: Tailwind CSS
- **图表**: Recharts
- **状态管理**: React Hooks
- **API通信**: Fetch API

### 开发工具

```bash
# 开发服务器
npm run dev

# 类型检查
npm run type-check

# 代码格式化
npm run lint

# 构建
npm run build

# API测试
node test-api.js
```

## 🐛 故障排除

### 常见问题

1. **API连接失败**
   - 检查后端服务是否运行在正确端口
   - 确认 `NEXT_PUBLIC_API_BASE_URL` 环境变量设置正确
   - 运行 `node test-api.js` 测试API连接

2. **WebRTC连接问题**
   - 确认浏览器支持WebRTC
   - 检查网络防火墙设置
   - 查看浏览器控制台错误信息

3. **构建失败**
   - 清理依赖: `rm -rf node_modules package-lock.json && npm install`
   - 检查Node.js版本是否符合要求

### 日志调试

浏览器控制台会显示详细的API调用和WebRTC连接日志，便于调试。

## 📝 更新日志

### v1.0.0 (当前版本)
- ✅ 完整的API集成
- ✅ WebRTC视频流支持
- ✅ 实时性能监控
- ✅ 响应式UI设计
- ✅ 错误处理和重连机制

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个项目。

## 📄 许可证

MIT License