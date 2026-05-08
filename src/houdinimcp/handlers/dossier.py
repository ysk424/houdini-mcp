"""One-shot read-only snapshot of the current Houdini scene.

Aggregates existing read-only handlers into a single structured payload so
clients can avoid many small inspection calls. Per-section try/except keeps
partial results available when a single source fails.
"""
from datetime import datetime, timezone

import hou

from .scene import get_scene_info
from .nodes import find_error_nodes
from .context import get_selection
from .undo import get_undo_history
from .rendering import list_render_nodes, get_rop_output_path
from .materials import list_materials


_FLAG_METHODS = [
    ("isDisplayFlagSet", "display"),
    ("isRenderFlagSet", "render"),
    ("isBypassed", "bypass"),
    ("isTemplateFlagSet", "template"),
]


def _section_error(exc):
    return {"error": str(exc)[:500]}


def _node_flags(node):
    flags = {}
    for method_name, key in _FLAG_METHODS:
        method = getattr(node, method_name, None)
        if method is None:
            continue
        try:
            flags[key] = method()
        except Exception:
            pass
    return flags


def _get_current_network():
    try:
        pane = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
        if pane is None:
            return None
        return pane.pwd().path()
    except Exception:
        return None


def _build_scene_section():
    info = get_scene_info()
    if isinstance(info, dict) and "error" in info:
        return info
    out = {
        "hip_name": info.get("name"),
        "hip_path": info.get("filepath"),
        "fps": info.get("fps"),
        "frame_range": [info.get("start_frame"), info.get("end_frame")],
        "current_frame": hou.frame(),
        "playback_range": list(hou.playbar.playbackRange()),
        "node_count_total": info.get("node_count"),
    }
    return out


def _build_contexts_section(max_children_per_node, truncations):
    root = hou.node("/")
    if root is None:
        return {}
    out = {}
    for ctx in root.children():
        ctx_path = ctx.path()
        children = list(ctx.children())
        total = len(children)
        if total > max_children_per_node:
            truncations[f"contexts:{ctx_path}"] = (
                f"{max_children_per_node} of {total}"
            )
            children = children[:max_children_per_node]
        out[ctx_path] = {
            "child_count": total,
            "children": [c.name() for c in children],
        }
    return out


def _build_node_tree(max_node_depth, max_children_per_node, truncations):
    root = hou.node("/")
    if root is None:
        return []

    def walk(node, depth):
        children = list(node.children())
        total = len(children)
        if total > max_children_per_node:
            truncations[f"node_tree:{node.path()}"] = (
                f"{max_children_per_node} of {total}"
            )
            children = children[:max_children_per_node]

        entry = {
            "name": node.name(),
            "path": node.path(),
            "type": node.type().name(),
            "flags": _node_flags(node),
        }

        if depth >= max_node_depth:
            entry["children"] = []
            if children:
                entry["truncated_children"] = total
            return entry

        entry["children"] = [walk(c, depth + 1) for c in children]
        return entry

    return [walk(c, 1) for c in root.children()]


def _slim_rop_output(rop_path):
    raw = get_rop_output_path(rop_path, expand=False)
    return {
        "path_raw": raw.get("path_raw"),
        "is_sequence": raw.get("is_sequence"),
        "frame_range": raw.get("frame_range"),
        "frame_range_active": raw.get("frame_range_active"),
        "category": raw.get("category"),
    }


def _build_rops_section():
    listing = list_render_nodes()
    rops = listing.get("nodes", []) if isinstance(listing, dict) else []
    out = []
    for rop in rops:
        entry = {
            "path": rop.get("path"),
            "name": rop.get("name"),
            "type": rop.get("type"),
        }
        try:
            entry["output"] = _slim_rop_output(rop["path"])
        except Exception as e:
            entry["output"] = _section_error(e)
        out.append(entry)
    return out


def _build_materials_section():
    raw = list_materials("/mat")
    return raw.get("materials", [])


def _build_cameras_section():
    obj = hou.node("/obj")
    if obj is None:
        return []
    out = []
    for node in obj.allSubChildren():
        try:
            if node.type().name() != "cam":
                continue
        except Exception:
            continue
        entry = {
            "path": node.path(),
            "name": node.name(),
        }
        for parm_name in ("resx", "resy", "focal", "aperture"):
            parm = node.parm(parm_name)
            entry[parm_name] = parm.evalAsFloat() if parm is not None else None
        out.append(entry)
    return out


def get_scene_dossier(
    include_node_tree=True,
    include_errors=True,
    include_undo_history=True,
    include_rops=True,
    include_materials=True,
    include_cameras=True,
    include_selection=True,
    max_node_depth=3,
    max_undo_entries=20,
    max_children_per_node=100,
):
    """One-shot read-only scene snapshot. See module docstring for shape."""
    if (not isinstance(max_node_depth, int)
            or isinstance(max_node_depth, bool)
            or max_node_depth < 1):
        raise ValueError(
            "max_node_depth must be a positive integer >= 1 (got {!r})".format(
                max_node_depth)
        )
    if (not isinstance(max_children_per_node, int)
            or isinstance(max_children_per_node, bool)
            or max_children_per_node < 1):
        raise ValueError(
            "max_children_per_node must be a positive integer >= 1 (got {!r})".format(
                max_children_per_node)
        )

    truncations = {}
    out = {}

    try:
        out["scene"] = _build_scene_section()
    except Exception as e:
        out["scene"] = _section_error(e)

    try:
        out["contexts"] = _build_contexts_section(
            max_children_per_node, truncations)
    except Exception as e:
        out["contexts"] = _section_error(e)

    if include_node_tree:
        try:
            out["node_tree"] = _build_node_tree(
                max_node_depth, max_children_per_node, truncations)
        except Exception as e:
            out["node_tree"] = _section_error(e)

    if include_selection:
        try:
            out["selection"] = {
                "selected": get_selection(),
                "current_network": _get_current_network(),
            }
        except Exception as e:
            out["selection"] = _section_error(e)

    if include_errors:
        try:
            out["errors"] = find_error_nodes("/")
        except Exception as e:
            out["errors"] = _section_error(e)

    if include_undo_history:
        try:
            out["undo_history"] = get_undo_history(limit=max_undo_entries)
        except Exception as e:
            out["undo_history"] = _section_error(e)

    if include_rops:
        try:
            out["rops"] = _build_rops_section()
        except Exception as e:
            out["rops"] = _section_error(e)

    if include_materials:
        try:
            out["materials"] = _build_materials_section()
        except Exception as e:
            out["materials"] = _section_error(e)

    if include_cameras:
        try:
            out["cameras"] = _build_cameras_section()
        except Exception as e:
            out["cameras"] = _section_error(e)

    try:
        version = hou.applicationVersionString()
    except Exception:
        version = "unknown"

    out["meta"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "houdini_version": version,
        "truncations": truncations,
    }
    return out
