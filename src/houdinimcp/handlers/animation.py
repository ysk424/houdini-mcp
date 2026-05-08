"""Animation and playbar handlers."""
import hou


def set_keyframes(node_path, parm_name, keyframes):
    """Set multiple keyframes on a parameter.

    keyframes: list of dicts with 'frame' and 'value' keys.
    """
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    for kf in keyframes:
        key = hou.Keyframe()
        key.setFrame(kf["frame"])
        key.setValue(kf["value"])
        parm.setKeyframe(key)
    return {"path": node_path, "parm": parm_name, "count": len(keyframes)}


def delete_keyframe(node_path, parm_name, frame):
    """Delete a keyframe at a specific frame."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    parm.deleteKeyframeAtFrame(frame)
    return {"path": node_path, "parm": parm_name, "frame": frame, "deleted": True}


def get_keyframes(node_path, parm_name):
    """Get all keyframes on a parameter."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    keyframes = []
    for key in parm.keyframes():
        keyframes.append({
            "frame": key.frame(),
            "value": key.value(),
            "expression": key.expression() if key.isExpressionSet() else None,
        })
    return {"path": node_path, "parm": parm_name, "keyframes": keyframes}


def get_frame():
    """Get the current frame."""
    return {"frame": hou.intFrame(), "time": hou.time()}


def set_frame_range(start, end):
    """Set the global animation frame range."""
    hou.playbar.setFrameRange(start, end)
    return {"start": start, "end": end}


def set_playback_range(start, end):
    """Set the playback range (subset of the global range)."""
    hou.playbar.setPlaybackRange(start, end)
    return {"start": start, "end": end}


def playbar_control(action):
    """Control playbar: play, stop, reverse, step_forward, step_backward."""
    actions = {
        "play": lambda: hou.playbar.play(),
        "stop": lambda: hou.playbar.stop(),
        "reverse": lambda: hou.playbar.reverse(),
        "step_forward": lambda: hou.setFrame(hou.intFrame() + 1),
        "step_backward": lambda: hou.setFrame(hou.intFrame() - 1),
    }
    fn = actions.get(action)
    if not fn:
        raise ValueError(f"Unknown action: {action}. Use: {list(actions.keys())}")
    fn()
    return {"action": action, "frame": hou.intFrame()}
