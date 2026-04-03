import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from coral_inference.runtime.contracts import RuntimeModelBinding


@dataclass(frozen=True)
class CoralRKNNModelBundle:
    package_dir: str
    weights_path: str
    class_names: List[str]
    inference_config: Dict[str, Any]
    runtime_metadata: Dict[str, Any]
    binding: Optional[RuntimeModelBinding] = None


def _read_json_if_exists(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_class_names(path: Path) -> List[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_coral_rknn_package(
    *,
    package_dir: str,
    binding: Optional[RuntimeModelBinding] = None,
    **kwargs,
) -> CoralRKNNModelBundle:
    package_root = Path(package_dir)
    return CoralRKNNModelBundle(
        package_dir=package_dir,
        weights_path=str(package_root / "weights.rknn"),
        class_names=_read_class_names(package_root / "class_names.txt"),
        inference_config=_read_json_if_exists(package_root / "inference_config.json"),
        runtime_metadata=_read_json_if_exists(package_root / "runtime_metadata.json"),
        binding=binding,
    )
