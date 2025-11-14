# Phase 1 – Runtime Initialization & Patch Modularization Guideline

本阶段目标：将当前 import 副作用式的 patch 机制改造为可配置、可组合的 runtime 初始化流程，为后续多芯片 adapter/插件化奠定基础。

---

## 1. Phase 1 目标
1. **显式入口**：提供 `coral_inference.runtime.init(config)`（名称可调整），由调用方决定何时加载 patch。
2. **RuntimeContext**：初始化后返回上下文对象，暴露当前启用的后端、补丁、版本信息。
3. **Feature Flag 管控**：能够按需启用/禁用特定补丁（如 stream manager、WebRTC、录像/指标、plugins），默认行为等同当前版本。
4. **兼容旧入口**：`import coral_inference` 仍可触发旧逻辑，但会发出 deprecation 提示，未来逐步迁移到显式初始化。

---

## 2. 核心设计建议

### 2.1 模块结构
```
coral_inference/
  runtime/
    __init__.py        # init() 暴露入口
    context.py         # RuntimeContext 定义
    config.py          # 配置解析（env / dict / dataclass）
    patches/
      __init__.py      # register/enable helpers
      stream_manager.py
      camera.py
      sinks.py
      plugins.py
      ...
```

### 2.2 Config & Context
- `RuntimeConfig` 字段示例：
  - `platform: Optional[str]`（rknn/onnx/auto）
  - `enable_stream_manager_patch: bool`
  - `enable_webrtc: bool`
  - `enable_video_sink: bool`
  - `enable_metric_sink: bool`
  - `load_workflow_plugins: bool`
  - `extra_patches: List[str]`（预留）
- `RuntimeContext` 提供：
  - `platform`（最终判定值）
  - `patches_enabled`（列表或映射）
  - `version_info`（`inference` 版本等）
  - `logger` / `config` 引用

### 2.3 初始化流程
1. 解析传入配置或环境变量 -> `RuntimeConfig`。
2. 调用 `get_runtime_platform()`（或等价逻辑）决定运行时后端。
3. 根据配置依次启用 patch 模块，每个模块暴露 `enable(context)` / `disable(context)`。
4. 记录启用状态，返回 `RuntimeContext`。

### 2.4 向后兼容策略
- `coral_inference/__init__.py` 在 import 时检测 `CI_RUNTIME_AUTOINIT`（默认 True），若开启自动调用 `runtime.init(DefaultConfig)`。
- 打印一次性的 warning，提示推荐显式调用 `runtime.init()`。

---

## 3. 任务拆解
1. **基础骨架**
   - [x] 创建 `coral_inference/runtime` 包，定义 `RuntimeConfig`、`RuntimeContext`。
   - [x] 实现 `init(config: RuntimeConfig | None) -> RuntimeContext`，包含平台检测与 patch 调度。
2. **Patch & Backend 模块化**
   - [x] 将 `core/__init__.py` 中的 patch 逻辑拆分为独立函数（camera/stream/sinks/plugins 等）。
   - [x] 新增 `runtime.backends` 注册机制，默认提供 RKNN/ONNX adapter，后续芯片可通过 `register_adapter` 扩展。
   - [x] 在 runtime init 中按 Flag 调用这些函数并记录启用的 patch / backend。
3. **默认行为兼容**
   - [x] `coral_inference/__init__.py` 中保留原有导入，但若检测到未显式初始化，则调用 `runtime.init()` 并记录 context。
   - [x] 提供 `runtime.get_current_context()` 便于调试/测试（并新增 `reset_runtime()` 供测试使用）。
4. **配置解析**
   - [x] 通过 `RuntimeConfig` Dataclass 支持自定义 flag，README 中给出 `init` 调用示例；后续可扩展 env/YAML 解析。
5. **测试**
   - [x] 编写 `tests/test_runtime_init.py`，覆盖默认与禁用场景；`tests/smoke` 全量运行验证 auto-init 行为。
6. **文档与示例**
   - [x] 更新 README 增加 runtime 初始化与 backend 扩展章节；架构/phase 文档保持同步。

---

## 4. 时间预估 & 依赖
- Phase 1 总计预估 1-2 周（含设计验证、代码重构、测试与文档）。
- 建议先对 patch 逻辑做清单，确认每个 patch 对 `inference` 的依赖范围，避免拆分过程中遗漏。
- 若某些 patch 难以模块化，可先保持在一个 “legacy” 模块内，通过 flag 控制整体启用，后续 Phase 2 再细化。

---

## 5. 验收标准
1. `runtime.init()` 可被示例脚本/测试调用，返回包含平台与 patch 信息的 context。
2. 不调用 `init()` 时，导入 `coral_inference` 仍能使用现有功能，但日志提示建议显式初始化。
3. smoke 测试可同时覆盖 auto-init 与手动 init 场景。
4. 文档说明清晰，开发者知道如何配置/扩展 patch。

---

## 6. 下一步
1. 评审本指南，补充缺失的配置项或 patch 列表。
2. 开始实现 `runtime` 包和 `RuntimeConfig`/`RuntimeContext`。
3. 按任务拆解逐项推进，优先完成最小可运行版本，再逐步迁移 patch。
