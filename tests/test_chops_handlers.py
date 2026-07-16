"""Tests for CHOP handlers."""
import sys
import os
import types

import pytest

if "hou" not in sys.modules:
    pytest.skip("hou mock not loaded", allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from houdinimcp.handlers.chops import (
    get_chop_data, list_chop_channels, export_chop_to_parm,
)


class MockTrack:
    def __init__(self, name, samples=None):
        self._name = name
        self._samples = samples or [0.0, 1.0, 0.0]

    def name(self):
        return self._name

    def allSamples(self):
        return self._samples

    def numSamples(self):
        return len(self._samples)


class MockChopNode:
    def __init__(self, name, path, tracks=None):
        self._name = name
        self._path = path
        self._tracks = tracks or [MockTrack("tx"), MockTrack("ty")]

    def name(self):
        return self._name

    def path(self):
        return self._path

    def type(self):
        return types.SimpleNamespace(name=lambda: "wave")

    def tracks(self):
        return self._tracks

    def createNode(self, node_type, node_name=None):
        n = node_name or node_type
        return MockChopNode(n, f"{self._path}/{n}")


class MockParm:
    def __init__(self, name):
        self._name = name
        self._expr = None

    def name(self):
        return self._name

    def path(self):
        return f"/obj/node1/{self._name}"

    def setExpression(self, expr, lang):
        self._expr = expr


class MockTargetNode:
    def __init__(self, path, parms=None):
        self._path = path
        self._parms = {p.name(): p for p in (parms or [])}

    def parm(self, name):
        return self._parms.get(name)


class TestChopHandlers:
    def setup_method(self):
        self._orig_node = sys.modules["hou"].node

    def teardown_method(self):
        sys.modules["hou"].node = self._orig_node

    def test_get_chop_data(self):
        chop = MockChopNode("wave1", "/ch/chop1/wave1")
        sys.modules["hou"].node = lambda p: chop if p == "/ch/chop1/wave1" else None
        result = get_chop_data("/ch/chop1/wave1")
        assert len(result["channels"]) == 2

    def test_get_chop_data_single_channel(self):
        chop = MockChopNode("wave1", "/ch/chop1/wave1")
        sys.modules["hou"].node = lambda p: chop if p == "/ch/chop1/wave1" else None
        result = get_chop_data("/ch/chop1/wave1", channel="tx")
        assert len(result["channels"]) == 1
        assert result["channels"][0]["name"] == "tx"

    def test_list_chop_channels(self):
        chop = MockChopNode("wave1", "/ch/chop1/wave1")
        sys.modules["hou"].node = lambda p: chop if p == "/ch/chop1/wave1" else None
        result = list_chop_channels("/ch/chop1/wave1")
        assert result["count"] == 2

    def test_export_chop_to_parm(self):
        chop = MockChopNode("wave1", "/ch/chop1/wave1")
        parm = MockParm("tx")
        target = MockTargetNode("/obj/node1", [parm])
        nodes = {"/ch/chop1/wave1": chop, "/obj/node1": target}
        sys.modules["hou"].node = lambda p: nodes.get(p)
        result = export_chop_to_parm("/ch/chop1/wave1", "tx", "/obj/node1", "tx")
        assert "expression" in result
