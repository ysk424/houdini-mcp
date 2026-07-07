"""Tests for scripts/ingest_hips.py — Houdini install detection & .hip discovery."""
import os
import sys

# scripts/ is not a package — add it to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from ingest_hips import find_houdini_install, discover_hip_files


# ---------------------------------------------------------------------------
# find_houdini_install
# ---------------------------------------------------------------------------
class TestFindHoudiniInstall:
    def _make_steam_root(self, path):
        bin_dir = path / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "steam_appid.txt").write_text("502570")
        return str(path)

    def test_hfs_dir_arg_valid(self, tmp_path):
        """Explicit Steam --hfs-dir is returned."""
        steam_root = self._make_steam_root(tmp_path / "Houdini Indie")
        result = find_houdini_install(hfs_dir=steam_root)
        assert result == steam_root

    def test_hfs_dir_arg_missing(self):
        """Explicit --hfs-dir that doesn't exist returns None."""
        result = find_houdini_install(hfs_dir="/nonexistent/hfs99.9")
        assert result is None

    def test_hfs_dir_arg_rejects_non_steam(self, tmp_path):
        """Explicit non-Steam Houdini roots are ignored."""
        regular_root = tmp_path / "Houdini 21.0"
        (regular_root / "bin").mkdir(parents=True)
        result = find_houdini_install(hfs_dir=str(regular_root))
        assert result is None

    def test_hfs_env_var(self, tmp_path, monkeypatch):
        """$HFS env var pointing to Steam Houdini is returned."""
        steam_root = self._make_steam_root(tmp_path / "Houdini Indie")
        monkeypatch.setenv("HFS", steam_root)
        result = find_houdini_install()
        assert result == steam_root

    def test_hfs_env_var_invalid(self, monkeypatch):
        """$HFS set but dir doesn't exist — falls through."""
        monkeypatch.setenv("HFS", "/nonexistent/hfs")
        monkeypatch.setenv("PROGRAMFILES(X86)", "/nonexistent/programfiles")
        result = find_houdini_install()
        assert result is None

    def test_known_steam_location(self, tmp_path, monkeypatch):
        """Default Steam install location is detected."""
        monkeypatch.delenv("HFS", raising=False)
        program_files_x86 = tmp_path / "Program Files (x86)"
        steam_root = self._make_steam_root(
            program_files_x86 / "Steam" / "steamapps" / "common" / "Houdini Indie"
        )
        monkeypatch.setenv("PROGRAMFILES(X86)", str(program_files_x86))
        result = find_houdini_install()
        assert result == steam_root

    def test_nothing_found(self, monkeypatch):
        """No env and no Steam install returns None."""
        monkeypatch.delenv("HFS", raising=False)
        monkeypatch.setenv("PROGRAMFILES(X86)", "/nonexistent/programfiles")
        result = find_houdini_install()
        assert result is None


# ---------------------------------------------------------------------------
# discover_hip_files
# ---------------------------------------------------------------------------
class TestDiscoverHipFiles:
    def _make_tree(self, base, files):
        """Create files in a directory tree. files is a list of relative paths."""
        for rel in files:
            full = os.path.join(base, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write("dummy")

    def test_finds_hip_and_hda(self, tmp_path):
        """Discovers .hip, .hipnc, .hda, .otl under $HFS subdirs."""
        hfs = str(tmp_path / "hfs")
        self._make_tree(hfs, [
            "houdini/help/examples/sop/box.hip",
            "houdini/help/examples/sop/scatter.hipnc",
            "houdini/otls/custom.hda",
            "packages/demo/legacy.otl",
            "houdini/help/examples/sop/readme.txt",  # should be ignored
        ])
        results = discover_hip_files(hfs)
        assert len(results) == 4
        types = {r["type"] for r in results}
        assert types == {"hip", "hda"}

    def test_file_entry_fields(self, tmp_path):
        """Each entry has path, type, size, rel_dir."""
        hfs = str(tmp_path / "hfs")
        self._make_tree(hfs, ["houdini/help/sop/box.hip"])
        results = discover_hip_files(hfs)
        assert len(results) == 1
        entry = results[0]
        assert set(entry.keys()) == {"path", "type", "size", "rel_dir"}
        assert entry["type"] == "hip"
        assert entry["size"] > 0
        assert entry["rel_dir"] == "sop"

    def test_extra_dirs(self, tmp_path):
        """--extra-dir paths are also scanned."""
        hfs = str(tmp_path / "hfs")
        extra = str(tmp_path / "my_hips")
        self._make_tree(hfs, ["houdini/help/sop/box.hip"])
        self._make_tree(extra, ["project/scene.hip"])

        results = discover_hip_files(hfs, extra_dirs=[extra])
        assert len(results) == 2

    def test_no_known_subdirs(self, tmp_path):
        """hfs_path with no known subdirs returns empty list."""
        hfs = str(tmp_path / "hfs")
        os.makedirs(hfs)
        results = discover_hip_files(hfs)
        assert results == []

    def test_extra_dir_missing(self, tmp_path):
        """Non-existent extra dir is silently skipped."""
        hfs = str(tmp_path / "hfs")
        os.makedirs(hfs)
        results = discover_hip_files(hfs, extra_dirs=["/nonexistent/dir"])
        assert results == []

    def test_nested_subdirectories(self, tmp_path):
        """Files in deeply nested dirs are found."""
        hfs = str(tmp_path / "hfs")
        self._make_tree(hfs, [
            "houdini/help/a/b/c/deep.hip",
            "houdini/help/x/flat.hipnc",
        ])
        results = discover_hip_files(hfs)
        assert len(results) == 2
        rel_dirs = {r["rel_dir"] for r in results}
        assert os.path.join("a", "b", "c") in rel_dirs
        assert "x" in rel_dirs

    def test_multiple_subdirs(self, tmp_path):
        """Files from multiple $HFS subdirs are all discovered."""
        hfs = str(tmp_path / "hfs")
        self._make_tree(hfs, [
            "houdini/help/examples/box.hip",
            "houdini/otls/tools.hda",
            "packages/demo/scene.hip",
            "toolkit/samples/test.hipnc",
            "engine/examples/export.hip",
        ])
        results = discover_hip_files(hfs)
        assert len(results) == 5
