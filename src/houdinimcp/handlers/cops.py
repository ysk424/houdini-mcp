"""COP (compositing) handlers."""
import hou


def get_cop_info(path):
    """Get info about a COP node: resolution, planes, depth."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    cop = node
    planes = []
    for plane in cop.planes():
        planes.append(plane)
    return {
        "path": node.path(),
        "type": node.type().name(),
        "xres": cop.xRes(),
        "yres": cop.yRes(),
        "planes": planes,
    }


def get_cop_geometry(path):
    """Get geometry data from a COP node (if applicable)."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    geo = node.geometry()
    if not geo:
        raise ValueError(f"No geometry on COP: {path}")
    return {
        "path": node.path(),
        "num_points": len(geo.points()),
        "num_prims": len(geo.prims()),
    }


def get_cop_layer(path, plane_name="C"):
    """Get info about a specific plane/layer in a COP node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    planes = node.planes()
    if plane_name not in planes:
        raise ValueError(f"Plane not found: {plane_name}")
    return {
        "path": path,
        "plane": plane_name,
        "depth": str(node.depth(plane_name)),
        "components": node.components(plane_name),
    }


def list_cop_node_types():
    """List available COP node types."""
    result = []
    for cat_name, cat in hou.nodeTypeCategories().items():
        if "Cop" not in cat_name:
            continue
        for name, nt in cat.nodeTypes().items():
            result.append({
                "name": name,
                "category": cat_name,
                "label": nt.description(),
            })
    return {"count": len(result), "types": result}


def get_cop_vdb(path):
    """Get VDB info from a COP node (for volume COP operations)."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    geo = node.geometry()
    if not geo:
        raise ValueError(f"No geometry on COP: {path}")
    vdbs = []
    for prim in geo.prims():
        if hasattr(prim, "resolution"):
            vdbs.append({
                "name": prim.attribValue("name") if geo.findPrimAttrib("name") else str(prim.number()),
                "resolution": list(prim.resolution()),
            })
    return {"path": path, "vdbs": vdbs}
