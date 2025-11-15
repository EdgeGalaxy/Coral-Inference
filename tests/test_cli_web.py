from __future__ import annotations

import importlib
from types import SimpleNamespace
import argparse

import pytest

cli_main = importlib.import_module("coral_inference.cli.main")
from coral_inference.config import RuntimeDescriptor
from coral_inference.runtime.config import RuntimeConfig


def test_resolve_asgi_app():
    app = cli_main._resolve_asgi_app("tests.fixtures.dummy_web_app:app")
    assert callable(app)


def test_handle_web_serve(monkeypatch):
    captured = {}

    def fake_runtime_init(config: RuntimeConfig):
        captured["runtime_config"] = config
        return SimpleNamespace()

    monkeypatch.setattr(cli_main, "runtime_init", fake_runtime_init)

    descriptor = RuntimeDescriptor()

    monkeypatch.setattr(
        cli_main,
        "_build_descriptor_from_args",
        lambda args: descriptor,
    )

    def fake_uvicorn_run(app, host, port, reload):  # noqa: A002
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port
        captured["reload"] = reload

    monkeypatch.setattr(cli_main.uvicorn, "run", fake_uvicorn_run)

    args = argparse.Namespace(
        command="web",
        web_command="serve",
        config=None,
        overrides=[],
        no_env=True,
        host="127.0.0.1",
        port=9999,
        reload=False,
        app="tests.fixtures.dummy_web_app:app",
    )

    assert cli_main._handle_web_serve(args) == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9999
    assert captured["reload"] is False
    # runtime_init should have been called with RuntimeConfig
    assert isinstance(captured["runtime_config"], RuntimeConfig)
    # ASGI app resolves from fixture
    assert captured["app"] is cli_main._resolve_asgi_app("tests.fixtures.dummy_web_app:app")
