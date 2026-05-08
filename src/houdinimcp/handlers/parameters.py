"""Parameter read/write handlers."""
import hou


def get_parameter(node_path, parm_name):
    """Get a single parameter's value and metadata."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    template = parm.parmTemplate()
    result = {
        "name": parm.name(),
        "label": template.label(),
        "value": parm.eval(),
        "raw_value": parm.rawValue(),
        "type": template.type().name(),
        "is_at_default": parm.isAtDefault(),
        "is_locked": parm.isLocked(),
    }
    try:
        result["expression"] = parm.expression()
        result["expression_language"] = str(parm.expressionLanguage())
    except hou.OperationFailed:
        result["expression"] = None
    return result


def _parm_diagnostic_snapshot(parm):
    """Collect parm state useful for diagnosing why ``.set()`` failed.

    Houdini's PermissionError message ("locked / take / product / user
    specified") doesn't tell you which cause applied. This snapshot
    surfaces the state callers most often need to act on.
    """
    info = {}
    try:
        info["is_locked"] = parm.isLocked()
    except Exception:
        pass
    try:
        info["is_disabled"] = parm.isDisabled()
    except Exception:
        pass
    try:
        info["has_keyframes"] = bool(parm.keyframes())
    except Exception:
        pass
    try:
        expr = parm.expression()
    except hou.OperationFailed:
        expr = None
    except Exception:
        expr = None
    info["expression"] = expr
    try:
        template = parm.parmTemplate()
        tags = template.tags() if hasattr(template, "tags") else None
        if tags:
            info["tags"] = dict(tags)
    except Exception:
        pass
    return info


def set_parameters(node_path, parameters):
    """Set parameters on a node. For a single parm, pass a 1-element dict: {parm_name: value}.

    Multi-parm dicts return a structured payload:

    - ``changes``: parms that were successfully set (already committed in
      Houdini).
    - ``failed``: parms whose ``.set()`` raised, with a diagnostic snapshot
      (``is_locked``, ``is_disabled``, ``has_keyframes``, ``expression``,
      ``tags``) so the caller can tell why; also covers parm names that did
      not exist on the node.
    - ``not_attempted``: parms that came after the first failure and were
      not attempted (the handler stops on first failure to preserve the
      current de-facto atomicity). Empty if all parms were attempted.

    For 1-parm dicts where the only parm fails, this raises with the
    original exception type (PermissionError, ValueError, ...) and a
    parm-state diagnostic embedded in the message — typos and lock errors
    surface immediately at the dispatcher layer instead of silently
    landing in ``failed``.
    """
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    items = list(parameters.items())
    changes = []
    failed = []
    not_attempted = []
    first_error_exc = None
    for idx, (parm_name, value) in enumerate(items):
        parm = node.parm(parm_name)
        if parm is None:
            err = ValueError(f"Parameter not found: {parm_name}")
            if first_error_exc is None:
                first_error_exc = err
            failed.append({
                "parm": parm_name,
                "error_type": "ParameterNotFound",
                "error_message": f"Parameter not found: {parm_name}",
            })
            not_attempted = [n for n, _ in items[idx + 1:]]
            break
        old_value = parm.eval()
        try:
            parm.set(value)
        except Exception as e:
            if first_error_exc is None:
                first_error_exc = e
            failed.append({
                "parm": parm_name,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "diagnostics": _parm_diagnostic_snapshot(parm),
            })
            not_attempted = [n for n, _ in items[idx + 1:]]
            break
        changes.append({"parm": parm_name, "old": old_value, "new": parm.eval()})

    # Pure-failure for 1-parm dicts: re-raise to surface the error at the
    # dispatcher layer (matches the old set_parameter error semantics).
    if len(parameters) == 1 and failed:
        f0 = failed[0]
        if f0["error_type"] == "ParameterNotFound":
            raise ValueError(f"Parameter not found: {f0['parm']} on {node_path}")
        diag = f0.get("diagnostics", {})
        raise type(first_error_exc)(
            f"Cannot set {node_path}/{f0['parm']}: {f0['error_message']} | parm state: {diag}"
        ) from first_error_exc

    return {
        "path": node_path,
        "changes": changes,
        "failed": failed,
        "not_attempted": not_attempted,
    }


def get_parameter_schema(node_path):
    """Get the full parameter schema (all parm templates) for a node."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parms = []
    for parm in node.parms():
        template = parm.parmTemplate()
        info = {
            "name": parm.name(),
            "label": template.label(),
            "type": template.type().name(),
            "is_at_default": parm.isAtDefault(),
        }
        if hasattr(template, "menuItems"):
            items = template.menuItems()
            labels = template.menuLabels()
            if items:
                info["menu_items"] = list(items)
                info["menu_labels"] = list(labels)
        if hasattr(template, "minValue"):
            info["min"] = template.minValue()
            info["max"] = template.maxValue()
        parms.append(info)
    return {"path": node_path, "parameters": parms}


def get_expression(node_path, parm_name):
    """Get the expression set on a parameter, if any."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    try:
        expr = parm.expression()
        lang = str(parm.expressionLanguage())
        return {"path": node_path, "parm": parm_name, "expression": expr, "language": lang}
    except hou.OperationFailed:
        return {"path": node_path, "parm": parm_name, "expression": None}


def revert_parameter(node_path, parm_name):
    """Revert a parameter to its default value."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    parm.revertToDefaults()
    return {"path": node_path, "parm": parm_name, "value": parm.eval(), "reverted": True}


def link_parameters(src_path, src_parm, dst_path, dst_parm):
    """Create a channel reference from dst_parm to src_parm."""
    src_node = hou.node(src_path)
    dst_node = hou.node(dst_path)
    if not src_node:
        raise ValueError(f"Source node not found: {src_path}")
    if not dst_node:
        raise ValueError(f"Destination node not found: {dst_path}")
    src_p = src_node.parm(src_parm)
    dst_p = dst_node.parm(dst_parm)
    if not src_p:
        raise ValueError(f"Source parameter not found: {src_parm}")
    if not dst_p:
        raise ValueError(f"Destination parameter not found: {dst_parm}")
    ref = f'ch("{src_p.path()}")'
    dst_p.setExpression(ref, hou.exprLanguage.Hscript)
    return {"src": src_p.path(), "dst": dst_p.path(), "expression": ref}


def lock_parameter(node_path, parm_name, locked=True):
    """Lock or unlock a parameter."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    parm.lock(locked)
    return {"path": node_path, "parm": parm_name, "locked": locked}


def create_spare_parameters(node_path, parameters):
    """Add spare parameters to a node. Types: float, int, string, toggle.

    parameters: list of dicts with keys: name, label, parm_type, default (optional).
    For a single parm, pass a 1-element list.
    """
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    type_map = {
        "float": hou.FloatParmTemplate,
        "int": hou.IntParmTemplate,
        "string": hou.StringParmTemplate,
        "toggle": hou.ToggleParmTemplate,
    }
    ptg = node.parmTemplateGroup()
    results = []
    for p in parameters:
        name, label, parm_type = p["name"], p["label"], p["parm_type"]
        default = p.get("default")
        template_cls = type_map.get(parm_type)
        if not template_cls:
            raise ValueError(f"Unknown parm type: {parm_type}. Use: {list(type_map.keys())}")
        if parm_type == "toggle":
            template = template_cls(name, label, default_value=bool(default) if default is not None else False)
        elif parm_type == "string":
            template = template_cls(name, label, 1, default_value=(str(default),) if default is not None else ("",))
        else:
            template = template_cls(name, label, 1, default_value=(default,) if default is not None else (0,))
        ptg.addParmTemplate(template)
        results.append({"path": node_path, "parm": name, "type": parm_type, "created": True})
    node.setParmTemplateGroup(ptg)
    return {"path": node_path, "created": results}
