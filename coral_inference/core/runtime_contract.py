from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class RuntimeCompatibilityProfile(BaseModel):
    supported_runtimes: List[str] = Field(default_factory=list)
    preferred_runtime: Optional[str] = None


class TrainingArtifactRuntimeProfile(RuntimeCompatibilityProfile):
    weight_index_by_runtime: Dict[str, str] = Field(default_factory=dict)


class ArtifactManifestDescriptor(BaseModel):
    artifact_id: str
    kind: str
    runtime: Optional[str] = None
    uri: str
    file_name: Optional[str] = None
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    content_type: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class TrainingArtifactManifest(BaseModel):
    schema_version: str = "v2"
    source: Dict[str, Any] = Field(default_factory=dict)
    dataset: Dict[str, Any] = Field(default_factory=dict)
    training_spec: Dict[str, Any] = Field(default_factory=dict)
    summary: Dict[str, Any] = Field(default_factory=dict)
    label_schema: Dict[str, Any] = Field(default_factory=dict)
    io_schema: Dict[str, Any] = Field(default_factory=dict)
    metric_schema: Dict[str, Any] = Field(default_factory=dict)
    postprocessing: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[ArtifactManifestDescriptor] = Field(default_factory=list)
    runtime: TrainingArtifactRuntimeProfile = Field(
        default_factory=TrainingArtifactRuntimeProfile
    )
    metrics_summary: Dict[str, Any] = Field(default_factory=dict)


class RuntimePackageBindingReferenceProfile(BaseModel):
    primary_reference: Optional[str] = None
    primary_reference_kind: Optional[str] = None
    asset_reference: Optional[str] = None
    requested_binding_ref: Optional[str] = None
    effective_binding_ref: Optional[str] = None
    binding_type: Optional[str] = None
    binding_ref_changed: bool = False
    resolution_source: Optional[str] = None


class RuntimePackageModelMetadata(BaseModel):
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    model_title: Optional[str] = None
    task_type: Optional[str] = None
    framework: Optional[str] = None
    selected_runtime: Optional[str] = None
    source: Dict[str, Any] = Field(default_factory=dict)
    dataset: Dict[str, Any] = Field(default_factory=dict)
    class_mapping: Dict[str, Any] = Field(default_factory=dict)
    preprocessing: Dict[str, Any] = Field(default_factory=dict)
    metrics_summary: Dict[str, Any] = Field(default_factory=dict)
    label_schema: Dict[str, Any] = Field(default_factory=dict)
    io_schema: Dict[str, Any] = Field(default_factory=dict)
    metric_schema: Dict[str, Any] = Field(default_factory=dict)
    postprocessing: Dict[str, Any] = Field(default_factory=dict)
    runtime_profile: RuntimeCompatibilityProfile = Field(default_factory=RuntimeCompatibilityProfile)
    artifact_manifest_version: Optional[str] = None
    artifacts: List[ArtifactManifestDescriptor] = Field(default_factory=list)
    execution_reference: Dict[str, Any] = Field(default_factory=dict)


class RuntimePackageModelAsset(BaseModel):
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    model_title: Optional[str] = None
    task_type: Optional[str] = None
    framework: Optional[str] = None
    source_model_asset_id: Optional[int] = None
    source_task_id: Optional[int] = None
    source_project_id: Optional[int] = None
    source_version_id: Optional[int] = None
    artifact_manifest_version: Optional[str] = None
    runtime_profile: RuntimeCompatibilityProfile = Field(default_factory=RuntimeCompatibilityProfile)
    class_mapping: Dict[str, Any] = Field(default_factory=dict)
    preprocessing: Dict[str, Any] = Field(default_factory=dict)
    metrics_summary: Dict[str, Any] = Field(default_factory=dict)
    label_schema: Dict[str, Any] = Field(default_factory=dict)
    io_schema: Dict[str, Any] = Field(default_factory=dict)
    metric_schema: Dict[str, Any] = Field(default_factory=dict)
    postprocessing: Dict[str, Any] = Field(default_factory=dict)
    dataset: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[ArtifactManifestDescriptor] = Field(default_factory=list)
    environment: Dict[str, Any] = Field(default_factory=dict)
    artifact_manifest: TrainingArtifactManifest = Field(default_factory=TrainingArtifactManifest)
    standardized_metadata: Dict[str, Any] = Field(default_factory=dict)


class RuntimePackageBinding(BaseModel):
    node_name: str
    field_name: str
    model_reference: str
    reference_profile: Optional[RuntimePackageBindingReferenceProfile] = None
    binding_id: str
    binding_ref: str
    binding_type: str
    model_id: str
    model_name: str
    model_title: Optional[str] = None
    task_type: Optional[str] = None
    framework: Optional[str] = None
    model_type: Optional[str] = None
    source_type: Optional[str] = None
    selected_runtime: str
    workflow_binding_metadata: Dict[str, Any] = Field(default_factory=dict)
    source_model_asset_id: Optional[int] = None
    source_version_id: Optional[int] = None
    artifact_manifest_version: Optional[str] = None
    inference_target: Optional[str] = None
    artifact_manifest: TrainingArtifactManifest = Field(default_factory=TrainingArtifactManifest)
    supported_runtimes: List[str] = Field(default_factory=list)
    preferred_runtime: Optional[str] = None
    model_environment: Dict[str, Any] = Field(default_factory=dict)
    runtime_environment: Dict[str, Any] = Field(default_factory=dict)
    class_mapping: Dict[str, Any] = Field(default_factory=dict)
    preprocessing: Dict[str, Any] = Field(default_factory=dict)
    metrics_summary: Dict[str, Any] = Field(default_factory=dict)
    dataset: Dict[str, Any] = Field(default_factory=dict)
    model_metadata: Optional[RuntimePackageModelMetadata] = None
    model_asset: Optional[RuntimePackageModelAsset] = None
    runtime_model_endpoint: Optional[str] = None


class RuntimePackageSource(BaseModel):
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    type: Optional[str] = None
    path: Optional[Any] = None
    resolved_path: Optional[str] = None


class RuntimePackageStreamConfig(BaseModel):
    output_image_fields: List[str] = Field(default_factory=list)
    max_fps: Optional[int] = None
    is_file_source: Optional[bool] = None
    video_source_properties: Dict[str, Any] = Field(default_factory=dict)


class RuntimePackageMetricsConfig(BaseModel):
    deployment_id: Optional[str] = None
    gateway_id: Optional[str] = None


class RuntimeReportSourceProperties(BaseModel):
    is_file: Optional[bool] = None
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None


class RuntimeReportSourceMetadata(BaseModel):
    source_id: Optional[int] = None
    source_reference: Optional[str] = None
    state: Optional[str] = None
    source_properties: Optional[RuntimeReportSourceProperties] = None

    @field_validator("state")
    @classmethod
    def normalise_state(cls, value: Optional[str]) -> Optional[str]:
        return str(value).upper() if value is not None else None


class RuntimeReportLatency(BaseModel):
    source_id: Optional[int] = None
    frame_decoding_latency: Optional[float] = None
    inference_latency: Optional[float] = None
    e2e_latency: Optional[float] = None


class RuntimeReportStatusUpdate(BaseModel):
    timestamp: Optional[str] = None
    severity: Optional[str] = None
    event_type: Optional[str] = None
    context: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("severity")
    @classmethod
    def normalise_severity(cls, value: Optional[str]) -> Optional[str]:
        return str(value).upper() if value is not None else None

    @field_validator("payload", mode="before")
    @classmethod
    def ensure_payload_dict(cls, value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}


class RuntimeStatusReport(BaseModel):
    sources_metadata: List[RuntimeReportSourceMetadata] = Field(default_factory=list)
    latency_reports: List[RuntimeReportLatency] = Field(default_factory=list)
    video_source_status_updates: List[RuntimeReportStatusUpdate] = Field(
        default_factory=list
    )
    inference_throughput: Optional[float] = None


class RuntimePackageContract(BaseModel):
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
    model_bindings: List[RuntimePackageBinding] = Field(default_factory=list)
    model_bindings_digest: Optional[str] = None
    sources: List[RuntimePackageSource] = Field(default_factory=list)
    video_reference: List[Any] = Field(default_factory=list)
    stream_config: RuntimePackageStreamConfig = Field(default_factory=RuntimePackageStreamConfig)
    metrics_config: RuntimePackageMetricsConfig = Field(default_factory=RuntimePackageMetricsConfig)
    sinks: Dict[str, Any] = Field(default_factory=dict)
    package_generated_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    package_digest: Optional[str] = None


def normalize_runtime_status_report(
    report: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not report:
        return {}
    return RuntimeStatusReport.model_validate(report).model_dump(exclude_none=True)
