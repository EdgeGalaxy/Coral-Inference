# Coral WebApp（Next.js Dashboard）重构设计

本文聚焦 `docker/config/inference/landing/` 中的 Next.js 前端。当前代码基于 Next 15 + App Router，直接在组件内访问后端 API，缺少统一数据层与配置抽象；构建产物通过 `npm run build:static` 导出到 `out/` 供 FastAPI mount。为了对齐后端重构（Phase 4/WebApp 重构），需要一个更清晰、可扩展的前端架构。

## 1. 现状分析

| 模块 | 描述 | 问题 |
| --- | --- | --- |
| 数据访问 | 组件内部直接 `fetch`（或在未来版本使用 `fetch`）调用 `NEXT_PUBLIC_API_BASE_URL` 下的 REST 接口 | 缺少统一 API 客户端/错误处理；不可配置多集群；缺乏类型定义 |
| 状态管理 | 组件本地 `useState`/`useEffect`（例如 `PipelineSelector` 维护 pipeline 列表），没有共享层 | 难以缓存/轮询；WebRTC/录像/metrics 状态重复实现 |
| UI 组织 | `/src/app` + `/src/components`，未区分 domain/feature；UI 与业务逻辑混杂 | 难以拆分、复用或测试；较难引入插件化 |
| 配置/主题 | `.env` 中仅定义 `NEXT_PUBLIC_API_BASE_URL`、`APP_NAME` 等；没有统一的 ConfigProvider | 无法根据 RuntimeDescriptor.services 生成前端配置；多环境部署麻烦 |
| 构建/部署 | `npm run build:static` 复制 `_next/static`；`out/` 供 FastAPI 静态挂载 | 缺少 CI 校验/预览；对 CDN/版本管理支持不足 |
| 可测试性 | 目前无单测/端到端测试；`package.json` 未包含 `test` 脚本 | 难以保证 UI/交互稳定 |

## 2. 目标
1. **配置对齐**：前端可消费后端 `WebAppConfig`/RuntimeDescriptor（例如通过 `/conf.json` 或环境变量注入），避免硬编码 API URL。
2. **模块化结构**：按 Domain/Feature 组织，例如 `features/pipelines`, `features/streams`, `features/monitoring`，每个 feature 暴露 hooks + UI 组件。
3. **数据层统一**：使用 React Query/SWR + `apiClient` 封装 HTTP 调用，集中处理鉴权、错误、轮询与缓存。
4. **WebRTC/录像等实时场景**：将 WebRTC session、video capture、录像播放抽象为可复用 hooks/service（配合后端 StreamService 重构）。
5. **主题/布局**：引入 Layout + ThemeProvider，统一暗/亮模式、全局样式、加载状态。
6. **扩展能力**：支持“前端插件”或配置开关（例如隐藏录像 tab、定制 metrics dashboard），与后端 plugin 生态匹配。
7. **测试/CI**：增加组件单测（Vitest/React Testing Library）与基本 e2e（Playwright），并在构建流水线上校验 `npm run lint && npm run test`.

## 3. 建议目录结构
```
src/
├── app/
│   ├── layout.tsx        # 全局 Layout，注入 ThemeProvider/ConfigProvider
│   ├── page.tsx          # 仪表盘主页面
│   ├── api/client.ts     # Next Server Actions/RouteHandler 可选
│   └── (routes)/...      # 自定义指标、录像详情等页面
├── config/
│   └── index.ts          # 前端配置接口：API base、feature flags、ui settings
├── features/
│   ├── pipelines/
│   │   ├── api.ts        # list/init/… HTTP 调用
│   │   ├── hooks.ts      # usePipelines/usePipelineActions
│   │   └── components/   # PipelineSelector 等
│   ├── streams/
│   │   ├── webrtc.ts     # WebRTC 管理（adapter & config）
│   │   └── components/
│   ├── monitoring/
│   │   ├── api.ts
│   │   └── components/   # Metrics charts、monitor modals
│   └── recordings/
├── libs/
│   ├── api-client.ts     # fetch wrapper + interceptors
│   ├── query-client.ts   # React Query 设置
│   └── utils/            # 共用工具
├── providers/
│   ├── ConfigProvider.tsx
│   ├── QueryProvider.tsx
│   └── ThemeProvider.tsx
└── types/
    ├── pipelines.ts
    └── monitoring.ts
```

## 4. 前后端约定
- 后端在 `create_web_app` 时暴露 `/config.json`（或在 `index.html` 中注入 `<script>window.__CORAL_CONFIG__ = {...}</script>`），内容来自 `WebAppConfig`。前端 `ConfigProvider` 读取该配置，决定 API base、feature flag、UI 字段（logo、标题等）。
- WebRTC/录像 API 与后端 StreamService 保持一致；若后端提供签名/鉴权，前端需在 `apiClient` 层实现 token 刷新/错误处理。
- 自定义插件：可在配置中列出前端插件（JS bundle URL、元素ID），前端通过动态 import/iframe 加载（后续 Roadmap 决定）。

## 5. 技术选型
- 框架：Next.js 15 (App Router) + React 19。
- UI：Tailwind + Shadcn 组件库（沿用现有）。
- 数据层：React Query +自定义 fetch（支持 abort、缓存、重试）。
- 图表：可继续使用 `recharts`/`chart.js`，但建议统一数据接口。
- WebRTC：封装在 `features/streams/webrtc-client.ts`，便于替换。
- 测试：Vitest + RTL；Playwright 做关键流程（pipeline 选择、指标弹窗、录像列表）。

## 6. 上线路径

| 阶段 | 目标 | 交付 |
| --- | --- | --- |
| A. 配置/基础设施 | ConfigProvider + API Client + React Query Provider；将现有页面迁移到新 providers | 能从 `/config.json` 读取 API base/feature flag；`apiClient` 统一请求 |
| B. Feature 模块化 | pipelines/streams/monitoring 拆分为 features，主页面组装改为 Hooks + Components；同时增加 toast/loading/error 处理 | `PipelineSelector`, `VideoStream`, `MetricsModal` 等依赖 hooks；共用状态 |
| C. 插件 & UI 扩展 | 支持隐藏/禁用某些模块、加载第三方插件、主题切换；新增 `/custom-metrics` 等路由 | 配置中 `features.*` 控制 UI；提供 `webPlugins` 接口 |
| D. 测试与构建 | 补充 Vitest/Playwright 测试、ESLint/Prettier 配置，并在 CI 执行；文档说明 docker 集成与本地运行 | `npm run test`/`lint`/`build:static` 在 CI 通过；README 更新 |

（对应的 Roadmap 详见 `WEBAPP_FRONTEND_ROADMAP.md`）

## 7. 风险
- **API 变更同步**：前端重构需配合后端服务层调整（尤其是 WebRTC/monitor）。Mitigation：在 Phase A 保持旧 API；Phase B 逐步切换。
- **打包体积**：引入 React Query/图表可能扩大 bundle，需通过动态 import、懒加载优化。
- **静态导出**：部分实时功能（例如 WebRTC）依赖浏览器 API，但 Next 静态导出与 SPA 模式兼容；需确保 `npm run build:static` 仍能生成 `out/`。

## 8. 结论
通过上述架构调整，前端将从“单页面+散装组件”转变为“配置驱动 + Feature 模块化 + 可测试”的开源 Dashboard。它与后端 `WebAppConfig`、CLI、插件体系配合，便于社区扩展和维护。🥥
