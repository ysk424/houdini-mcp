"""Tests for Steam-only Houdini launcher detection."""
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import launch


def _make_steam_houdini(root):
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    exe = bin_dir / "hindie.steam.exe"
    exe.write_text("")
    (bin_dir / "steam_appid.txt").write_text("502570")
    return str(exe)


def test_find_houdini_detects_default_steam_location(tmp_path, monkeypatch):
    monkeypatch.delenv("HOUDINI_PATH", raising=False)
    program_files_x86 = tmp_path / "Program Files (x86)"
    exe = _make_steam_houdini(
        program_files_x86 / "Steam" / "steamapps" / "common" / "Houdini Indie"
    )
    monkeypatch.setenv("PROGRAMFILES(X86)", str(program_files_x86))

    assert launch.find_houdini() == exe


def test_find_houdini_rejects_non_steam_houdini_path(tmp_path, monkeypatch):
    regular_bin = tmp_path / "Side Effects Software" / "Houdini 21.0" / "bin"
    regular_bin.mkdir(parents=True)
    regular_houdini = regular_bin / "houdini.exe"
    regular_houdini.write_text("")

    monkeypatch.setenv("HOUDINI_PATH", str(regular_houdini))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "missing"))

    assert launch.find_houdini() is None


def test_houdini_path_accepts_only_steam_executable(tmp_path, monkeypatch):
    exe = _make_steam_houdini(tmp_path / "Houdini Indie")
    monkeypatch.setenv("HOUDINI_PATH", exe)
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "missing"))

    assert launch.find_houdini() == exe
