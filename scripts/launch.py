#!/usr/bin/env python3
"""
launch.py — Start Houdini with the MCP plugin and optionally the MCP bridge.

Usage:
    python launch.py                  # Launch Houdini only (bridge started separately)
    python launch.py --bridge         # Launch Houdini + MCP bridge
    python launch.py --bridge-only    # Launch MCP bridge only (Houdini already running)

Environment variables:
    HOUDINI_PATH       Path to Steam hindie.steam.exe
    HOUDINIMCP_STEAM_HOUDINI_DIR
                       Steam Houdini Indie install root when outside the default library
    HOUDINIMCP_PORT    TCP port for plugin communication (default: 9876)
    HOUDINIMCP_HIP     Optional .hip file to open on launch
"""
import os
import sys
import subprocess
import argparse


STEAM_HOUDINI_DIR_ENV = "HOUDINIMCP_STEAM_HOUDINI_DIR"


def _steam_houdini_root_candidates():
    """Return Steam Houdini Indie install roots to probe."""
    candidates = []
    override = os.environ.get(STEAM_HOUDINI_DIR_ENV)
    if override:
        candidates.append(override)
    candidates.append(os.path.join(
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        "Steam", "steamapps", "common", "Houdini Indie",
    ))
    return candidates


def _is_steam_houdini_root(path):
    """True when path looks like the Steam Houdini Indie install root."""
    if not path or not os.path.isdir(path):
        return False
    return os.path.isfile(os.path.join(path, "bin", "steam_appid.txt"))


def _is_steam_houdini_executable(path):
    """True for Steam Houdini Indie's launcher executable."""
    if not path or not os.path.isfile(path):
        return False
    if os.path.basename(path).lower() != "hindie.steam.exe":
        return False
    return _is_steam_houdini_root(os.path.dirname(os.path.dirname(path)))


def find_houdini():
    """Locate the Steam Houdini Indie executable."""
    env_path = os.environ.get("HOUDINI_PATH")
    if _is_steam_houdini_executable(env_path):
        return env_path

    for root in _steam_houdini_root_candidates():
        candidate = os.path.join(root, "bin", "hindie.steam.exe")
        if _is_steam_houdini_executable(candidate):
            return candidate

    return None


def launch_houdini(houdini_path, hip_file=None):
    """Launch Houdini as a detached subprocess."""
    cmd = [houdini_path]
    if hip_file:
        cmd.append(hip_file)

    print(f"Launching Houdini: {' '.join(cmd)}")
    subprocess.Popen(cmd, start_new_session=True)


def launch_bridge():
    """Launch the MCP bridge server in the foreground."""
    # scripts/ is one level below the repo root where houdini_mcp_server.py lives
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bridge_script = os.path.join(repo_root, "houdini_mcp_server.py")

    if not os.path.isfile(bridge_script):
        print(f"Error: Bridge script not found at {bridge_script}", file=sys.stderr)
        sys.exit(1)

    print(f"Starting MCP bridge: uv run python {bridge_script}")
    try:
        subprocess.run(["uv", "run", "python", bridge_script])
    except KeyboardInterrupt:
        print("\nMCP bridge stopped.")


def main():
    parser = argparse.ArgumentParser(description="Launch HoudiniMCP components")
    parser.add_argument("--bridge", action="store_true", help="Also start the MCP bridge after launching Houdini")
    parser.add_argument("--bridge-only", action="store_true", help="Start only the MCP bridge (Houdini already running)")
    parser.add_argument("--hip", default=os.environ.get("HOUDINIMCP_HIP"), help="Path to .hip file to open")
    parser.add_argument("--houdini-path", default=None, help="Explicit path to Steam hindie.steam.exe")
    args = parser.parse_args()

    if args.bridge_only:
        launch_bridge()
        return

    if args.houdini_path:
        if not _is_steam_houdini_executable(args.houdini_path):
            print("Error: --houdini-path must point to Steam Houdini Indie hindie.steam.exe.", file=sys.stderr)
            sys.exit(1)
        houdini_path = args.houdini_path
    else:
        houdini_path = find_houdini()
    if not houdini_path:
        print("Error: Could not find Steam Houdini Indie. Set HOUDINI_PATH, "
              f"{STEAM_HOUDINI_DIR_ENV}, or use --houdini-path.", file=sys.stderr)
        sys.exit(1)

    launch_houdini(houdini_path, args.hip)

    if args.bridge:
        print("Waiting a few seconds for Houdini to start...")
        import time
        time.sleep(5)
        launch_bridge()
    else:
        print("Houdini launched. Start the MCP bridge separately with: uv run python houdini_mcp_server.py")


if __name__ == "__main__":
    main()
