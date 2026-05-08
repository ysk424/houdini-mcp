"""Node-type schema introspection without instantiation.

`describe_node_type(context, node_type)` walks `hou.NodeType` directly so the
caller can inspect parameters, IO, metadata before deciding to create a node.
Spec frozen at v0.3.1 — see git history for design discussion.
"""
import difflib
import re

import hou


# --- Constants ---------------------------------------------------------------

_MULTIPARM_FOLDER_TYPES = {
    "MultiparmBlock",
    "ScrollingMultiparmBlock",
    "TabbedMultiparmBlock",
}

# UI-only or structurally redundant — filtered from default `tags` output.
# Kept in `raw_tags` when verbose=True. Justifications:
#   autoscope                  : appears on nearly every parm, no API value
#   sidefx::look               : UI presentation hint
#   takecontrol                : take-system flag, irrelevant to schema
#   rampfloatdefault           : redundant with structured `default` for Ramp
#   rampcolordefault           : same
#   rampshowcontrolsdefault    : UI-only
#   script_callback            : exposed via canonical scriptCallback() method
_TAG_BLACKLIST = {
    "autoscope",
    "sidefx::look",
    "takecontrol",
    "rampfloatdefault",
    "rampcolordefault",
    "rampshowcontrolsdefault",
    "script_callback",
}

# ParmTemplateType.name() values that are not exposed as `parms` entries.
_SKIP_PARM_TYPES = {"Separator", "Label"}

# Verified `actual_parm_names` rules. Anything not listed → unverified flag.
# Format: (naming_scheme, num_components) -> suffix list.
_VERIFIED_NAMING_SUFFIXES = {
    ("XYZW", 2): ["x", "y"],
    ("XYZW", 3): ["x", "y", "z"],
}

# Ramp default tokenizer: matches "<idx><key> ( <value> )" tokens.
_RAMP_TOKEN_RE = re.compile(r"(\d+)([A-Za-z]+)\s*\(\s*([^)]+?)\s*\)")


# --- Public entrypoint -------------------------------------------------------

def describe_node_type(context, node_type, verbose=False):
    """Return the static schema of a Houdini node type without instantiating it.

    Args:
        context: NodeTypeCategory name (e.g. "Lop", "Sop", "Object").
        node_type: internal type name as it appears in nodeTypes() keys
            (e.g. "camera", "filecache::2.0", "kinefx::sopcharacterimport").
        verbose: include heavy advisory fields (embedded help, callback bodies,
            full unfiltered tags, dynamic-menu script bodies, parser raw).

    Returns:
        dict with "ok": True on success or "ok": False with an "error" object.
        See module docstring / v0.3.1 spec for full shape.
    """
    categories = hou.nodeTypeCategories()

    if context not in categories:
        return _category_not_found(context, categories)

    category_obj = categories[context]
    nt = hou.nodeType(category_obj, node_type)
    if nt is None:
        return _node_type_not_found(context, node_type, category_obj, categories)

    return _build_response(nt, context, verbose)


# --- Error responses ---------------------------------------------------------

def _category_not_found(context, categories):
    candidates = difflib.get_close_matches(
        context, list(categories.keys()), n=5, cutoff=0.5
    )
    return {
        "ok": False,
        "error": {
            "kind": "category_not_found",
            "category": context,
            "did_you_mean": [{"category": c} for c in candidates],
        },
    }


def _node_type_not_found(context, node_type, category_obj, categories):
    same_cat_keys = list(category_obj.nodeTypes().keys())
    same_cat_matches = difflib.get_close_matches(
        node_type, same_cat_keys, n=5, cutoff=0.6
    )
    did_you_mean = [
        {
            "category": context,
            "node_type": m,
            "score": difflib.SequenceMatcher(None, node_type, m).ratio(),
        }
        for m in same_cat_matches
    ]

    if not did_you_mean:
        for cat_name, cat in categories.items():
            if cat_name == context:
                continue
            if node_type in cat.nodeTypes():
                did_you_mean.append({
                    "category": cat_name,
                    "node_type": node_type,
                    "score": 1.0,
                    "note": "exact match in different category",
                })

    return {
        "ok": False,
        "error": {
            "kind": "node_type_not_found",
            "category": context,
            "node_type": node_type,
            "did_you_mean": did_you_mean,
        },
    }


# --- Top-level response ------------------------------------------------------

def _build_response(nt, category_name, verbose):
    is_hda = nt.definition() is not None

    response = {
        "ok": True,
        "resolved_name": nt.name(),
        "resolved_full_name": nt.nameWithCategory(),
        "name_components": _name_components(nt),
        "category": category_name,
        "label": nt.description(),
        "icon": _safe_call(nt.icon),
        "help_url": _safe_call(nt.helpUrl),
        "is_hda": is_hda,
        "dynamic_parms_possible": is_hda,
        "inputs": _inputs(nt),
        "outputs": _outputs(nt),
    }

    try:
        group = nt.parmTemplateGroup()
        parms, folders = _walk_group(group, verbose)
        response["parms"] = parms
        response["folders"] = folders
        response["parm_extraction_failed"] = False
    except Exception as e:
        response["parms"] = []
        response["folders"] = []
        response["parm_extraction_failed"] = True
        if verbose:
            response["parm_extraction_error"] = str(e)

    if verbose:
        response["embedded_help"] = _safe_call(nt.embeddedHelp)

    return response


def _safe_call(fn):
    try:
        return fn()
    except Exception:
        return None


def _name_components(nt):
    try:
        scope_op, namespace, name, version = nt.nameComponents()
    except Exception:
        return None
    return {
        "scope_op": scope_op,
        "namespace": namespace,
        "name": name,
        "version": version,
    }


def _inputs(nt):
    max_in = nt.maxNumInputs()
    return {
        "min": nt.minNumInputs(),
        "max": max_in,
        "is_variable": max_in >= 9999 or nt.unorderedInputsFlag(),
        "has_unordered": nt.hasUnorderedInputs(),
    }


def _outputs(nt):
    return {"max": nt.maxNumOutputs()}


# --- Parm template walk ------------------------------------------------------

def _walk_group(group, verbose):
    """Recursively walk a parmTemplateGroup, returning (parms, folders).

    Both lists preserve walk order (= UI display order). FolderSet is treated
    as a transparent container (legacy in modern Houdini per empirical scan).
    """
    parms = []
    folders = []

    def visit(template, folder_path, multiparm_chain):
        ttype = template.type()
        ttype_name = ttype.name()

        if ttype_name == "Folder":
            folder_name = template.name()
            new_folder_path = folder_path + [folder_name]
            try:
                folder_type_name = template.folderType().name()
            except Exception:
                folder_type_name = "Simple"
            is_multiparm = folder_type_name in _MULTIPARM_FOLDER_TYPES

            folder_entry = {
                "path": list(new_folder_path),
                "name": folder_name,
                "label": template.label(),
                "folder_type": folder_type_name,
                "is_multiparm": is_multiparm,
                "multiparm_folder_chain": list(multiparm_chain),
                "hash_token_count": folder_name.count("#"),
            }
            folders.append(folder_entry)

            child_chain = (
                multiparm_chain + [folder_name] if is_multiparm else multiparm_chain
            )
            for child in template.parmTemplates():
                visit(child, new_folder_path, child_chain)
            return

        if ttype_name == "FolderSet":
            # Legacy container — flatten its children at the same level.
            try:
                children = template.parmTemplates()
            except Exception:
                children = ()
            for child in children:
                visit(child, folder_path, multiparm_chain)
            return

        if ttype_name in _SKIP_PARM_TYPES:
            return

        parms.append(_extract_parm(template, folder_path, multiparm_chain, verbose))

    for top in group.parmTemplates():
        visit(top, [], [])

    return parms, folders


# --- Parm extraction ---------------------------------------------------------

def _extract_parm(pt, folder_path, multiparm_chain, verbose):
    name = pt.name()
    ttype = pt.type()
    ttype_name = ttype.name()

    raw_tags = _safe_call(pt.tags) or {}
    if not isinstance(raw_tags, dict):
        raw_tags = {}

    entry = {
        "name": name,
        "label": pt.label(),
        "type": ttype_name,
        "folder_path": list(folder_path),
        "in_multiparm": len(multiparm_chain) > 0,
        "multiparm_folder_chain": list(multiparm_chain),
        "hash_token_count": name.count("#"),
        "is_menu": False,
        "tags": _filter_tags(raw_tags),
        "conditionals": _extract_conditionals(pt),
    }

    if ttype_name == "Float":
        _fill_float(entry, pt)
    elif ttype_name == "Int":
        _fill_int(entry, pt)
    elif ttype_name == "String":
        _fill_string(entry, pt)
    elif ttype_name == "Toggle":
        _fill_toggle(entry, pt)
    elif ttype_name == "Menu":
        _fill_menu_type(entry, pt)
    elif ttype_name == "Button":
        _fill_button(entry, pt)
    elif ttype_name == "Ramp":
        _fill_ramp(entry, pt, raw_tags, verbose)
    elif ttype_name == "Data":
        _fill_data(entry, pt)

    _fill_script_callback(entry, pt, verbose)

    if verbose:
        entry["raw_tags"] = dict(raw_tags)

    return entry


# Per-type fill helpers --------------------------------------------------

def _fill_float(entry, pt):
    n = pt.numComponents()
    entry["num_components"] = n
    entry["naming_scheme"] = _safe_enum_name(pt.namingScheme) if n > 1 else None
    entry["actual_parm_names"], entry["actual_parm_names_unverified"] = (
        _component_names(pt, n)
    )
    entry["default"] = list(pt.defaultValue())
    entry["min"] = pt.minValue()
    entry["max"] = pt.maxValue()
    entry["min_is_strict"] = pt.minIsStrict()
    entry["max_is_strict"] = pt.maxIsStrict()
    entry["look"] = _safe_enum_name(pt.look)


def _fill_int(entry, pt):
    n = pt.numComponents()
    entry["num_components"] = n
    entry["naming_scheme"] = _safe_enum_name(pt.namingScheme) if n > 1 else None
    entry["actual_parm_names"], entry["actual_parm_names_unverified"] = (
        _component_names(pt, n)
    )
    entry["default"] = list(pt.defaultValue())
    entry["min"] = pt.minValue()
    entry["max"] = pt.maxValue()
    entry["min_is_strict"] = pt.minIsStrict()
    entry["max_is_strict"] = pt.maxIsStrict()
    _add_menu_fields(entry, pt)


def _fill_string(entry, pt):
    n = pt.numComponents()
    entry["num_components"] = n
    entry["naming_scheme"] = None
    entry["actual_parm_names"], entry["actual_parm_names_unverified"] = (
        _component_names(pt, n)
    )
    entry["default"] = list(pt.defaultValue())
    entry["string_type"] = _safe_enum_name(pt.stringType)
    if entry["string_type"] == "FileReference":
        entry["file_type"] = _safe_enum_name(pt.fileType)
    else:
        entry["file_type"] = None
    _add_menu_fields(entry, pt)


def _fill_toggle(entry, pt):
    entry["num_components"] = 1
    entry["default"] = bool(pt.defaultValue())


def _fill_menu_type(entry, pt):
    entry["num_components"] = 1
    try:
        entry["default"] = int(pt.defaultValue())
    except Exception:
        entry["default"] = 0
    _add_menu_fields(entry, pt)


def _fill_button(entry, pt):
    entry["num_components"] = 1
    entry["default"] = None


def _fill_ramp(entry, pt, raw_tags, verbose):
    entry["num_components"] = 1
    entry["ramp_parm_type"] = _safe_enum_name(pt.parmType)
    if entry["ramp_parm_type"] == "Color":
        entry["color_type"] = _safe_enum_name(pt.colorType)
    else:
        entry["color_type"] = None

    raw_float = raw_tags.get("rampfloatdefault")
    raw_color = raw_tags.get("rampcolordefault")
    raw = raw_float or raw_color
    is_color = bool(raw_color)

    if not raw:
        entry["default"] = {"point_count": 0, "points": []}
        return

    try:
        points = _parse_ramp_default(raw, is_color)
        entry["default"] = {"point_count": len(points), "points": points}
        if verbose:
            entry["default_raw"] = raw
    except Exception as e:
        # Per spec: on parse failure, default → null and raw is promoted to
        # default response (not gated by verbose).
        entry["default"] = None
        entry["default_raw"] = raw
        entry["parse_failed"] = True
        if verbose:
            entry["parse_error"] = str(e)


def _fill_data(entry, pt):
    entry["num_components"] = 1
    entry["data_parm_type"] = _safe_enum_name(pt.dataParmType)
    try:
        entry["default"] = list(pt.defaultValue())
    except Exception:
        entry["default"] = None


# --- Menu fields -------------------------------------------------------------

def _add_menu_fields(entry, pt):
    """Populate menu_* fields. Caller already set is_menu=False as default."""
    items = ()
    labels = ()
    script = ""
    try:
        items = pt.menuItems()
    except AttributeError:
        return
    try:
        labels = pt.menuLabels()
    except AttributeError:
        labels = items
    try:
        script = pt.itemGeneratorScript()
    except AttributeError:
        script = ""

    has_static = bool(items)
    has_dynamic = bool(script)

    if not has_static and not has_dynamic:
        return

    entry["is_menu"] = True
    entry["menu_style"] = _safe_enum_name(pt.menuType)

    if has_dynamic:
        lang = _safe_enum_name(pt.itemGeneratorScriptLanguage)
        if lang == "Python":
            entry["menu_source"] = "script_python"
        elif lang == "Hscript":
            entry["menu_source"] = "script_hscript"
        else:
            # Spec enumerates static / script_python / script_hscript only.
            entry["menu_source"] = "script_python"
        entry["menu_choices"] = []
    else:
        entry["menu_source"] = "static"
        entry["menu_choices"] = [
            {"value": v, "label": l} for v, l in zip(items, labels)
        ]


# --- Conditionals ------------------------------------------------------------

def _extract_conditionals(pt):
    try:
        cond = pt.conditionals()
    except AttributeError:
        return None
    if not cond:
        return None
    out = {}
    for ct, expr in cond.items():
        try:
            key = ct.name()
        except AttributeError:
            key = str(ct)
        out[key] = expr
    return out or None


# --- script_callback (canonical method-based) --------------------------------

def _fill_script_callback(entry, pt, verbose):
    body = ""
    try:
        body = pt.scriptCallback() or ""
    except AttributeError:
        entry["script_callback"] = False
        entry["script_callback_language"] = None
        return

    entry["script_callback"] = bool(body)
    if body:
        entry["script_callback_language"] = _safe_enum_name(
            pt.scriptCallbackLanguage
        )
        if verbose:
            entry["callback_script_body"] = body
    else:
        entry["script_callback_language"] = None


# --- Helpers -----------------------------------------------------------------

def _filter_tags(raw_tags):
    return {k: v for k, v in raw_tags.items() if k not in _TAG_BLACKLIST}


def _safe_enum_name(getter):
    """Call a getter that returns a Houdini enum value and return its .name()."""
    try:
        val = getter()
    except (AttributeError, Exception):
        return None
    if val is None:
        return None
    try:
        return val.name()
    except AttributeError:
        return str(val)


def _component_names(pt, n):
    """Return (component_names_or_None, unverified_flag).

    For n==1, the parm has no component split: returns ([name], False).
    For n>1, only XYZW with n in {2,3} is verified per v0.3.1 spec; everything
    else returns (None, True) so callers know not to trust precomputed names.
    """
    name = pt.name()
    if n == 1:
        return ([name], False)

    scheme = _safe_enum_name(pt.namingScheme)
    if scheme is None:
        return (None, True)

    suffixes = _VERIFIED_NAMING_SUFFIXES.get((scheme, n))
    if suffixes is None:
        return (None, True)
    return ([name + s for s in suffixes], False)


def _parse_ramp_default(raw, is_color):
    """Parse the rampfloatdefault / rampcolordefault tag string.

    Format observed empirically (Houdini 21.0.700):
      "1pos ( 0 ) 1value ( 0 ) 1interp ( linear ) 2pos ( 0.5 ) ..."
    Color ramp uses cr/cg/cb triples instead of (or alongside) value.
    """
    points_by_idx = {}
    for idx_str, key, value in _RAMP_TOKEN_RE.findall(raw):
        idx = int(idx_str)
        points_by_idx.setdefault(idx, {})[key] = value.strip()

    points = []
    for idx in sorted(points_by_idx.keys()):
        data = points_by_idx[idx]
        point = {"interp": data.get("interp", "linear")}
        if "pos" in data:
            point["pos"] = float(data["pos"])
        if is_color:
            if all(k in data for k in ("cr", "cg", "cb")):
                point["value"] = [
                    float(data["cr"]), float(data["cg"]), float(data["cb"])
                ]
            elif "value" in data:
                point["value"] = float(data["value"])
        else:
            if "value" in data:
                point["value"] = float(data["value"])
        points.append(point)
    return points
