from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Mapping, Dict, Any

from coral_inference.config import RuntimeDescriptor

@dataclass
class RuntimeConfig:
    platform: Optional[str] = None
    enable_stream_manager_patch: bool = True
    enable_camera_patch: bool = True
    enable_sink_patch: bool = True
    enable_webrtc: bool = True
    enable_plugins: bool = True
    enable_buffer_sink_patch: bool = True
    enable_metric_sink_patch: bool = True
    enable_video_sink_patch: bool = True
    auto_patch_rknn: bool = True
    auto_discover_backends: bool = True
    backend_entry_modules: List[str] = field(default_factory=list)
    extra_patches: List[str] = field(default_factory=list)
    services: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(
        cls,
        env: Optional[Mapping[str, str]] = None,
        prefix: str = "CORAL_",
    ) -> "RuntimeConfig":
        descriptor = RuntimeDescriptor.from_env(env=env, prefix=prefix)
        return descriptor.to_runtime_config(cls())
