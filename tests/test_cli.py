import importlib
import json

cli_main = importlib.import_module("coral_inference.cli.main")
from coral_inference.runtime.context import RuntimeContext, RuntimeState


def test_cli_config_validate(tmp_path, capsys):
    config_path = tmp_path / "descriptor.yaml"
    config_path.write_text(
        """
platform: custom
patches:
  camera: false
"""
    )

    exit_code = cli_main.main(["config", "validate", "-c", str(config_path), "--no-env"])
    assert exit_code == 0

    captured = capsys.readouterr().out.strip()
    payload = json.loads(captured)
    assert payload["descriptor"]["platform"] == "custom"
    assert payload["descriptor"]["enable_camera_patch"] is False


def test_cli_init_uses_descriptor(monkeypatch, capsys, tmp_path):
    config_path = tmp_path / "descriptor.yaml"
    config_path.write_text("platform: cli-demo\n")

    captured_config = {}

    def fake_init(config):  # noqa: ANN001
        captured_config.update(config.__dict__)
        return RuntimeContext(
            config=config,
            state=RuntimeState(platform="cli-demo"),
            inference_version="1.0.0",
            log_messages=["init called"],
        )

    monkeypatch.setattr(cli_main, "runtime_init", fake_init)

    exit_code = cli_main.main(["init", "-c", str(config_path), "--no-env"])
    assert exit_code == 0
    assert captured_config["platform"] == "cli-demo"

    payload = json.loads(capsys.readouterr().out)
    assert payload["state"]["platform"] == "cli-demo"
    assert payload["state"]["plugins_loaded"] == {}
    assert payload["log_messages"] == ["init called"]


def test_cli_plugins_list(monkeypatch, capsys):
    monkeypatch.setattr(
        cli_main.runtime_plugins,
        "list_all_plugins",
        lambda group=None: {
            "backends": [{"entry_point": "alpha"}],
            "patches": [{"entry_point": "patch_ep", "plugins": [{"name": "patch_a"}]}],
            "workflows": [],
        },
    )

    exit_code = cli_main.main(["plugins", "list"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["backends"][0]["entry_point"] == "alpha"
    assert payload["patches"][0]["plugins"][0]["name"] == "patch_a"
