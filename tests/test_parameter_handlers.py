"""Tests for parameter handlers."""
import sys
import os
import types

import pytest

if "hou" not in sys.modules:
    pytest.skip("hou mock not loaded", allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from houdinimcp.handlers.parameters import (
    get_parameter, set_parameter, set_parameters,
    get_parameter_schema, get_expression, revert_parameter,
    link_parameters, lock_parameter,
    create_spare_parameter, create_spare_parameters,
)


class MockParmTemplate:
    def __init__(self, parm_type="Float", label=""):
        self._type = parm_type
        self._label = label

    def type(self):
        return types.SimpleNamespace(name=lambda: self._type)

    def label(self):
        return self._label

    def menuItems(self):
        return ()

    def menuLabels(self):
        return ()


class MockParm:
    """Mirrors real hou.Parm: NO .label() method (label lives on parmTemplate)."""
    def __init__(self, name, value=0.0, label="", locked=False, at_default=True):
        self._name = name
        self._value = value
        self._label = label or name
        self._locked = locked
        self._at_default = at_default
        self._expression = None
        self._path = f"/obj/node1/{name}"

    def name(self):
        return self._name

    def eval(self):
        return self._value

    def rawValue(self):
        return str(self._value)

    def set(self, val):
        self._value = val

    def parmTemplate(self):
        return MockParmTemplate(label=self._label)

    def isAtDefault(self):
        return self._at_default

    def isLocked(self):
        return self._locked

    def lock(self, val):
        self._locked = val

    def revertToDefaults(self):
        self._value = 0.0
        self._at_default = True

    def expression(self):
        if self._expression:
            return self._expression
        raise sys.modules["hou"].OperationFailed("No expression")

    def expressionLanguage(self):
        return "Hscript"

    def setExpression(self, expr, lang=None):
        self._expression = expr

    def path(self):
        return self._path


class MockNodeWithParms:
    def __init__(self, name, path, parms=None):
        self._name = name
        self._path = path
        self._parms = {p.name(): p for p in (parms or [])}
        self._ptg = types.SimpleNamespace(
            addParmTemplate=lambda t: None,
        )

    def name(self):
        return self._name

    def path(self):
        return self._path

    def parm(self, name):
        return self._parms.get(name)

    def parms(self):
        return list(self._parms.values())

    def parmTemplateGroup(self):
        return self._ptg

    def setParmTemplateGroup(self, ptg):
        self._ptg = ptg


def _setup_hou_mock():
    """Add OperationFailed exception to hou mock."""
    hou = sys.modules["hou"]
    if not hasattr(hou, "OperationFailed"):
        hou.OperationFailed = type("OperationFailed", (Exception,), {})
    if not hasattr(hou, "FloatParmTemplate"):
        hou.FloatParmTemplate = lambda name, label, num, default_value=(0,): types.SimpleNamespace(name=name)
        hou.IntParmTemplate = lambda name, label, num, default_value=(0,): types.SimpleNamespace(name=name)
        hou.StringParmTemplate = lambda name, label, num, default_value=("",): types.SimpleNamespace(name=name)
        hou.ToggleParmTemplate = lambda name, label, default_value=False: types.SimpleNamespace(name=name)


class TestParameterHandlers:
    def setup_method(self):
        _setup_hou_mock()
        self._orig_node = sys.modules["hou"].node
        self.parm_tx = MockParm("tx", 1.0, "Translate X", at_default=False)
        self.parm_ty = MockParm("ty", 0.0, "Translate Y")
        self.node = MockNodeWithParms("node1", "/obj/node1", [self.parm_tx, self.parm_ty])
        sys.modules["hou"].node = lambda p: self.node if p == "/obj/node1" else None

    def teardown_method(self):
        sys.modules["hou"].node = self._orig_node

    def test_get_parameter(self):
        result = get_parameter("/obj/node1", "tx")
        assert result["value"] == 1.0
        assert result["name"] == "tx"

    def test_get_parameter_regression_label_via_template(self):
        """Regression: get_parameter previously called parm.label(), which raises
        AttributeError on real hou.Parm in 21.x for ANY parm on ANY node. The
        label must be read from the parm template instead. See B1.
        """
        result = get_parameter("/obj/node1", "tx")
        assert isinstance(result, dict)
        assert result["name"] == "tx"
        assert result["label"] == "Translate X"
        assert "value" in result
        assert "type" in result

    def test_get_parameter_not_found(self):
        with pytest.raises(ValueError, match="Parameter not found"):
            get_parameter("/obj/node1", "nonexistent")

    def test_get_parameter_node_not_found(self):
        with pytest.raises(ValueError, match="Node not found"):
            get_parameter("/obj/missing", "tx")

    def test_set_parameter(self):
        result = set_parameter("/obj/node1", "tx", 5.0)
        assert result["old_value"] == 1.0
        assert result["new_value"] == 5.0

    def test_set_parameters(self):
        result = set_parameters("/obj/node1", {"tx": 10.0, "ty": 20.0})
        assert len(result["changes"]) == 2
        assert self.parm_tx._value == 10.0
        assert self.parm_ty._value == 20.0

    def test_get_parameter_schema(self):
        result = get_parameter_schema("/obj/node1")
        assert len(result["parameters"]) == 2
        assert result["parameters"][0]["name"] == "tx"

    def test_get_expression_none(self):
        result = get_expression("/obj/node1", "tx")
        assert result["expression"] is None

    def test_get_expression_exists(self):
        self.parm_tx._expression = "$F"
        result = get_expression("/obj/node1", "tx")
        assert result["expression"] == "$F"

    def test_revert_parameter(self):
        result = revert_parameter("/obj/node1", "tx")
        assert result["reverted"] is True
        assert self.parm_tx._value == 0.0

    def test_lock_parameter(self):
        result = lock_parameter("/obj/node1", "tx", locked=True)
        assert result["locked"] is True
        assert self.parm_tx._locked is True

    def test_link_parameters(self):
        node2_parm = MockParm("rx", 0.0)
        node2 = MockNodeWithParms("node2", "/obj/node2", [node2_parm])
        sys.modules["hou"].node = lambda p: {"/obj/node1": self.node, "/obj/node2": node2}.get(p)
        sys.modules["hou"].exprLanguage = types.SimpleNamespace(Hscript=0, Python=1)
        result = link_parameters("/obj/node1", "tx", "/obj/node2", "rx")
        assert "expression" in result

    def test_create_spare_parameter(self):
        result = create_spare_parameter("/obj/node1", "my_float", "My Float", "float", 1.0)
        assert result["created"] is True
        assert result["parm"] == "my_float"

    def test_create_spare_parameter_bad_type(self):
        with pytest.raises(ValueError, match="Unknown parm type"):
            create_spare_parameter("/obj/node1", "x", "X", "badtype")

    def test_create_spare_parameters(self):
        result = create_spare_parameters("/obj/node1", [
            {"name": "a", "label": "A", "parm_type": "float"},
            {"name": "b", "label": "B", "parm_type": "int"},
        ])
        assert len(result["created"]) == 2
