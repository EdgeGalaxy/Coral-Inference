from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RuntimePackageFile(BaseModel):
    file_handle: str
    download_url: str = ""
    md5_hash: Optional[str] = None
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    content_type: Optional[str] = None
    storage_key: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RuntimeModelBinding(BaseModel):
    node_name: str
    field_name: str
    model_reference: str
    reference_profile: Dict[str, Any] = Field(default_factory=dict)
    binding_id: str
    binding_ref: str
    binding_type: str
    model_id: str
    model_name: str
    model_title: Optional[str] = None
    task_type: Optional[str] = None
    framework: Optional[str] = None
    selected_package_id: Optional[str] = None
    selected_loader_type: Optional[str] = None
    selected_backend: Optional[str] = None
    selected_runtime: Optional[str] = None
    inference_target: Optional[str] = None
    runtime_environment: Dict[str, Any] = Field(default_factory=dict)
    standardized_metadata: Dict[str, Any] = Field(default_factory=dict)
    artifact_manifest: Dict[str, Any] = Field(default_factory=dict)
    model_asset: Dict[str, Any] = Field(default_factory=dict)
    package_manifest_snapshot: Dict[str, Any] = Field(default_factory=dict)
    package_files_snapshot: List[RuntimePackageFile] = Field(default_factory=list)
    supported_runtimes: List[str] = Field(default_factory=list)
    preferred_runtime: Optional[str] = None
    runtime_model_endpoint: Optional[str] = None


class RuntimeLockfile(BaseModel):
    schema_version: str = "v2"
    deployment_id: str
    deployment_revision: Optional[str] = None
    deployment_name: Optional[str] = None
    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None
    gateway_id: Optional[str] = None
    gateway_name: Optional[str] = None
    gateway_run_env: Optional[str] = None
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    workflow_spec: Dict[str, Any] = Field(default_factory=dict)
    workflow_data: Dict[str, Any] = Field(default_factory=dict)
    workflow_md5: Optional[str] = None
    workflow_digest: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    model_bindings: List[RuntimeModelBinding] = Field(default_factory=list)
    model_bindings_digest: Optional[str] = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    video_reference: List[Any] = Field(default_factory=list)
    stream_config: Dict[str, Any] = Field(default_factory=dict)
    metrics_config: Dict[str, Any] = Field(default_factory=dict)
    sinks: Dict[str, Any] = Field(default_factory=dict)
    package_generated_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    package_digest: Optional[str] = None


class MaterializedModelPackage(BaseModel):
    package_id: str
    loader_type: str
    backend_type: Optional[str] = None
    runtime_name: Optional[str] = None
    package_dir: str
    model_config_path: Optional[str] = None
    file_paths: Dict[str, str] = Field(default_factory=dict)
