# Coral WebApp/服务平面重构方案

## 1. 背景
目前 `docker/config` 目录中承载了 FastAPI Web 服务、Pipeline/Stream/Monitor 路由、自定义静态资源以及 supervisor/health check 脚本。随着 Phase 4 构建新的配置/插件体系，该 Web 平面存在以下问题：

- **配置割裂**：仅靠环境变量描述复杂行为（WebRTC ICE、监控、录像存储等），无法沿用 `RuntimeDescriptor`/CLI 的配置能力，也缺少类型校验。
- **耦合严重**：路由函数直接操控 SQLite、文件系统、StreamManagerClient；没有 service 层，无法单测或替换实现。
- **可观测/运维弱**：没有标准 `/healthz`；health check 通过 supervisorctl 重启；监控只支持 InfluxDB 且逻辑散落。
- **扩展困难**：无法通过插件挂载自定义 UI/路由，也没有 CLI 启动入口，Docker 与其他部署方式高度耦合。

目标是建设一个可复用的 `coral_inference.webapp` 子系统，统一配置、服务职责与插件化能力，为 Docker 镜像和社区部署提供一致体验。

## 2. 目标架构

### 2.1 组件
1. **WebAppConfig**：由 `RuntimeDescriptor.services`/CLI 生成，包含：
   - `http`: host/port/workers、CORS、静态资源 mount。
   - `pipelines`: cache 路径、自动恢复、下载/存储策略。
   - `streams`: WebRTC ICE servers、摄像头参数、抓帧超时。
   - `monitoring`: enable 标志、poll/flush 间隔、Influx/Prometheus 目标、磁盘配额。
   - `health`: liveness/readiness 设置、外部健康探针。
2. **Service Layer**
   - `PipelineService`：封装 PipelineCache、视频下载、恢复/终止；暴露 async API 供路由调用。
   - `StreamService`：管理 WebRTC/摄像头/session 池；可切换底层实现。
   - `MonitorService`：统一后台任务（metrics 采集、磁盘清理），可插入不同 Sink（Influx/Prometheus/Stdout）。
   - `HealthService`：健康状态汇总，供 `/healthz` `/readyz` `/metrics`。
3. **FastAPI 组装**
   - 入口函数 `create_web_app(config: WebAppConfig)` 注册所有路由，中间件、静态资源、插件注册点。
   - 前端 UI mount 通过可选插件（内置 inference landing、纯 API、第三方 SPA）。
4. **CLI + Docker**
   - 新增 `coral-runtime web serve -c config.yaml [--set KEY=VALUE]`，封装 uvicorn 启动。
   - Docker entrypoint 调用 CLI，允许用户用挂载的 YAML/环境变量配置 Web 服务。
5. **插件扩展**
   - 定义 `coral_inference.web_plugins` entry point：插件可注册路由、依赖或静态资源。
   - RuntimeContext 中记录已注册的 Web 插件，CLI `plugins list` 输出。

## 3. 实施阶段与细节

### Phase A：配置与 CLI 融合
**目标**：让 Web 服务读取 `RuntimeDescriptor`/`WebAppConfig`，并提供「配置→RuntimeConfig→Web 服务」的 CLI 流程。

**任务**：
1. `coral_inference/config.py`
   - 扩展 `services` schema：新增 `http`, `pipelines`, `streams`, `monitoring`, `health` 字段及默认值。
   - 增加 `WebAppConfig` dataclass + `from_descriptor`.
2. `coral_inference/cli/main.py`
   - 加入 `web serve` 子命令：加载 descriptor，构造 `RuntimeConfig` + `WebAppConfig`，调用 `create_web_app`.
3. `docker/config/entrypoint.sh`
   - 精简为 `coral-runtime web serve -c /app/config/runtime.yaml --set ...`（保留 supervisor 作为可选模式，但默认 CLI）。
4. 新增示例配置 `examples/runtime_web.yaml` 并更新 README/Phase 文档。

**验收**：`coral-runtime web serve -c tests/fixtures/runtime_cli.yaml --no-env` 可以启动（集成测试可通过 uvicorn TestClient 快速验证）。

### Phase B：服务层重构
**目标**：将 pipeline/stream/monitor 逻辑抽象成 service，并在路由层解耦。

**任务**：
1. `coral_inference/webapp/services/pipeline.py`
   - 封装 SQLite 交互，切换到 `aiosqlite` 或线程池。
   - 提供 `initialise`, `list`, `status`, `terminate`, `consume` 等 async 方法。
   - 视频下载放入 service（支持并发/重试/超时配置）。
2. `coral_inference/webapp/routes/pipelines.py`
   - FastAPI 路由仅依赖 `PipelineService`（通过 `Depends` 注入）。
3. `StreamService`：管理 WebRTC offer、摄像头抓帧、录像访问；缓存 `PatchedCV2VideoFrameProducer`；支持从 `streams.webrtc.ice_servers` 获取 ICE 配置。
4. `MonitorService`：整合 `setup_optimized_monitor_with_influxdb`，抽象 `MetricsSink`（Influx/Prometheus/Stdout），background tasks 采用 `asyncio.create_task`，在 app shutdown 时统一关闭。
5. `HealthService` & `/healthz` `/readyz`
   - 汇总 pipeline cache 状态、monitor 后台任务状态、StreamService 状态，提供 JSON 响应；health checker & supervisor restart 移除。
6. 单元测试：分别 mock StreamManagerClient/视频下载/Influx sink，覆盖核心逻辑。

**验收**：新服务层 API 走通，旧路由逻辑迁移完毕；已有 smoke/单测通过。

### Phase C：插件化与 Docker 对齐
**目标**：开放 Web 插件与 UI 插件机制，更新 Docker 镜像/文档。

**任务**：
1. `web_plugins` entry point
   - 约定返回 `WebPluginSpec`（路由工厂、静态资源目录、依赖注入）。
   - CLI `plugins list` 展示 Web 插件；`RuntimeContext.state.plugins_loaded` 加入 web entries。
2. UI mount 策略
   - `WebAppConfig.ui.mode = "default|none|plugin"`；默认 mount inference landing，可通过配置关闭或挂载其他目录。
3. Dockerfile
   - 将 `docker/config` 逻辑迁移到新包；镜像只需复制 wheel + config + `examples/runtime_web.yaml`；entrypoint 调 CLI。
   - 说明如何用环境变量/卷挂载 YAML 控制 Web 服务；提供 health endpoint 供容器探针。
4. 文档
   - README 新增 “运行 Web 控制面” 章节，展示 CLI/Docker 指令。
   - `PLUGIN_PUBLISHING.md` 增加 Web 插件示例。
5. 端到端测试
   - 在 CI 添加 `pytest tests/webapp` + CLI smoke（TestClient 调路由）。
   - Docker build & basic run 指令示例（可选 GitHub Actions job）。

**验收**：`coral-runtime web serve` 正式替代 docker/config 网页；Docker 镜像/文档同步；插件机制可加载第三方 UI/路由。

## 4. 风险与缓解
- **迁移期间的兼容**：Phase A/B 中保留旧入口（通过 feature flag `WEBAPP_LEGACY_MODE`）；待新路径稳定后逐步淘汰。
- **性能回归**：`PipelineService` & MonitorService 改动较大，需要 profiling/metrics；提供开关 fallback。
- **部署差异**：CLI + YAML 对部分用户是新概念；文档给出 env→YAML 映射、常见模板（Docker Compose/裸机）；可提供 `config init` 命令生成默认文件。

## 5. 结论
通过以上阶段，将散落在 `docker/config` 的 Web 层重构为 `coral_inference.webapp`，不仅能与 Phase 4 配置/插件体系融合，也能让 Docker/裸机/K8s 部署共享同一入口，提高可维护性与扩展性。后续 Phase 5 接入新芯片时，只需在 descriptor 中声明服务参数即可，不再需要手写脚本或分支逻辑。
