from typing import Any

from coral_inference.runtime.contracts import MaterializedModelPackage, RuntimeModelBinding
from coral_inference.runtime.loaders import (
    load_coral_rknn_package,
    load_inference_models_package,
)


def load_runtime_binding(
    *,
    binding: RuntimeModelBinding,
    materialized_package: MaterializedModelPackage,
    **kwargs,
) -> Any:
    loader_type = materialized_package.loader_type
    if loader_type == "inference_models":
        return load_inference_models_package(
            package_dir=materialized_package.package_dir,
            **kwargs,
        )
    if loader_type == "coral_rknn":
        return load_coral_rknn_package(
            package_dir=materialized_package.package_dir,
            binding=binding,
            **kwargs,
        )
    raise ValueError(f"unsupported runtime loader type: {loader_type}")
