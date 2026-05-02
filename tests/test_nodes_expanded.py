"""Tests for expanded node handlers."""
import sys
import os
import types

import pytest

if "hou" not in sys.modules:
    pytest.skip("hou mock not loaded", allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from houdinimcp.handlers.nodes import (
    copy_node, move_node, rename_node, list_children,
    find_nodes, list_node_types, connect_nodes_batch, reorder_inputs,
    get_node_info,
)


class MockNode:
    def __init__(self, name, path, node_type="geo"):
        self._name = name
        self._path = path
        self._type = node_type
        self._inputs = [None, None, None, None]

    def name(self):
        return self._name

    def path(self):
        return self._path

    def type(self):
        return types.SimpleNamespace(name=lambda: self._type)

    def setName(self, n):
        old = self._name
        self._name = n
        self._path = self._path.rsplit("/", 1)[0] + "/" + n

    def children(self):
        return []

    def allSubChildren(self):
        return []

    def glob(self, pattern):
        return []

    def inputs(self):
        return self._inputs

    def setInput(self, idx, node, output_idx=0):
        if idx < len(self._inputs):
            self._inputs[idx] = node


class TestNodeExpanded:
    def setup_method(self):
        self._orig_node = sys.modules["hou"].node
        self._orig_copy = getattr(sys.modules["hou"], "copyNodesTo", None)
        self._orig_move = getattr(sys.modules["hou"], "moveNodesTo", None)

    def teardown_method(self):
        sys.modules["hou"].node = self._orig_node
        if self._orig_copy is not None:
            sys.modules["hou"].copyNodesTo = self._orig_copy
        if self._orig_move is not None:
            sys.modules["hou"].moveNodesTo = self._orig_move

    def test_rename_node(self):
        n = MockNode("box1", "/obj/box1", "box")
        sys.modules["hou"].node = lambda p: n if p == "/obj/box1" else None
        result = rename_node("/obj/box1", "cube1")
        assert result["old_name"] == "box1"
        assert result["new_name"] == "cube1"

    def test_rename_node_not_found(self):
        sys.modules["hou"].node = lambda p: None
        with pytest.raises(ValueError, match="Node not found"):
            rename_node("/obj/missing", "x")

    def test_list_children(self):
        child1 = MockNode("a", "/obj/geo1/a", "box")
        child2 = MockNode("b", "/obj/geo1/b", "sphere")
        parent = MockNode("geo1", "/obj/geo1")
        parent.children = lambda: [child1, child2]
        sys.modules["hou"].node = lambda p: parent if p == "/obj/geo1" else None
        result = list_children("/obj/geo1")
        assert result["count"] == 2

    def test_list_children_recursive(self):
        child = MockNode("a", "/obj/geo1/a", "box")
        parent = MockNode("geo1", "/obj/geo1")
        parent.allSubChildren = lambda: [child]
        sys.modules["hou"].node = lambda p: parent if p == "/obj/geo1" else None
        result = list_children("/obj/geo1", recursive=True)
        assert result["count"] == 1

    def test_find_nodes(self):
        root = MockNode("root", "/")
        n1 = MockNode("box1", "/obj/box1", "box")
        root.glob = lambda p: [n1]
        sys.modules["hou"].node = lambda p: root if p == "/" else None
        result = find_nodes("box*")
        assert result["count"] == 1

    def test_find_nodes_with_type_filter(self):
        root = MockNode("root", "/")
        n1 = MockNode("box1", "/obj/box1", "box")
        n2 = MockNode("sphere1", "/obj/sphere1", "sphere")
        root.glob = lambda p: [n1, n2]
        sys.modules["hou"].node = lambda p: root if p == "/" else None
        result = find_nodes("*", node_type="box")
        assert result["count"] == 1
        assert result["nodes"][0]["type"] == "box"

    def test_copy_node(self):
        src = MockNode("box1", "/obj/box1", "box")
        dest = MockNode("geo1", "/obj/geo1")
        copy_result = MockNode("box2", "/obj/geo1/box2", "box")
        nodes = {"/obj/box1": src, "/obj/geo1": dest}
        sys.modules["hou"].node = lambda p: nodes.get(p)
        sys.modules["hou"].copyNodesTo = lambda nodes_list, parent: [copy_result]
        result = copy_node("/obj/box1", "/obj/geo1")
        assert result["path"] == "/obj/geo1/box2"

    def test_move_node(self):
        src = MockNode("box1", "/obj/box1", "box")
        dest = MockNode("geo1", "/obj/geo1")
        moved = MockNode("box1", "/obj/geo1/box1", "box")
        nodes = {"/obj/box1": src, "/obj/geo1": dest}
        sys.modules["hou"].node = lambda p: nodes.get(p)
        sys.modules["hou"].moveNodesTo = lambda nodes_list, parent: [moved]
        result = move_node("/obj/box1", "/obj/geo1")
        assert result["path"] == "/obj/geo1/box1"

    def test_connect_nodes_batch(self):
        n1 = MockNode("a", "/obj/a", "box")
        n2 = MockNode("b", "/obj/b", "xform")
        nodes = {"/obj/a": n1, "/obj/b": n2}
        sys.modules["hou"].node = lambda p: nodes.get(p)
        result = connect_nodes_batch([
            {"src_path": "/obj/a", "dst_path": "/obj/b", "dst_input_index": 0},
        ])
        assert result["connected"] == 1

    def test_reorder_inputs(self):
        n = MockNode("merge", "/obj/merge", "merge")
        a = MockNode("a", "/obj/a")
        b = MockNode("b", "/obj/b")
        n._inputs = [a, b, None, None]
        sys.modules["hou"].node = lambda p: n if p == "/obj/merge" else None
        result = reorder_inputs("/obj/merge", [1, 0])
        assert result["new_order"] == [1, 0]

    def test_list_node_types(self):
        result = list_node_types()
        assert result["count"] == 0


class _FakeColor:
    """Mirrors real hou.Color: NOT iterable. RGB lives on .rgb()."""
    def __init__(self, r, g, b):
        self._rgb = (r, g, b)
    def rgb(self):
        return self._rgb


class _FakeTemplate:
    def __init__(self, label, type_name="String"):
        self._label = label
        self._type = type_name
    def label(self):
        return self._label
    def type(self):
        return types.SimpleNamespace(name=lambda: self._type)


class _FakeParm:
    """Mirrors real hou.Parm: NO .label() method."""
    def __init__(self, name, value, label):
        self._name = name
        self._value = value
        self._template = _FakeTemplate(label)
    def name(self):
        return self._name
    def eval(self):
        return self._value
    def rawValue(self):
        return str(self._value)
    def parmTemplate(self):
        return self._template


class _FakeNodeForInfo:
    def __init__(self, parms, color):
        self._parms = parms
        self._color = color
    def name(self):
        return "node1"
    def path(self):
        return "/obj/node1"
    def type(self):
        return types.SimpleNamespace(
            name=lambda: "geo",
            category=lambda: types.SimpleNamespace(name=lambda: "Object"),
        )
    def position(self):
        return (0.0, 0.0)
    def color(self):
        return self._color
    def isBypassed(self):
        return False
    def parms(self):
        return self._parms
    def inputs(self):
        return []
    def outputConnections(self):
        return []


class TestGetNodeInfo:
    """Regression tests for get_node_info covering B1 (parm.label) and B2 (Color)."""

    def setup_method(self):
        self._orig_node = sys.modules["hou"].node

    def teardown_method(self):
        sys.modules["hou"].node = self._orig_node

    def test_color_serialised_via_rgb(self):
        """B2 regression: hou.Color is not iterable. list(node.color()) used to raise.
        Must use .rgb() to get an [r, g, b] list.
        """
        node = _FakeNodeForInfo([], _FakeColor(0.5, 0.6, 0.7))
        sys.modules["hou"].node = lambda p: node if p == "/obj/node1" else None
        result = get_node_info("/obj/node1")
        assert result["color"] == [0.5, 0.6, 0.7]

    def test_color_none_when_node_color_falsy(self):
        node = _FakeNodeForInfo([], None)
        sys.modules["hou"].node = lambda p: node if p == "/obj/node1" else None
        result = get_node_info("/obj/node1")
        assert result["color"] is None

    def test_parameter_label_via_template(self):
        """B1 regression at the get_node_info call site: parm.label() does not
        exist on real hou.Parm. Label must come from parmTemplate().label().
        """
        parms = [_FakeParm("attrib", "P", "Attribute")]
        node = _FakeNodeForInfo(parms, _FakeColor(0, 0, 0))
        sys.modules["hou"].node = lambda p: node if p == "/obj/node1" else None
        result = get_node_info("/obj/node1")
        assert len(result["parameters"]) == 1
        assert result["parameters"][0]["name"] == "attrib"
        assert result["parameters"][0]["label"] == "Attribute"
