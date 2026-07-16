#!/usr/bin/env python3
"""
install.py — Set up HoudiniMCP for automatic loading in Houdini 22.

The plugin runs directly from this repository: instead of copying the Python
sources into the Houdini prefs directory, the generated package puts
<repo>/src on Houdini's PYTHONPATH. Edits to the working tree take effect on
the next Houdini restart, with no reinstall step.

This script:
1. Detects the Houdini 22 user preferences directory
2. Writes a packages JSON pointing PYTHONPATH at <repo>/src
3. Copies the panel/shelf definitions (Houdini only scans those under prefs)
4. Adds the UI-ready auto-start hook

Usage:
    python install.py                    # Install for Houdini 22
    python install.py --prefs-dir /path/to/houdini22.0  # Explicit prefs directory
    python install.py --claude-code      # Also auto-allow Houdini MCP tools in Claude Code
    python install.py --codex            # Also register Houdini MCP in Codex
    python install.py --dry-run          # Show what would be done without doing it
"""
import os
import sys
import shutil
import json
import argparse
import platform
import re


# Houdini 22 only. Its embedded interpreter is Python 3.13, which fixes the
# prefs subdirectory Houdini scans for startup scripts.
HOUDINI_VERSION = "22.0"
PYTHON_LIBS_DIR = "python3.13libs"

PANEL_FILES = [
    "src/houdinimcp/ClaudeTerminal.pypanel",
]
SHELF_FILES = [
    "src/houdinimcp/houdinimcp.shelf",
]
PACKAGE_NAME = "houdinimcp"


def find_houdini_prefs():
    """Return the Houdini 22 user preferences directory."""
    system = platform.system()
    home = os.path.expanduser("~")

    if system == "Windows":
        return os.path.join(home, "Documents", f"houdini{HOUDINI_VERSION}")
    if system == "Darwin":
        return os.path.join(home, "Library", "Preferences", "houdini", HOUDINI_VERSION)
    return os.path.join(home, f"houdini{HOUDINI_VERSION}")


def install(prefs_dir, source_dir, dry_run=False):
    """Point Houdini at the plugin in this repo and create the packages JSON."""
    python_src = os.path.join(source_dir, "src")
    packages_dir = os.path.join(prefs_dir, "packages")

    print(f"Source directory:  {source_dir}")
    print(f"Plugin runs from:  {python_src} (no copy)")
    print(f"Package config:    {os.path.join(packages_dir, f'{PACKAGE_NAME}.json')}")
    print()

    if not os.path.isdir(os.path.join(python_src, PACKAGE_NAME)):
        print(f"Error: {os.path.join(python_src, PACKAGE_NAME)} not found.", file=sys.stderr)
        sys.exit(1)

    # An older install copied the plugin into the prefs tree. That copy sits on
    # PYTHONPATH too and would shadow this repo, so retire it.
    stale_copy = os.path.join(prefs_dir, "scripts", "python", PACKAGE_NAME)
    if os.path.isdir(stale_copy):
        if dry_run:
            print(f"  REMOVE stale copied plugin {stale_copy}")
        else:
            shutil.rmtree(stale_copy)
            print(f"  Removed stale copied plugin {stale_copy}")

    # Copy .pypanel files to Houdini's python_panels directory
    panels_dest = os.path.join(prefs_dir, "python_panels")
    if not dry_run:
        os.makedirs(panels_dest, exist_ok=True)
    for filepath in PANEL_FILES:
        src = os.path.join(source_dir, filepath)
        dst = os.path.join(panels_dest, os.path.basename(filepath))
        if not os.path.isfile(src):
            print(f"  SKIP {filepath} (not found in source)")
            continue
        if dry_run:
            print(f"  COPY {src} -> {dst}")
        else:
            shutil.copy2(src, dst)
            print(f"  Copied {os.path.basename(filepath)} -> python_panels/")

    # Copy .shelf files to Houdini's toolbar directory
    toolbar_dest = os.path.join(prefs_dir, "toolbar")
    if not dry_run:
        os.makedirs(toolbar_dest, exist_ok=True)
    for filepath in SHELF_FILES:
        src = os.path.join(source_dir, filepath)
        dst = os.path.join(toolbar_dest, os.path.basename(filepath))
        if not os.path.isfile(src):
            print(f"  SKIP {filepath} (not found in source)")
            continue
        if dry_run:
            print(f"  COPY {src} -> {dst}")
        else:
            shutil.copy2(src, dst)
            print(f"  Copied {os.path.basename(filepath)} -> toolbar/")

    # Create packages JSON.
    # Use forward slashes for cross-platform Houdini compatibility.
    # No "path" entry: that would put the repo root on HOUDINI_PATH and let
    # Houdini scan its scripts/ and toolbar/ as if they were prefs dirs. Only
    # PYTHONPATH is needed to make `import houdinimcp` resolve to the repo.
    package_json = {
        "load_package_once": True,
        "version": "0.1",
        "env": [
            {
                "PYTHONPATH": {
                    "value": python_src.replace("\\", "/"),
                    "method": "append",
                }
            }
        ]
    }

    package_file = os.path.join(packages_dir, f"{PACKAGE_NAME}.json")
    if dry_run:
        print(f"\n  WRITE {package_file}:")
        print(f"  {json.dumps(package_json, indent=2)}")
    else:
        os.makedirs(packages_dir, exist_ok=True)
        with open(package_file, "w") as f:
            json.dump(package_json, f, indent=2)
        print(f"\n  Created package file: {package_file}")

    # Write MCP config so Claude Code launched from Houdini gets MCP tools
    mcp_config = {
        "mcpServers": {
            "houdini": {
                "command": "uv",
                "args": ["--directory", source_dir, "run", "python", "houdini_mcp_server.py"],
            }
        }
    }
    # claude_terminal.py looks for mcp.json next to itself, which now means
    # inside the repo. It holds machine-specific paths, so it stays untracked.
    mcp_config_path = os.path.join(python_src, PACKAGE_NAME, "mcp.json")
    if dry_run:
        print(f"  WRITE {mcp_config_path}")
    else:
        with open(mcp_config_path, "w") as f:
            json.dump(mcp_config, f, indent=2)
            f.write("\n")
        print(f"  Created MCP config: {mcp_config_path}")

    # Create/update uiready.py so Houdini auto-imports the plugin after the GUI is ready.
    # pythonrc.py is too early for the QTimer-backed GUI server, and it is discovered from
    # pythonX.Ylibs/pythonrc.py, not scripts/pythonrc.py.
    startup_code = "import houdinimcp  # Auto-start HoudiniMCP server\n"
    startup_targets = [
        os.path.join(prefs_dir, PYTHON_LIBS_DIR, "uiready.py"),
    ]
    legacy_startup_paths = [
        os.path.join(prefs_dir, "scripts", "pythonrc.py"),
        os.path.join(prefs_dir, "scripts", "python", "uiready.py"),
    ]
    for legacy_path in legacy_startup_paths:
        if not os.path.isfile(legacy_path):
            continue
        with open(legacy_path, encoding="utf-8") as f:
            legacy_content = f.read()
        if "import houdinimcp" not in legacy_content:
            continue
        cleaned_lines = [
            line for line in legacy_content.splitlines()
            if "import houdinimcp" not in line
            and "HOUDINIMCP_STARTUP_LOG" not in line
        ]
        cleaned = "\n".join(cleaned_lines).strip()
        if dry_run:
            print(f"  CLEAN legacy HoudiniMCP auto-start from {legacy_path}")
        elif cleaned:
            with open(legacy_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(cleaned + "\n")
            print(f"  Removed legacy HoudiniMCP auto-start from {legacy_path}")
        else:
            os.remove(legacy_path)
            print(f"  Removed legacy HoudiniMCP auto-start file {legacy_path}")
    for startup_path in startup_targets:
        existing_content = ""
        if os.path.isfile(startup_path):
            with open(startup_path, encoding="utf-8") as f:
                existing_content = f.read()

        if "import houdinimcp" in existing_content:
            print(f"  {startup_path} already imports houdinimcp")
        elif dry_run:
            print(f"  APPEND auto-start import to {startup_path}")
        else:
            os.makedirs(os.path.dirname(startup_path), exist_ok=True)
            with open(startup_path, "a", encoding="utf-8", newline="\n") as f:
                if existing_content and not existing_content.endswith("\n"):
                    f.write("\n")
                f.write(startup_code)
            print(f"  Added UI-ready auto-start to {startup_path}")

    print("\nDone!" if not dry_run else "\nDry run complete - no files were changed.")
    if not dry_run:
        print("Restart Houdini for changes to take effect.")
        print("The MCP server will auto-start when Houdini loads the plugin.")


def main():
    parser = argparse.ArgumentParser(
        description=f"Install HoudiniMCP plugin for auto-loading in Houdini {HOUDINI_VERSION}")
    parser.add_argument("--prefs-dir", default=None, help="Explicit Houdini preferences directory")
    parser.add_argument("--claude-code", action="store_true",
                        help="Auto-allow Houdini MCP tools in Claude Code (no per-tool prompts)")
    parser.add_argument("--codex", action="store_true",
                        help="Register the Houdini MCP bridge in Codex config.toml")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    args = parser.parse_args()

    # scripts/ is one level below the repo root
    source_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    prefs_dir = args.prefs_dir or find_houdini_prefs()

    if not os.path.isdir(prefs_dir):
        print(f"Error: Houdini {HOUDINI_VERSION} preferences directory not found: {prefs_dir}",
              file=sys.stderr)
        print("Launch Houdini once to create it, or pass --prefs-dir.", file=sys.stderr)
        sys.exit(1)

    print(f"Houdini prefs directory: {prefs_dir}\n")
    install(prefs_dir, source_dir, args.dry_run)

    if args.claude_code:
        configure_claude_code(args.dry_run)
    if args.codex:
        configure_codex(source_dir, args.dry_run)


def configure_claude_code(dry_run=False):
    """Add HoudiniMCP permissions to Claude Code's allowed tools."""
    settings_dir = os.path.join(os.path.expanduser("~"), ".claude")
    settings_file = os.path.join(settings_dir, "settings.json")

    permissions = [
        "mcp__houdini__*",
        "Bash(mplay *)",
        "Bash(ls -la /tmp/*)",
        "Read(/tmp/*)",
    ]

    if os.path.isfile(settings_file):
        with open(settings_file) as f:
            settings = json.load(f)
    else:
        settings = {}

    allow_list = settings.setdefault("permissions", {}).setdefault("allow", [])
    added = []
    for permission in permissions:
        if permission not in allow_list:
            added.append(permission)
            if not dry_run:
                allow_list.append(permission)

    if not added:
        print(f"\nClaude Code: All permissions already in {settings_file}")
        return

    if dry_run:
        for permission in added:
            print(f"\n  WOULD ADD '{permission}' to {settings_file}")
        return

    os.makedirs(settings_dir, exist_ok=True)
    with open(settings_file, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    for permission in added:
        print(f"  Claude Code: Added '{permission}' to {settings_file}")
    print("Houdini MCP tools and mplay will no longer require per-call approval.")


def configure_codex(source_dir, dry_run=False):
    """Register the bridge in Codex's TOML configuration."""
    config_dir = os.path.join(os.path.expanduser("~"), ".codex")
    config_file = os.path.join(config_dir, "config.toml")
    bridge_script = os.path.join(source_dir, "houdini_mcp_server.py")
    if platform.system() == "Windows":
        venv_python = os.path.join(source_dir, ".venv", "Scripts", "python.exe")
    else:
        venv_python = os.path.join(source_dir, ".venv", "bin", "python")
    bridge_python = venv_python if os.path.isfile(venv_python) else sys.executable

    def toml_literal(value):
        return "'" + value.replace("'", "''") + "'"

    block = (
        "[mcp_servers.houdini]\n"
        f"command = {toml_literal(bridge_python)}\n"
        f"args = [{json.dumps(bridge_script)}]\n"
    )

    existing = ""
    if os.path.isfile(config_file):
        with open(config_file, encoding="utf-8") as f:
            existing = f.read()

    section_pattern = re.compile(
        r"(?ms)^\[mcp_servers\.houdini\]\n.*?(?=^\[|\Z)"
    )
    if section_pattern.search(existing):
        updated = section_pattern.sub(lambda _match: block + "\n", existing, count=1)
    else:
        separator = "" if not existing or existing.endswith("\n\n") else "\n"
        updated = existing + separator + block

    if updated == existing:
        print(f"\nCodex: Houdini MCP is already registered in {config_file}")
        return
    if dry_run:
        print(f"\n  WOULD REGISTER Houdini MCP in {config_file}:")
        print(block)
        return

    os.makedirs(config_dir, exist_ok=True)
    with open(config_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated)
    print(f"\nCodex: Registered Houdini MCP in {config_file}")
    print("Restart Codex to load the Houdini MCP tools.")


if __name__ == "__main__":
    main()
