# Phase 2 – Backend Registry & Plugin Discovery Plan

## 1. 目标对齐
Roadmap 在 Phase 2 要求将芯片适配抽象为可注册的 `BackendAdapter`，支持：
- 在 runtime 初始化时决定启用哪些后端；
- 通过配置或外部插件扩展新芯片；
- 与现有 patch/Feature Flag 协同工作，保持可测试性。

在 Phase 1 我们已经引入 `coral_inference.runtime.backends` 并内置 RKNN/ONNX 适配器，但仍缺少：
1. **插件发现**：通过 entry points 或配置文件加载外部 adapter。
2. **配置入口**：支持从 environment/配置文件定义平台、启用的 patch、插件包等。
3. **可观测性**：记录哪些 adapter 被注册/启用，用于调试与诊断。

## 2. 计划拆解

### 2.1 Adapter 插件机制
- 使用 `importlib.metadata.entry_points(group="coral_inference.backends")` 自动发现第三方 adapter。
- Adapter 需要暴露 `BackendAdapter` 兼容实例；runtime 初始化时先加载本地注册，再加载 entry points。
- 提供 `register_backend_entry_module(path: str)` helper，以便通过配置直接导入指定模块。

### 2.2 RuntimeConfig 扩展
- 新增字段：
  - `platform_overrides`: Optional[str]
  - `backend_entry_points`: List[str]（额外模块路径）
  - `auto_discover_backends`: bool（默认 True）
- 添加 `RuntimeConfig.from_env(prefix="CORAL_")`，支持环境变量控制：
  - `CORAL_RUNTIME_PLATFORM`
  - `CORAL_ENABLE_STREAM_MANAGER`, `CORAL_ENABLE_WEBRTC` 等
  - `CORAL_BACKENDS=module_a,module_b`

### 2.3 初始化流程更新
- `runtime.init()`：
  1. 在加载默认 adapter 后，若 `auto_discover_backends` 为 True，遍历 entry points 注册。
  2. 对于 `backend_entry_points` 中的模块，import 后调用其中的 `register()` 或直接导入 adapter。
  3. 在 `RuntimeContext.log_messages` 中记录加载结果，并在 `state.backends_enabled` 中保存成功列表。

### 2.4 测试策略
- 新增单元测试覆盖：
  - `RuntimeConfig.from_env()` 的布尔/列表解析；
  - entry point discovery（使用 monkeypatch 注入假 entry point）；
  - `backend_entry_points` 导入失败/成功时的日志与状态。
- 扩展 smoke 测试，使之可以运行在显式 `RuntimeConfig` 下，并验证 `state.backends_enabled`。

### 2.5 文档更新
- README 增补 “通过 entry point 扩展芯片” 与 “环境变量配置” 部分。
- `ARCHITECTURE_ROADMAP.md` Section 6 更新为 Phase 2 进行中的任务，并记录完成情况。

## 3. 风险与缓解
- **Entry point 加载失败**：需要 try/except，记录 warning 但不中断其他 adapter。
- **配置冲突**：若配置禁用 auto-discover 但仍传入 `backend_entry_points`，以显式配置优先。
- **测试依赖**：entry point 相关测试需使用 monkeypatch 模拟 `importlib.metadata.entry_points`，避免真实依赖安装。

## 4. 下一步
1. 实现 `RuntimeConfig.from_env` 与新的配置字段。
2. 在 `runtime.backends` 中增加 entry point 发现与 reset helper。
3. 扩展 `runtime.init()` 调用流程、记录 log 消息，并更新单元/Smoke 测试。
4. 更新 README 与 roadmap 文档，说明新的扩展方式。
