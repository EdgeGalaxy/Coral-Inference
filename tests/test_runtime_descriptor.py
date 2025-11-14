import pytest

from coral_inference.config import RuntimeDescriptor
from coral_inference.runtime.config import RuntimeConfig


def test_descriptor_from_env_and_to_runtime_config():
    env = {
        "CORAL_RUNTIME_PLATFORM": "custom",
        "CORAL_ENABLE_CAMERA": "0",
        "CORAL_ENABLE_WEBRTC": "false",
        "CORAL_ENABLE_BUFFER_SINK": "1",
        "CORAL_BACKEND_MODULES": "pkg.alpha,pkg.beta",
    }
    descriptor = RuntimeDescriptor.from_env(env)
    config = descriptor.to_runtime_config(RuntimeConfig())

    assert config.platform == "custom"
    assert config.enable_camera_patch is False
    assert config.enable_webrtc is False
    assert config.enable_buffer_sink_patch is True
    assert config.backend_entry_modules == ["pkg.alpha", "pkg.beta"]


def test_descriptor_merge_priority():
    base = RuntimeDescriptor.from_dict({"patches": {"camera": False}})
    env = RuntimeDescriptor.from_env(
        {"CORAL_ENABLE_CAMERA": "1", "CORAL_ENABLE_STREAM_MANAGER": "0"}
    )
    override = RuntimeDescriptor.from_overrides({"patches.camera": "false", "platform": "edge"})

    merged = RuntimeDescriptor.merge_many([base, env, override])
    config = merged.to_runtime_config(RuntimeConfig())

    assert config.platform == "edge"
    assert config.enable_camera_patch is False  # override takes precedence
    assert config.enable_stream_manager_patch is False  # env applied


def test_descriptor_from_file_yaml(tmp_path):
    pytest.importorskip("yaml")
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text(
        """
platform: "demo"
patches:
  camera: false
  buffer_sink: true
backends:
  auto_discover: false
  modules:
    - sample.module
services:
  webrtc:
    stun_servers:
      - "stun:demo"
"""
    )

    descriptor = RuntimeDescriptor.from_file(str(config_path))
    config = descriptor.to_runtime_config(RuntimeConfig())

    assert config.platform == "demo"
    assert config.enable_camera_patch is False
    assert config.enable_buffer_sink_patch is True
    assert config.auto_discover_backends is False
    assert config.backend_entry_modules == ["sample.module"]
    assert config.services["webrtc"]["stun_servers"][0] == "stun:demo"
