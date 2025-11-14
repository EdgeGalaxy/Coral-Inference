# Coral Inference – Architecture Refactor & Hardware Roadmap

## 1. 背景与目标
当前对 `inference` 包的适配依赖 import 级别的 monkey patch，并将 RKNN/Jetson、流管理、WebRTC、录像/指标等改动直接写入上游类中。这带来以下问题：

- 入口不可控：只要有人直接 `import inference` 而非 `coral_inference`，所有 patch 都失效。
- 多芯片扩展困难：`coral_inference/core/__init__.py` 存在大量硬编码逻辑；再加新芯片意味着继续叠加条件分支。
- 升级风险高：上游方法签名或模块路径变化会让 patch 静默失效，影响稳定性。
- 维护成本高：当前补丁跨越模型、流管理、WebRTC 等多个子系统，缺少统一抽象与开关。

目标是在不修改 `inference` 源码的前提下，完成如下能力建设：

1. 以显式初始化 + 后端注册表代替 import side effect，方便根据芯片选择不同适配层。
2. 将所有改动模块化为可组合补丁，并提供配置/Feature Flag 控制。
3. 构建版本兼容层与测试基线，确保可以持续升级 `inference`。
4. 形成清晰的迭代 roadmap，逐步引入更多芯片支持。

## 2. 设计原则
- **最小侵入**：不修改 `inference` 源码，仅通过公开 API 或包装层扩展。
- **显式初始化**：由调用方或 CLI 主进程调用入口函数触发 patch，避免 import 副作用。
- **插件化**：芯片适配、流管理补丁、Workflow 扩展都通过注册表或 entry point 加载。
- **可观测与可测试**：关键路径要有版本/依赖检测与自动化回归用例。

## 3. 目标架构概览

### 3.1 Runtime 初始化流程
```
main process ──▶ coral_inference.runtime.init(config)
                    ├─ 检测 inference 版本 / 环境
                    ├─ 注册模型后端 adapter
                    ├─ 启用所需 patch（流管理/WebRTC/sink）
                    └─ 返回 RuntimeContext（可供 pipeline 查询）
```

- `init(config)` 接受显式的 `platform=“rknn” | “triton” | …`、启用的补丁集合、插件列表等。
- 初始化完成后，通过 `RuntimeContext` 暴露查询接口，例如 `get_backend("vision")`、`is_patch_enabled("stream_manager")`。

### 3.2 Backend Adapter Registry
- 定义 `BackendAdapter` 协议，封装 `prepare_session`, `preprocess`, `list_artifacts`, `download_artifacts` 等方法。
- 以 `Registry.register("rknn", RknnAdapter)` 的形式注册；Runtime 根据配置或自动检测选择实例。
- 允许同进程注册多个 adapter；InferencePipeline 可通过上下文选择后端（便于未来并行支持）。

### 3.3 补丁模块与 Feature Flag
- 将现有补丁拆成独立模块（例如 `patches.stream_manager`, `patches.sinks`, `patches.camera`），每个模块暴露 `enable(context)` 与 `disable(context)`。
- Feature Flag 由配置文件或环境变量驱动，可按需启用 WebRTC、录像、InfluxDB 等扩展。
- 每个补丁模块需声明支持的 `inference` 版本范围，运行时做校验。

### 3.4 配置与插件加载
- 新增 `coral_inference/config.py`，解析 env / YAML / CLI 传入的配置。
- 使用 `importlib.metadata.entry_points(group="coral_inference.backends")` discover 外部芯片插件；默认内置 RKNN adapter，可后续下发 NPU、Ascend 等实现。
- Workflow blocks 的加载沿用 `WORKFLOWS_PLUGINS` 机制，但同样通过配置控制是否启用。

### 3.5 兼容性与测试
- 引入 `compat.py`，集中封装对 `inference` 版本的检测及常用对象导入，避免在 patch 中直接引用深层路径。
- 构建基础测试矩阵（至少包含：模型初始化、推理一次、WebRTC offer/answer、录像 sink enqueue、Metric sink 伪写入）。
- 在 CI 中对主要平台（ONNX fallback + RKNN）跑 smoke test，确保升级 `inference` 时能快速发现破坏性变更。

## 4. Roadmap（迭代计划）

| 阶段 | 状态 | 目标 | 关键交付 | 备注 |
| --- | --- | --- | --- | --- |
| Phase 0: Baseline | ✅ 完成 | 梳理现有 patch 与依赖，建立最小测试集 | - `PHASE0_BASELINE.md` 特性映射<br>- `tests/smoke/` 覆盖运行时/模型/流/录像/指标/WebRTC | 不改代码，先锁定行为 |
| Phase 1: 初始化层 | ✅ 完成 | 实现 `init(config)` 流程与版本检测 | - `coral_inference/runtime` 包<br>- Feature Flag + `RuntimeContext`<br>- README 初始化说明 (`PHASE1_RUNTIME_INIT.md`) | 保持旧入口兼容，自动/显式 init 可选 |
| Phase 2: Backend Registry | ✅ 完成 | 抽象 `BackendAdapter`，支持插件发现与 env 配置 | - `runtime.backends` 注册/entry point 机制<br>- `RuntimeConfig.from_env` + backend modules(`PHASE2_BACKEND_PLUGINS.md`)<br>- 单元/Smoke 测试覆盖 | RKNN/ONNX adapter 已迁移到注册表；支持外部扩展 |
| Phase 3: Patch 模块化 | ✅ 完成 | 将 stream manager / sinks / camera patch 改为独立模块 | - `patches.*` 模块 + 版本元数据<br>- `compat.py` 统一版本探测/导入<br>- 细粒度 sink Feature Flag + 测试 (`PHASE3_PATCH_COMPAT.md`) | Runtime 日志记录 patch 结果，可在 Phase 4 基础上继续扩展配置 |
| Phase 4: 插件化 & 配置系统 | ⏳ 进行中 | 支持外部芯片插件、集中配置 | - 配置加载器（YAML/CLI）<br>- Entry point 使用文档 (`PHASE4_CONFIG_SYSTEM.md`)<br>- CLI/Descriptor 合并策略 | 依赖 Phase 2/3 成果，已进入实现阶段 |
| Phase 5: 扩展芯片试点 | 🔜 规划中 | 在新框架下接入下一款芯片（示例：某 NPU） | - 新 adapter / 测试<br>- 文档 / 教程 | 验证框架可扩展性 |

## 5. 风险与缓解
- **兼容性回归**：阶段性重构需保持旧流程可选；在迁移完成前提供开关以便回退。
- **上游频繁变动**：通过 `compat.py` 和版本对齐策略减少大面积修改；必要时锁定兼容版本区间。
- **文档与培训**：重构后需要更新 README / Docker / 示例脚本，确保使用者知晓 `init()` 新入口。

## 6. 下一步
1. **Phase 4：配置系统 & CLI（进行中）**
   - 在 `PHASE4_CONFIG_SYSTEM.md` 规划基础上，实现 `RuntimeDescriptor` schema、YAML/CLI/env merge 以及导出 `RuntimeConfig`。
   - 构建 `coral-runtime` CLI：支持 `config validate`、`init`、`plugins list` 等命令，输出 patch/backends 状态。
   - 扩展插件发现 API（backend/patch/workflow entry points），并记录版本兼容性信息。
2. **配置与部署示例**
   - 提供 reference config（YAML）与 CLI 调用示例，纳入 README/文档。
   - 在 CI 增加 CLI smoke 测试，确保配置文件入口稳定。
3. **WebApp 重构 Roadmap**
   - 参考 `WEBAPP_REFACTOR_PLAN.md` 与 `WEBAPP_ROADMAP.md`，逐阶段替换 `docker/config` 中的 Web 平面实现。
4. **Phase 5 准备**
   - 在 Phase 4 完成后评估新芯片试点所需的额外接口（额外 adapter APIs、descriptor 字段等）。

> 当 Phase 3 核心任务完成并稳定后，再评估是否进入 Phase 4（更完善的配置系统）或 Phase 5（新芯片试点）。

> 此文档将作为后续重构的指导，后续阶段完成后需更新状态与经验总结。
