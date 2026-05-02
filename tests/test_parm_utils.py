"""Tests for the shared parm_label helper.

Confirms the helper reads label off ParmTemplate, NOT off Parm/ParmTuple,
matching the real hou API in 21.x where Parm has no .label() method.
"""
import sys
import os
import types

import pytest

if "hou" not in sys.modules:
    pytest.skip("hou mock not loaded", allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from houdinimcp.handlers._parm_utils import parm_label


class FakeTemplate:
    def __init__(self, label):
        self._label = label
    def label(self):
        return self._label


class FakeParm:
    """Mimics real hou.Parm: NO .label() method."""
    def __init__(self, name, label):
        self._name = name
        self._template = FakeTemplate(label)
    def name(self):
        return self._name
    def parmTemplate(self):
        return self._template


class FakeParmTuple(FakeParm):
    """ParmTuple has the same parmTemplate() shape."""


def test_parm_label_reads_from_template():
    p = FakeParm("tx", "Translate X")
    assert parm_label(p) == "Translate X"


def test_parm_label_works_for_parmtuple():
    pt = FakeParmTuple("t", "Translate")
    assert parm_label(pt) == "Translate"


def test_parm_label_does_not_call_parm_label_method():
    """Regression: helper must not rely on parm.label() (does not exist on real hou.Parm)."""
    p = FakeParm("sizex", "Size X")
    # FakeParm has no .label() attribute at all - mirrors real hou.Parm.
    assert not hasattr(p, "label")
    assert parm_label(p) == "Size X"


def test_parm_label_falls_back_to_name_when_template_none():
    class NoTemplateParm:
        def name(self):
            return "x"
        def parmTemplate(self):
            return None
    assert parm_label(NoTemplateParm()) == "x"
