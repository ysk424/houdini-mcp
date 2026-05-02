"""Shared helpers for parameter introspection.

`hou.Parm` does not expose `.label()` directly; the label lives on the
parm template. This helper centralises the lookup so handlers do not
each reimplement (and drift from) the same access pattern.
"""
import hou


def parm_label(parm):
    """Return the user-facing label for a hou.Parm or hou.ParmTuple.

    Falls back to the parm name if the template is unavailable
    (defensive only — should not happen for parms returned by
    node.parms() / node.parmTuples()).
    """
    template = parm.parmTemplate()
    if template is None:
        return parm.name()
    return template.label()
