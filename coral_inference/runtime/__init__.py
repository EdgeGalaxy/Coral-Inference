from coral_inference.runtime.catalog_client import ReefRuntimePackageClient
from coral_inference.runtime.compat import (
    _normalise_environment,
    _normalise_model_metadata,
    build_initialise_payload_from_runtime_package,
    get_runtime_deployment,
    get_runtime_model_binding,
    is_runtime_model_endpoint,
    make_runtime_model_endpoint,
    materialize_runtime_workflow_specification,
    register_runtime_model_bindings,
    register_runtime_package,
)
from coral_inference.runtime.contracts import (
    MaterializedModelPackage,
    RuntimeLockfile,
    RuntimeModelBinding,
    RuntimePackageFile,
)
from coral_inference.runtime.registry import RuntimeRegistry


def materialize_model_binding(*args, **kwargs):
    from coral_inference.runtime.package_materializer import materialize_model_binding as _impl

    return _impl(*args, **kwargs)


def load_runtime_binding(*args, **kwargs):
    from coral_inference.runtime.model_loader import load_runtime_binding as _impl

    return _impl(*args, **kwargs)


__all__ = [
    "MaterializedModelPackage",
    "ReefRuntimePackageClient",
    "RuntimeLockfile",
    "RuntimeModelBinding",
    "RuntimePackageFile",
    "RuntimeRegistry",
    "_normalise_environment",
    "_normalise_model_metadata",
    "build_initialise_payload_from_runtime_package",
    "get_runtime_deployment",
    "get_runtime_model_binding",
    "is_runtime_model_endpoint",
    "load_runtime_binding",
    "make_runtime_model_endpoint",
    "materialize_model_binding",
    "materialize_runtime_workflow_specification",
    "register_runtime_model_bindings",
    "register_runtime_package",
]
