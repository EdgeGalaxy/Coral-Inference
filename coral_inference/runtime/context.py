from dataclasses import dataclass, field
from typing import Dict, Optional

from .config import RuntimeConfig


@dataclass
class RuntimeState:
    platform: Optional[str] = None
    patches_enabled: Dict[str, bool] = field(default_factory=dict)
    backends_enabled: list[str] = field(default_factory=list)
    plugins_loaded: Dict[str, bool] = field(default_factory=dict)


@dataclass
class RuntimeContext:
    config: RuntimeConfig
    state: RuntimeState
    inference_version: str
    log_messages: list[str] = field(default_factory=list)

    def enabled(self, patch_name: str) -> bool:
        return self.state.patches_enabled.get(patch_name, False)
