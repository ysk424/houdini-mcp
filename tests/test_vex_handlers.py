"""Tests for VEX handlers."""
import sys
import os
import types
import contextlib

import pytest

if "hou" not in sys.modules:
    pytest.skip("hou mock not loaded", allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))


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


class MockCreatedNode:
    def __init__(self, name, path, node_type, parent=None):
        self._name = name
        self._path = path
        self._type = node_type
        self._parent = parent
        self._children = {}
        self._parms = {"snippet": MockParm("snippet"), "class": MockParm("class", 1)}
        self._errors = ()
        self._destroyed = False

    def name(self):
        return self._name

    def path(self):
        return self._path

    def type(self):
        return types.SimpleNamespace(name=lambda: self._type)

    def parm(self, name):
        return self._parms.get(name)

    def createNode(self, node_type, node_name=None):
        name = node_name or node_type
        child = MockCreatedNode(name, f"{self._path}/{name}", node_type, parent=self)
        self._children[name] = child
        return child

    def cook(self, force=False):
        snippet = self._parms["snippet"].eval()
        if "BAD" in snippet:
            self._errors = (f"Syntax error in {self._path}: BAD",)
            raise sys.modules["hou"].OperationFailed("cook failed")
        self._errors = ()

    def errors(self):
        return self._errors

    def destroy(self):
        self._destroyed = True
        if self._parent is not None:
            self._parent._children.pop(self._name, None)


class MockParentNode:
    def __init__(self, path):
        self._path = path
        self._children = {}

    def path(self):
        return self._path

    def createNode(self, node_type, node_name=None):
        name = node_name or node_type
        child = MockCreatedNode(name, f"{self._path}/{name}", node_type, parent=self)
        self._children[name] = child
        return child


def _setup_hou_undos():
    hou = sys.modules["hou"]
    if not hasattr(hou, "OperationFailed"):
        hou.OperationFailed = type("OperationFailed", (Exception,), {})
    if not hasattr(hou, "undos"):
        hou.undos = types.SimpleNamespace()
    if not hasattr(hou.undos, "disabler"):
        @contextlib.contextmanager
        def _disabler():
            yield
        hou.undos.disabler = _disabler


from houdinimcp.handlers.vex import (
    create_wrangle, set_wrangle_code, get_wrangle_code,
    create_vex_expression, validate_vex,
)


class TestVexHandlers:
    def setup_method(self):
        _setup_hou_undos()
        self._orig_node = sys.modules["hou"].node
        self.parent = MockParentNode("/obj/geo1")
        # Pre-populate /obj/geo1/wrangle1 for the create/get/set wrangle tests
        self.wrangle = MockCreatedNode("wrangle1", "/obj/geo1/wrangle1", "attribwrangle")
        self.obj = MockParentNode("/obj")
        nodes = {
            "/obj": self.obj,
            "/obj/geo1": self.parent,
            "/obj/geo1/wrangle1": self.wrangle,
        }
        sys.modules["hou"].node = lambda p: nodes.get(p)

    def teardown_method(self):
        sys.modules["hou"].node = self._orig_node

    def test_create_wrangle(self):
        result = create_wrangle("/obj/geo1", code="@Cd = {1,0,0};")
        assert result["type"] == "attribwrangle"

    def test_set_wrangle_code(self):
        result = set_wrangle_code("/obj/geo1/wrangle1", "@P.y += 1;")
        assert result["code_length"] > 0
        assert self.wrangle._parms["snippet"]._value == "@P.y += 1;"

    def test_get_wrangle_code(self):
        self.wrangle._parms["snippet"]._value = "@P *= 2;"
        result = get_wrangle_code("/obj/geo1/wrangle1")
        assert result["code"] == "@P *= 2;"

    def test_create_vex_expression(self):
        result = create_vex_expression("/obj/geo1", "dist", "length(@P)")
        assert "@dist" in result["code"]

    def test_validate_vex_valid(self):
        result = validate_vex("@P.y += 1;")
        assert result["valid"] is True
        assert result["errors"] is None

    def test_validate_vex_invalid(self):
        result = validate_vex("BAD this is not valid VEX")
        assert result["valid"] is False
        assert result["errors"]
        assert "Syntax error" in result["errors"]

    def test_validate_vex_empty(self):
        result = validate_vex("")
        assert result["valid"] is True
        assert result["errors"] is None

    def test_validate_vex_cleans_up_temp_geo(self):
        """Scene-cleanup invariant: the temp /obj/__mcp_vex_validate_*__ container
        must be destroyed even if cooking raised. No residue allowed.
        """
        before = set(self.obj._children.keys())
        validate_vex("BAD code that fails to compile")
        after = set(self.obj._children.keys())
        assert before == after, f"leaked temp nodes: {after - before}"

    def test_validate_vex_cleans_up_on_unexpected_exception(self, monkeypatch):
        """If anything beyond OperationFailed escapes, cleanup must still run."""
        # Sabotage the wrangle's parm() so the validate flow raises after the
        # temp geo has already been created. The finally block must still
        # destroy the geo.
        original = MockCreatedNode.createNode

        def patched(self, node_type, node_name=None):
            child = original(self, node_type, node_name)
            child.parm = lambda name: (_ for _ in ()).throw(RuntimeError("boom"))
            return child

        monkeypatch.setattr(MockCreatedNode, "createNode", patched)
        before = set(self.obj._children.keys())
        with pytest.raises(RuntimeError, match="boom"):
            validate_vex("@P.y += 1;")
        after = set(self.obj._children.keys())
        assert before == after

    def test_set_wrangle_node_not_found(self):
        sys.modules["hou"].node = lambda p: None
        with pytest.raises(ValueError, match="Node not found"):
            set_wrangle_code("/obj/missing", "code")

    def test_create_wrangle_parent_not_found(self):
        sys.modules["hou"].node = lambda p: None
        with pytest.raises(ValueError, match="Parent not found"):
            create_wrangle("/obj/missing")
