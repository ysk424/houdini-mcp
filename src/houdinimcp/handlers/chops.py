"""CHOP (channel) handlers."""
import hou


def get_chop_data(path, channel=None, start=None, end=None):
    """Get CHOP channel data, optionally for a specific channel and frame range."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    tracks = node.tracks()
    result = []
    for track in tracks:
        if channel and track.name() != channel:
            continue
        samples = list(track.allSamples())
        if start is not None or end is not None:
            s = start or 0
            e = end or len(samples)
            samples = samples[s:e]
        result.append({
            "name": track.name(),
            "num_samples": len(samples),
            "samples": [float(s) for s in samples[:1000]],  # cap at 1000
        })
    return {"path": path, "channels": result}


def list_chop_channels(path):
    """List all channels in a CHOP node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    channels = []
    for track in node.tracks():
        channels.append({
            "name": track.name(),
            "num_samples": track.numSamples(),
        })
    return {"path": path, "count": len(channels), "channels": channels}


def export_chop_to_parm(chop_path, channel_name, target_path, parm_name):
    """Export a CHOP channel to a parameter."""
    chop_node = hou.node(chop_path)
    if not chop_node:
        raise ValueError(f"CHOP node not found: {chop_path}")
    target = hou.node(target_path)
    if not target:
        raise ValueError(f"Target node not found: {target_path}")
    parm = target.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name}")
    # Set a CHOP export expression
    expr = f'chop("{chop_path}/{channel_name}")'
    parm.setExpression(expr, hou.exprLanguage.Hscript)
    return {"chop": chop_path, "channel": channel_name, "target_parm": parm.path(), "expression": expr}
