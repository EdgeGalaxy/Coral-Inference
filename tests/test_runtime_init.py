import importlib

from coral_inference.runtime import (
    RuntimeConfig,
    init as runtime_init,
    reset_runtime,
)
from coral_inference.runtime import patches, backends, plugins as runtime_plugins
from coral_inference.runtime.backends import BackendAdapter


def _capture(monkeypatch, name, result=True):
    called = []

    def marker(*args, **kwargs):  # noqa: ANN001
        called.append((name, args, kwargs))
        return result

    monkeypatch.setattr(patches, name, marker)
    return called


def test_runtime_init_default_calls_all_patches(monkeypatch):
    reset_runtime()
    cam_calls = _capture(monkeypatch, "enable_camera_patch")
    buffer_calls = _capture(monkeypatch, "enable_buffer_sink_patch")
    video_calls = _capture(monkeypatch, "enable_video_sink_patch")
    metric_calls = _capture(monkeypatch, "enable_metric_sink_patch")
    stream_calls = _capture(monkeypatch, "enable_stream_manager_patch")
    webrtc_calls = _capture(monkeypatch, "enable_webrtc_patch")
    plugin_calls = _capture(monkeypatch, "enable_plugins_patch")
    backend_calls = []

    monkeypatch.setattr(
        backends,
        "activate_backends",
        lambda platform, config: backend_calls.append(platform) or ["dummy_backend"],
    )

    monkeypatch.setattr(
        runtime_plugins,
        "load_runtime_plugins",
        lambda config, inference_version=None: {"patches:demo": True},
    )

    ctx = runtime_init(RuntimeConfig(auto_patch_rknn=True))

    assert (
        cam_calls
        and buffer_calls
        and video_calls
        and metric_calls
        and stream_calls
        and webrtc_calls
        and plugin_calls
    )
    assert ctx.enabled(patches.PATCH_CAMERA)
    assert ctx.enabled(patches.PATCH_BUFFER_SINK)
    assert ctx.enabled(patches.PATCH_VIDEO_SINK)
    assert ctx.enabled(patches.PATCH_METRIC_SINK)
    assert ctx.enabled(patches.PATCH_STREAM_MANAGER)
    assert ctx.enabled(patches.PATCH_WEBRTC)
    assert ctx.enabled(patches.PATCH_PLUGINS)
    assert ctx.state.backends_enabled == ["dummy_backend"]
    assert ctx.state.plugins_loaded == {"patches:demo": True}
    assert backend_calls == ["onnx"]


def test_runtime_init_respects_disabled_flags(monkeypatch):
    reset_runtime()
    cam_calls = _capture(monkeypatch, "enable_camera_patch")
    buffer_calls = _capture(monkeypatch, "enable_buffer_sink_patch")
    backend_calls = []
    monkeypatch.setattr(
        backends, "activate_backends", lambda platform, config: backend_calls
    )
    plugin_calls = []

    def fake_load_plugins(config, inference_version=None):  # noqa: ANN001
        plugin_calls.append(1)
        return {"patches:demo": True}

    monkeypatch.setattr(runtime_plugins, "load_runtime_plugins", fake_load_plugins)

    ctx = runtime_init(
        RuntimeConfig(
            enable_camera_patch=False,
            enable_sink_patch=False,
            enable_buffer_sink_patch=False,
            enable_metric_sink_patch=False,
            enable_video_sink_patch=False,
            auto_patch_rknn=False,
            enable_webrtc=False,
            enable_stream_manager_patch=False,
            enable_plugins=False,
        )
    )

    assert not cam_calls
    assert not buffer_calls
    assert not ctx.enabled(patches.PATCH_CAMERA)
    assert not ctx.enabled(patches.PATCH_BUFFER_SINK)
    assert not ctx.enabled(patches.PATCH_METRIC_SINK)
    assert not ctx.enabled(patches.PATCH_VIDEO_SINK)
    assert not ctx.enabled(patches.PATCH_WEBRTC)
    assert not ctx.enabled(patches.PATCH_STREAM_MANAGER)
    assert not ctx.enabled(patches.PATCH_PLUGINS)
    assert ctx.state.backends_enabled == []
    assert ctx.state.plugins_loaded == {}
    assert not plugin_calls


def test_runtime_config_from_env_parses_values():
    env = {
        "CORAL_RUNTIME_PLATFORM": "custom",
        "CORAL_ENABLE_CAMERA": "0",
        "CORAL_ENABLE_STREAM_MANAGER": "false",
        "CORAL_ENABLE_SINK": "no",
        "CORAL_ENABLE_WEBRTC": "off",
        "CORAL_ENABLE_PLUGINS": "false",
        "CORAL_ENABLE_BUFFER_SINK": "0",
        "CORAL_ENABLE_METRIC_SINK": "0",
        "CORAL_ENABLE_VIDEO_SINK": "0",
        "CORAL_AUTO_PATCH_RKNN": "0",
        "CORAL_AUTO_DISCOVER_BACKENDS": "0",
        "CORAL_BACKEND_MODULES": "pkg.a,pkg.b",
    }

    config = RuntimeConfig.from_env(env)
    assert config.platform == "custom"
    assert not config.enable_camera_patch
    assert not config.enable_stream_manager_patch
    assert not config.enable_sink_patch
    assert not config.enable_webrtc
    assert not config.enable_plugins
    assert not config.enable_buffer_sink_patch
    assert not config.enable_metric_sink_patch
    assert not config.enable_video_sink_patch
    assert not config.auto_patch_rknn
    assert not config.auto_discover_backends
    assert config.backend_entry_modules == ["pkg.a", "pkg.b"]


def test_discover_entry_point_adapters(monkeypatch):
    reset_runtime()

    class DummyEntryPoint:
        def __init__(self, name, value):
            self.name = name
            self.group = "coral_inference.backends"
            self._value = value

        def load(self):
            return self._value

    class DummyEntryPoints:
        def __init__(self, items):
            self._items = items

        def select(self, group):
            return [item for item in self._items if item.group == group]

    adapter = BackendAdapter(
        name="dummy_backend",
        supports=lambda platform, config: True,
        activate=lambda platform, config: True,
    )

    monkeypatch.setattr(
        backends.metadata,
        "entry_points",
        lambda: DummyEntryPoints([DummyEntryPoint("dummy_backend", adapter)]),
    )

    loaded = backends.discover_entry_point_adapters()
    assert loaded == ["dummy_backend"]
    assert "dummy_backend" in backends.activate_backends(
        platform="any", config=RuntimeConfig(auto_discover_backends=False)
    )

    importlib.reload(backends)


def test_import_backend_modules(monkeypatch):
    calls = []

    def fake_import(name):
        calls.append(name)
        return None

    monkeypatch.setattr(backends, "import_module", fake_import)
    modules = backends.import_backend_modules(["pkg.alpha", "pkg.beta"])
    assert modules == ["pkg.alpha", "pkg.beta"]
    assert calls == ["pkg.alpha", "pkg.beta"]
