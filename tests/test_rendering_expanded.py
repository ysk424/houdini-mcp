"""Tests for expanded rendering handlers."""
import sys
import os
import types

import pytest

if "hou" not in sys.modules:
    pytest.skip("hou mock not loaded", allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from houdinimcp.handlers.rendering import (
    list_render_nodes, get_render_settings, set_render_settings,
    create_render_node, start_render, get_render_progress,
    screenshot_viewport,
)
import houdinimcp.handlers.rendering as rendering


class MockParm:
    def __init__(self, name, value=""):
        self._name = name
        self._value = value

    def name(self):
        return self._name

    def eval(self):
        return self._value

    def set(self, val):
        self._value = val


class MockRopNode:
    def __init__(self, name, path, node_type="opengl"):
        self._name = name
        self._path = path
        self._type = node_type
        self._parms = {
            "camera": MockParm("camera", "/obj/cam1"),
            "picture": MockParm("picture", "/tmp/render.exr"),
        }

    def name(self):
        return self._name

    def path(self):
        return self._path

    def type(self):
        return types.SimpleNamespace(name=lambda: self._type)

    def parm(self, name):
        return self._parms.get(name)

    def render(self, frame_range=None):
        pass

    def isCooking(self):
        return False


class MockOutNode:
    def __init__(self, children=None):
        self._children = children or []

    def children(self):
        return self._children

    def createNode(self, node_type, node_name=None):
        name = node_name or node_type
        return MockRopNode(name, f"/out/{name}", node_type)


class TestRenderingExpanded:
    def setup_method(self):
        hou = sys.modules["hou"]
        self._orig_node = sys.modules["hou"].node
        self._orig_ui = getattr(hou, "ui", None)
        self._orig_pane_tab_type = getattr(hou, "paneTabType", None)
        self._orig_geometry_viewport_layout = getattr(
            hou, "geometryViewportLayout", None
        )
        self._orig_frame = getattr(hou, "frame", None)
        self._orig_capture_viewwrite = rendering._capture_viewwrite

    def teardown_method(self):
        hou = sys.modules["hou"]
        hou.node = self._orig_node
        hou.ui = self._orig_ui
        hou.paneTabType = self._orig_pane_tab_type
        if self._orig_geometry_viewport_layout is None:
            if hasattr(hou, "geometryViewportLayout"):
                delattr(hou, "geometryViewportLayout")
        else:
            hou.geometryViewportLayout = self._orig_geometry_viewport_layout
        hou.frame = self._orig_frame
        rendering._capture_viewwrite = self._orig_capture_viewwrite

    def test_list_render_nodes(self):
        rop = MockRopNode("mantra1", "/out/mantra1", "ifd")
        out = MockOutNode([rop])
        sys.modules["hou"].node = lambda p: out if p == "/out" else None
        result = list_render_nodes()
        assert result["count"] == 1
        assert result["nodes"][0]["name"] == "mantra1"

    def test_list_render_nodes_no_out(self):
        sys.modules["hou"].node = lambda p: None
        result = list_render_nodes()
        assert result["count"] == 0

    def test_get_render_settings(self):
        rop = MockRopNode("rop1", "/out/rop1")
        sys.modules["hou"].node = lambda p: rop if p == "/out/rop1" else None
        result = get_render_settings("/out/rop1")
        assert "camera" in result["settings"]

    def test_set_render_settings(self):
        rop = MockRopNode("rop1", "/out/rop1")
        sys.modules["hou"].node = lambda p: rop if p == "/out/rop1" else None
        result = set_render_settings("/out/rop1", {"camera": "/obj/cam2"})
        assert "camera" in result["changed"]

    def test_create_render_node(self):
        out = MockOutNode()
        sys.modules["hou"].node = lambda p: out if p == "/out" else None
        result = create_render_node("karma", name="karma1")
        assert result["type"] == "karma"

    def test_start_render(self):
        rop = MockRopNode("rop1", "/out/rop1")
        sys.modules["hou"].node = lambda p: rop if p == "/out/rop1" else None
        result = start_render("/out/rop1")
        assert result["rendering"] is True

    def test_get_render_progress(self):
        rop = MockRopNode("rop1", "/out/rop1")
        sys.modules["hou"].node = lambda p: rop if p == "/out/rop1" else None
        result = get_render_progress("/out/rop1")
        assert result["is_cooking"] is False

    def test_screenshot_uses_exact_viewwrite_target(self):
        hou = sys.modules["hou"]
        hou.paneTabType = types.SimpleNamespace(SceneViewer=1)
        hou.geometryViewportLayout = types.SimpleNamespace(Single="Single")
        hou.frame = lambda: 12

        class Viewport:
            def __init__(self, name):
                self._name = name
            def name(self):
                return self._name

        viewport = Viewport("solaris.persp1")
        viewer = types.SimpleNamespace(
            name=lambda: "panetab7",
            type=lambda: hou.paneTabType.SceneViewer,
            isCurrentTab=lambda: True,
            viewports=lambda: [viewport],
            curViewport=lambda: viewport,
            viewportLayout=lambda: "Quad",
            pwd=lambda: types.SimpleNamespace(childTypeCategory=lambda: "LOP"),
        )
        hou.lopNodeTypeCategory = lambda: "LOP"
        hou.objNodeTypeCategory = lambda: "OBJ"
        hou.LopNode = type("LopNode", (), {})
        hou.ObjNode = type("ObjNode", (), {})
        hou.ui = types.SimpleNamespace(
            curDesktop=lambda: types.SimpleNamespace(name=lambda: "Solaris"),
            paneTabs=lambda: [viewer],
        )

        calls = []
        def fake_capture(target, output_path, frame, width, height):
            calls.append((target, frame, width, height))
            with open(output_path, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n" + b"test")

        rendering._capture_viewwrite = fake_capture
        result = screenshot_viewport(
            width=800,
            height=600,
            viewport_name="Solaris.panetab7.solaris.persp1",
        )

        assert result["status"] == "success"
        assert result["capture_method"] == "viewwrite"
        assert result["viewwrite_target_used"] == "Solaris.panetab7.solaris.persp1"
        assert calls == [("Solaris.panetab7.solaris.persp1", 12, 800, 600)]

    def test_screenshot_reports_ambiguous_viewport_name(self):
        hou = sys.modules["hou"]
        hou.paneTabType = types.SimpleNamespace(SceneViewer=1)

        class Viewport:
            def name(self):
                return "persp"

        def make_viewer(name):
            viewport = Viewport()
            return types.SimpleNamespace(
                name=lambda: name,
                type=lambda: hou.paneTabType.SceneViewer,
                isCurrentTab=lambda: False,
                viewports=lambda: [viewport],
                curViewport=lambda: viewport,
                pwd=lambda: None,
            )

        hou.ui = types.SimpleNamespace(
            curDesktop=lambda: types.SimpleNamespace(name=lambda: "Solaris"),
            paneTabs=lambda: [make_viewer("panetab1"), make_viewer("panetab2")],
        )

        result = screenshot_viewport(viewport_name="persp")

        assert result["status"] == "error"
        assert "ambiguous" in result["message"]
        assert "Solaris.panetab1.persp" in result["message"]
