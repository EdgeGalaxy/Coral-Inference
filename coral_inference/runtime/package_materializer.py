from pathlib import Path, PurePosixPath
from typing import Callable, Dict

from coral_inference.runtime.contracts import (
    MaterializedModelPackage,
    RuntimeModelBinding,
    RuntimePackageFile,
)
from coral_inference.runtime.offline_package import write_model_config

FetchFileContent = Callable[[RuntimePackageFile], bytes]


def _resolve_target_path(package_dir: Path, file_handle: str) -> Path:
    relative_path = PurePosixPath(file_handle)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"unsafe package file handle: {file_handle}")
    return package_dir.joinpath(*relative_path.parts)


def materialize_model_binding(
    *,
    binding: RuntimeModelBinding,
    root_dir: str,
    fetch_file_content: FetchFileContent,
) -> MaterializedModelPackage:
    package_id = binding.selected_package_id or binding.model_id
    loader_type = binding.selected_loader_type or binding.binding_type
    package_dir = Path(root_dir) / package_id
    package_dir.mkdir(parents=True, exist_ok=True)

    file_paths: Dict[str, str] = {}
    for package_file in binding.package_files_snapshot:
        target_path = _resolve_target_path(package_dir, package_file.file_handle)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(fetch_file_content(package_file))
        file_paths[package_file.file_handle] = str(target_path)

    model_config_path = None
    if loader_type == "inference_models":
        model_config_path = write_model_config(
            package_dir=str(package_dir),
            binding=binding,
        )
        file_paths["model_config.json"] = model_config_path

    return MaterializedModelPackage(
        package_id=package_id,
        loader_type=loader_type,
        backend_type=binding.selected_backend,
        runtime_name=binding.selected_runtime,
        package_dir=str(package_dir),
        model_config_path=model_config_path,
        file_paths=file_paths,
    )
