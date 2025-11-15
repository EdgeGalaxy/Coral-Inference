# Coral Inference

基于inferencek框架适配多个终端（jetson、rknn等）和云端设备的推理框架

## Runtime 初始化

默认导入 `coral_inference` 时会根据环境变量 `CI_RUNTIME_AUTOINIT`（默认 `1`）自动执行 runtime 初始化，完成摄像头、流管理、sink、插件、RKNN 等补丁加载。也可以显式配置：

```python
from coral_inference.runtime import RuntimeConfig, init

config = RuntimeConfig(enable_plugins=False, auto_patch_rknn=False)
context = init(config)
print(context.state.platform, context.state.patches_enabled)
```

将 `CI_RUNTIME_AUTOINIT=0` 写入环境变量即可禁用自动初始化，用于按需控制 patch 组合或自定义多芯片流程。

## 兼容层与 Patch 控制

`coral_inference.runtime.compat` 提供 `get_inference_version_tuple()`、`is_version_supported()` 与 `import_object()` 等辅助函数，用于在启用补丁前检测当前 `inference` 版本并提供友好日志。Runtime 会在 `RuntimeContext.log_messages` 中记录每个补丁的启用/禁用原因，方便在升级 `inference` 时快速检查哪些 patch 受版本影响被跳过。

### 自定义芯片后端

Runtime 暴露 `BackendAdapter` 注册机制，便于为新芯片实现专属初始化逻辑：

```python
from coral_inference.runtime.backends import BackendAdapter, register_adapter

def supports_my_chip(platform, config):
    return platform == "mychip"

def activate_my_chip(platform, config):
    # 注入自定义 session / patch
    return True

register_adapter(
    BackendAdapter(
        name="mychip",
        supports=supports_my_chip,
        activate=activate_my_chip,
    )
)
```

只要在调用 `runtime.init()` 前注册适配器，即可与现有 RKNN/ONNX adapter 并存。

### 环境变量配置

`RuntimeConfig.from_env()` 支持通过 `CORAL_` 前缀环境变量控制运行时行为，常用项包括：

- `CORAL_RUNTIME_PLATFORM`
- `CORAL_ENABLE_CAMERA`, `CORAL_ENABLE_STREAM_MANAGER`, `CORAL_ENABLE_SINK`, `CORAL_ENABLE_WEBRTC`, `CORAL_ENABLE_PLUGINS`
- `CORAL_ENABLE_BUFFER_SINK`, `CORAL_ENABLE_VIDEO_SINK`, `CORAL_ENABLE_METRIC_SINK`
- `CORAL_AUTO_PATCH_RKNN`, `CORAL_AUTO_DISCOVER_BACKENDS`
- `CORAL_BACKEND_MODULES`（逗号分隔的模块路径，在导入时注册 adapter）

未设置时均采用默认值（True），保持向后兼容。

### 配置文件与 CLI

Phase 4 引入了 `RuntimeDescriptor` 层，可通过 YAML/JSON/CLI 组合生成 `RuntimeConfig`。典型 YAML 示例如下：

```yaml
platform: "rknn"
patches:
  camera: false
  buffer_sink: true
backends:
  auto_discover: false
  modules:
    - "my_project.backends"
services:
  webrtc:
    stun_servers:
      - "stun:stun.l.google.com:19302"
```

使用 `coral-runtime` CLI 可以验证或应用配置：

```bash
# 校验配置（忽略当前环境变量）
coral-runtime config validate -c runtime.yaml --no-env

# 使用配置初始化 runtime，并输出启用的补丁/后端
coral-runtime init -c runtime.yaml --set patches.camera=true

# 查看通过 entry point 可发现的后端/patch/workflow 插件
coral-runtime plugins list
```

CLI 会输出 JSON，便于在部署脚本中消费或记录。`services` 区块用于集中声明 WebRTC/metrics 等外部依赖参数，运行后可通过 `RuntimeConfig.services` 访问（例如自定义插件根据 STUN/InfluxDB 地址做初始化）。

仓库提供了一个示例文件 `tests/fixtures/runtime_cli.yaml`，包含常见的 patch/backends 组合及外部服务占位配置，可直接用于 `coral-runtime init -c tests/fixtures/runtime_cli.yaml --no-env` 的 smoke 测试。

### 插件打包

通过 entry point 可以为 Coral Runtime 挂载自定义 patch/workflow 插件。插件应返回 `coral_inference.runtime.plugins.PluginSpec`，声明激活逻辑与版本要求，例如：

```python
# my_package/plugins.py
from coral_inference.runtime.plugins import PluginSpec

def register_camera_patch():
    def activate(config):
        # 在这里执行自定义 patch/注册逻辑
        return True

    return PluginSpec(
        name="my_camera_patch",
        activate=activate,
        description="Improve camera stability",
        min_core_version="0.0.3",
    )
```

在插件项目的 `pyproject.toml` 中注册 entry point：

```toml
[tool.poetry.plugins."coral_inference.patches"]
"my_camera_patch" = "my_package.plugins:register_camera_patch"

[tool.poetry.plugins."coral_inference.workflows"]
"my_visual_block" = "my_package.workflow_plugins:register_block"
```

当 `RuntimeConfig.enable_plugins=True` 时，Runtime 会发现并执行这些插件，执行结果记录在 `RuntimeContext.state.plugins_loaded` 以及 `coral-runtime init` 输出中。通过 `coral-runtime plugins list` 可查看当前环境可用的插件及其版本声明。

> 详细的插件发布流程与 checklist 见 `PLUGIN_PUBLISHING.md`。

## WebApp 重构进展

- `RuntimeDescriptor.services.webapp` 现可注入前端所需的 `WebAppConfig`。FastAPI 在 `docker/config/core/route.py` 中通过 `load_webapp_config` 聚合 descriptor/YAML/env 后，向 `/config.json` 以及 `app.state.webapp_config` 注入同一份配置，供 Next.js 仪表盘消费。
- `docker/config/inference/landing` 引入 `ConfigProvider`（负责加载 `/config.json` 并回填 `window.__CORAL_CONFIG__`）、`QueryProvider`（React Query）以及 `useApiBaseUrl`/`usePipelinesWithStatus` 等 hooks。`PipelineSelector` 已迁移到 React Query 数据流，并遵守 `WebAppConfig.features`。
- 若要在自定义 descriptor 中声明前端配置，可在 `services` 区域添加：
  ```yaml
  services:
    webapp:
      app:
        name: "Coral Runtime"
        tagline: "Realtime pipelines"
      api:
        baseUrl: "https://runtime.example.com"
      features:
        recordings:
          enabled: false
  ```
  完整 schema 见 `WEBAPP_CONFIG_CONTRACT.md`。
- CLI 已支持 `coral-runtime web serve -c examples/runtime_web.yaml --host 0.0.0.0 --port 9001`（可传 `--app MODULE:ATTR` 指向自定义 FastAPI ASGI 对象）。`examples/runtime_web.yaml` 展示了一个最小的 `services.webapp` 配置，便于 Docker/裸机部署直接引用。
- Docker 镜像中 `entrypoint.sh` 默认仍使用 legacy `uvicorn web:app`，可通过 `WEBAPP_START_MODE=cli` + `WEBAPP_DESCRIPTOR=/app/runtime_web.yaml` 切换至 CLI 模式：此时 supervisor 会执行 `coral-runtime web serve ...`，同时沿用 `HOST/PORT` 环境变量。若 descriptor 缺失脚本会直接报错，可自行挂载/生成。

后续阶段会继续根据 `WEBAPP_FRONTEND_ROADMAP.md` / `WEBAPP_ROADMAP.md` 推进插件入口、CLI 集成与 CI 验收，请在提交对应成果时同步更新两份表格的“状态”列。
