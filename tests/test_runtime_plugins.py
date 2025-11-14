from coral_inference.runtime import plugins as runtime_plugins
from coral_inference.runtime.config import RuntimeConfig
from coral_inference.runtime.plugins import PluginSpec


def test_list_plugins_for_group_backends(monkeypatch):
    class DummyEntryPoint:
        def __init__(self, name):
            self.name = name
            self.value = f"{name}:callable"
            self.module = "dummy"

    class DummyEntryPoints:
        def select(self, group):
            if group == runtime_plugins.PLUGIN_GROUPS["backends"]:
                return [DummyEntryPoint("alpha")]
            return []

    monkeypatch.setattr(runtime_plugins.metadata, "entry_points", lambda: DummyEntryPoints())

    entries = runtime_plugins.list_plugins_for_group("backends")
    assert entries == [
        {"entry_point": "alpha", "value": "alpha:callable", "module": "dummy"}
    ]


def test_list_plugins_for_group_with_specs(monkeypatch):
    spec = PluginSpec(name="demo", activate=lambda config: True, description="demo patch")

    class DummyEntryPoint:
        def __init__(self, name, value):
            self.name = name
            self.value = "pkg:callable"
            self.module = "pkg"
            self._value = value

        def load(self):
            return self._value

    class DummyEntryPoints:
        def select(self, group):
            if group == runtime_plugins.PLUGIN_GROUPS["patches"]:
                return [DummyEntryPoint("patch_ep", spec)]
            return []

    monkeypatch.setattr(runtime_plugins.metadata, "entry_points", lambda: DummyEntryPoints())

    entries = runtime_plugins.list_plugins_for_group("patches")
    assert entries[0]["entry_point"] == "patch_ep"
    assert entries[0]["plugins"][0]["name"] == "demo"


def test_load_runtime_plugins(monkeypatch):
    called = []

    def activate(config):  # noqa: ANN001
        called.append(config)
        return True

    class DummyEntryPoint:
        def __init__(self, spec):
            self.name = "patch_ep"
            self._spec = spec

        def load(self):
            return self._spec

    class DummyEntryPoints:
        def select(self, group):
            if group == runtime_plugins.PLUGIN_GROUPS["patches"]:
                return [DummyEntryPoint(PluginSpec(name="demo", activate=activate))]
            return []

    monkeypatch.setattr(runtime_plugins.metadata, "entry_points", lambda: DummyEntryPoints())

    statuses = runtime_plugins.load_runtime_plugins(RuntimeConfig())
    assert statuses == {"patches:demo": True}
    assert called


def test_load_runtime_plugins_version_block(monkeypatch):
    class DummyEntryPoint:
        def __init__(self, spec):
            self.name = "patch_ep"
            self._spec = spec

        def load(self):
            return self._spec

    class DummyEntryPoints:
        def select(self, group):
            if group == runtime_plugins.PLUGIN_GROUPS["patches"]:
                return [
                    DummyEntryPoint(
                        PluginSpec(
                            name="future",
                            activate=lambda config: True,
                            min_core_version="99.0.0",
                        )
                    )
                ]
            return []

    monkeypatch.setattr(runtime_plugins.metadata, "entry_points", lambda: DummyEntryPoints())
    monkeypatch.setattr(runtime_plugins, "_CORE_VERSION_TUPLE", (0, 0, 1))
    statuses = runtime_plugins.load_runtime_plugins(RuntimeConfig())
    assert statuses == {"patches:future": False}


def test_list_all_plugins_with_error(monkeypatch):
    def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(runtime_plugins.metadata, "entry_points", broken)
    names = runtime_plugins.list_all_plugins(group="backends")
    assert names == {"backends": []}
