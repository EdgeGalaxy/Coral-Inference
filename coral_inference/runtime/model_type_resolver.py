from typing import Any, Callable, Optional, Tuple

from inference.core.exceptions import ModelArtefactError

from coral_inference.runtime.compat import (
    get_runtime_model_binding,
    is_runtime_model_endpoint,
)
from coral_inference.runtime.contracts import RuntimeModelBinding
from coral_inference.runtime.capabilities import (
    resolve_runtime_binding_model_signature,
)


def resolve_runtime_endpoint_model_type(model_id: str) -> Optional[Tuple[str, str]]:
    if not is_runtime_model_endpoint(model_id):
        return None
    binding = get_runtime_model_binding(model_id)
    if not binding:
        raise ModelArtefactError(
            f"Could not resolve runtime binding for model endpoint {model_id}"
        )
    task_type, model_type = resolve_runtime_binding_model_signature(
        RuntimeModelBinding.model_validate(binding)
    )
    if not task_type or not model_type:
        raise ModelArtefactError(
            f"Runtime binding {model_id} does not expose enough metadata to resolve model type"
        )
    return str(task_type), str(model_type)


def extend_get_model_type(
    original_method: Callable[..., Tuple[str, str]],
) -> Callable[..., Tuple[str, str]]:
    def wrapper(
        model_id: str,
        api_key: Optional[str] = None,
        countinference: Optional[bool] = None,
        service_secret: Optional[str] = None,
    ) -> Tuple[str, str]:
        runtime_model_type = resolve_runtime_endpoint_model_type(model_id)
        if runtime_model_type is not None:
            return runtime_model_type
        return original_method(
            model_id,
            api_key=api_key,
            countinference=countinference,
            service_secret=service_secret,
        )

    return wrapper


def extend_access_check(
    original_method: Callable[..., bool],
) -> Callable[..., bool]:
    def wrapper(
        api_key: str,
        model_id: str,
        *args,
        **kwargs,
    ) -> bool:
        if is_runtime_model_endpoint(model_id):
            return get_runtime_model_binding(model_id) is not None
        return original_method(api_key, model_id, *args, **kwargs)

    return wrapper
