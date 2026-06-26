"""Tests for expanded LOP/USD handlers."""
import sys
import os
import types

import pytest

if "hou" not in sys.modules:
    pytest.skip("hou mock not loaded", allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from houdinimcp.handlers.lop import (
    list_usd_prims, get_usd_attribute, get_usd_prim_stats,
    get_usd_composition, get_usd_variants, inspect_usd_layer,
    list_lights,
)


class MockUsdPrim:
    def __init__(self, path, type_name="Xform", children=None, attrs=None):
        self._path = path
        self._type_name = type_name
        self._children = children or []
        self._attrs = attrs or {}

    def GetPath(self):
        return self._path

    def GetTypeName(self):
        return self._type_name

    def GetChildren(self):
        return self._children

    def GetAttributes(self):
        return list(self._attrs.values())

    def GetAttribute(self, name):
        return self._attrs.get(name)

    def IsActive(self):
        return True

    def HasPayload(self):
        return False

    def GetReferences(self):
        return None

    def GetPayloads(self):
        return None

    def GetInherits(self):
        return None

    def GetSpecializes(self):
        return None

    def GetVariantSets(self):
        return types.SimpleNamespace(GetNames=lambda: [])

    def GetVariantSet(self, name):
        return None


class MockUsdAttr:
    def __init__(self, name, value, type_name="float"):
        self._name = name
        self._value = value
        self._type_name = type_name

    def GetName(self):
        return self._name

    def Get(self):
        return self._value

    def GetTypeName(self):
        return self._type_name

    def Set(self, val):
        self._value = val


class MockLayer:
    def __init__(self, identifier="anon", path=""):
        self.identifier = identifier
        self.realPath = path
        self.rootPrims = []


class MockStage:
    def __init__(self, prims=None, layers=None):
        self._prims = prims or []
        self._layers = layers or [MockLayer()]

    def GetPseudoRoot(self):
        return MockUsdPrim("/", "Root", self._prims)

    def GetPrimAtPath(self, path):
        if path == "/":
            return self.GetPseudoRoot()
        for p in self._prims:
            if str(p.GetPath()) == path:
                return p
        return None

    def Traverse(self):
        return self._prims

    def GetLayerStack(self):
        return self._layers

    def GetEditTarget(self):
        return types.SimpleNamespace(GetLayer=lambda: self._layers[0])

    def HasDefaultPrim(self):
        return False

    def GetDefaultPrim(self):
        return None


class MockLopNode:
    def __init__(self, path, stage=None):
        self._path = path
        self._stage = stage or MockStage()

    def path(self):
        return self._path

    def stage(self):
        return self._stage

    def name(self):
        return self._path.split("/")[-1]

    def type(self):
        return types.SimpleNamespace(name=lambda: "lopnode")

    def createNode(self, node_type, node_name=None):
        n = node_name or node_type
        return MockLopNode(f"{self._path}/{n}")


class TestLopExpanded:
    def setup_method(self):
        self._orig_node = sys.modules["hou"].node

    def teardown_method(self):
        sys.modules["hou"].node = self._orig_node

    def test_list_usd_prims(self):
        child = MockUsdPrim("/World", "Xform")
        stage = MockStage(prims=[child])
        node = MockLopNode("/stage/lopnet1", stage)
        sys.modules["hou"].node = lambda p: node if p == "/stage/lopnet1" else None
        result = list_usd_prims("/stage/lopnet1")
        assert result["count"] == 1

    def test_get_usd_attribute(self):
        attr = MockUsdAttr("radius", 1.0, "float")
        prim = MockUsdPrim("/World/sphere", "Sphere", attrs={"radius": attr})
        stage = MockStage(prims=[prim])
        node = MockLopNode("/stage/lopnet1", stage)
        sys.modules["hou"].node = lambda p: node if p == "/stage/lopnet1" else None
        result = get_usd_attribute("/stage/lopnet1", "/World/sphere", "radius")
        assert result["value"] == "1.0"

    def test_get_usd_prim_stats(self):
        prim = MockUsdPrim("/World", "Xform")
        stage = MockStage(prims=[prim])
        node = MockLopNode("/stage/lopnet1", stage)
        sys.modules["hou"].node = lambda p: node if p == "/stage/lopnet1" else None
        result = get_usd_prim_stats("/stage/lopnet1", "/World")
        assert result["is_active"] is True

    def test_get_usd_composition(self):
        prim = MockUsdPrim("/World", "Xform")
        stage = MockStage(prims=[prim])
        node = MockLopNode("/stage/lopnet1", stage)
        sys.modules["hou"].node = lambda p: node if p == "/stage/lopnet1" else None
        result = get_usd_composition("/stage/lopnet1", "/World")
        assert "composition" in result

    def test_inspect_usd_layer(self):
        layer = MockLayer("test.usd", "/tmp/test.usd")
        stage = MockStage(layers=[layer])
        node = MockLopNode("/stage/lopnet1", stage)
        sys.modules["hou"].node = lambda p: node if p == "/stage/lopnet1" else None
        result = inspect_usd_layer("/stage/lopnet1", 0)
        assert result["identifier"] == "test.usd"

    def test_list_lights(self):
        light = MockUsdPrim("/World/Light1", "DistantLight")
        stage = MockStage(prims=[light])
        node = MockLopNode("/stage/lopnet1", stage)
        sys.modules["hou"].node = lambda p: node if p == "/stage/lopnet1" else None
        result = list_lights("/stage/lopnet1")
        assert result["count"] == 1

    def test_node_not_found(self):
        sys.modules["hou"].node = lambda p: None
        with pytest.raises(ValueError, match="Node not found"):
            list_usd_prims("/stage/missing")
