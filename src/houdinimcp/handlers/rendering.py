"""Rendering handlers (OpenGL, Karma, Mantra, flipbook)."""
import base64
import os
import tempfile
import time
import traceback
from pathlib import Path

import hou
from ..HoudiniMCPRender import render_single_view, render_quad_view, render_specific_camera


def _process_rendered_image(filepath, camera_path=None, view_name=None):
    """Return metadata for a rendered image file."""
    if not filepath or not os.path.exists(filepath):
        return {"status": "error", "message": f"Rendered file not found: {filepath}",
                "origin": "_process_rendered_image"}

    _, ext = os.path.splitext(filepath)
    fmt = ext[1:].lower() if ext else 'unknown'

    resolution = [0, 0]
    if camera_path:
        cam_node = hou.node(camera_path)
        if cam_node and cam_node.parm("resx") and cam_node.parm("resy"):
            resolution = [cam_node.parm("resx").eval(), cam_node.parm("resy").eval()]

    result_data = {
        "status": "success",
        "format": fmt,
        "resolution": resolution,
        "filepath": filepath,
    }
    if view_name:
        result_data["view_name"] = view_name
    return result_data


def handle_render_single_view(orthographic=False, rotation=(0, 90, 0),
                               render_path=None, render_engine="opengl",
                               karma_engine="cpu"):
    """Handles the 'render_single_view' command."""
    if not render_path:
        render_path = tempfile.gettempdir()
    try:
        if isinstance(rotation, list):
            rotation = tuple(rotation)
        filepath = render_single_view(
            orthographic=orthographic,
            rotation=rotation,
            render_path=render_path,
            render_engine=render_engine,
            karma_engine=karma_engine
        )
        return _process_rendered_image(filepath, "/obj/MCP_CAMERA")
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": f"Render Single View Failed: {str(e)}",
                "origin": "handle_render_single_view"}


def handle_render_quad_view(orthographic=True, render_path=None,
                             render_engine="opengl", karma_engine="cpu"):
    """Handles the 'render_quad_view' command."""
    if not render_path:
        render_path = tempfile.gettempdir()
    try:
        filepaths = render_quad_view(
            orthographic=orthographic,
            render_path=render_path,
            render_engine=render_engine,
            karma_engine=karma_engine
        )
        results = []
        camera_path = "/obj/MCP_CAMERA"
        for fp in filepaths:
            view_name = None
            try:
                filename = os.path.basename(fp)
                parts = filename.split('_')
                if len(parts) > 2:
                    view_name = parts[2]
            except Exception:
                pass
            results.append(_process_rendered_image(fp, camera_path, view_name))
        return {"status": "success", "results": results}
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": f"Render Quad View Failed: {str(e)}",
                "origin": "handle_render_quad_view"}


def handle_render_specific_camera(camera_path, render_path=None,
                                   render_engine="opengl", karma_engine="cpu"):
    """Handles the 'render_specific_camera' command."""
    if not render_path:
        render_path = tempfile.gettempdir()
    if not camera_path or not hou.node(camera_path):
        return {"status": "error",
                "message": f"Camera path '{camera_path}' is invalid or node not found.",
                "origin": "handle_render_specific_camera"}
    try:
        filepath = render_specific_camera(
            camera_path=camera_path,
            render_path=render_path,
            render_engine=render_engine,
            karma_engine=karma_engine
        )
        return _process_rendered_image(filepath, camera_path)
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": f"Render Specific Camera Failed: {str(e)}",
                "origin": "handle_render_specific_camera"}


def list_render_nodes():
    """List all ROP (render) nodes in the scene."""
    out_node = hou.node("/out")
    if not out_node:
        return {"count": 0, "nodes": []}
    nodes = []
    for child in out_node.children():
        nodes.append({
            "name": child.name(),
            "path": child.path(),
            "type": child.type().name(),
        })
    return {"count": len(nodes), "nodes": nodes}


def get_render_settings(path):
    """Get render settings from a ROP node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    settings = {}
    for parm_name in ["camera", "picture", "res_overridex", "res_overridey",
                       "trange", "f1", "f2", "f3"]:
        parm = node.parm(parm_name)
        if parm:
            settings[parm_name] = str(parm.eval())
    return {"path": path, "type": node.type().name(), "settings": settings}


_IMAGE_EXTS = (".exr", ".jpg", ".jpeg", ".png", ".tif", ".tiff",
               ".tga", ".pic", ".rat", ".deepexr", ".deepscan")

_KNOWN_OUTPUT_PARMS = {
    "opengl":        ("picture",),
    "karma":         ("picture",),
    "usdrender_rop": ("outputimage",),
    "ifd":           ("vm_picture",),
    "arnold":        ("ar_picture",),
    "Redshift_ROP":  ("RS_outputFileNamePrefix",),
    "vray_renderer": ("SettingsOutput_img_file",),
    "geometry":      ("sopoutput",),
    "rop_geometry":  ("sopoutput",),
    "alembic":       ("filename",),
    "rop_alembic":   ("filename",),
    "usd":           ("lopoutput", "outputfile"),
    "usdexport":     ("lopoutput", "outputfile"),
    "comp":          ("copoutput",),
}

_NON_IMAGE_TYPE_CATEGORY = {
    "geometry": "geometry", "rop_geometry": "geometry",
    "alembic": "geometry", "rop_alembic": "geometry",
    "usd": "usd", "usdexport": "usd",
    "comp": "comp",
}

_TAG_SCAN_REJECT_PREFIXES = ("husk_", "soho_", "vm_tmp", "dcm")
_TAG_SCAN_REJECT_CONTAINS = ("_storage", "_chromefile", "_stdout", "_stderr")


def _list_filereference_parms(node):
    out = []
    for p in node.parms():
        pt = p.parmTemplate()
        if pt.type() != hou.parmTemplateType.String:
            continue
        if pt.stringType() != hou.stringParmType.FileReference:
            continue
        out.append(p)
    return out


def _tag_scan_candidates(node):
    candidates = []
    for p in _list_filereference_parms(node):
        tags = p.parmTemplate().tags() or {}
        is_write = (tags.get("filechooser_mode") == "write"
                    or "filechooser_pattern" in tags)
        if not is_write:
            continue
        name = p.name()
        if any(name.startswith(pre) for pre in _TAG_SCAN_REJECT_PREFIXES):
            continue
        if any(s in name for s in _TAG_SCAN_REJECT_CONTAINS):
            continue
        if not p.unexpandedString():
            continue
        candidates.append(p)
    return candidates


def _classify(path_str, node_type):
    if node_type in _NON_IMAGE_TYPE_CATEGORY:
        return _NON_IMAGE_TYPE_CATEGORY[node_type]
    if not path_str:
        return "unknown"
    ext = os.path.splitext(path_str)[1].lower()
    return "image" if ext in _IMAGE_EXTS else "unknown"


def _empty_payload(path, node_type, parm, param_source, tag_cands,
                   raw, category, warnings, hint=None):
    return {
        "node": path,
        "node_type": node_type,
        "param_used": parm.name() if parm else None,
        "param_source": param_source,
        "tag_scan_candidates": tag_cands,
        "path_raw": raw,
        "path_resolved": None,
        "frame_used": None,
        "is_sequence": False,
        "frame_range": None,
        "frame_range_active": False,
        "first_frame_path": None,
        "last_frame_path": None,
        "representative_path": None,
        "category": category,
        "exists": False,
        "mtime": None,
        "size_bytes": None,
        "warnings": warnings,
        "hint": hint,
    }


def get_rop_output_path(path, picture_param=None, frame=None,
                        expand=True, min_mtime=None):
    """Resolve a ROP's primary output path with sequence + freshness metadata.

    Tiers: explicit picture_param override → known parm-name map per ROP type
    → tag-based scan of FileReference write parms.
    """
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")

    node_type = node.type().name()
    warnings = []
    tag_cands = None
    parm = None
    param_source = None

    if picture_param is not None:
        parm = node.parm(picture_param)
        if not parm:
            available = [p.name() for p in _list_filereference_parms(node)]
            raise ValueError(
                f"Parameter '{picture_param}' not found on {path}. "
                f"Available FileReference parms: {available}"
            )
        param_source = "override"
    else:
        for cand in _KNOWN_OUTPUT_PARMS.get(node_type, ()):
            p = node.parm(cand)
            if p:
                parm = p
                param_source = "known_map"
                break
        if parm is None:
            scan = _tag_scan_candidates(node)
            if scan:
                parm = scan[0]
                param_source = "tag_scan"
                tag_cands = [p.name() for p in scan]

    if parm is None:
        raise ValueError(
            f"Could not locate output parameter on {path} (type={node_type}). "
            f"Pass picture_param= explicitly."
        )

    pt = parm.parmTemplate()
    if pt.type() != hou.parmTemplateType.String:
        raise ValueError(
            f"Parameter '{parm.name()}' on {path} is not a String parm "
            f"(got {pt.type()})"
        )

    raw = parm.unexpandedString()

    if raw in ("ip", "md"):
        return _empty_payload(path, node_type, parm, param_source, tag_cands,
                              raw, "mplay", warnings)

    if param_source == "override" and raw == "":
        return _empty_payload(path, node_type, parm, param_source, tag_cands,
                              "", "unknown", warnings + ["override_param_empty"])

    if node_type == "usdrender_rop" and parm.name() == "outputimage" and raw == "":
        rs = node.parm("rendersettings")
        return _empty_payload(path, node_type, parm, param_source, tag_cands,
                              "", "usd_render_via_settings", warnings,
                              hint=rs.eval() if rs else None)

    is_sequence = parm.evalAtFrame(1) != parm.evalAtFrame(2)

    trange_p = node.parm("trange")
    f1_p, f2_p = node.parm("f1"), node.parm("f2")
    frame_range_active = bool(trange_p and trange_p.eval() != 0)
    frame_range = [int(f1_p.eval()), int(f2_p.eval())] if (f1_p and f2_p) else None

    if expand:
        frame_used = frame if frame is not None else int(hou.frame())
        path_resolved = parm.evalAtFrame(frame_used)
    else:
        frame_used = None
        path_resolved = None

    first_frame_path = None
    last_frame_path = None
    if is_sequence and frame_range_active and frame_range:
        first_frame_path = parm.evalAtFrame(frame_range[0])
        last_frame_path = parm.evalAtFrame(frame_range[1])

    if is_sequence and frame_range_active and first_frame_path is not None:
        representative_path = first_frame_path
    else:
        representative_path = path_resolved

    exists = False
    mtime = None
    size_bytes = None
    if representative_path and os.path.exists(representative_path):
        mtime = os.path.getmtime(representative_path)
        size_bytes = os.path.getsize(representative_path)
        exists = True
        if min_mtime is not None and mtime <= min_mtime:
            exists = False

    if hou.hipFile.name() == "untitled.hip" and ("$HIP" in raw or "$HIPNAME" in raw):
        warnings.append("hip_unsaved")

    category = _classify(path_resolved or representative_path or raw, node_type)

    return {
        "node": path,
        "node_type": node_type,
        "param_used": parm.name(),
        "param_source": param_source,
        "tag_scan_candidates": tag_cands,
        "path_raw": raw,
        "path_resolved": path_resolved,
        "frame_used": frame_used,
        "is_sequence": is_sequence,
        "frame_range": frame_range,
        "frame_range_active": frame_range_active,
        "first_frame_path": first_frame_path,
        "last_frame_path": last_frame_path,
        "representative_path": representative_path,
        "category": category,
        "exists": exists,
        "mtime": mtime,
        "size_bytes": size_bytes,
        "warnings": warnings,
        "hint": None,
    }


def set_render_settings(path, settings):
    """Set render settings on a ROP node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    changes = []
    for name, value in settings.items():
        parm = node.parm(name)
        if parm:
            parm.set(value)
            changes.append(name)
    return {"path": path, "changed": changes}


def create_render_node(render_type="opengl", name=None, parent_path="/out"):
    """Create a ROP node."""
    parent = hou.node(parent_path)
    if not parent:
        raise ValueError(f"Parent not found: {parent_path}")
    node = parent.createNode(render_type, node_name=name)
    return {"path": node.path(), "name": node.name(), "type": render_type}


def start_render(path, frame_range=None):
    """Start a render from a ROP node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    if frame_range and len(frame_range) == 2:
        node.render(frame_range=(frame_range[0], frame_range[1]))
    else:
        node.render()
    return {"path": path, "rendering": True}


def get_render_progress(path):
    """Get render progress from a ROP node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    return {
        "path": path,
        "is_cooking": node.isCooking() if hasattr(node, "isCooking") else False,
    }


def render_flipbook(frame_range=None, output=None, resolution=None):
    """Render a flipbook sequence from the viewport."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found for flipbook")
    settings = viewer.flipbookSettings().stash()
    if frame_range and len(frame_range) == 2:
        settings.frameRange((frame_range[0], frame_range[1]))
    if not output:
        output = os.path.join(tempfile.gettempdir(), "mcp_flipbook.$F4.jpg")
    settings.output(output)
    if resolution and len(resolution) == 2:
        settings.useResolution(True)
        settings.resolution((resolution[0], resolution[1]))
    viewer.flipbook(settings=settings)
    return {"flipbook": True, "output": output}


_SCREENSHOT_MIN_DIM = 128
_SCREENSHOT_MAX_DIM = 4096
_SCREENSHOT_MAX_PIXEL_AREA = 8_000_000
_SCREENSHOT_TESTED_DIM = 1920


def _desktop_name():
    try:
        desktop = hou.ui.curDesktop()
        if desktop is not None and hasattr(desktop, "name"):
            return desktop.name()
    except Exception:
        pass
    return None


def _scene_viewers():
    return [t for t in hou.ui.paneTabs()
            if t.type() == hou.paneTabType.SceneViewer]


def _viewport_target_paths(viewer, viewport):
    """Return likely hscript/viewwrite viewport target names."""
    pane = viewer.name()
    vp = viewport.name()
    targets = []
    desktop = _desktop_name()
    contexts = _viewport_context_names(viewer)
    if desktop:
        if "." in vp:
            targets.append(f"{desktop}.{pane}.{vp}")
        for context in contexts:
            if not vp.startswith(f"{context}."):
                targets.append(f"{desktop}.{pane}.{context}.{vp}")
        targets.append(f"{desktop}.{pane}.{vp}")
    if "." in vp:
        targets.append(f"{pane}.{vp}")
    for context in contexts:
        if not vp.startswith(f"{context}."):
            targets.append(f"{pane}.{context}.{vp}")
    targets.append(f"{pane}.{vp}")
    targets.append(vp)
    return list(dict.fromkeys(targets))


def _viewport_context_names(viewer):
    names = []
    try:
        pwd = viewer.pwd()
    except Exception:
        pwd = None

    if pwd is not None:
        try:
            if isinstance(pwd, hou.LopNode):
                names.append("solaris")
            elif isinstance(pwd, hou.ObjNode):
                names.append("world")
            else:
                category = pwd.childTypeCategory()
                if category == hou.lopNodeTypeCategory():
                    names.append("solaris")
                elif category == hou.objNodeTypeCategory():
                    names.append("world")
        except Exception:
            pass

    for fallback in ("world", "solaris"):
        if fallback not in names:
            names.append(fallback)
    return names


def _available_viewport_targets(scene_viewer_panes=None):
    panes = scene_viewer_panes if scene_viewer_panes is not None else _scene_viewers()
    out = []
    for viewer in panes:
        try:
            cur = viewer.curViewport()
            cur_name = cur.name() if cur is not None else None
        except Exception:
            cur_name = None
        for viewport in viewer.viewports():
            paths = _viewport_target_paths(viewer, viewport)
            out.append({
                "pane_tab_name": viewer.name(),
                "viewport_name": viewport.name(),
                "is_current": viewport.name() == cur_name,
                "targets": paths,
                "viewwrite_target": paths[0],
            })
    return out


def _resolve_screenshot_viewer(scene_viewer_panes, viewport_name=None,
                               pane_tab_name=None):
    """Resolve screenshot target with deterministic errors and hscript path."""
    if pane_tab_name is not None:
        viewer = next((p for p in scene_viewer_panes
                       if p.name() == pane_tab_name), None)
        if viewer is None:
            available = [p.name() for p in scene_viewer_panes]
            return None, None, None, {
                "status": "error",
                "message": f"Pane tab '{pane_tab_name}' not found. "
                           f"Available SceneViewer panes: {available}",
                "origin": "screenshot_viewport",
            }
        viewers = [viewer]
    else:
        current = [p for p in scene_viewer_panes
                   if hasattr(p, "isCurrentTab") and p.isCurrentTab()]
        viewers = current or scene_viewer_panes
        viewer = viewers[0]

    if viewport_name is not None:
        matches = []
        for candidate_viewer in viewers:
            for viewport in candidate_viewer.viewports():
                targets = _viewport_target_paths(candidate_viewer, viewport)
                if viewport_name == viewport.name() or viewport_name in targets:
                    matches.append((candidate_viewer, viewport, targets[0]))

        if not matches and pane_tab_name is None:
            for candidate_viewer in scene_viewer_panes:
                for viewport in candidate_viewer.viewports():
                    targets = _viewport_target_paths(candidate_viewer, viewport)
                    if viewport_name == viewport.name() or viewport_name in targets:
                        matches.append((candidate_viewer, viewport, targets[0]))

        if len(matches) > 1:
            available = _available_viewport_targets(scene_viewer_panes)
            return None, None, None, {
                "status": "error",
                "message": f"Viewport name '{viewport_name}' is ambiguous. "
                           "Use pane_tab_name plus viewport_name, or pass an "
                           "exact viewwrite target such as "
                           "'Solaris.panetab7.solaris.persp1'. "
                           f"Available targets: {available}",
                "origin": "screenshot_viewport",
            }
        if not matches:
            available = _available_viewport_targets(scene_viewer_panes)
            return None, None, None, {
                "status": "error",
                "message": f"Viewport '{viewport_name}' not found. "
                           f"Available targets: {available}",
                "origin": "screenshot_viewport",
            }
        return matches[0][0], matches[0][1], matches[0][2], None

    viewport = viewer.curViewport()
    if viewport is None:
        return None, None, None, {
            "status": "error",
            "message": "SceneViewer has no current viewport",
            "origin": "screenshot_viewport",
        }
    return viewer, viewport, _viewport_target_paths(viewer, viewport)[0], None


def _hscript_quote(value):
    return '"' + str(value).replace("\\", "/").replace('"', '\\"') + '"'


def _capture_viewwrite(target, output_path, frame, width, height):
    command = (
        f"viewwrite -f {int(frame)} {int(frame)} "
        f"-r {int(width)} {int(height)} "
        f"{target} {_hscript_quote(output_path)}"
    )
    out, err = hou.hscript(command)
    if err:
        raise RuntimeError(err)
    return out


def _capture_viewwrite_any(targets, output_path, frame, width, height):
    errors = []
    for target in targets:
        try:
            _capture_viewwrite(target, output_path, frame, width, height)
            return target
        except Exception as e:
            errors.append(f"{target}: {e}")
    raise RuntimeError("; ".join(errors))


def screenshot_viewport(width=800, height=600, viewport_name=None,
                        pane_tab_name=None, frame=None):
    """Capture the current SceneViewer viewport as a PNG via OpenGL flipbook.

    Returns base64-encoded PNG bytes plus metadata. No scene side-effects:
    the user's flipbook settings are stashed, the playbar is not moved
    (flipbook's frameRange is self-contained), and temp files are deleted.
    """
    t0 = time.time()

    for label, value in (("width", width), ("height", height)):
        if not isinstance(value, int) or isinstance(value, bool):
            return {"status": "error",
                    "message": f"{label} must be int, got {type(value).__name__}",
                    "origin": "screenshot_viewport"}
        if value < _SCREENSHOT_MIN_DIM or value > _SCREENSHOT_MAX_DIM:
            return {"status": "error",
                    "message": f"{label} must be in [{_SCREENSHOT_MIN_DIM}, "
                               f"{_SCREENSHOT_MAX_DIM}], got {value}",
                    "origin": "screenshot_viewport"}

    if width * height > _SCREENSHOT_MAX_PIXEL_AREA:
        return {"status": "error",
                "message": f"width*height must be <= {_SCREENSHOT_MAX_PIXEL_AREA}, "
                           f"got {width*height} ({width}x{height})",
                "origin": "screenshot_viewport"}

    if frame is not None:
        if not isinstance(frame, int) or isinstance(frame, bool):
            return {"status": "error",
                    "message": f"frame must be int or null, got {type(frame).__name__}",
                    "origin": "screenshot_viewport"}

    if hou.ui.curDesktop() is None:
        return {"status": "error",
                "message": "No Houdini desktop available (running headless?)",
                "origin": "screenshot_viewport"}

    scene_viewer_panes = _scene_viewers()
    if not scene_viewer_panes:
        return {"status": "error",
                "message": "No SceneViewer pane found. "
                           "Open a SceneViewer in the active desktop.",
                "origin": "screenshot_viewport"}

    viewer, viewport, viewwrite_target, error = _resolve_screenshot_viewer(
        scene_viewer_panes,
        viewport_name=viewport_name,
        pane_tab_name=pane_tab_name,
    )
    if error is not None:
        return error

    # In a Single layout only curViewport is actually drawn; the other
    # SceneViewer.viewports() entries exist as off-screen stubs and asking
    # flipbook to capture them silently produces no file (or, in some
    # builds, hangs the renderer until the bridge times out).
    if (viewer.viewportLayout() == hou.geometryViewportLayout.Single
            and viewport.name() != viewer.curViewport().name()):
        cur_name = viewer.curViewport().name()
        return {"status": "error",
                "message": (f"Viewport '{viewport.name()}' is not visible "
                            f"in the current Single layout (only '{cur_name}' "
                            f"is drawn). Either omit viewport_name to capture "
                            f"the current viewport, or switch the SceneViewer "
                            f"to a multi-view layout (Quad, Double, Triple)."),
                "origin": "screenshot_viewport"}

    frame_used = int(frame) if frame is not None else int(hou.frame())

    warnings = []
    if width > _SCREENSHOT_TESTED_DIM or height > _SCREENSHOT_TESTED_DIM:
        warnings.append(
            f"resolution {width}x{height} exceeds tested range "
            f"({_SCREENSHOT_TESTED_DIM}); Indie watermark unverified above this"
        )

    tmpdir = Path(tempfile.mkdtemp(prefix="mcp_viewport_"))
    template = str(tmpdir / "shot.$F4.png").replace("\\", "/")
    expected_file = tmpdir / f"shot.{frame_used:04d}.png"
    viewwrite_file = tmpdir / "shot.png"
    capture_method = "viewwrite"
    viewwrite_targets = _viewport_target_paths(viewer, viewport)

    try:
        try:
            viewwrite_target = _capture_viewwrite_any(
                viewwrite_targets,
                str(viewwrite_file),
                frame_used,
                width,
                height,
            )
            expected_file = viewwrite_file
        except Exception as e:
            warnings.append(f"viewwrite failed, fell back to flipbook: {e}")
            capture_method = "flipbook"
            try:
                settings = viewer.flipbookSettings().stash()
                settings.useResolution(True)
                settings.resolution((width, height))
                settings.outputToMPlay(False)
                settings.output(template)
                settings.frameRange((frame_used, frame_used))
                viewer.flipbook(viewport, settings)
            except Exception as flipbook_error:
                return {"status": "error",
                        "message": (f"Viewport capture failed. "
                                    f"viewwrite targets {viewwrite_targets} "
                                    f"failed with: {e}; flipbook failed with: "
                                    f"{flipbook_error}"),
                        "origin": "screenshot_viewport",
                        "available_targets": _available_viewport_targets(
                            scene_viewer_panes
                        )}

        if not expected_file.exists():
            pngs = sorted(tmpdir.glob("*.png"))
            if not pngs:
                return {"status": "error",
                        "message": f"Capture file not produced at {expected_file}",
                        "origin": "screenshot_viewport"}
            expected_file = pngs[0]

        raw = expected_file.read_bytes()
        if len(raw) < 8 or raw[:8] != b"\x89PNG\r\n\x1a\n":
            return {"status": "error",
                    "message": f"Capture file invalid "
                               f"(size={len(raw)}, magic={raw[:8].hex()})",
                    "origin": "screenshot_viewport"}

        b64 = base64.b64encode(raw).decode("ascii")
        elapsed = time.time() - t0

        return {
            "status": "success",
            "image_base64": b64,
            "mime_type": "image/png",
            "width_used": width,
            "height_used": height,
            "viewport_name_used": viewport.name(),
            "pane_tab_name_used": viewer.name(),
            "viewwrite_target_used": viewwrite_target,
            "capture_method": capture_method,
            "frame_used": frame_used,
            "file_size_bytes": len(raw),
            "elapsed_seconds": round(elapsed, 3),
            "warnings": warnings,
        }
    finally:
        try:
            for f in tmpdir.glob("*"):
                try:
                    f.unlink()
                except Exception:
                    pass
            tmpdir.rmdir()
        except Exception:
            pass
