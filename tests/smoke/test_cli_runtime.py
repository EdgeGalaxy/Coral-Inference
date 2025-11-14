import importlib
import json
from pathlib import Path

cli_main = importlib.import_module("coral_inference.cli.main")
from coral_inference.runtime.context import RuntimeContext, RuntimeState

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "runtime_cli.yaml"
)


def test_cli_init_with_fixture(monkeypatch, capsys):
    captured = {}

    def fake_init(config):  # noqa: ANN001
        captured["platform"] = config.platform
        captured["enable_webrtc"] = config.enable_webrtc
        captured["services"] = config.services
        return RuntimeContext(
            config=config,
            state=RuntimeState(platform=config.platform),
            inference_version="1.0.0",
            log_messages=["fixture init"],
        )

    monkeypatch.setattr(cli_main, "runtime_init", fake_init)

    exit_code = cli_main.main(["init", "-c", str(FIXTURE_PATH), "--no-env"])
    assert exit_code == 0
    assert captured["platform"] == "onnx"
    assert captured["enable_webrtc"] is False
    assert captured["services"]["webrtc"]["stun_servers"][0] == "stun:stun.l.google.com:19302"

    payload = json.loads(capsys.readouterr().out)
    assert payload["runtime_config"]["platform"] == "onnx"
    assert payload["runtime_config"]["services"]["metrics"]["influxdb_url"] == "http://localhost:8086"
    assert payload["state"]["platform"] == "onnx"
    assert payload["log_messages"] == ["fixture init"]
