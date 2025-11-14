# Phase 4 – Configuration System & Plugin Packaging

## 1. 背景
Phase 3 已经让 runtime patch/后端具备显式初始化与版本感知能力，但在真实部署中仍缺少一个统一的“配置面”来描述芯片、补丁组合、后端插件与周边服务（WebRTC/录像/指标等）的启用方式。当前主要依赖环境变量和硬编码入口，存在以下问题：

1. 部署脚本需要跨多个 env var 才能描述一次完整运行；无法直观表达复杂拓扑（例如多相机 + 多 sink）。
2. 尚未有 CLI/配置文件可以声明“加载哪些第三方插件、使用哪个配置模板”，不利于在多设备集群中复用。
3. Patch/Adapter 插件的发布流程缺乏约定：entry point 只覆盖了 backend adapter，sink/workflow 扩展仍需 import side-effect。

Phase 4 的目标是建设一个“可配置、可扩展、可校验”的配置系统，并完善插件打包约定，为 Phase 5 的多芯片扩展铺路。

## 2. 目标
- 提供 YAML/JSON/CLI 三层入口来生成 `RuntimeConfig`，并与现有 env var 解析互补，支持优先级合并。
- 定义“配置描述符（Descriptor）”：描述平台、补丁、后端、工作流插件、外部服务参数（WebRTC/录像/指标），并可序列化/反序列化。
- 设计插件打包规范：
  - Backend adapter 继续使用 `coral_inference.backends` entry point。
  - 新增 `coral_inference.patches` / `coral_inference.workflows` entry point 组，用于上游扩展。
  - 允许插件声明自身依赖的最低 `coral_inference`/`inference` 版本，运行时校验。
- 提供 CLI（例如 `coral-runtime apply -c config.yaml`）触发 runtime 初始化，输出 patch/插件/后端状态，便于调试与集成部署脚本。
- 增强可观测性：初始化完成后可导出一份配置摘要（JSON），展示启用的补丁、插件、适配器与版本信息。

## 3. 范围与拆解

### 3.1 配置加载层
1. **Schema**：定义 `RuntimeDescriptor` dataclass，字段涵盖：
   - `platform`, `patches`（bool map），`backends`（启用列表/禁用列表），`plugins`（workflow/sink/webrtc 等）。
   - 外部服务参数（WebRTC ICE 服务器、录像路径、指标写入地址等），聚合已有散落配置。
2. **来源合并**：
   - `RuntimeDescriptor.from_file(path)` 读取 YAML/JSON Schema 并做类型校验。
   - `RuntimeDescriptor.from_cli(args)` 解析命令行覆盖项。
   - `RuntimeDescriptor.from_env()` 延用现有 env 解析；合并顺序为 file < env < cli。
3. **转换**：提供 `RuntimeDescriptor.to_runtime_config()` -> `RuntimeConfig`，保持 runtime 代码最小改动。

### 3.2 CLI/工具
- 新增 `coral_inference.cli` 模块（点击/argparse），暴露指令：
  1. `coral-runtime config validate -c config.yaml`：校验 schema、打印结果。
  2. `coral-runtime init -c config.yaml [--set KEY=VALUE ...]`：加载配置并调用 `runtime.init()`，输出状态（平台、patch、backends、插件）。
  3. `coral-runtime plugins list`：列出通过 entry point 可发现的后端/patch/workflow 插件。
- CLI 输出 JSON 以便脚本消费，同时保留人类可读摘要。

### 3.3 插件打包规范
- 在 `pyproject.toml` 文档中新增示例 entry point 注册片段。
- `coral_inference.runtime.plugins` 模块负责：
  - `discover_plugins(group: str)`：扫描 entry points；按声明版本范围过滤。
  - `load_patch_plugins()` / `load_workflow_plugins()`：以与 backend 相同的日志结构记录启用结果。
- 插件 manifest 应能声明：
  - `name`, `type`（backend/patch/workflow），`min_core_version`, `min_inference_version`.
  - 可选的 `default_config_overrides`，用于自动补足配置。
- RuntimeContext 增加 `plugins_loaded: dict[str, bool]`。

### 3.4 验证与测试
- 单元测试覆盖：
  - Descriptor 的 schema 验证、merge 优先级、环境变量解析。
  - CLI 命令在 mock runtime 上运行，验证 JSON 输出。
  - 插件发现：通过伪 entry point 模拟版本不兼容/兼容等场景。
- Smoke/集成测试：在 CI 中运行 `coral-runtime init -c tests/fixtures/runtime_minimal.yaml`，验证 CLI 可调起 runtime。

## 4. 交付物
1. `coral_inference/config.py`（或新模块）中的 `RuntimeDescriptor` + merge 工具。
2. `coral_inference/cli` 命令集与 README 使用示例。
3. 新的 entry point 规范文档 + 示例插件（可选 stub）。
4. 扩展测试（unit + CLI smoke）。

## 5. 风险与缓解
- **配置复杂度**：Schema 设计需明确“必填/可选”，并提供默认模板；CLI 应提供 `config init` 生成示例。
- **插件兼容性**：需在 discovery 阶段严格校验版本，防止加载不兼容插件；日志中给出原因。
- **CLI 依赖冲突**：尽量使用 stdlib `argparse` 避免额外依赖；若需要 click，需评估包体积与依赖。
- **多入口同步**：Env/YAML/CLI 需共享同一解析逻辑，避免 drift。建议实现单一 `RuntimeDescriptor.merge` 函数。

## 6. 下一步
1. 设计 `RuntimeDescriptor` schema 与 merge 顺序，并在 `coral_inference/runtime/config.py` 内实现。
2. 草拟 `coral-runtime` CLI 入口（解析参数 + 调用 descriptor/RuntimeConfig），提供最小可行命令。
3. 扩展插件 discovery API 覆盖 patch/workflow，定义 entry point 规范及元数据结构。
4. 编写 README/Phase 文档示例与测试，确保配置文件 + CLI 用例均在 CI 覆盖。

## 7. 当前进展
- ✅ `RuntimeDescriptor` + CLI：YAML/JSON/Env/CLI 合并流程与 `coral-runtime` 命令集已落地，README 提供示例。
- ✅ 插件入口：`coral_inference.runtime.plugins.PluginSpec` 定义了最小版本要求与激活回调，Runtime 会在 `enable_plugins=True` 时加载 entry point 并记录 `plugins_loaded` 状态，CLI `plugins list` 输出详细元数据。
- ✅ 示例与测试：新增 `tests/fixtures/runtime_cli.yaml` / `tests/smoke/test_cli_runtime.py`，覆盖实际配置文件 + CLI `init` smoke；插件加载单测覆盖版本兼容、失败路径。`pytest tests/smoke/test_cli_runtime.py` 已纳入默认测试集。
- ✅ 发布指南：`PLUGIN_PUBLISHING.md` 描述第三方插件的 entry point 注册、验证与发布 checklist。
- 🔄 待办：将 CLI smoke 纳入 CI workflow，并扩展示例配置以覆盖更复杂的服务参数映射（metrics/webrtc 字段的实际消费逻辑）。
