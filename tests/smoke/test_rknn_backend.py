import importlib
from unittest import mock


def test_rknn_inference_session_initializes_and_runs(monkeypatch):
    """Ensure the RKNN session wrapper loads model and produces predictions."""

    from coral_inference.core.models.utils import RknnInferenceSession

    mock_inputs = mock.Mock()
    mock_inputs.name = "input"
    mock_inputs.shape = (1, 3, 640, 640)

    class DummyRKNN:
        def __init__(self, verbose=False):  # noqa: ARG002
            self.loaded_path = None

        def load_rknn(self, model_fp):
            self.loaded_path = model_fp

        def init_runtime(self, core_mask):  # noqa: ARG002
            return 0

        def inference(self, inputs):
            # Echo back the same shape, as RKNNLite would do
            return inputs

    monkeypatch.setitem(
        importlib.import_module("sys").modules,
        "rknnlite.api",
        mock.Mock(RKNNLite=DummyRKNN),
    )

    session = RknnInferenceSession(model_fp="/tmp/model.rknn", inputs=mock_inputs)
    output = session.run(output_names=None, input_feed={"input": [[1, 2], [3, 4]]})

    assert isinstance(output, list)
    assert output[0] is not None


def test_extend_preproc_image_transforms_tensor():
    import numpy as np

    from coral_inference.core.models.rknn_base import extend_preproc_image

    class DummyModel:
        def preproc_image(self, image):
            return np.ones((1, 3, 4, 4)), (640, 640)

    DummyModel.preproc_image = extend_preproc_image(DummyModel.preproc_image)

    processed, dims = DummyModel().preproc_image(None)

    assert processed.shape == (4, 4, 3)
    assert processed.max() == 255.0
    assert dims == (640, 640)
