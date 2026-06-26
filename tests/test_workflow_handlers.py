"""Tests for workflow template handlers."""
import sys
import os
import types

import pytest

if "hou" not in sys.modules:
    pytest.skip("hou mock not loaded", allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from houdinimcp.handlers.workflow import (
    setup_pyro_sim, setup_rbd_sim, setup_flip_sim, setup_vellum_sim,
    build_sop_chain, setup_render,
)


class MockParm:
    def __init__(self, name, value=""):
        self._name = name
        self._value = value

    def name(self):
        return self._name

    def set(self, val):
        self._value = val

    def eval(self):
        return self._value


class MockNode:
    def __init__(self, name, path, node_type="geo"):
        self._name = name
        self._path = path
        self._type = node_type
        self._parms = {}
        self._display = False
        self._render = False

    def name(self):
        return self._name

    def path(self):
        return self._path

    def type(self):
        return types.SimpleNamespace(name=lambda: self._type)

    def createNode(self, node_type, node_name=None):
        n = node_name or node_type
        return MockNode(n, f"{self._path}/{n}", node_type)

    def setInput(self, idx, node, output_idx=0):
        pass

    def setDisplayFlag(self, v):
        self._display = v

    def setRenderFlag(self, v):
        self._render = v

    def parm(self, name):
        return self._parms.get(name)

    def layoutChildren(self):
        pass


class TestWorkflowHandlers:
    def setup_method(self):
        self._orig_node = sys.modules["hou"].node
        self.obj = MockNode("obj", "/obj")
        self.geo = MockNode("geo1", "/obj/geo1")
        self.mat = MockNode("mat", "/mat")
        self.out = MockNode("out", "/out")
        nodes = {
            "/obj": self.obj,
            "/obj/geo1": self.geo,
            "/mat": self.mat,
            "/out": self.out,
        }
        sys.modules["hou"].node = lambda p: nodes.get(p)

    def teardown_method(self):
        sys.modules["hou"].node = self._orig_node

    def test_setup_pyro_sim(self):
        result = setup_pyro_sim("/obj/geo1")
        assert "dopnet" in result

    def test_setup_rbd_sim(self):
        result = setup_rbd_sim("/obj/geo1")
        assert "rbd" in result

    def test_setup_flip_sim(self):
        result = setup_flip_sim("/obj/geo1")
        assert "solver" in result

    def test_setup_vellum_sim(self):
        result = setup_vellum_sim("/obj/geo1", sim_type="cloth")
        assert result["type"] == "cloth"

    def test_build_sop_chain(self):
        result = build_sop_chain("/obj/geo1", [
            {"type": "box"},
            {"type": "xform", "parameters": {}},
        ])
        assert len(result["nodes"]) == 2

    def test_setup_render(self):
        result = setup_render(render_engine="karma")
        assert result["engine"] == "karma"

    def test_source_not_found(self):
        sys.modules["hou"].node = lambda p: self.obj if p == "/obj" else None
        with pytest.raises(ValueError, match="Source not found"):
            setup_pyro_sim("/obj/missing")

    def test_parent_not_found(self):
        sys.modules["hou"].node = lambda p: None
        with pytest.raises(ValueError, match="Parent not found"):
            build_sop_chain("/obj/missing", [{"type": "box"}])
