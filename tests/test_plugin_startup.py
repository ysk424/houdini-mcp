import importlib.util
import os
import sys
import types


class FakeServer:
    instances = []

    def __init__(self):
        self.running = False
        self.socket = None
        self.stop_calls = 0
        self.__class__.instances.append(self)

    def start(self):
        self.running = True
        self.socket = object()

    def stop(self):
        self.stop_calls += 1
        self.running = False
        self.socket = None


def load_plugin_init(monkeypatch):
    fake_hou = types.ModuleType("hou")
    fake_hou.session = types.SimpleNamespace()
    fake_package = types.ModuleType("houdinimcp")
    fake_package.__path__ = []
    fake_server_module = types.ModuleType("houdinimcp.server")
    fake_server_module.HoudiniMCPServer = FakeServer

    monkeypatch.setitem(sys.modules, "hou", fake_hou)
    monkeypatch.setitem(sys.modules, "houdinimcp", fake_package)
    monkeypatch.setitem(sys.modules, "houdinimcp.server", fake_server_module)
    monkeypatch.setenv("HOUDINIMCP_HEADLESS", "1")

    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "src",
        "houdinimcp",
        "__init__.py",
    )
    spec = importlib.util.spec_from_file_location(
        "houdinimcp.__init_under_test", path
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "houdinimcp"
    spec.loader.exec_module(module)
    return module, fake_hou


def test_start_server_reuses_healthy_server(monkeypatch):
    FakeServer.instances.clear()
    plugin, hou = load_plugin_init(monkeypatch)
    healthy = FakeServer()
    healthy.start()
    hou.session.houdinimcp_server = healthy

    assert plugin.start_server() is healthy
    assert len(FakeServer.instances) == 1


def test_start_server_replaces_stale_server(monkeypatch):
    FakeServer.instances.clear()
    plugin, hou = load_plugin_init(monkeypatch)
    stale = FakeServer()
    stale.running = True
    stale.socket = None
    hou.session.houdinimcp_server = stale

    replacement = plugin.start_server()

    assert replacement is not stale
    assert replacement.running is True
    assert replacement.socket is not None
    assert stale.stop_calls == 1
    assert hou.session.houdinimcp_server is replacement
