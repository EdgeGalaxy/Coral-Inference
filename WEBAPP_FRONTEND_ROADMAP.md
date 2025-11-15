# Coral WebApp（Next.js Dashboard）Roadmap

> 目标：按照开源项目标准，逐步将 `docker/config/inference/landing/` 重构为配置驱动、模块化、可测试的前端。完成每一阶段后，请在“状态”列标记 ✅ 并附一句总结。

| 阶段 | 状态 | 目标 | 核心任务 | 交付 / 成功标准 |
| --- | --- | --- | --- | --- |
| **Phase A – 基础设施 & 配置** | 🟡 ConfigProvider + QueryProvider + `/config.json` 已落地 | 建立统一配置入口、HTTP 客户端和状态管理 Provider，确保页面能消费 `/config.json` | 1. `ConfigProvider` + `apiClient` + React Query Provider <br> 2. 在构建/部署时生成 `config.json`（来源于后端 WebAppConfig） <br> 3. 现有页面迁移到 hooks（读取配置、API base） <br> 4. 新增 lint/formatter 基线 | - `ConfigProvider` 自动注入 `NEXT_PUBLIC_CoralConfig` 或 `/config.json` <br> - `npm run dev/build:static` 无兼容回归 <br> - 代码通过 `npm run lint` |
| **Phase B – Feature 模块化** | ⬜ | 拆分 pipelines/streams/monitoring 等域模块，复用 hooks + service，改进错误/loading/空态 | 1. 设计 `features/*` 文件夹，分别实现 API/Hooks/组件 <br> 2. `PipelineSelector`/`VideoStream`/`MetricsModal` 等依赖 hooks <br> 3. 统一 Toast/对话框/Loading Skeleton <br> 4. 在 React Query 中处理轮询/缓存 | - 主页面组装来自 `features/*` <br> - 共享 `usePipelineActions` 等 hooks <br> - Storybook 或单测覆盖核心组件（可选） |
| **Phase C – 插件/主题/可配置 UI** | ⬜ | 支持 feature flag、主题切换、自定义入口；准备前端插件接口 | 1. `featuresConfig`（来自 WebAppConfig）控制模块显示/顺序 <br> 2. 主题系统（深浅色、品牌色）+ Layout <br> 3. 针对 Web 插件预留占位（动态 import/iframe） <br> 4. 新增 `/custom-metrics` 等页面并提取路由常量 | - Config 控制下可以禁用录像/metrics <br> - 主题切换/品牌名称来自配置 <br> - 插件示例文档（与后端 Web 插件相呼应） |
| **Phase D – 测试 & CI 集成** | ⬜ | 引入单测/e2e、CI 构建规范，与后端流水线集成 | 1. Vitest + RTL 组件测试；Playwright 覆盖关键流程 <br> 2. `npm run test`、`npm run lint`、`npm run build:static` 纳入 CI job <br> 3. 更新 README/CONTRIBUTING，说明如何开发/发布 Dashboard <br> 4. 构建产物与 Docker 镜像对齐（自动复制至 `out/`） | - CI 任务包含 lint/test/build <br> - 文档列出开发/部署步骤 <br> - `out/` 静态文件与新 WebAppConfig/CLI 对应 |

## 近期进展
- ConfigProvider 已可从 `/config.json` 注入 `WebAppConfig` 并写入 `window.__CORAL_CONFIG__`；React Query `QueryProvider` 在 `layout.tsx` 中包裹主树，`PipelineSelector` 使用 `usePipelinesWithStatus` Hook 以及 API base hook 获取共享状态。
- Lint baseline (`.eslintrc.json`) 与 `npm run lint` 通路建立，可在 Phase D 直接纳入 CI。
- 自定义指标页面迁移至 React Query hooks（含列表/图表/创建/删除），并由 `features.customMetrics` 控制显隐，保持与监控、录像等模块一致的配置驱动体验。

## 备注
- 若后续需新增阶段（例如“SSR/多租户支持”），可在表格末尾追加行。
- Roadmap 与 `WEBAPP_FRONTEND_PLAN.md` 对应：计划文档描述架构细节，Roadmap 追踪交付进度。
