from pathlib import Path
from types import SimpleNamespace

from coral_inference.runtime.contracts import MaterializedModelPackage, RuntimeModelBinding
from coral_inference.runtime.loaders.rknn_loader import CoralRKNNModelBundle
from coral_inference.runtime.model_loader import load_runtime_binding
from coral_inference.runtime.rknn_adapters import (
    _CoralRuntimeRKNNObjectDetectionMixin,
)


FIXTURE_DIR = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "runtime_packages"
    / "coral_rknn_rfdetr"
)


def _build_binding() -> RuntimeModelBinding:
    return RuntimeModelBinding.model_validate(
        {
            "node_name": "detect",
            "field_name": "model",
            "model_reference": "asset:9",
            "binding_id": "rknn-1",
            "binding_ref": "binding:rknn-1",
            "binding_type": "package_ref",
            "model_id": "model-9",
            "model_name": "helmet-detector",
            "task_type": "object-detection",
            "framework": "rfdetr",
            "selected_package_id": "pkg-rknn-1",
            "selected_loader_type": "coral_rknn",
            "selected_backend": "rknn",
            "selected_runtime": "rknn",
            "runtime_environment": {
                "PREPROCESSING": {"resize": {"width": 640, "height": 640}},
                "CLASS_MAP": {"0": "helmet", "1": "person"},
                "COLORS": {"0": "#ffcc00", "1": "#00ccff"},
                "BATCH_SIZE": 1,
            },
            "package_files_snapshot": [
                {"file_handle": "weights.rknn"},
                {"file_handle": "class_names.txt"},
                {"file_handle": "inference_config.json"},
                {"file_handle": "runtime_metadata.json"},
                {"file_handle": "environment.json"},
            ],
        }
    )


def test_load_runtime_binding_reads_realistic_coral_rknn_fixture():
    binding = _build_binding()
    materialized_package = MaterializedModelPackage(
        package_id="pkg-rknn-1",
        loader_type="coral_rknn",
        backend_type="rknn",
        runtime_name="rknn",
        package_dir=str(FIXTURE_DIR),
    )

    bundle = load_runtime_binding(
        binding=binding,
        materialized_package=materialized_package,
    )

    assert isinstance(bundle, CoralRKNNModelBundle)
    assert bundle.package_dir == str(FIXTURE_DIR)
    assert bundle.class_names == ["helmet", "person"]
    assert bundle.inference_config["network_input"]["training_input_size"]["width"] == 640
    assert bundle.runtime_metadata["framework"] == "rfdetr"


def test_runtime_rknn_mixin_initializes_session_from_realistic_fixture(monkeypatch):
    binding = _build_binding()
    runtime_bundle = load_runtime_binding(
        binding=binding,
        materialized_package=MaterializedModelPackage(
            package_id="pkg-rknn-1",
            loader_type="coral_rknn",
            backend_type="rknn",
            runtime_name="rknn",
            package_dir=str(FIXTURE_DIR),
        ),
    )
    captured = {}

    class FakeSession:
        def __init__(self, model_fp, inputs):
            captured["model_fp"] = model_fp
            captured["input_name"] = inputs.name
            captured["input_shape"] = list(inputs.shape)

    class DummyRuntimeAdapter(_CoralRuntimeRKNNObjectDetectionMixin):
        def write_model_metadata_to_memcache(self, payload):
            self._metadata_payload = payload

    monkeypatch.setattr(
        "coral_inference.runtime.rknn_adapters.RknnInferenceSession",
        FakeSession,
    )

    adapter = DummyRuntimeAdapter.__new__(DummyRuntimeAdapter)
    adapter._runtime_binding = binding
    adapter._runtime_materialized_package = SimpleNamespace(package_dir=str(FIXTURE_DIR))
    adapter._runtime_rknn_bundle = runtime_bundle
    adapter.runtime_input_layout = "nchw"
    adapter.convert_preprocessed_image_to_rknn = False

    adapter.initialize_model()

    assert captured["model_fp"].endswith("weights.rknn")
    assert captured["input_name"] == "images"
    assert captured["input_shape"] == [1, 3, 640, 640]
    assert adapter.class_names == ["helmet", "person"]
    assert adapter.img_size_h == 640
    assert adapter.img_size_w == 640
    assert adapter._metadata_payload == {
        "batch_size": 1,
        "img_size_h": 640,
        "img_size_w": 640,
    }
