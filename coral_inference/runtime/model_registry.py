from typing import Any, Callable, Optional, Type

from inference.core.env import API_KEY
from inference.core.exceptions import ModelArtefactError

from coral_inference.runtime.compat import (
    get_runtime_model_binding,
    is_runtime_model_endpoint,
)
from coral_inference.runtime.capabilities import get_runtime_binding_support_issue
from coral_inference.runtime.contracts import RuntimeModelBinding


def resolve_runtime_model_adapter(model_id: str) -> Optional[Type]:
    if not is_runtime_model_endpoint(model_id):
        return None
    binding_payload = get_runtime_model_binding(model_id)
    if not binding_payload:
        raise ModelArtefactError(
            f"Could not resolve runtime binding for model endpoint {model_id}"
        )
    binding = RuntimeModelBinding.model_validate(binding_payload)
    support_issue = get_runtime_binding_support_issue(binding)
    if support_issue:
        raise ModelArtefactError(
            f"Runtime endpoint {model_id} is not supported by the current Coral runtime: "
            f"{support_issue}"
        )
    if binding.selected_loader_type == "inference_models":
        try:
            from coral_inference.runtime.adapters import (
                get_runtime_inference_models_adapter,
            )
        except ModuleNotFoundError as error:
            raise ModelArtefactError(
                "Runtime endpoint requires the inference_models stack, "
                "but inference_models is not installed in this Coral-Inference environment"
            ) from error

        return get_runtime_inference_models_adapter(
            model_id=model_id,
            binding=binding,
        )
    if binding.selected_loader_type == "coral_rknn":
        from coral_inference.runtime.rknn_adapters import get_runtime_rknn_adapter

        return get_runtime_rknn_adapter(
            model_id=model_id,
            binding=binding,
        )
    return None


def extend_registry_get_model(
    original_method: Callable[..., Type],
) -> Callable[..., Type]:
    def wrapper(
        self: Any,
        model_id: str,
        api_key: str,
        countinference: Optional[bool] = None,
        service_secret: Optional[str] = None,
    ) -> Type:
        runtime_adapter = resolve_runtime_model_adapter(model_id)
        if runtime_adapter is not None:
            return runtime_adapter
        return original_method(
            self,
            model_id,
            api_key,
            countinference=countinference,
            service_secret=service_secret,
        )

    return wrapper


def extend_model_getter(
    original_method: Callable[..., Any],
) -> Callable[..., Any]:
    def wrapper(model_id: str, api_key: str = API_KEY, **kwargs) -> Any:
        runtime_adapter = resolve_runtime_model_adapter(model_id)
        if runtime_adapter is not None:
            return runtime_adapter(
                model_id=model_id,
                api_key=api_key,
                **kwargs,
            )
        return original_method(
            model_id,
            api_key=api_key,
            **kwargs,
        )

    return wrapper
