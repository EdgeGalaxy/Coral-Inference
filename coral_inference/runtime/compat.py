import importlib
import re
from importlib import metadata
from typing import Optional, Tuple, TypeVar

Version = Tuple[int, int, int]
_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")
T = TypeVar("T")


def _detect_inference_version() -> str:
    try:
        from inference import __version__ as version  # type: ignore

        return version
    except ImportError:  # pragma: no cover - handled via metadata fallback
        try:
            return metadata.version("inference")
        except metadata.PackageNotFoundError:  # pragma: no cover
            return "0.0.0"


inference_version = _detect_inference_version()


def get_inference_version_tuple() -> Version:
    match = _VERSION_PATTERN.match(inference_version)
    if not match:
        return (0, 0, 0)
    return tuple(int(group) for group in match.groups())  # type: ignore


def is_version_supported(min_version: Optional[Version] = None, max_version: Optional[Version] = None) -> bool:
    ver = get_inference_version_tuple()
    if min_version and ver < min_version:
        return False
    if max_version and ver > max_version:
        return False
    return True


def import_object(path: str) -> T:
    module_name, _, attr = path.partition(":")
    if not module_name:
        raise ValueError(f"Invalid import path: {path}")
    module = importlib.import_module(module_name)
    if attr:
        return getattr(module, attr)
    return module  # type: ignore


__all__ = [
    "get_inference_version_tuple",
    "is_version_supported",
    "import_object",
    "inference_version",
]
