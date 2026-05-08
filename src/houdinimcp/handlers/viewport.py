"""Viewport and pane manipulation handlers."""
import hou


def list_panes():
    """List all pane tabs in the desktop."""
    panes = []
    for tab in hou.ui.paneTabs():
        panes.append({
            "name": tab.name(),
            "type": str(tab.type()),
            "is_current": tab.isCurrentTab(),
        })
    return {"count": len(panes), "panes": panes}


def get_viewport_info():
    """Get current viewport settings."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    viewport = viewer.curViewport()
    settings = viewport.settings()
    return {
        "name": viewport.name(),
        "type": str(viewport.type()),
        "camera": viewport.camera().path() if viewport.camera() else None,
        "display_set": str(settings.displaySet()),
    }


def _viewer_in_lop_context(viewer):
    """Return True if the SceneViewer's current network is LOP/stage."""
    try:
        pwd = viewer.pwd()
    except Exception:
        return False
    if pwd is None:
        return False
    if isinstance(pwd, hou.LopNode):
        return True
    try:
        return pwd.childTypeCategory() == hou.lopNodeTypeCategory()
    except Exception:
        return False


def set_viewport_camera(camera_path):
    """Set the viewport camera.

    Accepts three forms:
      - Object camera path (``/obj/cam1``) → passed as ObjNode.
      - LOP camera node path (``/stage/camera1``) → ``primpath`` parm is read
        and the SceneViewer is auto-switched into LOP context if not already.
      - Raw USD camera prim path (``/cameras/cam1``) → passed as a string.
        Requires the SceneViewer to already be in LOP context, otherwise
        Houdini silently no-ops.
    """
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    viewport = viewer.curViewport()

    node = hou.node(camera_path)
    if node is None:
        viewport.setCamera(camera_path)
        return {"camera": camera_path, "kind": "usd_prim_path"}

    if isinstance(node, hou.ObjNode):
        viewport.setCamera(node)
        return {"camera": camera_path, "kind": "obj_camera"}

    if isinstance(node, hou.LopNode):
        primpath_parm = node.parm("primpath")
        if primpath_parm is None:
            raise ValueError(
                f"LOP node has no 'primpath' parm: {camera_path}. "
                f"If this is a wrapped HDA, pass the USD camera prim path "
                f"directly (e.g. '/cameras/<name>') instead of the LOP node path."
            )
        prim_path = primpath_parm.evalAsString()
        switched = False
        if not _viewer_in_lop_context(viewer):
            viewer.setCurrentNode(node)
            switched = True
        viewport.setCamera(prim_path)
        return {
            "camera": camera_path,
            "kind": "lop_camera",
            "primpath": prim_path,
            "viewer_context_switched": switched,
        }

    raise ValueError(
        f"Unsupported camera node type: {type(node).__name__} at {camera_path}. "
        f"Expected ObjNode (Object camera) or LopNode (Solaris camera)."
    )


def set_viewport_display(shading_mode=None, guide=None):
    """Set viewport display options (shading mode, guides)."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    viewport = viewer.curViewport()
    settings = viewport.settings()
    changes = []
    if shading_mode is not None:
        mode_map = {
            "wireframe": hou.glShadingType.Wire,
            "flat": hou.glShadingType.Flat,
            "smooth": hou.glShadingType.Smooth,
            "smooth_wire": hou.glShadingType.SmoothWire,
        }
        mode = mode_map.get(shading_mode)
        if mode is not None:
            settings.setDisplaySet(mode)
            changes.append(f"shading={shading_mode}")
    if guide is not None:
        settings.enableGuide(hou.viewportGuide.NodeGuides, guide)
        changes.append(f"guides={'on' if guide else 'off'}")
    return {"changes": changes}


def set_viewport_renderer(renderer):
    """Set the viewport renderer (GL, Karma, etc.)."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    viewport = viewer.curViewport()
    viewport.changeType(hou.geometryViewportType.__dict__.get(renderer, hou.geometryViewportType.Perspective))
    return {"renderer": renderer}


def frame_selection():
    """Frame the viewport on the current selection."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    viewport = viewer.curViewport()
    viewport.frameSelected()
    return {"framed": "selection"}


def frame_all():
    """Frame the viewport on all geometry."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    viewport = viewer.curViewport()
    viewport.frameAll()
    return {"framed": "all"}


def set_viewport_direction(direction):
    """Set viewport to a standard direction: front, back, left, right, top, bottom, persp."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    viewport = viewer.curViewport()
    dir_map = {
        "front": hou.geometryViewportType.Front,
        "back": hou.geometryViewportType.Back,
        "left": hou.geometryViewportType.Left,
        "right": hou.geometryViewportType.Right,
        "top": hou.geometryViewportType.Top,
        "bottom": hou.geometryViewportType.Bottom,
        "persp": hou.geometryViewportType.Perspective,
    }
    vtype = dir_map.get(direction)
    if vtype is None:
        raise ValueError(f"Unknown direction: {direction}. Use: {list(dir_map.keys())}")
    viewport.changeType(vtype)
    return {"direction": direction}


def set_current_network(path):
    """Set the current network path in the network editor."""
    editor = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    if not editor:
        raise RuntimeError("No network editor found")
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    editor.setCurrentNode(node)
    return {"path": path}
