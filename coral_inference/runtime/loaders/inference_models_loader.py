from typing import Any

from inference_models import AutoModel


def load_inference_models_package(
    *,
    package_dir: str,
    **kwargs,
) -> Any:
    return AutoModel.from_pretrained(
        package_dir,
        allow_local_code_packages=False,
        **kwargs,
    )
