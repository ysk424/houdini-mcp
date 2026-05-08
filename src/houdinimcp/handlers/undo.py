"""Undo / redo / history handlers."""
import hou


def undo():
    """Undo the most recent operation in Houdini's global undo stack."""
    labels = hou.undos.undoLabels() or ()
    if not labels:
        return {"performed": False, "reason": "undo stack empty"}
    label = labels[0]
    try:
        hou.undos.performUndo()
    except hou.OperationFailed as e:
        return {"performed": False, "reason": f"performUndo failed: {e}"}
    return {"performed": True, "undone_label": label}


def redo():
    """Redo the most recently undone operation."""
    labels = hou.undos.redoLabels() or ()
    if not labels:
        return {"performed": False, "reason": "redo stack empty"}
    label = labels[0]
    try:
        hou.undos.performRedo()
    except hou.OperationFailed as e:
        return {"performed": False, "reason": f"performRedo failed: {e}"}
    return {"performed": True, "redone_label": label}


def get_undo_history(limit=20):
    """Return undo and redo stack labels (newest first). limit: 1-200."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 200:
        raise ValueError("limit must be an integer between 1 and 200")
    u = list(hou.undos.undoLabels() or ())
    r = list(hou.undos.redoLabels() or ())
    return {
        "undo_stack": u[:limit],
        "redo_stack": r[:limit],
        "undo_total": len(u),
        "redo_total": len(r),
        "current_head_label": u[0] if u else None,
    }
