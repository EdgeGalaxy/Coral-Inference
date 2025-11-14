import types

import coral_inference  # noqa: F401

from coral_inference.core.inference.stream_manager import patch_app
from inference.core.interfaces.stream_manager.manager_app import app


def test_app_handle_command_is_patched():
    assert app.handle_command is patch_app.patched_handle_command
    assert app.get_response_ignoring_thrash is patch_app.patched_get_response_ignoring_thrash


def test_patched_handle_command_returns_not_found():
    response = patch_app.patched_handle_command({}, "req-1", "pipe-1", command={})
    assert response["error_type"].name == "NOT_FOUND"
    assert "pipe-1" in response["public_error_message"]
