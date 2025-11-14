import importlib

import pytest


def test_cv2_video_frame_producer_is_patched():
    """
    Importing coral_inference should replace the default CV2VideoFrameProducer
    with the patched variant that handles Jetson/RKNN devices.
    """

    import coral_inference  # noqa: F401

    from inference.core.interfaces.camera import video_source
    from coral_inference.core.inference.camera.patch_video_source import (
        PatchedCV2VideoFrameProducer,
    )

    assert (
        video_source.CV2VideoFrameProducer is PatchedCV2VideoFrameProducer
    ), "Video source patch not applied"


@pytest.mark.parametrize(
    "env_value,expected",
    [
        ("rknn", "rknn"),
        ("RKNN", "RKNN"),
        ("onnx", "onnx"),
    ],
)
def test_get_runtime_platform_respects_manual_env(monkeypatch, env_value, expected):
    import coral_inference.core.models.utils as utils_module

    # Ensure we operate on a clean copy of the module-level constant
    importlib.reload(utils_module)

    monkeypatch.setattr(utils_module, "CURRENT_INFERENCE_PLATFORM", env_value)
    platform = utils_module.get_runtime_platform()

    assert platform == expected


def test_get_runtime_platform_detects_rknn_server(monkeypatch):
    import coral_inference.core.models.utils as utils_module

    importlib.reload(utils_module)

    monkeypatch.setattr(utils_module, "CURRENT_INFERENCE_PLATFORM", None)
    monkeypatch.setattr(
        utils_module.subprocess,
        "check_output",
        lambda *args, **kwargs: b"rknn-server",
    )

    assert utils_module.get_runtime_platform() == "rknn"


def test_get_runtime_platform_falls_back_to_onnx(monkeypatch):
    import coral_inference.core.models.utils as utils_module

    importlib.reload(utils_module)

    monkeypatch.setattr(utils_module, "CURRENT_INFERENCE_PLATFORM", None)

    def _raise(*_args, **_kwargs):
        raise FileNotFoundError("rknn-server missing")

    monkeypatch.setattr(utils_module.subprocess, "check_output", _raise)

    assert utils_module.get_runtime_platform() == "onnx"
