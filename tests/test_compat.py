from coral_inference.runtime import compat, patches


def test_get_inference_version_tuple_parses_semver(monkeypatch):
    monkeypatch.setattr(compat, "inference_version", "1.2.3", raising=False)
    assert compat.get_inference_version_tuple() == (1, 2, 3)

    monkeypatch.setattr(compat, "inference_version", "invalid", raising=False)
    assert compat.get_inference_version_tuple() == (0, 0, 0)


def test_is_version_supported_bounds(monkeypatch):
    monkeypatch.setattr(compat, "get_inference_version_tuple", lambda: (1, 5, 0))
    assert compat.is_version_supported((1, 0, 0), (2, 0, 0))
    assert not compat.is_version_supported((2, 0, 0), None)
    assert not compat.is_version_supported(None, (1, 0, 0))


def test_import_object_supports_modules_and_attributes():
    math_module = compat.import_object("math")
    assert math_module.__name__ == "math"
    sqrt = compat.import_object("math:sqrt")
    assert sqrt(16) == 4


def test_patch_meta_blocks_incompatible_versions(monkeypatch):
    monkeypatch.setattr(patches, "is_version_supported", lambda *_: False)
    assert not patches._is_supported(patches.PATCH_CAMERA)
    monkeypatch.setattr(patches, "is_version_supported", lambda *_: True)
    assert patches._is_supported(patches.PATCH_CAMERA)
