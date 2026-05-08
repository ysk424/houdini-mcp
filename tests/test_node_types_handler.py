"""Tests for handlers/node_types.py — describe_node_type and helpers."""
import sys
import os
import types

import pytest


# Set up a minimal `hou` stub before importing the handler under test.
# We load node_types.py via importlib (see below) to avoid pulling in
# houdinimcp/__init__.py — which would chain into server.py and every other
# handler, caching them with our stub. That caching breaks later test files
# that set up their own hou mock for `from houdinimcp.handlers.X import Y`.

_hou_was_present = "hou" in sys.modules
if not _hou_was_present:
    _hou = types.ModuleType("hou")
    _hou.nodeTypeCategories = lambda: {}
    _hou.nodeType = lambda cat, name: None
    sys.modules["hou"] = _hou

hou = sys.modules["hou"]


class _Enum:
    """Hashable stand-in for a Houdini enum value with a .name() method."""
    __slots__ = ("_n",)

    def __init__(self, n):
        self._n = n

    def name(self):
        return self._n


def _enum(name):
    """Make an object whose .name() returns the given string."""
    return _Enum(name)


_HANDLER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "houdinimcp", "handlers", "node_types.py",
)


# --- ParmTemplate mocks -----------------------------------------------------

class FakeTemplate:
    """Generic parm template mock; per-type subclasses fill in the rest."""

    def __init__(self, name, type_name, label=None, tags=None, conditionals=None,
                 callback="", callback_lang="Python"):
        self._name = name
        self._type_name = type_name
        self._label = label or name
        self._tags = tags or {}
        self._conditionals = conditionals or {}
        self._callback = callback
        self._callback_lang = callback_lang

    def name(self):
        return self._name

    def label(self):
        return self._label

    def type(self):
        return _enum(self._type_name)

    def tags(self):
        return dict(self._tags)

    def conditionals(self):
        return {_enum(k): v for k, v in self._conditionals.items()}

    def scriptCallback(self):
        return self._callback

    def scriptCallbackLanguage(self):
        return _enum(self._callback_lang)


class FakeFloat(FakeTemplate):
    def __init__(self, name, n=1, default=None, naming="XYZW",
                 min_val=0.0, max_val=1.0, **kw):
        super().__init__(name, "Float", **kw)
        self._n = n
        self._default = default if default is not None else [0.0] * n
        self._naming = naming
        self._min = min_val
        self._max = max_val

    def numComponents(self):
        return self._n

    def namingScheme(self):
        return _enum(self._naming)

    def defaultValue(self):
        return tuple(self._default)

    def minValue(self):
        return self._min

    def maxValue(self):
        return self._max

    def minIsStrict(self):
        return False

    def maxIsStrict(self):
        return False

    def look(self):
        return _enum("Regular")


class FakeInt(FakeTemplate):
    def __init__(self, name, n=1, default=None, naming="XYZW",
                 menu_items=(), menu_labels=(), menu_script="",
                 menu_script_lang="Python", **kw):
        super().__init__(name, "Int", **kw)
        self._n = n
        self._default = default if default is not None else [0] * n
        self._naming = naming
        self._menu_items = menu_items
        self._menu_labels = menu_labels or menu_items
        self._menu_script = menu_script
        self._menu_script_lang = menu_script_lang

    def numComponents(self):
        return self._n

    def namingScheme(self):
        return _enum(self._naming)

    def defaultValue(self):
        return tuple(self._default)

    def minValue(self):
        return 0

    def maxValue(self):
        return 100

    def minIsStrict(self):
        return False

    def maxIsStrict(self):
        return False

    def menuItems(self):
        return tuple(self._menu_items)

    def menuLabels(self):
        return tuple(self._menu_labels)

    def menuType(self):
        return _enum("Normal")

    def itemGeneratorScript(self):
        return self._menu_script

    def itemGeneratorScriptLanguage(self):
        return _enum(self._menu_script_lang)


class FakeString(FakeTemplate):
    def __init__(self, name, default=("",), string_type="Regular",
                 file_type="Image", menu_items=(), menu_script="", **kw):
        super().__init__(name, "String", **kw)
        self._default = default
        self._string_type = string_type
        self._file_type = file_type
        self._menu_items = menu_items
        self._menu_script = menu_script

    def numComponents(self):
        return len(self._default)

    def defaultValue(self):
        return tuple(self._default)

    def stringType(self):
        return _enum(self._string_type)

    def fileType(self):
        return _enum(self._file_type)

    def menuItems(self):
        return tuple(self._menu_items)

    def menuLabels(self):
        return tuple(self._menu_items)

    def menuType(self):
        return _enum("Normal")

    def itemGeneratorScript(self):
        return self._menu_script

    def itemGeneratorScriptLanguage(self):
        return _enum("Python")


class FakeToggle(FakeTemplate):
    def __init__(self, name, default=False, **kw):
        super().__init__(name, "Toggle", **kw)
        self._default = default

    def defaultValue(self):
        return self._default


class FakeButton(FakeTemplate):
    def __init__(self, name, callback="", callback_lang="Python", **kw):
        super().__init__(name, "Button", callback=callback,
                         callback_lang=callback_lang, **kw)


class FakeRamp(FakeTemplate):
    def __init__(self, name, ramp_type="Float", color_type="RGB", **kw):
        super().__init__(name, "Ramp", **kw)
        self._ramp_type = ramp_type
        self._color_type = color_type

    def parmType(self):
        return _enum(self._ramp_type)

    def colorType(self):
        return _enum(self._color_type)


class FakeFolder(FakeTemplate):
    def __init__(self, name, folder_type="Tabs", children=(), label=None):
        super().__init__(name, "Folder", label=label)
        self._folder_type = folder_type
        self._children = list(children)

    def folderType(self):
        return _enum(self._folder_type)

    def parmTemplates(self):
        return tuple(self._children)


class FakeSeparator(FakeTemplate):
    def __init__(self, name="sep"):
        super().__init__(name, "Separator")


# --- NodeType mock ----------------------------------------------------------

class FakeNodeType:
    def __init__(self, name, parm_templates=(), is_hda=False,
                 min_inputs=0, max_inputs=1, max_outputs=1,
                 unordered=False, namespace="", scope="", version=""):
        self._name = name
        self._templates = list(parm_templates)
        self._is_hda = is_hda
        self._min_in = min_inputs
        self._max_in = max_inputs
        self._max_out = max_outputs
        self._unordered = unordered
        self._namespace = namespace
        self._scope = scope
        self._version = version

    def name(self):
        return self._name

    def nameWithCategory(self):
        return f"Sop/{self._name}"

    def nameComponents(self):
        return (self._scope, self._namespace, self._name, self._version)

    def description(self):
        return self._name.title()

    def icon(self):
        return f"SOP_{self._name}"

    def helpUrl(self):
        return f"https://example.test/{self._name}"

    def embeddedHelp(self):
        return f"# {self._name}\n\nHelp text."

    def definition(self):
        return object() if self._is_hda else None

    def minNumInputs(self):
        return self._min_in

    def maxNumInputs(self):
        return self._max_in

    def maxNumOutputs(self):
        return self._max_out

    def unorderedInputsFlag(self):
        return self._unordered

    def hasUnorderedInputs(self):
        return self._unordered

    def parmTemplateGroup(self):
        return types.SimpleNamespace(parmTemplates=lambda: tuple(self._templates))


class FakeCategory:
    def __init__(self, name, types_dict):
        self._name = name
        self._types = types_dict

    def name(self):
        return self._name

    def nodeTypes(self):
        return dict(self._types)


# --- hou setup helper -------------------------------------------------------

def install_categories(monkeypatch, categories_dict):
    """Wire hou.nodeTypeCategories and hou.nodeType to the given dict."""
    monkeypatch.setattr(hou, "nodeTypeCategories",
                        lambda: dict(categories_dict), raising=False)

    def _node_type(cat, type_name):
        return cat.nodeTypes().get(type_name)

    monkeypatch.setattr(hou, "nodeType", _node_type, raising=False)


# --- Tests ------------------------------------------------------------------

import importlib.util as _importlib_util

# Load node_types.py directly without triggering houdinimcp/__init__.py.
# Going through the package would import server.py which imports every other
# handler module — caching them with our hou stub bound. Later test files that
# set up their OWN hou mock for `from houdinimcp.handlers.X import Y` would
# then get the cached module with the wrong hou reference.
_spec = _importlib_util.spec_from_file_location(
    "_node_types_under_test", _HANDLER_PATH
)
_module = _importlib_util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

describe_node_type = _module.describe_node_type
_parse_ramp_default = _module._parse_ramp_default
_component_names = _module._component_names

# Pop the `hou` stub now so other test files' "skip if hou not in sys.modules"
# guards still trigger. Tests reinstall it via monkeypatch per-test.
if not _hou_was_present:
    _hou_stub_for_tests = sys.modules.pop("hou")
else:
    _hou_stub_for_tests = hou


@pytest.fixture(autouse=True)
def _hou_present_during_test(monkeypatch):
    """Re-install our stub as `hou` during each test so monkeypatch.setattr
    targets a module that lives in sys.modules. Auto cleanup via monkeypatch."""
    monkeypatch.setitem(sys.modules, "hou", _hou_stub_for_tests)


def test_category_not_found_returns_did_you_mean(monkeypatch):
    cats = {"Sop": FakeCategory("Sop", {}), "Lop": FakeCategory("Lop", {})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("sop", "anything")  # wrong case
    assert result["ok"] is False
    assert result["error"]["kind"] == "category_not_found"
    assert any(c["category"] == "Sop"
               for c in result["error"]["did_you_mean"])


def test_node_type_not_found_within_category(monkeypatch):
    box = FakeNodeType("box")
    sphere = FakeNodeType("sphere")
    cats = {"Sop": FakeCategory("Sop", {"box": box, "sphere": sphere})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "boxx")
    assert result["ok"] is False
    assert result["error"]["kind"] == "node_type_not_found"
    candidates = [c["node_type"] for c in result["error"]["did_you_mean"]]
    assert "box" in candidates


def test_node_type_not_found_cross_category(monkeypatch):
    merge_lop = FakeNodeType("merge")
    cats = {
        "Sop": FakeCategory("Sop", {}),
        "Lop": FakeCategory("Lop", {"merge": merge_lop}),
    }
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "merge")
    assert result["ok"] is False
    matches = result["error"]["did_you_mean"]
    assert any(m["category"] == "Lop" and m["score"] == 1.0 for m in matches)


def test_simple_node_type_basic_response(monkeypatch):
    nt = FakeNodeType(
        "box",
        parm_templates=[FakeFloat("size", n=1, default=[1.0])],
        max_inputs=0,
    )
    cats = {"Sop": FakeCategory("Sop", {"box": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "box")
    assert result["ok"] is True
    assert result["resolved_name"] == "box"
    assert result["category"] == "Sop"
    assert result["label"] == "Box"
    assert result["is_hda"] is False
    assert result["dynamic_parms_possible"] is False
    assert result["inputs"]["max"] == 0
    assert result["outputs"]["max"] == 1
    assert result["parm_extraction_failed"] is False
    assert len(result["parms"]) == 1
    assert result["parms"][0]["name"] == "size"
    assert result["parms"][0]["num_components"] == 1
    assert result["parms"][0]["default"] == [1.0]
    assert "embedded_help" not in result  # default mode


def test_verbose_adds_embedded_help_and_raw_tags(monkeypatch):
    nt = FakeNodeType(
        "box",
        parm_templates=[FakeFloat("size", tags={"autoscope": "1", "custom": "x"})],
    )
    cats = {"Sop": FakeCategory("Sop", {"box": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "box", verbose=True)
    assert "embedded_help" in result
    parm = result["parms"][0]
    assert "raw_tags" in parm
    assert parm["raw_tags"] == {"autoscope": "1", "custom": "x"}
    # Filtered tags drop autoscope but keep custom
    assert parm["tags"] == {"custom": "x"}


def test_xyzw_n3_actual_parm_names_verified(monkeypatch):
    nt = FakeNodeType(
        "xform",
        parm_templates=[FakeFloat("t", n=3, naming="XYZW", default=[0.0, 0.0, 0.0])],
    )
    cats = {"Sop": FakeCategory("Sop", {"xform": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "xform")
    parm = result["parms"][0]
    assert parm["actual_parm_names"] == ["tx", "ty", "tz"]
    assert parm["actual_parm_names_unverified"] is False


def test_xyzw_n4_actual_parm_names_unverified(monkeypatch):
    # Spec: only n=2 and n=3 of XYZW are empirically verified
    nt = FakeNodeType(
        "weird",
        parm_templates=[FakeFloat("v", n=4, naming="XYZW",
                                  default=[0.0, 0.0, 0.0, 0.0])],
    )
    cats = {"Sop": FakeCategory("Sop", {"weird": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "weird")
    parm = result["parms"][0]
    assert parm["actual_parm_names"] is None
    assert parm["actual_parm_names_unverified"] is True


def test_unverified_naming_scheme_flagged(monkeypatch):
    nt = FakeNodeType(
        "rng",
        parm_templates=[FakeFloat("range", n=2, naming="MinMax",
                                  default=[0.0, 1.0])],
    )
    cats = {"Sop": FakeCategory("Sop", {"rng": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "rng")
    parm = result["parms"][0]
    assert parm["actual_parm_names"] is None
    assert parm["actual_parm_names_unverified"] is True


def test_n1_always_verified_no_suffix(monkeypatch):
    nt = FakeNodeType(
        "single",
        parm_templates=[FakeFloat("size", n=1, default=[1.0])],
    )
    cats = {"Sop": FakeCategory("Sop", {"single": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "single")
    parm = result["parms"][0]
    assert parm["actual_parm_names"] == ["size"]
    assert parm["actual_parm_names_unverified"] is False


def test_static_menu_choices(monkeypatch):
    menu_int = FakeInt("engine", n=1, default=[0],
                       menu_items=("cpu", "xpu"),
                       menu_labels=("CPU", "XPU"))
    nt = FakeNodeType("renderer", parm_templates=[menu_int])
    cats = {"Sop": FakeCategory("Sop", {"renderer": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "renderer")
    parm = result["parms"][0]
    assert parm["is_menu"] is True
    assert parm["menu_source"] == "static"
    assert parm["menu_choices"] == [
        {"value": "cpu", "label": "CPU"},
        {"value": "xpu", "label": "XPU"},
    ]


def test_dynamic_menu_returns_empty_choices(monkeypatch):
    menu_int = FakeInt("dynmenu", n=1, default=[0],
                       menu_script="return ['a', 'A', 'b', 'B']",
                       menu_script_lang="Python")
    nt = FakeNodeType("dynmenu_node", parm_templates=[menu_int])
    cats = {"Sop": FakeCategory("Sop", {"dynmenu_node": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "dynmenu_node")
    parm = result["parms"][0]
    assert parm["is_menu"] is True
    assert parm["menu_source"] == "script_python"
    assert parm["menu_choices"] == []


def test_non_menu_capable_type_has_is_menu_false(monkeypatch):
    nt = FakeNodeType("box",
                      parm_templates=[FakeFloat("size", n=1, default=[1.0])])
    cats = {"Sop": FakeCategory("Sop", {"box": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "box")
    assert result["parms"][0]["is_menu"] is False


def test_toggle_default_is_bool(monkeypatch):
    nt = FakeNodeType("t",
                      parm_templates=[FakeToggle("flag", default=True)])
    cats = {"Sop": FakeCategory("Sop", {"t": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "t")
    parm = result["parms"][0]
    assert parm["type"] == "Toggle"
    assert parm["default"] is True


def test_button_default_null_with_callback(monkeypatch):
    nt = FakeNodeType("rop",
                      parm_templates=[FakeButton("execute",
                                                 callback="hou.phm().run()")])
    cats = {"Sop": FakeCategory("Sop", {"rop": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "rop")
    parm = result["parms"][0]
    assert parm["default"] is None
    assert parm["script_callback"] is True
    assert parm["script_callback_language"] == "Python"
    assert "callback_script_body" not in parm  # not verbose


def test_button_callback_body_in_verbose(monkeypatch):
    nt = FakeNodeType("rop",
                      parm_templates=[FakeButton("execute",
                                                 callback="hou.phm().run()")])
    cats = {"Sop": FakeCategory("Sop", {"rop": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "rop", verbose=True)
    parm = result["parms"][0]
    assert parm["callback_script_body"] == "hou.phm().run()"


def test_string_filereference_includes_file_type(monkeypatch):
    s = FakeString("file", default=("$HIP/x.bgeo",),
                   string_type="FileReference", file_type="Geometry",
                   tags={"filechooser_mode": "write"})
    nt = FakeNodeType("filenode", parm_templates=[s])
    cats = {"Sop": FakeCategory("Sop", {"filenode": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "filenode")
    parm = result["parms"][0]
    assert parm["string_type"] == "FileReference"
    assert parm["file_type"] == "Geometry"
    assert parm["tags"]["filechooser_mode"] == "write"


def test_separator_is_skipped(monkeypatch):
    nt = FakeNodeType("n", parm_templates=[
        FakeFloat("a", n=1, default=[0.0]),
        FakeSeparator(),
        FakeFloat("b", n=1, default=[0.0]),
    ])
    cats = {"Sop": FakeCategory("Sop", {"n": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "n")
    names = [p["name"] for p in result["parms"]]
    assert names == ["a", "b"]


def test_simple_folder_path_and_no_multiparm_chain(monkeypatch):
    folder = FakeFolder("output", folder_type="Tabs",
                        children=[FakeFloat("size", n=1, default=[1.0])])
    nt = FakeNodeType("n", parm_templates=[folder])
    cats = {"Sop": FakeCategory("Sop", {"n": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "n")
    assert len(result["folders"]) == 1
    folder_entry = result["folders"][0]
    assert folder_entry["path"] == ["output"]
    assert folder_entry["is_multiparm"] is False
    assert folder_entry["multiparm_folder_chain"] == []
    assert folder_entry["folder_type"] == "Tabs"

    parm = result["parms"][0]
    assert parm["folder_path"] == ["output"]
    assert parm["in_multiparm"] is False
    assert parm["multiparm_folder_chain"] == []


def test_multiparm_chain_one_level(monkeypatch):
    leaf = FakeString("transform#", default=("",))
    multiparm = FakeFolder("numobj", folder_type="MultiparmBlock",
                           children=[leaf])
    nt = FakeNodeType("n", parm_templates=[multiparm])
    cats = {"Sop": FakeCategory("Sop", {"n": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "n")
    folder_entry = result["folders"][0]
    assert folder_entry["is_multiparm"] is True
    assert folder_entry["multiparm_folder_chain"] == []
    assert folder_entry["hash_token_count"] == 0

    parm = result["parms"][0]
    assert parm["in_multiparm"] is True
    assert parm["multiparm_folder_chain"] == ["numobj"]
    assert parm["hash_token_count"] == 1


def test_multiparm_chain_three_levels(monkeypatch):
    """motionmixer-style nesting: tracks → clips# → clipeffects#_# → leaf."""
    leaf = FakeString("trackfx#_#_#", default=("",))
    inner = FakeFolder("clipeffects#_#", folder_type="MultiparmBlock",
                       children=[leaf])
    middle = FakeFolder("clips#", folder_type="MultiparmBlock",
                        children=[inner])
    outer = FakeFolder("tracks", folder_type="MultiparmBlock",
                       children=[middle])
    nt = FakeNodeType("motionmixer", parm_templates=[outer])
    cats = {"Sop": FakeCategory("Sop", {"motionmixer": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "motionmixer")

    folder_paths = [f["path"] for f in result["folders"]]
    assert ["tracks"] in folder_paths
    assert ["tracks", "clips#"] in folder_paths
    assert ["tracks", "clips#", "clipeffects#_#"] in folder_paths

    inner_folder = next(
        f for f in result["folders"] if f["name"] == "clipeffects#_#"
    )
    assert inner_folder["multiparm_folder_chain"] == ["tracks", "clips#"]
    assert inner_folder["hash_token_count"] == 2

    parm = result["parms"][0]
    assert parm["multiparm_folder_chain"] == ["tracks", "clips#", "clipeffects#_#"]
    assert parm["hash_token_count"] == 3


def test_conditionals_use_enum_name(monkeypatch):
    f = FakeFloat("a", n=1, default=[0.0],
                  conditionals={"DisableWhen": "{ x == 1 }"})
    nt = FakeNodeType("n", parm_templates=[f])
    cats = {"Sop": FakeCategory("Sop", {"n": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "n")
    parm = result["parms"][0]
    assert parm["conditionals"] == {"DisableWhen": "{ x == 1 }"}


def test_no_conditionals_returns_null(monkeypatch):
    nt = FakeNodeType("n", parm_templates=[FakeFloat("a", n=1, default=[0.0])])
    cats = {"Sop": FakeCategory("Sop", {"n": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "n")
    assert result["parms"][0]["conditionals"] is None


def test_tag_blacklist_filters_default(monkeypatch):
    f = FakeFloat("a", n=1, default=[0.0], tags={
        "autoscope": "1",
        "sidefx::look": "x",
        "rampfloatdefault": "y",
        "filechooser_mode": "read",
    })
    nt = FakeNodeType("n", parm_templates=[f])
    cats = {"Sop": FakeCategory("Sop", {"n": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "n")
    parm = result["parms"][0]
    assert parm["tags"] == {"filechooser_mode": "read"}
    assert "raw_tags" not in parm


def test_hda_flags(monkeypatch):
    nt = FakeNodeType("custom", parm_templates=[], is_hda=True,
                      namespace="myco", version="1.0")
    cats = {"Sop": FakeCategory("Sop", {"custom": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "custom")
    assert result["is_hda"] is True
    assert result["dynamic_parms_possible"] is True
    assert result["name_components"]["namespace"] == "myco"
    assert result["name_components"]["version"] == "1.0"


def test_parm_extraction_failure_is_graceful(monkeypatch):
    class BrokenGroup:
        def parmTemplates(self):
            raise RuntimeError("HDA file missing")

    class BrokenNT(FakeNodeType):
        def parmTemplateGroup(self):
            return BrokenGroup()

    nt = BrokenNT("broken", parm_templates=[])
    cats = {"Sop": FakeCategory("Sop", {"broken": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "broken")
    assert result["ok"] is True
    assert result["parm_extraction_failed"] is True
    assert result["parms"] == []
    assert result["folders"] == []


def test_inputs_variable(monkeypatch):
    nt = FakeNodeType("merge", max_inputs=9999)
    cats = {"Sop": FakeCategory("Sop", {"merge": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "merge")
    assert result["inputs"]["is_variable"] is True
    assert result["inputs"]["max"] == 9999


def test_inputs_unordered(monkeypatch):
    nt = FakeNodeType("switch", max_inputs=4, unordered=True)
    cats = {"Sop": FakeCategory("Sop", {"switch": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "switch")
    assert result["inputs"]["is_variable"] is True
    assert result["inputs"]["has_unordered"] is True


# --- Ramp parser tests ------------------------------------------------------

def test_ramp_parser_float():
    raw = "1pos ( 0 ) 1value ( 0 ) 1interp ( linear ) 2pos ( 1 ) 2value ( 1 ) 2interp ( linear )"
    points = _parse_ramp_default(raw, is_color=False)
    assert len(points) == 2
    assert points[0] == {"pos": 0.0, "value": 0.0, "interp": "linear"}
    assert points[1] == {"pos": 1.0, "value": 1.0, "interp": "linear"}


def test_ramp_parser_color_triple():
    raw = ("1pos ( 0 ) 1cr ( 1 ) 1cg ( 0 ) 1cb ( 0 ) 1interp ( linear ) "
           "2pos ( 1 ) 2cr ( 0 ) 2cg ( 0 ) 2cb ( 1 ) 2interp ( linear )")
    points = _parse_ramp_default(raw, is_color=True)
    assert len(points) == 2
    assert points[0]["value"] == [1.0, 0.0, 0.0]
    assert points[1]["value"] == [0.0, 0.0, 1.0]


def test_ramp_with_default_tag_in_response(monkeypatch):
    raw = "1pos ( 0 ) 1value ( 0 ) 1interp ( linear ) 2pos ( 1 ) 2value ( 1 ) 2interp ( linear )"
    ramp = FakeRamp("ramp", ramp_type="Float",
                    tags={"rampfloatdefault": raw})
    nt = FakeNodeType("n", parm_templates=[ramp])
    cats = {"Sop": FakeCategory("Sop", {"n": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "n")
    parm = result["parms"][0]
    assert parm["ramp_parm_type"] == "Float"
    assert parm["color_type"] is None
    assert parm["default"]["point_count"] == 2
    assert "default_raw" not in parm  # not verbose


def test_ramp_no_tag_returns_empty(monkeypatch):
    ramp = FakeRamp("ramp", ramp_type="Float", tags={})
    nt = FakeNodeType("n", parm_templates=[ramp])
    cats = {"Sop": FakeCategory("Sop", {"n": nt})}
    install_categories(monkeypatch, cats)

    result = describe_node_type("Sop", "n")
    parm = result["parms"][0]
    assert parm["default"] == {"point_count": 0, "points": []}


# --- _component_names helper unit tests -------------------------------------

def test_component_names_helper_n1():
    pt = FakeFloat("size", n=1, default=[0.0])
    names, unverified = _component_names(pt, 1)
    assert names == ["size"]
    assert unverified is False


def test_component_names_helper_xyzw_n2():
    pt = FakeFloat("uv", n=2, naming="XYZW", default=[0.0, 0.0])
    names, unverified = _component_names(pt, 2)
    assert names == ["uvx", "uvy"]
    assert unverified is False


def test_component_names_helper_unknown_scheme():
    pt = FakeFloat("range", n=2, naming="MinMax", default=[0.0, 1.0])
    names, unverified = _component_names(pt, 2)
    assert names is None
    assert unverified is True
