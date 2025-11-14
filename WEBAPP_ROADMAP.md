# Coral WebApp 重构 Roadmap

> 目标：将现有 `docker/config` Web 服务迁移为模块化、可配置、可插件扩展的 `coral_inference.webapp`，同时兼容现有 Docker/部署方式。各阶段完成后请在“状态”列勾选 ✅ 并附简短说明。

| 阶段 | 状态 | 目标 | 核心任务 | 交付/参考 |
| --- | --- | --- | --- | --- |
| **Phase A – 配置 & CLI 融合** | ⬜ | 让 Web 服务复用 `RuntimeDescriptor`/CLI，将 YAML/Env 驱动的 `WebAppConfig` 与 `coral-runtime web serve` 建立起来 | 1. 扩展 `services.*` schema，定义 `WebAppConfig` <br> 2. 新增 `coral-runtime web serve` 命令 + TestClient smoke <br> 3. Docker entrypoint 支持 CLI（保留 legacy 模式） | - `WEBAPP_REFACTOR_PLAN.md` §3.1 <br> - 新示例 `examples/runtime_web.yaml` |
| **Phase B – 服务层重构** | ⬜ | 解耦 Pipeline/Stream/Monitor 逻辑，提供可测试的 Service 层与标准化健康接口 | 1. `PipelineService`/`StreamService`/`MonitorService` 提供 async API + 单测 <br> 2. FastAPI 路由仅通过依赖注入使用 service <br> 3. 引入 `HealthService` 与 `/healthz` `/readyz` endpoints，取代脚本轮询 | - 迁移后的 `coral_inference/webapp` 模块 <br> - 新增 service 测试套件 |
| **Phase C – 插件化 & Docker 对齐** | ⬜ | 开放 Web 插件、UI 插件，完善 Docker/文档/CI 流程 | 1. 定义 `web_plugins` entry point 与 `WebPluginSpec` <br> 2. CLI `plugins list` 展示 Web 插件；RuntimeContext 记录状态 <br> 3. Dockerfile/README 更新，健康检查使用 `/healthz` <br> 4. CI 加入 WebApp smoke（CLI + TestClient） | - 更新后的 Dockerfiles/entrypoint <br> - README/PLUGIN_PUBLISHING.md Web 章节 |

## 里程碑 & 验收
- **每阶段完成条件**：
  - 所有对应任务合并到主分支，并在上述表格中将“状态”改为 ✅，附一句总结（例如“✅ CLI 融合：新增 WebAppConfig + coral-runtime web serve”）。
  - README/相关 Phase 文档更新，列出成果与使用方式。
  - 必要的测试/CI（例如 CLI smoke）纳入默认测试流程。
- **阶段间依赖**：
  - Phase B 依赖 Phase A（新的配置入口准备就绪）。
  - Phase C 依赖前两阶段（服务层稳定后再开放插件/镜像）。

> 若出现新增需求（例：新的服务块、额外 Phase），请在表格后追加行并保持类似格式，确保后续“完成一个标记一个”。
