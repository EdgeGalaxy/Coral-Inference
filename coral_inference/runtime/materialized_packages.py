import os
from pathlib import Path
from typing import Optional

import requests
from inference.core.env import MODEL_CACHE_DIR
from inference.core.exceptions import ModelArtefactError

from coral_inference.runtime.contracts import (
    MaterializedModelPackage,
    RuntimeModelBinding,
    RuntimePackageFile,
)
from coral_inference.runtime.package_materializer import materialize_model_binding


_RUNTIME_PACKAGE_CACHE_ROOT = os.path.join(MODEL_CACHE_DIR, "runtime_packages")


def _fetch_runtime_package_file_content(package_file: RuntimePackageFile) -> bytes:
    if not package_file.download_url:
        raise ModelArtefactError(
            "Runtime package file is missing download URL. "
            f"file_handle={package_file.file_handle} storage_key={package_file.storage_key}"
        )
    response = requests.get(package_file.download_url, timeout=120)
    response.raise_for_status()
    return response.content


def _materialized_package_is_complete(
    *,
    binding: RuntimeModelBinding,
    package_dir: Path,
) -> bool:
    for package_file in binding.package_files_snapshot:
        if not package_dir.joinpath(*Path(package_file.file_handle).parts).exists():
            return False
    if binding.selected_loader_type == "inference_models":
        return (package_dir / "model_config.json").exists()
    return True


def _build_existing_materialized_package(
    *,
    binding: RuntimeModelBinding,
    package_dir: Path,
) -> MaterializedModelPackage:
    file_paths = {
        package_file.file_handle: str(package_dir.joinpath(*Path(package_file.file_handle).parts))
        for package_file in binding.package_files_snapshot
    }
    model_config_path: Optional[str] = None
    if binding.selected_loader_type == "inference_models":
        model_config_path = str(package_dir / "model_config.json")
        file_paths["model_config.json"] = model_config_path
    return MaterializedModelPackage(
        package_id=binding.selected_package_id or binding.model_id,
        loader_type=binding.selected_loader_type or binding.binding_type,
        backend_type=binding.selected_backend,
        runtime_name=binding.selected_runtime,
        package_dir=str(package_dir),
        model_config_path=model_config_path,
        file_paths=file_paths,
    )


def ensure_runtime_package_materialized(
    *,
    binding: RuntimeModelBinding,
) -> MaterializedModelPackage:
    package_id = binding.selected_package_id or binding.model_id
    package_dir = Path(_RUNTIME_PACKAGE_CACHE_ROOT) / package_id
    if _materialized_package_is_complete(binding=binding, package_dir=package_dir):
        return _build_existing_materialized_package(
            binding=binding,
            package_dir=package_dir,
        )
    return materialize_model_binding(
        binding=binding,
        root_dir=_RUNTIME_PACKAGE_CACHE_ROOT,
        fetch_file_content=_fetch_runtime_package_file_content,
    )
