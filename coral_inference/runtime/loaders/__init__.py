def load_inference_models_package(*args, **kwargs):
    from coral_inference.runtime.loaders.inference_models_loader import (
        load_inference_models_package as _impl,
    )

    return _impl(*args, **kwargs)


def load_coral_rknn_package(*args, **kwargs):
    from coral_inference.runtime.loaders.rknn_loader import (
        load_coral_rknn_package as _impl,
    )

    return _impl(*args, **kwargs)


__all__ = [
    "load_coral_rknn_package",
    "load_inference_models_package",
]
