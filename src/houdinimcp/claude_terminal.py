"""
claude_terminal.py — Claude CLI launcher panel for Houdini.

Provides a PySide2/PySide6-based panel that launches `claude` in the user's
native terminal emulator with full Houdini context: environment variables,
working directory, and an appended system prompt with scene state.

Requires: PySide6 (Houdini 21+) or PySide2 (older).
"""
import os
import re
import shutil
import subprocess
import sys

_IS_WINDOWS = sys.platform == "win32"

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui


# ANSI escape stripping — use pyte if available, otherwise regex fallback
try:
    import pyte
    _PYTE_AVAILABLE = True
except ImportError:
    _PYTE_AVAILABLE = False

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07')


def strip_ansi(text):
    """Remove ANSI escape sequences from text."""
    if _PYTE_AVAILABLE:
        screen = pyte.Screen(200, 50)
        stream = pyte.Stream(screen)
        stream.feed(text)
        return "\n".join(screen.display).rstrip()
    return _ANSI_RE.sub('', text)


def _detect_terminal():
    """Detect the best available terminal emulator.

    Respects CLAUDE_TERMINAL env var as an override.
    """
    override = os.environ.get("CLAUDE_TERMINAL")
    if override and shutil.which(override):
        return override
    if _IS_WINDOWS:
        for cmd in ["wt", "powershell", "cmd"]:
            if shutil.which(cmd):
                return cmd
        return "cmd"
    for cmd in ["x-terminal-emulator", "gnome-terminal", "konsole",
                "xfce4-terminal", "alacritty", "kitty", "xterm"]:
        if shutil.which(cmd):
            return cmd
    return "xterm"


def _build_houdini_env():
    """Build environment dict with Houdini context for the terminal."""
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    port = os.environ.get("HOUDINIMCP_PORT", "9876")
    env["HOUDINIMCP_PORT"] = port
    try:
        import hou
        hip = hou.hipFile.path()
        if hip:
            env["HIP"] = hip
        env["HOUDINI_VERSION"] = hou.applicationVersionString()
    except ImportError:
        pass
    return env


def _build_system_prompt():
    """Build an append-system-prompt string with current Houdini state."""
    lines = []
    port = os.environ.get("HOUDINIMCP_PORT", "9876")
    lines.append(f"Connected to a live Houdini session via MCP (port {port}).")
    try:
        import hou
        lines.append(f"Houdini version: {hou.applicationVersionString()}")
        hip = hou.hipFile.path()
        if hip:
            lines.append(f"Scene file: {hip}")
        lines.append(f"Current frame: {hou.frame()} (FPS: {hou.fps()})")
        obj = hou.node("/obj")
        if obj:
            lines.append(f"Objects in /obj: {len(obj.children())}")
        selected = hou.selectedNodes()
        if selected:
            paths = [n.path() for n in selected[:10]]
            lines.append(f"Selected nodes: {', '.join(paths)}")
    except ImportError:
        pass
    return "\n".join(lines)


def _find_mcp_config():
    """Find the MCP config written during install."""
    config = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp.json")
    if os.path.isfile(config):
        return config
    return None


def _launch_in_terminal(terminal, cmd_args, cwd, env):
    """Launch cmd_args in the specified terminal emulator."""
    if _IS_WINDOWS:
        if terminal == "wt":
            subprocess.Popen(["wt", "-d", cwd] + cmd_args, env=env)
        elif terminal == "powershell":
            ps_cmd = subprocess.list2cmdline(cmd_args)
            subprocess.Popen(
                ["powershell", "-NoExit", "-Command",
                 f"Set-Location '{cwd}'; {ps_cmd}"],
                env=env,
            )
        else:
            cmd_str = subprocess.list2cmdline(cmd_args)
            subprocess.Popen(
                ["cmd", "/k", f'cd /d "{cwd}" && {cmd_str}'],
                env=env,
            )
    else:
        if terminal == "gnome-terminal":
            subprocess.Popen(
                ["gnome-terminal", "--"] + cmd_args, cwd=cwd, env=env
            )
        elif terminal == "kitty":
            subprocess.Popen(
                ["kitty"] + cmd_args, cwd=cwd, env=env
            )
        else:
            # Most terminals support: terminal -e cmd [args...]
            subprocess.Popen(
                [terminal, "-e"] + cmd_args, cwd=cwd, env=env
            )


class ClaudeTerminalWidget(QtWidgets.QWidget):
    """Launcher panel that opens Claude CLI in the native terminal emulator."""

    def __init__(self, parent=None, command=None):
        super().__init__(parent)
        self._command = command or "claude"
        self._cwd = self._default_cwd()
        self._terminal = _detect_terminal()
        self._build_ui()

    @staticmethod
    def _default_cwd():
        try:
            import hou
            hip = hou.hipFile.path()
            if hip:
                return os.path.dirname(hip)
        except ImportError:
            pass
        return os.path.expanduser("~")

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Row 1: Launch + CWD
        toolbar = QtWidgets.QHBoxLayout()

        self._launch_btn = QtWidgets.QPushButton("Open Terminal")
        self._launch_btn.clicked.connect(self._launch)
        toolbar.addWidget(self._launch_btn)

        toolbar.addWidget(QtWidgets.QLabel("CWD:"))
        self._cwd_edit = QtWidgets.QLineEdit(self._cwd)
        self._cwd_edit.setMinimumWidth(120)
        self._cwd_edit.editingFinished.connect(self._on_cwd_changed)
        toolbar.addWidget(self._cwd_edit)

        self._cwd_browse = QtWidgets.QPushButton("...")
        self._cwd_browse.setFixedWidth(30)
        self._cwd_browse.clicked.connect(self._browse_cwd)
        toolbar.addWidget(self._cwd_browse)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Row 2: Context actions
        ctx = QtWidgets.QHBoxLayout()

        self._copy_scene_btn = QtWidgets.QPushButton("Copy Scene Info")
        self._copy_scene_btn.setToolTip("Copy Houdini scene summary to clipboard")
        self._copy_scene_btn.clicked.connect(self._copy_scene_info)
        ctx.addWidget(self._copy_scene_btn)

        self._refresh_btn = QtWidgets.QPushButton("Refresh")
        self._refresh_btn.setToolTip("Refresh the launch configuration display")
        self._refresh_btn.clicked.connect(self._update_info)
        ctx.addWidget(self._refresh_btn)

        ctx.addStretch()
        layout.addLayout(ctx)

        # Info display
        self._info = QtWidgets.QPlainTextEdit()
        self._info.setReadOnly(True)
        self._info.setFont(QtGui.QFont("Courier", 10))
        self._info.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(self._info)

        self._update_info()

    def _update_info(self):
        """Update the info display with current launch configuration."""
        env = _build_houdini_env()
        prompt = _build_system_prompt()
        lines = [
            f"Terminal:  {self._terminal}",
            f"Command:  {self._command}",
            f"CWD:      {self._cwd}",
            "",
            "Environment:",
        ]
        for key in ["HOUDINIMCP_PORT", "HIP", "HOUDINI_VERSION"]:
            if key in env:
                lines.append(f"  {key}={env[key]}")
        mcp_config = _find_mcp_config()
        lines.append(f"  MCP config: {mcp_config or 'not found (no MCP tools)'}")
        lines.append("")
        lines.append("System prompt (appended on launch):")
        for line in prompt.split("\n"):
            lines.append(f"  {line}")
        self._info.setPlainText("\n".join(lines))

    def _launch(self):
        """Launch claude in the detected terminal emulator."""
        env = _build_houdini_env()
        prompt = _build_system_prompt()
        cmd_args = [self._command]
        mcp_config = _find_mcp_config()
        if mcp_config:
            cmd_args.extend(["--mcp-config", mcp_config])
        cmd_args.extend(["--append-system-prompt", prompt])
        _launch_in_terminal(self._terminal, cmd_args, self._cwd, env)
        self._update_info()

    # ---- CWD ----

    def _on_cwd_changed(self):
        path = self._cwd_edit.text().strip()
        if os.path.isdir(path):
            self._cwd = path
            self._update_info()

    def _browse_cwd(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Working Directory", self._cwd)
        if path:
            self._cwd = path
            self._cwd_edit.setText(path)
            self._update_info()

    # ---- Context ----

    def _copy_scene_info(self):
        """Copy scene summary to clipboard for pasting in terminal."""
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(_build_system_prompt())


def create_panel():
    """Entry point called by the .pypanel definition."""
    return ClaudeTerminalWidget()
