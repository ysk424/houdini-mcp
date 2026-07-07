"""Tests for Steam-only headless hython detection in the MCP bridge."""
import ast
import os
import types


def _load_bridge_detection():
    bridge_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "houdini_mcp_server.py",
    )
    with open(bridge_path, encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    wanted_functions = {
        "_steam_houdini_root_candidates",
        "_is_steam_houdini_root",
        "find_hython",
    }
    nodes = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "os" for alias in node.names):
                nodes.append(node)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "typing":
                nodes.append(node)
        elif isinstance(node, ast.Assign):
            if any(getattr(target, "id", None) == "STEAM_HOUDINI_DIR_ENV" for target in node.targets):
                nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted_functions:
            nodes.append(node)

    ns = {"__builtins__": __builtins__}
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(module, bridge_path, "exec"), ns)
    return types.SimpleNamespace(
        find_hython=ns["find_hython"],
        steam_env=ns["STEAM_HOUDINI_DIR_ENV"],
    )


def _make_steam_houdini(root, hython_name="hython.exe"):
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    hython = bin_dir / hython_name
    hython.write_text("")
    (bin_dir / "steam_appid.txt").write_text("502570")
    return str(hython)


def test_find_hython_detects_default_steam_location(tmp_path, monkeypatch):
    bridge = _load_bridge_detection()
    monkeypatch.delenv("HFS", raising=False)
    monkeypatch.delenv(bridge.steam_env, raising=False)

    program_files_x86 = tmp_path / "Program Files (x86)"
    hython = _make_steam_houdini(
        program_files_x86 / "Steam" / "steamapps" / "common" / "Houdini Indie"
    )
    monkeypatch.setenv("PROGRAMFILES(X86)", str(program_files_x86))

    assert bridge.find_hython() == hython


def test_find_hython_rejects_non_steam_hfs(tmp_path, monkeypatch):
    bridge = _load_bridge_detection()
    regular_bin = tmp_path / "Side Effects Software" / "Houdini 21.0" / "bin"
    regular_bin.mkdir(parents=True)
    regular_hython = regular_bin / "hython.exe"
    regular_hython.write_text("")

    monkeypatch.setenv("HFS", str(regular_bin.parent))
    monkeypatch.delenv(bridge.steam_env, raising=False)
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "missing"))

    assert bridge.find_hython() is None


def test_find_hython_accepts_steam_hfs(tmp_path, monkeypatch):
    bridge = _load_bridge_detection()
    steam_root = tmp_path / "Houdini Indie"
    hython = _make_steam_houdini(steam_root, hython_name="hython3.11.exe")

    monkeypatch.setenv("HFS", str(steam_root))
    monkeypatch.delenv(bridge.steam_env, raising=False)
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "missing"))

    assert bridge.find_hython() == hython
