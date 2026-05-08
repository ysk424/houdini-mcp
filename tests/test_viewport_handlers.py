"""Tests for viewport handlers."""
import sys
import os
import types

import pytest

if "hou" not in sys.modules:
    pytest.skip("hou mock not loaded", allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from houdinimcp.handlers.viewport import (
    list_panes, set_current_network, set_viewport_camera,
)


class TestViewportHandlers:
    def setup_method(self):
        self._orig_ui = sys.modules["hou"].ui
        self._orig_node = sys.modules["hou"].node
        self._orig_attrs = {
            k: getattr(sys.modules["hou"], k, None)
            for k in ("ObjNode", "LopNode", "lopNodeTypeCategory", "paneTabType")
        }

    def teardown_method(self):
        sys.modules["hou"].ui = self._orig_ui
        sys.modules["hou"].node = self._orig_node
        for k, v in self._orig_attrs.items():
            if v is None:
                if hasattr(sys.modules["hou"], k):
                    delattr(sys.modules["hou"], k)
            else:
                setattr(sys.modules["hou"], k, v)

    def test_list_panes(self):
        tab1 = types.SimpleNamespace(
            name=lambda: "viewer1",
            type=lambda: "SceneViewer",
            isCurrentTab=lambda: True,
        )
        sys.modules["hou"].ui = types.SimpleNamespace(
            paneTabs=lambda: [tab1],
            paneTabOfType=lambda t: None,
        )
        result = list_panes()
        assert result["count"] == 1
        assert result["panes"][0]["name"] == "viewer1"

    def test_list_panes_empty(self):
        sys.modules["hou"].ui = types.SimpleNamespace(
            paneTabs=lambda: [],
            paneTabOfType=lambda t: None,
        )
        result = list_panes()
        assert result["count"] == 0

    def test_set_current_network(self):
        node = types.SimpleNamespace(path=lambda: "/obj/geo1")
        editor = types.SimpleNamespace(setCurrentNode=lambda n: None)
        sys.modules["hou"].ui = types.SimpleNamespace(
            paneTabOfType=lambda t: editor,
            paneTabs=lambda: [],
        )
        sys.modules["hou"].paneTabType = types.SimpleNamespace(
            NetworkEditor=1, SceneViewer=0,
        )
        sys.modules["hou"].node = lambda p: node if p == "/obj/geo1" else None
        result = set_current_network("/obj/geo1")
        assert result["path"] == "/obj/geo1"

    def test_set_current_network_not_found(self):
        editor = types.SimpleNamespace(setCurrentNode=lambda n: None)
        sys.modules["hou"].ui = types.SimpleNamespace(
            paneTabOfType=lambda t: editor,
            paneTabs=lambda: [],
        )
        sys.modules["hou"].paneTabType = types.SimpleNamespace(
            NetworkEditor=1, SceneViewer=0,
        )
        sys.modules["hou"].node = lambda p: None
        with pytest.raises(ValueError, match="Node not found"):
            set_current_network("/obj/missing")


class _ObjNodeStub:
    def __init__(self, path):
        self._path = path
    def path(self):
        return self._path


class _LopNodeStub:
    def __init__(self, path, primpath=None, has_primpath=True):
        self._path = path
        self._primpath = primpath
        self._has_primpath = has_primpath
    def path(self):
        return self._path
    def parm(self, name):
        if name == "primpath" and self._has_primpath:
            return types.SimpleNamespace(evalAsString=lambda: self._primpath)
        return None


def _install_node_classes(lop_category=None):
    hou = sys.modules["hou"]
    hou.ObjNode = _ObjNodeStub
    hou.LopNode = _LopNodeStub
    hou.lopNodeTypeCategory = lambda: lop_category if lop_category is not None else "LOP"


def _make_viewer(curViewport, pwd=None, switched_to=None):
    state = {"current": None}
    def setCurrentNode(n):
        state["current"] = n
        if switched_to is not None:
            switched_to.append(n)
    return types.SimpleNamespace(
        curViewport=lambda: curViewport,
        pwd=lambda: pwd,
        setCurrentNode=setCurrentNode,
        _state=state,
    )


class TestSetViewportCamera:
    def setup_method(self):
        self._orig_ui = sys.modules["hou"].ui
        self._orig_node = sys.modules["hou"].node
        self._orig_attrs = {
            k: getattr(sys.modules["hou"], k, None)
            for k in ("ObjNode", "LopNode", "lopNodeTypeCategory", "paneTabType")
        }
        sys.modules["hou"].paneTabType = types.SimpleNamespace(SceneViewer=0)

    def teardown_method(self):
        sys.modules["hou"].ui = self._orig_ui
        sys.modules["hou"].node = self._orig_node
        for k, v in self._orig_attrs.items():
            if v is None:
                if hasattr(sys.modules["hou"], k):
                    delattr(sys.modules["hou"], k)
            else:
                setattr(sys.modules["hou"], k, v)

    def test_no_scene_viewer(self):
        sys.modules["hou"].ui = types.SimpleNamespace(paneTabOfType=lambda t: None)
        with pytest.raises(RuntimeError, match="No scene viewer"):
            set_viewport_camera("/obj/cam1")

    def test_obj_camera(self):
        _install_node_classes()
        cam = _ObjNodeStub("/obj/cam1")
        captured = []
        viewport = types.SimpleNamespace(setCamera=lambda c: captured.append(c))
        viewer = _make_viewer(viewport)
        sys.modules["hou"].ui = types.SimpleNamespace(paneTabOfType=lambda t: viewer)
        sys.modules["hou"].node = lambda p: cam if p == "/obj/cam1" else None

        result = set_viewport_camera("/obj/cam1")
        assert result["kind"] == "obj_camera"
        assert captured == [cam]

    def test_usd_prim_path_passthrough(self):
        _install_node_classes()
        captured = []
        viewport = types.SimpleNamespace(setCamera=lambda c: captured.append(c))
        viewer = _make_viewer(viewport)
        sys.modules["hou"].ui = types.SimpleNamespace(paneTabOfType=lambda t: viewer)
        sys.modules["hou"].node = lambda p: None  # no node resolves

        result = set_viewport_camera("/cameras/camera1")
        assert result == {"camera": "/cameras/camera1", "kind": "usd_prim_path"}
        assert captured == ["/cameras/camera1"]

    def test_lop_camera_auto_switches_context(self):
        _install_node_classes(lop_category="LOP")
        cam = _LopNodeStub("/stage/cam1", primpath="/cameras/camera1")
        captured = []
        viewport = types.SimpleNamespace(setCamera=lambda c: captured.append(c))
        # pwd is /obj-like — childTypeCategory is "OBJ", not LOP → switch needed
        obj_pwd = types.SimpleNamespace(childTypeCategory=lambda: "OBJ")
        switched = []
        viewer = _make_viewer(viewport, pwd=obj_pwd, switched_to=switched)
        sys.modules["hou"].ui = types.SimpleNamespace(paneTabOfType=lambda t: viewer)
        sys.modules["hou"].node = lambda p: cam if p == "/stage/cam1" else None

        result = set_viewport_camera("/stage/cam1")
        assert result["kind"] == "lop_camera"
        assert result["primpath"] == "/cameras/camera1"
        assert result["viewer_context_switched"] is True
        assert switched == [cam]
        assert captured == ["/cameras/camera1"]

    def test_lop_camera_no_switch_when_pwd_is_lopnode(self):
        _install_node_classes(lop_category="LOP")
        cam = _LopNodeStub("/stage/cam1", primpath="/cameras/camera1")
        # pwd is itself a LopNode → already in context
        pwd_lop = _LopNodeStub("/stage")
        captured = []
        viewport = types.SimpleNamespace(setCamera=lambda c: captured.append(c))
        switched = []
        viewer = _make_viewer(viewport, pwd=pwd_lop, switched_to=switched)
        sys.modules["hou"].ui = types.SimpleNamespace(paneTabOfType=lambda t: viewer)
        sys.modules["hou"].node = lambda p: cam if p == "/stage/cam1" else None

        result = set_viewport_camera("/stage/cam1")
        assert result["viewer_context_switched"] is False
        assert switched == []
        assert captured == ["/cameras/camera1"]

    def test_lop_camera_no_switch_when_pwd_child_is_lop_category(self):
        lop_cat = object()
        _install_node_classes(lop_category=lop_cat)
        cam = _LopNodeStub("/stage/cam1", primpath="/cameras/camera1")
        pwd = types.SimpleNamespace(childTypeCategory=lambda: lop_cat)
        captured = []
        viewport = types.SimpleNamespace(setCamera=lambda c: captured.append(c))
        switched = []
        viewer = _make_viewer(viewport, pwd=pwd, switched_to=switched)
        sys.modules["hou"].ui = types.SimpleNamespace(paneTabOfType=lambda t: viewer)
        sys.modules["hou"].node = lambda p: cam if p == "/stage/cam1" else None

        result = set_viewport_camera("/stage/cam1")
        assert result["viewer_context_switched"] is False
        assert switched == []

    def test_lop_camera_missing_primpath_parm(self):
        _install_node_classes()
        cam = _LopNodeStub("/stage/wrapped_cam", has_primpath=False)
        viewport = types.SimpleNamespace(setCamera=lambda c: None)
        viewer = _make_viewer(viewport, pwd=None)
        sys.modules["hou"].ui = types.SimpleNamespace(paneTabOfType=lambda t: viewer)
        sys.modules["hou"].node = lambda p: cam if p == "/stage/wrapped_cam" else None

        with pytest.raises(ValueError, match="primpath"):
            set_viewport_camera("/stage/wrapped_cam")

    def test_unsupported_node_type(self):
        _install_node_classes()
        # SopNode-ish: neither ObjNode nor LopNode
        class _SopNodeStub:
            def path(self): return "/obj/geo1/box1"
        sop = _SopNodeStub()
        viewport = types.SimpleNamespace(setCamera=lambda c: None)
        viewer = _make_viewer(viewport)
        sys.modules["hou"].ui = types.SimpleNamespace(paneTabOfType=lambda t: viewer)
        sys.modules["hou"].node = lambda p: sop

        with pytest.raises(ValueError, match="Unsupported camera node type"):
            set_viewport_camera("/obj/geo1/box1")
