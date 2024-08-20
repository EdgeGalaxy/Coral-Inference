from inference.core.exceptions import ModelArtefactError


def rknnruntime_session(model_fp: str, device_id: int):
    try:
        from rknnlite.api import RKNNLite as RKNN
    except ImportError:
        raise ImportError("Please install rknnlite first!")

    rknn_session = RKNN(verbose=False)
    rknn_session.load_rknn(model_fp)
    ret = rknn_session.init_runtime(core_mask=int(device_id))
    if ret != 0:
        raise ModelArtefactError(f"Unable to initialize RKNN session. Cause: {ret}")
    return rknn_session
