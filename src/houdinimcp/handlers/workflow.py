"""Workflow template handlers — one-call composite setups."""
import hou


def setup_pyro_sim(source_path, name="pyro_sim", parent_path="/obj"):
    """Set up a Pyro simulation from a source geometry."""
    parent = hou.node(parent_path)
    if not parent:
        raise ValueError(f"Parent not found: {parent_path}")
    source = hou.node(source_path)
    if not source:
        raise ValueError(f"Source not found: {source_path}")
    # Create DOP network with pyro solver
    dopnet = parent.createNode("dopnet", node_name=name)
    # Create pyro source SOP
    pyro_src = dopnet.createNode("pyrosolver", "pyrosolver1")
    return {"dopnet": dopnet.path(), "solver": pyro_src.path(), "source": source_path}


def setup_rbd_sim(source_path, name="rbd_sim", parent_path="/obj"):
    """Set up an RBD simulation from a source geometry."""
    parent = hou.node(parent_path)
    if not parent:
        raise ValueError(f"Parent not found: {parent_path}")
    source = hou.node(source_path)
    if not source:
        raise ValueError(f"Source not found: {source_path}")
    dopnet = parent.createNode("dopnet", node_name=name)
    rbd = dopnet.createNode("rbdpackedobject", "rbd1")
    return {"dopnet": dopnet.path(), "rbd": rbd.path(), "source": source_path}


def setup_flip_sim(source_path, name="flip_sim", parent_path="/obj"):
    """Set up a FLIP fluid simulation from a source geometry."""
    parent = hou.node(parent_path)
    if not parent:
        raise ValueError(f"Parent not found: {parent_path}")
    source = hou.node(source_path)
    if not source:
        raise ValueError(f"Source not found: {source_path}")
    dopnet = parent.createNode("dopnet", node_name=name)
    flip = dopnet.createNode("flipsolver", "flipsolver1")
    return {"dopnet": dopnet.path(), "solver": flip.path(), "source": source_path}


def setup_vellum_sim(source_path, sim_type="cloth", name="vellum_sim", parent_path="/obj"):
    """Set up a Vellum simulation (cloth, hair, grain, etc.)."""
    parent = hou.node(parent_path)
    if not parent:
        raise ValueError(f"Parent not found: {parent_path}")
    source = hou.node(source_path)
    if not source:
        raise ValueError(f"Source not found: {source_path}")
    geo = parent.createNode("geo", node_name=name)
    type_map = {
        "cloth": "vellumdrapeconstraints",
        "hair": "vellumhairconstraints",
        "grain": "vellumgrainconstraints",
    }
    constraint_type = type_map.get(sim_type, "vellumconstraints")
    constraints = geo.createNode(constraint_type, "constraints1")
    solver = geo.createNode("vellumsolver", "solver1")
    solver.setInput(0, constraints)
    return {"geo": geo.path(), "constraints": constraints.path(), "solver": solver.path(), "type": sim_type}


def build_sop_chain(parent_path, nodes):
    """Build a chain of SOP nodes connected in sequence.

    nodes: list of dicts with 'type' and optional 'name', 'parameters' keys.
    """
    parent = hou.node(parent_path)
    if not parent:
        raise ValueError(f"Parent not found: {parent_path}")
    created = []
    prev_node = None
    for spec in nodes:
        node = parent.createNode(spec["type"], node_name=spec.get("name"))
        if spec.get("parameters"):
            for pname, pval in spec["parameters"].items():
                parm = node.parm(pname)
                if parm:
                    parm.set(pval)
        if prev_node:
            node.setInput(0, prev_node)
        created.append({"path": node.path(), "type": spec["type"]})
        prev_node = node
    if prev_node:
        prev_node.setDisplayFlag(True)
        prev_node.setRenderFlag(True)
    parent.layoutChildren()
    return {"parent": parent_path, "nodes": created}


def setup_render(camera_path=None, render_engine="karma", output_path=None):
    """Set up a render node in /out with optional camera and output path."""
    out = hou.node("/out")
    if not out:
        raise ValueError("/out context not found")
    type_map = {
        "karma": "karma",
        "mantra": "ifd",
        "opengl": "opengl",
    }
    rop_type = type_map.get(render_engine, render_engine)
    rop = out.createNode(rop_type, node_name=f"{render_engine}_render")
    if camera_path:
        cam_parm = rop.parm("camera")
        if cam_parm:
            cam_parm.set(camera_path)
    if output_path:
        pic_parm = rop.parm("picture")
        if pic_parm:
            pic_parm.set(output_path)
    return {"path": rop.path(), "engine": render_engine, "camera": camera_path, "output": output_path}
