"""Tests for expanded geometry handlers."""
import sys
import os
import types

import pytest

if "hou" not in sys.modules:
    pytest.skip("hou mock not loaded", allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from houdinimcp.handlers.geometry import (
    get_points, get_prims, get_attrib_values, set_detail_attrib,
    get_groups, get_group_members, get_bounding_box,
    get_prim_intrinsics, find_nearest_point,
)


class MockPoint:
    def __init__(self, num, pos=(0, 0, 0)):
        self._num = num
        self._pos = pos

    def number(self):
        return self._num

    def position(self):
        return self._pos

    def attribValue(self, attr):
        return 0.0


class MockPrim:
    def __init__(self, num, prim_type="Poly", num_verts=3):
        self._num = num
        self._type = prim_type
        self._num_verts = num_verts

    def number(self):
        return self._num

    def type(self):
        return self._type

    def numVertices(self):
        return self._num_verts

    def attribValue(self, attr):
        return 0.0

    def intrinsicNames(self):
        return ["measuredarea", "measuredperimeter"]

    def intrinsicValue(self, name):
        return 1.0


class MockGroup:
    def __init__(self, name, size=0):
        self._name = name
        self._size = size

    def name(self):
        return self._name

    def __len__(self):
        return self._size

    def iterEntries(self):
        return [MockPoint(i) for i in range(self._size)]


class MockBBox:
    def minvec(self):
        return (-1, -1, -1)

    def maxvec(self):
        return (1, 1, 1)

    def sizevec(self):
        return (2, 2, 2)

    def center(self):
        return (0, 0, 0)


class MockAttrib:
    def __init__(self, name, data_type="Float"):
        self._name = name
        self._data_type = data_type

    def name(self):
        return self._name

    def dataType(self):
        return types.SimpleNamespace(name=lambda: self._data_type)


class MockGeo:
    def __init__(self, points=None, prims=None):
        self._points = points or [MockPoint(0), MockPoint(1)]
        self._prims = prims or [MockPrim(0)]
        self._groups = {"point": [], "prim": []}

    def points(self):
        return self._points

    def prims(self):
        return self._prims

    def boundingBox(self):
        return MockBBox()

    def findPointAttrib(self, name):
        return MockAttrib(name) if name == "Cd" else None

    def findPrimAttrib(self, name):
        return MockAttrib(name) if name == "name" else None

    def findGlobalAttrib(self, name):
        return MockAttrib(name, "String") if name == "detail_name" else None

    def pointFloatAttribValues(self, name):
        return [0.0] * len(self._points)

    def primFloatAttribValues(self, name):
        return [0.0] * len(self._prims)

    def pointGroups(self):
        return self._groups.get("point", [])

    def primGroups(self):
        return self._groups.get("prim", [])

    def edgeGroups(self):
        return []

    def vertexGroups(self):
        return []

    def findPointGroup(self, name):
        for g in self._groups.get("point", []):
            if g.name() == name:
                return g
        return None

    def findPrimGroup(self, name):
        for g in self._groups.get("prim", []):
            if g.name() == name:
                return g
        return None

    def pointAttribs(self):
        return []

    def primAttribs(self):
        return []

    def globalAttribs(self):
        return []

    def intrinsicValue(self, name):
        if name == "vertexcount":
            return 0
        return None

    def attribValue(self, name):
        return "test"

    def addAttrib(self, atype, name, value):
        pass

    def setGlobalAttribValue(self, name, value):
        pass

    def nearestPoint(self, pos):
        return self._points[0]


class MockNodeWithGeo:
    def __init__(self, path, geo=None):
        self._path = path
        self._geo = geo or MockGeo()

    def path(self):
        return self._path

    def geometry(self):
        return self._geo


class TestGeometryExpanded:
    def setup_method(self):
        self._orig_node = sys.modules["hou"].node
        self.geo = MockGeo()
        self.node = MockNodeWithGeo("/obj/geo1/box1", self.geo)
        sys.modules["hou"].node = lambda p: self.node if p == "/obj/geo1/box1" else None
        if not hasattr(sys.modules["hou"], "Vector3"):
            sys.modules["hou"].Vector3 = lambda pos: pos
        if not hasattr(sys.modules["hou"], "attribType"):
            sys.modules["hou"].attribType = types.SimpleNamespace(Global=0, Point=1, Prim=2)

    def teardown_method(self):
        sys.modules["hou"].node = self._orig_node

    def test_get_points(self):
        result = get_points("/obj/geo1/box1")
        assert result["total"] == 2
        assert len(result["points"]) == 2

    def test_get_points_pagination(self):
        result = get_points("/obj/geo1/box1", start=1, count=1)
        assert len(result["points"]) == 1
        assert result["start"] == 1

    def test_get_prims(self):
        result = get_prims("/obj/geo1/box1")
        assert result["total"] == 1

    def test_get_bounding_box(self):
        result = get_bounding_box("/obj/geo1/box1")
        assert result["min"] == [-1, -1, -1]
        assert result["size"] == [2, 2, 2]

    def test_get_groups_empty(self):
        result = get_groups("/obj/geo1/box1", "point")
        assert result["groups"] == []

    def test_get_groups_with_data(self):
        self.geo._groups["point"] = [MockGroup("grp1", 3)]
        result = get_groups("/obj/geo1/box1", "point")
        assert len(result["groups"]) == 1
        assert result["groups"][0]["name"] == "grp1"

    def test_get_group_members(self):
        grp = MockGroup("grp1", 2)
        self.geo._groups["point"] = [grp]
        result = get_group_members("/obj/geo1/box1", "grp1", "point")
        assert result["count"] == 2

    def test_get_prim_intrinsics(self):
        result = get_prim_intrinsics("/obj/geo1/box1", 0)
        assert "measuredarea" in result["intrinsics"]

    def test_find_nearest_point(self):
        result = find_nearest_point("/obj/geo1/box1", [0, 0, 0])
        assert result["point_num"] == 0

    def test_set_detail_attrib(self):
        result = set_detail_attrib("/obj/geo1/box1", "my_attr", "hello")
        assert result["attrib"] == "my_attr"

    def test_node_not_found(self):
        sys.modules["hou"].node = lambda p: None
        with pytest.raises(ValueError, match="Node not found"):
            get_points("/obj/missing")
