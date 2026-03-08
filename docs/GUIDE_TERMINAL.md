# Claude Terminal Panel Guide

The Claude Terminal panel is a launcher that opens Claude Code (CLI) in your
native terminal emulator with full Houdini context. Claude gets environment
variables, working directory, and a system prompt describing your current scene.

## Opening the Panel

- Click **Claude Terminal** on the **HoudiniMCP** shelf toolbar (one click)
- Or: **Window > Python Panels > Claude Terminal**

The panel appears as a floating window. Drag it into any pane layout to dock it.

## Features

### Open Terminal

Click **Open Terminal** to launch `claude` in your system's terminal emulator.
The panel auto-detects the best available terminal:

- **Linux**: x-terminal-emulator, gnome-terminal, konsole, xfce4-terminal,
  alacritty, kitty, xterm
- **Windows**: Windows Terminal (wt), PowerShell, cmd

Override detection by setting the `CLAUDE_TERMINAL` environment variable to
your preferred terminal command.

### Working Directory

- The **CWD** field shows the working directory for new sessions
- Defaults to the directory of the current .hip file (or $HOME)
- Click **"..."** to browse for a different directory
- Edit the path directly and press Enter

### Context Preamble

Each launch passes context to Claude via `--append-system-prompt`:

- Houdini version
- Scene file path
- Current frame and FPS
- Object count in /obj
- Currently selected nodes (up to 10)
- MCP server port

This context is shown in the info display before launch so you can verify it.

### Copy Scene Info

Click **Copy Scene Info** to copy the current Houdini scene summary to your
clipboard. Paste it into the terminal to give Claude additional context
mid-conversation.

### Refresh

Click **Refresh** to update the info display with the latest Houdini state
(frame changes, selection changes, etc.) before launching.

## Environment Variables

The terminal is launched with these environment variables set:

| Variable | Value |
|----------|-------|
| `TERM` | `xterm-256color` |
| `HOUDINIMCP_PORT` | The MCP server port (default 9876) |
| `HIP` | Path to the current .hip file |
| `HOUDINI_VERSION` | Houdini version string |

This means Claude Code automatically knows how to connect to your Houdini session.

## Requirements

- `claude` CLI must be installed and on your PATH
- A terminal emulator must be installed (most systems have one by default)
- The HoudiniMCP plugin must be loaded (for scene context to work)
- PySide2/PySide6 is bundled with Houdini

## Troubleshooting

- **Panel not listed**: Re-run `python scripts/install.py` to install the `.pypanel` file
- **Terminal doesn't open**: Check that your terminal emulator is on PATH. Set
  `CLAUDE_TERMINAL` to the exact command name if auto-detection fails.
- **No Houdini context**: Make sure the HoudiniMCP plugin is loaded before
  opening the panel. The `hou` module must be available.
- **Wrong working directory**: Update the CWD field and click Refresh before
  launching.
