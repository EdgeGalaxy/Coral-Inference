# Phase 3 – Patch Modularization & Compatibility Layer

## 1. 目标概述
在 Phase 1/2 已完成 runtime 初始化与 backend 注册后，Phase 3 的重点是：
1. **兼容层 (`compat.py`)**：集中管理 `inference` 版本检测与公共符号导入，使补丁不直接引用深层模块。
2. **Patch 元数据**：为各 patch 模块声明支持的 `inference` 版本范围，初始化时如不满足条件给出警告或禁用。
3. **更细粒度的 Feature Flag**：拆分 sink/metrics/录像/WebRTC 等 patch，RuntimeConfig 可以按需启用/禁用。
4. **可观测性**：记录 patch 是否成功启用、若失败则附带原因，便于升级 `inference` 时快速定位问题。

## 2. 任务拆解

### 2.1 compat.py
- 实现函数：
  - `get_inference_version()`: 返回标准化的 semver tuple。
  - `import_path(path: str)`: 安全导入模块/符号，失败时抛出友好错误。
  - `is_version_supported(min_ver, max_ver)`：判断当前 `inference` 版本是否在补丁支持范围内。
- 将 runtime init 使用的 `inference` 版本获取逻辑迁入 compat。

### 2.2 Patch 元数据
- 在 `runtime/patches.py` 中为每个 patch 记录元数据（名称、描述、支持版本）。
- `enable_*` 函数在执行前先检查版本，若不满足则返回 False 并记录警告。
- RuntimeContext 的 `log_messages` 中加入 patch 启用结果。

### 2.3 Feature Flag 扩展
- 将当前 sink patch 拆分为 `buffer_sink`, `video_sink`, `metric_sink` 等 bool flag。
- RuntimeConfig 增加对应字段；`RuntimeConfig.from_env` 支持新的 env 名称。
- `runtime.init` 根据 flag 选择 patch，并在 `state.patches_enabled` 中记录更细粒度项。

### 2.4 文档与测试
- README/Phase 文档更新：
  - 说明 compat 层作用及 patch 版本失败时的日志。
  - 展示如何通过配置启用/禁用某个 patch。
- 新增单元测试：
  - `compat.get_inference_version` 的解析。
  - patch 版本校验通过/失败的行为。
  - RuntimeConfig 新 flag 的 env 解析。

## 3. 风险与缓解
- **版本解析错误**：需对非 semver 版本进行容错处理（fallback to string compare）。
- **Patch 依赖差异**：某些 patch 可能依赖可选模块，需要在 compat 中提供占位符或 graceful degradation。
- **配置膨胀**：新增 flag 需在 README 中明确，避免使用者困惑。

## 4. 下一步
1. 创建 `coral_inference/runtime/compat.py`，实现版本检测与 import 工具。
2. 拆分 `runtime/patches.py` 的 sink/webRTC 等子模块，并添加元数据与日志记录。
3. 更新 `RuntimeConfig`/env 解析及 README，补充测试，确保兼容层运作正常。

## 5. 交付结果
- `coral_inference/runtime/compat.py` 负责 `inference` 版本探测（优先读取模块 `__version__`，回退到 `importlib.metadata`），并提供 `import_object` 等工具；新增的 `tests/test_compat.py` 覆盖版本解析、范围校验与导入行为。
- `coral_inference/runtime/patches.py` 中的 Patch 元数据用于记录版本范围；Runtime 会在 `_apply_patch` 阶段把兼容性结果写入 `RuntimeContext.log_messages`，并在 `state.patches_enabled` 中记录精确的 patch 名称。
- RuntimeConfig/`init` 拆分 `buffer_sink`/`video_sink`/`metric_sink` 等开关，`CORAL_ENABLE_*` 环境变量与 README 文档同步更新。
- `tests/test_runtime_init.py` 覆盖新的 Feature Flag 行为，确保默认情况下三类 sink patch 均被调用；补充了兼容层单测以验证边界与回退逻辑。

> Phase 3 的核心工作（兼容层、Patch 元数据、细粒度配置与配套文档/测试）已全部落地，可继续推进 Phase 4 的配置系统与插件化迭代。
