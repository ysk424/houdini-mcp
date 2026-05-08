"""Tests for the get_scene_dossier handler.

Depends on test_server_commands.py to inject the hou mock into sys.modules.
Run via `pytest tests/` (full suite). Standalone run is unsupported.
"""
import sys
from unittest.mock import patch

import pytest

if "hou" not in sys.modules:
    pytest.skip(
        "Requires hou mock from test_server_commands.py — run via `pytest tests/`",
        allow_module_level=True,
    )

import hou  # noqa: E402  (the mock injected above)
from houdinimcp.handlers import dossier  # noqa: E402


# ---------- Mock node helpers ----------

class _MockType:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class _MockNode:
    def __init__(self, name, path, type_name="Object",
                 children=None, flags=None, parms=None,
                 errors=None, warnings=None):
        self._name = name
        self._path = path
        self._type = _MockType(type_name)
        self._children = children if children is not None else []
        self._flags = flags or {}
        self._parms = parms or {}
        self._errors = errors or ()
        self._warnings = warnings or ()
        for c in self._children:
            c._parent_path = path

    def name(self):
        return self._name

    def path(self):
        return self._path

    def type(self):
        return self._type

    def children(self):
        return list(self._children)

    def allSubChildren(self):
        out = []
        for c in self._children:
            out.append(c)
            out.extend(c.allSubChildren())
        return out

    def parm(self, name):
        return self._parms.get(name)

    def errors(self):
        return self._errors

    def warnings(self):
        return self._warnings

    # Flag methods are added dynamically per fixture so missing attrs
    # exercise the getattr() path in _node_flags().
    def add_flag(self, method_name, value):
        setattr(self, method_name, lambda v=value: v)


class _MockParm:
    def __init__(self, value):
        self._v = value

    def evalAsFloat(self):
        return float(self._v)


def _make_root(contexts_spec):
    """contexts_spec: list of (name, child_count, type_name).
    Returns (root_node, dict {path: node})."""
    nodes_by_path = {}
    ctx_nodes = []
    for ctx_name, child_count, type_name in contexts_spec:
        ctx_path = f"/{ctx_name}"
        children = []
        for i in range(child_count):
            cn = _MockNode(f"{ctx_name}_child{i}",
                          f"{ctx_path}/{ctx_name}_child{i}",
                          type_name=type_name)
            cn.add_flag("isDisplayFlagSet", True)
            children.append(cn)
            nodes_by_path[cn._path] = cn
        ctx = _MockNode(ctx_name, ctx_path, type_name="Manager",
                       children=children)
        ctx_nodes.append(ctx)
        nodes_by_path[ctx_path] = ctx
    root = _MockNode("", "/", type_name="Root", children=ctx_nodes)
    nodes_by_path["/"] = root
    return root, nodes_by_path


def _patch_hou_node(nodes_by_path):
    return patch.object(hou, "node", lambda p: nodes_by_path.get(p))


# ---------- Fixtures ----------

@pytest.fixture
def basic_scene():
    """Three contexts with small child counts; supports most tests."""
    root, nodes = _make_root([
        ("obj", 3, "geo"),
        ("mat", 2, "principledshader::2.0"),
        ("out", 1, "karma"),
    ])
    with _patch_hou_node(nodes):
        yield nodes


@pytest.fixture(autouse=False)
def patched_handlers():
    """Patch the read-only dependency handlers used inside dossier.

    Patched values can be overridden per-test by re-patching attributes.
    """
    with patch.object(dossier, "get_scene_info",
                       return_value={"name": "test.hip", "filepath": "/tmp/test.hip",
                                      "fps": 24.0, "start_frame": 1, "end_frame": 240,
                                      "node_count": 6}), \
         patch.object(dossier, "find_error_nodes",
                       return_value={"root": "/", "error_count": 0, "nodes": []}), \
         patch.object(dossier, "get_undo_history",
                       return_value={"undo_stack": [], "redo_stack": [],
                                      "undo_total": 0, "redo_total": 0,
                                      "current_head_label": None}), \
         patch.object(dossier, "list_render_nodes",
                       return_value={"count": 0, "nodes": []}), \
         patch.object(dossier, "get_rop_output_path",
                       return_value={"path_raw": "$HIP/render.exr",
                                      "is_sequence": False,
                                      "frame_range": [1, 240],
                                      "frame_range_active": True,
                                      "category": "image"}), \
         patch.object(dossier, "list_materials",
                       return_value={"path": "/mat", "count": 0, "materials": []}), \
         patch.object(dossier, "get_selection",
                       return_value={"count": 0, "nodes": []}):
        yield


# ---------- Tests ----------

def test_default_call_returns_all_sections(basic_scene, patched_handlers):
    result = dossier.get_scene_dossier()
    for key in ("scene", "contexts", "node_tree", "selection", "errors",
                "undo_history", "rops", "materials", "cameras", "meta"):
        assert key in result, f"missing section: {key}"


def test_include_flags_omit_sections(basic_scene, patched_handlers):
    result = dossier.get_scene_dossier(
        include_node_tree=False,
        include_errors=False,
        include_undo_history=False,
        include_rops=False,
        include_materials=False,
        include_cameras=False,
        include_selection=False,
    )
    for omitted in ("node_tree", "errors", "undo_history", "rops",
                    "materials", "cameras", "selection"):
        assert omitted not in result, f"{omitted} should be omitted"
    for kept in ("scene", "contexts", "meta"):
        assert kept in result, f"{kept} should always be present"


def test_max_node_depth_limits_recursion(patched_handlers):
    # Build a chain /obj/a/b/c/d and walk with depth=2.
    d = _MockNode("d", "/obj/a/b/c/d", "geo")
    c = _MockNode("c", "/obj/a/b/c", "geo", children=[d])
    b = _MockNode("b", "/obj/a/b", "geo", children=[c])
    a = _MockNode("a", "/obj/a", "geo", children=[b])
    obj = _MockNode("obj", "/obj", "Manager", children=[a])
    root = _MockNode("", "/", "Root", children=[obj])
    nodes = {n.path(): n for n in (root, obj, a, b, c, d)}
    with _patch_hou_node(nodes):
        result = dossier.get_scene_dossier(max_node_depth=2)
    # depth=1 → /obj, depth=2 → /obj/a; /obj/a/b should not appear as recursed entry.
    obj_entry = result["node_tree"][0]
    assert obj_entry["path"] == "/obj"
    a_entry = obj_entry["children"][0]
    assert a_entry["path"] == "/obj/a"
    # depth limit hit at /obj/a (depth 2): children list empty + truncated_children.
    assert a_entry["children"] == []
    assert a_entry.get("truncated_children") == 1


def test_max_undo_entries_passes_through(basic_scene, patched_handlers):
    with patch.object(dossier, "get_undo_history") as mock_undo:
        mock_undo.return_value = {"undo_stack": [], "redo_stack": [],
                                   "undo_total": 0, "redo_total": 0,
                                   "current_head_label": None}
        dossier.get_scene_dossier(max_undo_entries=5)
        mock_undo.assert_called_once_with(limit=5)


def test_max_children_per_node_truncates_contexts(patched_handlers):
    # Single context with 200 children; cap at 50.
    root, nodes = _make_root([("obj", 200, "geo")])
    with _patch_hou_node(nodes):
        result = dossier.get_scene_dossier(max_children_per_node=50,
                                            include_node_tree=False)
    obj_ctx = result["contexts"]["/obj"]
    assert obj_ctx["child_count"] == 200
    assert len(obj_ctx["children"]) == 50
    assert result["meta"]["truncations"]["contexts:/obj"] == "50 of 200"


def test_max_children_per_node_truncates_node_tree(patched_handlers):
    # Subnet with many children inside /obj.
    grand_children = [_MockNode(f"g{i}", f"/obj/big/g{i}", "geo")
                       for i in range(150)]
    big = _MockNode("big", "/obj/big", "subnet", children=grand_children)
    obj = _MockNode("obj", "/obj", "Manager", children=[big])
    root = _MockNode("", "/", "Root", children=[obj])
    nodes = {n.path(): n for n in [root, obj, big] + grand_children}
    with _patch_hou_node(nodes):
        result = dossier.get_scene_dossier(max_children_per_node=20,
                                            max_node_depth=5)
    truncations = result["meta"]["truncations"]
    assert truncations.get("node_tree:/obj/big") == "20 of 150"
    obj_entry = result["node_tree"][0]
    big_entry = obj_entry["children"][0]
    assert len(big_entry["children"]) == 20


def test_section_failure_does_not_break_dossier(basic_scene, patched_handlers):
    with patch.object(dossier, "find_error_nodes",
                       side_effect=RuntimeError("simulated boom")):
        result = dossier.get_scene_dossier()
    assert "error" in result["errors"]
    assert "simulated boom" in result["errors"]["error"]
    # Other sections still populated.
    assert "scene" in result
    assert "contexts" in result
    assert "meta" in result


def test_selection_section(basic_scene, patched_handlers):
    fake_selection = {"count": 3, "nodes": [
        {"name": "a", "path": "/obj/a", "type": "geo"},
        {"name": "b", "path": "/obj/b", "type": "geo"},
        {"name": "c", "path": "/obj/c", "type": "geo"},
    ]}
    with patch.object(dossier, "get_selection", return_value=fake_selection):
        result = dossier.get_scene_dossier()
    assert result["selection"]["selected"]["count"] == 3
    assert len(result["selection"]["selected"]["nodes"]) == 3
    assert "current_network" in result["selection"]


def test_meta_has_generated_at_and_houdini_version(basic_scene, patched_handlers):
    result = dossier.get_scene_dossier()
    meta = result["meta"]
    assert "generated_at" in meta
    assert meta["generated_at"].endswith("+00:00")
    assert meta["houdini_version"] == "21.0.700"


def test_rops_returns_slim_output(basic_scene, patched_handlers):
    rops_listing = {"count": 1, "nodes": [
        {"name": "karma1", "path": "/out/karma1", "type": "karma"}
    ]}
    with patch.object(dossier, "list_render_nodes", return_value=rops_listing):
        result = dossier.get_scene_dossier()
    assert len(result["rops"]) == 1
    entry = result["rops"][0]
    assert entry["path"] == "/out/karma1"
    assert entry["type"] == "karma"
    output = entry["output"]
    expected_keys = {"path_raw", "is_sequence", "frame_range",
                      "frame_range_active", "category"}
    assert set(output.keys()) == expected_keys


def test_returns_dict_not_other_type(basic_scene, patched_handlers):
    result = dossier.get_scene_dossier()
    assert isinstance(result, dict)


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, False, "3"])
def test_max_node_depth_rejects_invalid(bad, basic_scene, patched_handlers):
    with pytest.raises(ValueError):
        dossier.get_scene_dossier(max_node_depth=bad)


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, False, "10"])
def test_max_children_per_node_rejects_invalid(bad, basic_scene, patched_handlers):
    with pytest.raises(ValueError):
        dossier.get_scene_dossier(max_children_per_node=bad)
