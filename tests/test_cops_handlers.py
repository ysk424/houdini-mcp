"""Tests for COP handlers."""
import sys
import os
import types

import pytest

if "hou" not in sys.modules:
    pytest.skip("hou mock not loaded", allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from houdinimcp.handlers.cops import (
    get_cop_info, list_cop_node_types,
)


class MockCopNode:
    def __init__(self, name, path):
        self._name = name
        self._path = path
        self._display = True

    def name(self):
        return self._name

    def path(self):
        return self._path

    def type(self):
        return types.SimpleNamespace(name=lambda: "file")

    def planes(self):
        return ["C", "A"]

    def xRes(self):
        return 1920

    def yRes(self):
        return 1080

    def setDisplayFlag(self, v):
        self._display = v

    def setRenderFlag(self, v):
        pass

    def bypass(self, v):
        pass

    def createNode(self, node_type, node_name=None):
        n = node_name or node_type
        return MockCopNode(n, f"{self._path}/{n}")


class TestCopHandlers:
    def setup_method(self):
        self._orig_node = sys.modules["hou"].node

    def teardown_method(self):
        sys.modules["hou"].node = self._orig_node

    def test_get_cop_info(self):
        cop = MockCopNode("file1", "/img/comp1/file1")
        sys.modules["hou"].node = lambda p: cop if p == "/img/comp1/file1" else None
        result = get_cop_info("/img/comp1/file1")
        assert result["xres"] == 1920
        assert "C" in result["planes"]

    def test_list_cop_node_types(self):
        result = list_cop_node_types()
        assert "count" in result

    def test_node_not_found(self):
        sys.modules["hou"].node = lambda p: None
        with pytest.raises(ValueError, match="Node not found"):
            get_cop_info("/img/missing")
