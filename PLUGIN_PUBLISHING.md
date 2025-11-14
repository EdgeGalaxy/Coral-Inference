# Coral Runtime 插件发布指南

Coral Runtime 通过 entry point 扩展 patch/workflow 能力。插件只需实现 `PluginSpec` 并在 `pyproject.toml` 中声明，即可被 `coral-runtime init` 自动发现与执行。本指南给出发布流程与验证步骤。

## 1. 准备插件模块

```python
# my_package/coral_plugins.py
from coral_inference.runtime.plugins import PluginSpec

def register_camera_stabilizer():
    def activate(config):
        # 执行依赖导入、打补丁或注册 Workflow block 等
        return True  # True 表示加载成功，可用于 health 检查

    return PluginSpec(
        name="camera_stabilizer",
        activate=activate,
        description="Improve camera stream stability",
        min_core_version="0.0.4",
        min_inference_version="0.9.0",
    )
```

> `activate(config)` 可根据 `RuntimeConfig` 做条件判断（例如仅在某些平台启用）。若出现异常，请抛出或返回 False，Runtime 会在日志中记录失败原因。

## 2. 注册 entry point

在插件项目 `pyproject.toml` 中声明：

```toml
[tool.poetry.plugins."coral_inference.patches"]
"camera_stabilizer" = "my_package.coral_plugins:register_camera_stabilizer"

[tool.poetry.plugins."coral_inference.workflows"]
"custom_block" = "my_package.workflow_plugins:register_block"
```

命名空间说明：

| Group                         | 作用              |
|------------------------------|-------------------|
| `coral_inference.backends`   | 芯片 BackendAdapter（Phase 2 已存在） |
| `coral_inference.patches`    | Runtime 补丁 / Sink / WebRTC 扩展 |
| `coral_inference.workflows`  | Workflow block / pipeline 扩展 |

## 3. 验证与调试

1. 本地安装你的插件（`pip install -e .`）。
2. 使用 `coral-runtime plugins list` 查看是否被发现，输出会包含 entry point、元数据与版本要求。

```bash
coral-runtime plugins list --group patches
```

3. 运行 `coral-runtime init --set patches.<name>=true`（若需要覆盖 descriptor），并查看输出 JSON 中的 `state.plugins_loaded`。
4. 若插件有依赖版本要求，可通过 `PluginSpec` 的 `min_core_version`、`min_inference_version` 提前阻止不兼容环境；Runtime 会记录警告。

## 4. 发布 checklist

- [ ] `PluginSpec` 返回 `True/False` 反映启用状态，避免静默失败。
- [ ] README/CHANGELOG 中说明需要的环境变量或额外配置。
- [ ] 提供最小示例配置（YAML）给用户，可配合 `coral-runtime config validate` 验证。
- [ ] 在 CI 或 release 流程中运行 `coral-runtime plugins list` / `coral-runtime init` smoke，确保 entry point 可被解析。

遵循以上流程即可与 Coral Runtime Phase 4 配置/插件体系兼容。更多示例可参考 `README.md` 的“插件打包”章节以及 `tests/fixtures/runtime_cli.yaml` 中的配置示例。
