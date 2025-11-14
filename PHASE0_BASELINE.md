# Phase 0 Baseline – Feature Inventory & Smoke Test Plan

本文用于 Phase 0（Baseline）工作，目标是在不改动现有逻辑的情况下：

1. 明确 Coral Inference 目前依赖的所有关键特性与入口；
2. 规划能够快速验证这些特性的 Smoke Test；
3. 制定下一步执行步骤，为 Phase 1 重构提供安全网。

---

## 1. 现有功能清单

| 领域 | 功能/模块 | 说明 | 关键文件 |
| --- | --- | --- | --- |
| Runtime 初始化 | `coral_inference/__init__.py` | 导入即触发 monkey patch，替换模型、摄像头、sink、流管理器、WebRTC 等逻辑。 | `coral_inference/__init__.py`, `coral_inference/core/__init__.py` |
| 硬件探测/后端 | `get_runtime_platform()` | 依据 `CURRENT_INFERENCE_PLATFORM` 或 `rknn-server` 存在与否选择 RKNN/ONNX。 | `coral_inference/core/models/utils.py` |
| RKNN 适配 | `RknnInferenceSession` + 一系列 `extend_*` hook | 替换 ONNX Session，加载 `.rknn` 模型、调整预处理/权重下载。 | `coral_inference/core/models/rknn_base.py`, `coral_inference/core/models/utils.py` |
| 摄像头输入 | `PatchedCV2VideoFrameProducer` | 根据平台决定是否使用 V4L2/YUYV，兼容 Jetson/RKNN。 | `coral_inference/core/inference/camera/patch_video_source.py` |
| InMemory Buffer Sink 扩展 | `_webrtc_buffer` | 在 sink 上挂载 `deque`，供 WebRTC/录像消费。 | `coral_inference/core/inference/stream/patch_sinks.py` |
| WebRTC | `WebRTCManager` + stream manager `_offer` patch | 提供 webrtc offer/answer、帧合成、AIORTC track 扩展。 | `coral_inference/core/inference/camera/webrtc_manager.py`, `coral_inference/core/inference/stream_manager/webrtc.py`, `coral_inference/core/inference/stream_manager/patch_pipeline_manager.py`, `patch_manager_client.py` |
| Stream Manager (稳健性) | Queue 超时、健康检查、终止流程补丁 | 替换 `app.handle_command`、`get_response_*`, `check_process_health`, `ensure_idle_pipelines_warmed_up` 等。 | `coral_inference/core/inference/stream_manager/patch_app.py` |
| 录像 Sink | `TimeBasedVideoSink` | 异步队列 + 分段写入 + FFmpeg 优化 + 磁盘配额。 | `coral_inference/core/inference/stream/video_sink.py` |
| 指标 Sink | `MetricSink` | 批量写入 InfluxDB 3，支持字段筛选。 | `coral_inference/core/inference/stream/metric_sink.py` |
| Workflow 插件 | Batch line counter & visualization | 通过 `WORKFLOWS_PLUGINS` 注册自定义 block，并包含 pytest 覆盖。 | `coral_inference/plugins/*`, `tests/plugins/*` |

---

## 2. Smoke Test 范围

目标：在本地/CI 通过最小化的依赖模拟核心路径，确保升级或重构后关键能力仍可运行。建议按以下分组：

### 2.1 Runtime & Backend
1. **Import/Init 检查**  
   - 场景：`import coral_inference` 之后，验证关键对象（`roboflow.get_from_url`、`CV2VideoFrameProducer`、`InMemoryBufferSink` 等）已被替换。  
   - 方法：使用 `inspect.getsource` 或对比函数引用，确保 patch 生效。
2. **平台探测**  
   - 场景：分别设置/不设置 `CURRENT_INFERENCE_PLATFORM`，mock `subprocess.check_output` 结果，验证 `get_runtime_platform()` 输出与日志。

### 2.2 模型加载 (ONNX vs RKNN)
1. **ONNX 回退**  
   - 利用假模型（或 mock `OnnxRoboflowInferenceModel`）调用 `initialize_model`，确认未启用 RKNN 时流程不变。
2. **RKNN Session**  
   - mock `rknnlite.api.RKNNLite`，确保 `RknnInferenceSession.run()` 能处理输入并返回列表；验证 `extend_preproc_image` 变换（transpose/scale）。

### 2.3 摄像头 & Sink
1. **Video Source**  
   - mock `cv2.VideoCapture`，给定 `/dev/video0` 或普通路径，确认选择的 backend（V4L2 vs 默认）。
2. **InMemoryBufferSink**  
   - 构建 sink，调用 `on_prediction`，验证 `_webrtc_buffer` 有入队。

### 2.4 WebRTC / Stream Manager
1. **WebRTC Buffer Path**  
   - 模拟 `webrtc_buffer` 中的预测 + 帧，确保 `WebRTCManager._process_video_frames` 能合成图像（可 mock `merge_frames`）。  
   - 使用 `aiortc` 的 dummy peer（或 mock）验证 `init_rtc_peer_connection` 可返回本地描述。
2. **Manager Commands**  
   - 对 `patch_pipeline_manager.offer`、`rewrite_handle_command` 等函数使用 fake queues，验证不同命令路径的响应/错误处理。
3. **Health Check/Termination**  
   - 通过 dummy `ManagedInferencePipeline` 触发 `patched_check_process_health` 的正/负路径，确保超时/终止逻辑可运行（可限制为单位测试层面，不启动真实子进程）。

### 2.5 录像/指标
1. **TimeBasedVideoSink**  
   - 使用随机 `numpy` 帧调用 `on_prediction`，等待 worker 处理后确认生成的分段文件或至少调用 `VideoWriter.write`（可 mock）。  
   - 验证磁盘配额与 FFmpeg 调用逻辑可以在 mock 下执行而不抛异常。
2. **MetricSink**  
   - mock `InfluxDBClient3`，确保 `on_prediction` -> `_process_batch_metrics` 会构建 `Point` 并调用 `write`；测试选定字段提取。

### 2.6 Workflow 插件
1. **Block 执行**  
   - 现有 `pytest` 覆盖即可：`test_batch_line_counter.py`, `test_batch_line_zone.py`。  
   - Smoke Test 只需确保插件可通过 `load_blocks()` 注册并运行一次示例数据。

> 备注：多数场景使用 mock/伪实现即可，无需真实硬件；优先保证能在 CI 上稳定运行。

---

## 3. 执行计划（Phase 0）

1. **基线验证**  
   - [x] 建立 `tests/smoke/` 目录并实现首批用例：运行时补丁（`test_runtime.py`）、RKNN Session 与预处理（`test_rknn_backend.py`）、录像 sink 队列（`test_sinks.py`）、WebRTC 缓冲处理（`test_webrtc.py`）、MetricSink 批量写入（`test_metrics.py`）、stream manager 补丁验证（`test_stream_manager.py`）、插件注册（`test_plugins.py`）。  
   - [ ] 引入 pytest marker（如 `@pytest.mark.smoke`）以便单独执行更大范围的基线。
2. **依赖与环境**  
   - [ ] 准备 mock 工具（`pytest-mock` 或内置 `unittest.mock`）。  
   - [ ] 评估对 `aiortc`, `InfluxDBClient3`, `cv2`, `rknnlite` 的可替代策略（必要时条件导入或 mock）。
3. **CI 集成**  
   - [ ] 在现有 CI（若有）或手动命令中增加 `pytest -m smoke`。  
   - [ ] 记录预期运行时间和依赖，确保开发者易于复现。

---

## 4. 下一步
1. 评审本清单，补充遗漏的功能或测试场景。  
2. 定义 Smoke Test 的代码结构（目录、命令、mock 策略）。  
3. 已实现首批用例（runtime/RKNN/sink/WebRTC/MetricSink），后续可继续补充 stream manager 及更多硬件场景。推荐命令：  
   ```bash
   pytest tests/smoke
   ```

如对某些场景存在依赖或实现难度，请在 Phase 0 中记录假设与阻塞，便于 Phase 1 评估是否需要额外改动。
