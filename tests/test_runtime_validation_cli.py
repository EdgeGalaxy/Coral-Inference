import json

from coral_inference.cli.main import main
from coral_inference.runtime.validation import (
    build_runtime_binding_from_local_package,
    summarize_runtime_binding_validation,
)


def test_summarize_runtime_binding_validation_accepts_supported_local_rknn_package(
    tmp_path,
):
    package_dir = tmp_path / "rknn-package"
    package_dir.mkdir()
    for file_name in (
        "weights.rknn",
        "class_names.txt",
        "inference_config.json",
        "runtime_metadata.json",
    ):
        (package_dir / file_name).write_text("{}", encoding="utf-8")

    binding = build_runtime_binding_from_local_package(
        package_dir=str(package_dir),
        loader_type="coral_rknn",
        backend_type="rknn",
        task_type="object-detection",
        framework="rfdetr",
        selected_runtime="rknn",
    )
    summary = summarize_runtime_binding_validation(binding)

    assert summary["is_supported"] is True
    assert summary["missing_required_files"] == []


def test_cli_validate_runtime_package_returns_nonzero_for_missing_files(tmp_path, capsys):
    package_dir = tmp_path / "onnx-package"
    package_dir.mkdir()
    (package_dir / "class_names.txt").write_text("helmet\n", encoding="utf-8")

    exit_code = main(
        [
            "validate-runtime-package",
            "--package-dir",
            str(package_dir),
            "--loader-type",
            "inference_models",
            "--backend-type",
            "onnx",
            "--task-type",
            "object-detection",
            "--framework",
            "yolov8",
            "--selected-runtime",
            "onnx",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["is_supported"] is False
    assert payload["missing_required_files"] == [
        "inference_config.json",
        "weights.onnx",
    ]
