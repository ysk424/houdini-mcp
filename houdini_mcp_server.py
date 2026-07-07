#!/usr/bin/env python
"""
houdini_mcp_server.py

This is the "bridge" or "driver" script that Claude will run via `uv run`.
It uses the MCP library (fastmcp) to communicate with Claude over stdio,
and relays each command to the local Houdini plugin on port 9876.
"""
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))

import glob as _glob
_venv_candidates = [
    os.path.join(script_dir, '.venv', 'Lib', 'site-packages'),
    *_glob.glob(os.path.join(script_dir, '.venv', 'lib', 'python*', 'site-packages')),
]
for venv_site_packages in _venv_candidates:
    if os.path.exists(venv_site_packages):
        sys.path.insert(0, venv_site_packages)
        break
import json
import socket
import subprocess
import logging
import tempfile
import atexit
import time as _time
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager
import base64 as _base64
from mcp.server.fastmcp import FastMCP, Context, Image
import asyncio

HOUDINI_PORT = int(os.getenv("HOUDINIMCP_PORT", 9876))
HEADLESS_DISABLED = os.getenv("HOUDINIMCP_NO_HEADLESS", "").strip() in ("1", "true", "yes")
STEAM_HOUDINI_DIR_ENV = "HOUDINIMCP_STEAM_HOUDINI_DIR"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HoudiniMCP_StdioServer")


@dataclass
class HoudiniConnection:
    host: str
    port: int
    sock: socket.socket = None
    connected_since: float = None
    last_command_at: float = None
    command_count: int = 0

    def connect(self) -> bool:
        """Connect to the Houdini plugin (which is listening on self.host:self.port)."""
        if self.sock is not None:
            return True  # Already connected
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.connected_since = asyncio.get_event_loop().time()
            logger.info(f"Connected to Houdini at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Houdini: {str(e)}")
            self.sock = None
            self.connected_since = None
            return False

    def disconnect(self):
        """Close socket if open."""
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error disconnecting from Houdini: {str(e)}")
            self.sock = None
            self.connected_since = None

    def get_status(self) -> dict:
        """Return current connection status info."""
        return {
            "connected": self.sock is not None,
            "host": self.host,
            "port": self.port,
            "connected_since": self.connected_since,
            "last_command_at": self.last_command_at,
            "command_count": self.command_count,
        }

    def send_command(self, cmd_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Send a JSON command to Houdini's server and wait for the JSON response.
        Returns the parsed Python dict (e.g. {"status": "success", "result": {...}})
        """
        if not self.connect():
            error_msg = f"Could not connect to Houdini on port {self.port}."
            logger.error(error_msg)
            return {"status": "error", "message": error_msg, "origin": "mcp_server_connection"}

        command = {"type": cmd_type, "params": params or {}}
        data_out = json.dumps(command).encode("utf-8")

        timeout = 30.0
        recv_size = 8192

        try:
            # Send the command
            self.sock.sendall(data_out)
            self.last_command_at = asyncio.get_event_loop().time()
            self.command_count += 1
            logger.info(f"Sent command to Houdini: {command}")

            # Read response. We'll accumulate chunks until we can parse a full JSON.
            self.sock.settimeout(timeout)
            buffer = b""
            start_time = asyncio.get_event_loop().time()
            while True:
                if asyncio.get_event_loop().time() - start_time > timeout:
                     raise socket.timeout("Timeout waiting for Houdini response")

                chunk = self.sock.recv(recv_size)
                if not chunk:
                    if buffer:
                         raise ConnectionAbortedError("Connection closed by Houdini with incomplete data.")
                    else:
                         raise ConnectionAbortedError("Connection closed by Houdini before sending data.")

                buffer += chunk
                try:
                    decoded_string = buffer.decode("utf-8")
                    parsed = json.loads(decoded_string)
                    logger.info(f"Received response from Houdini: {parsed}")
                    return parsed
                except json.JSONDecodeError:
                    continue
                except UnicodeDecodeError:
                     logger.error("Received non-UTF-8 data from Houdini")
                     raise ValueError("Received non-UTF-8 data from Houdini")

        except socket.timeout:
            error_msg = "Timeout receiving data from Houdini."
            logger.error(error_msg)
            self.disconnect()
            return {"status": "error", "message": error_msg, "origin": "mcp_server_send_command_timeout"}
        except Exception as e:
            error_msg = f"Error during Houdini communication for command '{cmd_type}': {str(e)}"
            logger.error(error_msg)
            self.disconnect()
            return {"status": "error", "message": error_msg, "origin": "mcp_server_send_command"}


# ---- Headless hython management ----

_hython_process = None


def _steam_houdini_root_candidates() -> List[str]:
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


def _is_steam_houdini_root(path: str) -> bool:
    """True when path looks like the Steam Houdini Indie install root."""
    if not path or not os.path.isdir(path):
        return False
    return os.path.isfile(os.path.join(path, "bin", "steam_appid.txt"))


def find_hython() -> Optional[str]:
    """Locate Steam Houdini Indie's hython binary."""
    candidates = []

    # HFS may be set when launched from Houdini's environment. Accept it only
    # when it points at the Steam install, so the bridge never starts the
    # SideFX-installed build by accident.
    hfs = os.environ.get("HFS")
    if hfs:
        candidates.append(hfs)
    candidates.extend(_steam_houdini_root_candidates())

    for root in candidates:
        if not _is_steam_houdini_root(root):
            continue
        for name in ("hython.exe", "hython3.11.exe", "hython"):
            candidate = os.path.join(root, "bin", name)
            if os.path.isfile(candidate):
                return candidate
    return None


def _port_is_listening(port: int, host: str = "localhost") -> bool:
    """Check if a TCP port is accepting connections."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect((host, port))
        return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


def _launch_headless_houdini() -> bool:
    """Launch hython with the headless MCP server. Returns True if server is ready."""
    global _hython_process
    if _hython_process and _hython_process.poll() is None:
        return _port_is_listening(HOUDINI_PORT)

    hython = find_hython()
    if not hython:
        logger.warning("Cannot launch headless Houdini: Steam Houdini Indie hython not found.")
        return False

    headless_script = os.path.join(script_dir, "scripts", "headless_server.py")
    if not os.path.isfile(headless_script):
        logger.error(f"Headless server script not found: {headless_script}")
        return False

    env = os.environ.copy()
    env["HOUDINIMCP_PORT"] = str(HOUDINI_PORT)

    logger.info(f"Launching headless Houdini: {hython} {headless_script}")
    _hython_process = subprocess.Popen(
        [hython, headless_script],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for the server to start listening (up to 30 seconds — hython startup is slow)
    for _ in range(60):
        if _hython_process.poll() is not None:
            # Process exited unexpectedly
            stderr = _hython_process.stderr.read().decode(errors="replace")
            logger.error(f"hython exited early (code {_hython_process.returncode}): {stderr[:500]}")
            _hython_process = None
            return False
        if _port_is_listening(HOUDINI_PORT):
            logger.info("Headless Houdini is ready.")
            return True
        _time.sleep(0.5)

    logger.error("Headless Houdini failed to start within 30 seconds.")
    _cleanup_hython()
    return False


def _cleanup_hython():
    """Terminate the managed hython process if running."""
    global _hython_process
    if _hython_process and _hython_process.poll() is None:
        logger.info("Shutting down headless Houdini...")
        _hython_process.terminate()
        try:
            _hython_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _hython_process.kill()
            _hython_process.wait()
    _hython_process = None


atexit.register(_cleanup_hython)


# ---- Global connection ----

_houdini_connection: HoudiniConnection = None


def get_houdini_connection() -> HoudiniConnection:
    """Get or create a persistent HoudiniConnection object.

    If no Houdini instance is listening, attempts to launch a headless hython
    session automatically (unless HOUDINIMCP_NO_HEADLESS=1 is set).
    """
    global _houdini_connection
    if _houdini_connection is None:
        logger.info("Creating new HoudiniConnection.")
        _houdini_connection = HoudiniConnection(host="localhost", port=HOUDINI_PORT)

    if not _houdini_connection.connect():
        # No Houdini listening — try launching headless
        if not HEADLESS_DISABLED:
            logger.info("No Houdini detected. Attempting headless launch...")
            if _launch_headless_houdini():
                # Retry connection
                _houdini_connection = HoudiniConnection(host="localhost", port=HOUDINI_PORT)
                if _houdini_connection.connect():
                    return _houdini_connection

        _houdini_connection = None
        raise ConnectionError(
            f"Could not connect to Houdini on localhost:{HOUDINI_PORT}. "
            "Is the plugin running? (Set HOUDINIMCP_NO_HEADLESS=1 to disable auto-launch.)"
        )

    return _houdini_connection


# Now define the MCP server that Claude will talk to over stdio
mcp = FastMCP("HoudiniMCP", instructions="""\
IMPORTANT — Houdini MCP Connection Rules:

1. **Never rapid-fire commands.** Wait at least 1 second between consecutive tool calls.
   The Houdini plugin uses a single-threaded listener and needs time to reset between connections.

2. **Separate scene commands from render commands.** Do all scene setup (create nodes,
   modify parameters, set materials, connect nodes, etc.) FIRST. Then call render tools
   in a separate step.

3. **Render commands are slow.** Rendering takes significantly longer than node operations.
   Do not assume a render has failed just because it takes time.

4. **If you get a connection error, STOP.** Do not retry in a loop — you likely crashed
   the plugin. Tell the user to restart the Houdini MCP plugin and verify the port is
   listening before trying again.

5. **Verify connectivity first.** Use the `ping` tool before starting work to confirm
   the Houdini plugin is reachable. If ping fails, tell the user immediately.

6. **Render workflow:** Render tools save images to disk (in /tmp/ by default) and return
   the file path. Use the Read tool to view the rendered image directly, or tell the user
   the file path.

7. **Use batch for bulk operations.** When creating multiple nodes or making many
   changes at once, prefer the `batch` tool over individual calls. This executes
   atomically in a single undo group and avoids rapid-fire connection issues.

8. **Monitor long renders.** After launching a Karma or Mantra render, use
   `monitor_render` to poll for `husk` / `mantra-bin` processes and check if
   the output file exists. No Houdini connection needed.

9. **Document non-trivial discoveries.** If you encounter a silent failure,
   undocumented API quirk, or required workaround while using this MCP, read
   `BEST_PRACTICES.md` in the houdini-mcp repo root first to check it isn't
   already covered, then add a brief entry under the appropriate context
   section (COPs, SOPs, LOPs, etc.) and update the index. Keep entries short:
   problem, symptom, fix. No essays.
""")

@asynccontextmanager
async def server_lifespan(app: FastMCP):
    """Startup/shutdown logic. Called automatically by fastmcp."""
    logger.info("Houdini MCP server starting up (stdio).")
    yield {}
    logger.info("Houdini MCP server shutting down.")
    global _houdini_connection
    if _houdini_connection is not None:
        _houdini_connection.disconnect()
        _houdini_connection = None
    _cleanup_hython()
    logger.info("Connection to Houdini closed.")

mcp.lifespan = server_lifespan


def _send_tool_command(cmd_type: str, params: Dict[str, Any] = None) -> str:
    """Send a command to Houdini and return the JSON result string."""
    conn = get_houdini_connection()
    response = conn.send_command(cmd_type, params)
    if response.get("status") == "error":
        origin = response.get("origin", "houdini")
        return f"Error ({origin}): {response.get('message', 'Unknown error')}"
    return json.dumps(response.get("result", {}), indent=2)


@mcp.tool()
def ping(ctx: Context) -> str:
    """
    Health check to verify Houdini is connected and responsive.
    Returns server status info or an error if Houdini is unreachable.
    """
    try:
        conn = get_houdini_connection()
        response = conn.send_command("ping")
        if response.get("status") == "error":
            return f"Houdini unreachable: {response.get('message', 'Unknown error')}"
        return json.dumps(response.get("result", {}), indent=2)
    except ConnectionError as e:
        return f"Houdini unreachable: {str(e)}"
    except Exception as e:
        return f"Ping failed: {str(e)}"

@mcp.tool()
def get_scene_info(ctx: Context) -> str:
    """
    Ask Houdini for scene info. Returns JSON as a string.
    """
    return _send_tool_command("get_scene_info")

@mcp.tool()
def create_node(ctx: Context, node_type: str, parent_path: str = "/obj", name: str = None) -> str:
    """
    Create a single node in Houdini at the given parent path.
    Use for one-off nodes or top-level geo containers. For multi-node SOP pipelines wired in sequence, prefer build_sop_chain (one call vs many).
    Args: node_type (Houdini type name, e.g. "geo", "blast", "vellumconstraints", "file"), parent_path (default "/obj"; SOPs need a geo parent like "/obj/my_geo", not "/obj" itself), name (optional, auto-generated if omitted).
    Pitfall: parent_path must accept node_type. A SOP like "blast" placed under "/obj" fails; create a geo container first, then put SOPs inside it.
    Example: create_node("geo", parent_path="/obj", name="garment_test") then create_node("file", parent_path="/obj/garment_test", name="import_obj").
    """
    params = {"node_type": node_type, "parent_path": parent_path}
    if name:
        params["name"] = name
    return _send_tool_command("create_node", params)

@mcp.tool()
def execute_houdini_code(ctx: Context, code: str, allow_dangerous: bool = False) -> str:
    """
    Execute arbitrary Python in the running Houdini. Returns status, stdout, stderr.
    Use as a LAST RESORT when no specialized tool fits: enumerating node types, custom DOP introspection, or quick experiments. For routine work, prefer specialized tools.
    Args: code (Python source for the hou.* environment), allow_dangerous (default False; True to bypass pattern blocks for file removal, Houdini exit, shell spawning).
    Pitfall: this bypasses guardrails. Use set_parameters, create_node/build_sop_chain, connect_nodes_batch, get_parameter_schema for routine work; reach here only as last resort.
    Example: execute_houdini_code("import hou; print([t for t in hou.sopNodeTypeCategory().nodeTypes() if 'vellum' in t.lower()])") to list Vellum SOP types.
    """
    conn = get_houdini_connection()
    params = {"code": code}
    if allow_dangerous:
        params["allow_dangerous"] = True
    response = conn.send_command("execute_code", params)

    if response.get("status") == "error":
        origin = response.get('origin', 'houdini')
        return f"Error ({origin}): {response.get('message', 'Unknown error')}"

    result = response.get("result", {})
    if result.get("executed"):
        stdout = result.get("stdout", "").strip()
        stderr = result.get("stderr", "").strip()
        output_message = "Code executed successfully."
        if stdout:
            output_message += f"\\n--- Stdout ---\\n{stdout}"
        if stderr:
            output_message += f"\\n--- Stderr ---\\n{stderr}"
        return output_message

    return f"Execution status unclear from Houdini response: {json.dumps(response)}"

@mcp.tool()
def render_view(ctx: Context,
                mode: str = "single",
                camera_path: str = None,
                orthographic: bool = False,
                rotation: List[float] = [0, 90, 0],
                render_path: str = None,
                render_engine: str = "opengl",
                karma_engine: str = "cpu") -> str:
    """
    Render the scene and return the image path(s).

    mode:
      - "single" (default): one view; uses rotation/orthographic.
      - "quad": 4 canonical views (top/front/side/persp); returns multiple paths.
      - "camera": render from camera_path (required when mode="camera").
    render_engine: "opengl" (fast preview) or "karma"/"mantra" (karma_engine: "cpu"|"xpu").
    """
    rp = render_path or tempfile.gettempdir()
    try:
        conn = get_houdini_connection()
        if mode == "quad":
            response = conn.send_command("render_quad_view", {
                "render_path": rp,
                "render_engine": render_engine,
                "karma_engine": karma_engine,
            })
        elif mode == "camera":
            if not camera_path:
                return "Error: mode='camera' requires camera_path."
            response = conn.send_command("render_specific_camera", {
                "camera_path": camera_path,
                "render_path": rp,
                "render_engine": render_engine,
                "karma_engine": karma_engine,
            })
        else:  # single
            response = conn.send_command("render_single_view", {
                "orthographic": orthographic,
                "rotation": rotation,
                "render_path": rp,
                "render_engine": render_engine,
                "karma_engine": karma_engine,
            })

        if response.get("status") == "error":
            origin = response.get("origin", "houdini")
            return f"Error ({origin}): {response.get('message', 'Unknown error')}"

        result = response.get("result", {})
        if mode == "quad" and isinstance(result, dict) and isinstance(result.get("results"), list):
            lines = ["Rendered views:"]
            for view in result["results"]:
                name = view.get("view_name", "unknown")
                fp = view.get("filepath", "?")
                res = view.get("resolution", [0, 0])
                lines.append(f"  {name}: {fp} ({res[0]}x{res[1]})")
            return "\n".join(lines)
        if isinstance(result, dict) and result.get("filepath"):
            res = result.get("resolution", [0, 0])
            return f"Rendered to {result['filepath']} ({res[0]}x{res[1]}, {render_engine})"
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"render_view failed: {e}", exc_info=True)
        return f"Render failed: {str(e)}"


@mcp.tool()
def modify_node(ctx: Context, path: str, parameters: Dict[str, Any] = None,
                position: List[float] = None, name: str = None) -> str:
    """Modify an existing node — rename, reposition, or change parameters."""
    params = {"path": path}
    if parameters is not None:
        params["parameters"] = parameters
    if position is not None:
        params["position"] = position
    if name is not None:
        params["name"] = name
    return _send_tool_command("modify_node", params)

@mcp.tool()
def delete_node(ctx: Context, path: str) -> str:
    """Delete a node from the Houdini scene by path."""
    return _send_tool_command("delete_node", {"path": path})

@mcp.tool()
def get_node_info(ctx: Context, path: str) -> str:
    """Get detailed info about a node: type, parameters, inputs, outputs."""
    return _send_tool_command("get_node_info", {"path": path})

@mcp.tool()
def set_material(ctx: Context, node_path: str, material_type: str = "principledshader",
                 name: str = None, parameters: Dict[str, Any] = None) -> str:
    """Create or apply a material to an OBJ node."""
    params = {"node_path": node_path, "material_type": material_type}
    if name is not None:
        params["name"] = name
    if parameters is not None:
        params["parameters"] = parameters
    return _send_tool_command("set_material", params)

@mcp.tool()
def set_node_flags(ctx: Context, node_path: str, display: bool = None,
                   render: bool = None, bypass: bool = None) -> str:
    """Set display, render, and/or bypass flags on a node."""
    params = {"node_path": node_path}
    if display is not None:
        params["display"] = display
    if render is not None:
        params["render"] = render
    if bypass is not None:
        params["bypass"] = bypass
    return _send_tool_command("set_node_flags", params)

@mcp.tool()
def save_scene(ctx: Context, file_path: str = None) -> str:
    """Save the current Houdini scene, optionally to a new file path."""
    params = {}
    if file_path is not None:
        params["file_path"] = file_path
    return _send_tool_command("save_scene", params)

@mcp.tool()
def load_scene(ctx: Context, file_path: str = "") -> str:
    """Load a .hip file into Houdini."""
    return _send_tool_command("load_scene", {"file_path": file_path})

@mcp.tool()
def set_expression(ctx: Context, node_path: str, parm_name: str,
                   expression: str, language: str = "hscript") -> str:
    """Set an expression on a node parameter. Language: 'hscript' or 'python'."""
    return _send_tool_command("set_expression", {
        "node_path": node_path,
        "parm_name": parm_name,
        "expression": expression,
        "language": language,
    })

@mcp.tool()
def set_frame(ctx: Context, frame: float = 1.0) -> str:
    """Set the current frame in Houdini's playbar."""
    return _send_tool_command("set_frame", {"frame": frame})

@mcp.tool()
def get_geo_summary(ctx: Context, node_path: str) -> str:
    """
    Return geometry statistics for a SOP node: point/prim/vertex counts, bounding box, attribute names. Cheap; does NOT pull mesh data into context.
    Use to verify a SOP cooked, check bbox before passing downstream, see what attributes exist, or detect packed primitives before they cause failures.
    Args: node_path (full path like "/obj/geo1/hide_rig_for_view").
    Pitfall: when prim_count is suspiciously small (2-10) for a dense mesh and prim_type is PackedGeometry, the node emits packed prims. Vellum collision and most per-prim operations need raw triangles; insert an unpack SOP first.
    Example: get_geo_summary("/obj/geo1/hide_rig_for_view") on an APEX rig output returns prims=2, prim_type=PackedGeometry, signaling unpack is needed before vellumsolver collision.
    """
    return _send_tool_command("get_geo_summary", {"node_path": node_path})

@mcp.tool()
def layout_children(ctx: Context, node_path: str = "/obj") -> str:
    """Auto-layout child nodes in the network editor."""
    return _send_tool_command("layout_children", {"node_path": node_path})

@mcp.tool()
def find_error_nodes(ctx: Context, root_path: str = "/obj") -> str:
    """
    Scan a node subtree for cook errors and warnings; returns paths and messages.
    Use as the FIRST diagnostic when a cook fails, a node is red, or an upstream change caused silent failures. Faster than inspecting each node.
    Args: root_path (default "/obj"; narrow to the affected subtree like "/obj/garment_test" to reduce noise).
    Pitfall: errors INSIDE a DOP subnet (e.g. inside vellumsolver) bubble up to the solver node, but the cause is reported with a path into the DOP graph that find_error_nodes does NOT traverse. Treat the DOP-internal path as a hint, not a clickable target.
    Example: find_error_nodes("/obj/garment_test") after a failed Vellum sim returns [{"path":"/obj/garment_test/vellum_solver","errors":["Invalid source ... load_a_field"]}].
    """
    return _send_tool_command("find_error_nodes", {"root_path": root_path})


# ── Context tools ──

@mcp.tool()
def get_network_overview(ctx: Context, path: str = "/obj") -> str:
    """Get an overview of all nodes in a network with their connections."""
    return _send_tool_command("get_network_overview", {"path": path})

@mcp.tool()
def get_cook_chain(ctx: Context, path: str) -> str:
    """Get the cook dependency chain for a node (inputs all the way up)."""
    return _send_tool_command("get_cook_chain", {"path": path})

@mcp.tool()
def get_selection(ctx: Context) -> str:
    """Get the currently selected nodes in Houdini."""
    return _send_tool_command("get_selection")

@mcp.tool()
def set_selection(ctx: Context, paths: List[str]) -> str:
    """Set the node selection to the given list of node paths."""
    return _send_tool_command("set_selection", {"paths": paths})

# ── Parameter tools ──

@mcp.tool()
def get_parameter(ctx: Context, node_path: str, parm_name: str) -> str:
    """Get a single parameter's value, type, expression, and metadata."""
    return _send_tool_command("get_parameter", {"node_path": node_path, "parm_name": parm_name})

@mcp.tool()
def set_parameters(ctx: Context, node_path: str, parameters: Dict[str, Any]) -> str:
    """
    Set parameter values on a node. For a single parm, pass a 1-element dict: {parm_name: value}.
    Use after create_node or build_sop_chain to configure a node's behavior, or to tweak settings on an existing node.
    Args: node_path (full path like "/obj/garment_test/vellum_cloth"), parameters (a dict of {parm_internal_name: value}).
    Pitfall: parm keys are INTERNAL names from Houdini's parameter schema, NOT the GUI label strings. The GUI shows "Mass" but the internal name is "mass"; "Constraint Type" is "constrainttype"; "Material" on a material SOP is "shop_materialpath1". When unsure, call get_parameter_schema(node_path) first. Boolean toggles are integer 0/1, not Python True/False.
    Single-parm pure failure raises (PermissionError / ValueError) so typos surface immediately. Multi-parm dicts return changes/failed/not_attempted for partial-success handling.
    Example: set_parameters("/obj/garment_test/vellum_cloth", {"constrainttype": 3, "domass": 1, "mass": 0.15, "dothickness": 1, "thickness": 0.0005}).
    """
    return _send_tool_command("set_parameters", {"node_path": node_path, "parameters": parameters})

@mcp.tool()
def get_parameter_schema(ctx: Context, node_path: str) -> str:
    """
    Return the full parameter schema for a node: internal names, types, defaults, menu choices.
    Use before set_parameters when parm names or menu values are unknown, or to discover what's configurable on an unfamiliar node type. More reliable than guessing names from GUI labels.
    Args: node_path (full path like "/obj/garment_test/vellum_cloth").
    Pitfall: many menu parms (e.g. "constrainttype" on vellumconstraints) take INTEGER values where the GUI shows labels; the schema lists both labels and the integer to pass. Output can be large for parm-heavy nodes; scan for the parm you need.
    Example: get_parameter_schema("/obj/garment_test/vellum_cloth") returns templates including the constrainttype menu where label "Cloth" maps to integer 3.
    """
    return _send_tool_command("get_parameter_schema", {"node_path": node_path})

# ── Animation tools ──

@mcp.tool()
def set_keyframes(ctx: Context, node_path: str, parm_name: str,
                  keyframes: List[Dict[str, float]]) -> str:
    """Set keyframes on a parameter. Each: {frame, value}.

    For a single keyframe, pass a 1-element list.
    """
    return _send_tool_command("set_keyframes", {
        "node_path": node_path, "parm_name": parm_name, "keyframes": keyframes,
    })

@mcp.tool()
def get_keyframes(ctx: Context, node_path: str, parm_name: str) -> str:
    """Get all keyframes on a parameter."""
    return _send_tool_command("get_keyframes", {"node_path": node_path, "parm_name": parm_name})

@mcp.tool()
def get_frame(ctx: Context) -> str:
    """Get the current frame and time."""
    return _send_tool_command("get_frame")

@mcp.tool()
def set_frame_range(ctx: Context, start: float, end: float) -> str:
    """Set the global animation frame range."""
    return _send_tool_command("set_frame_range", {"start": start, "end": end})

@mcp.tool()
def set_playback_range(ctx: Context, start: float, end: float) -> str:
    """Set the playback range (subset of the global range)."""
    return _send_tool_command("set_playback_range", {"start": start, "end": end})

@mcp.tool()
def playbar_control(ctx: Context, action: str) -> str:
    """Control playbar: play, stop, reverse, step_forward, step_backward."""
    return _send_tool_command("playbar_control", {"action": action})

# ── VEX tools ──

@mcp.tool()
def create_wrangle(ctx: Context, parent_path: str,
                   wrangle_type: str = "attribwrangle",
                   name: str = None, code: str = "") -> str:
    """Create a VEX wrangle node with optional initial code."""
    params = {"parent_path": parent_path, "wrangle_type": wrangle_type, "code": code}
    if name is not None:
        params["name"] = name
    return _send_tool_command("create_wrangle", params)

@mcp.tool()
def validate_vex(ctx: Context, code: str) -> str:
    """Validate VEX code syntax."""
    return _send_tool_command("validate_vex", {"code": code})

# ── Material tools ──

@mcp.tool()
def list_materials(ctx: Context, mat_path: str = "/mat") -> str:
    """List all materials in a material network."""
    return _send_tool_command("list_materials", {"mat_path": mat_path})

@mcp.tool()
def get_material_info(ctx: Context, path: str) -> str:
    """Get detailed info about a material node."""
    return _send_tool_command("get_material_info", {"path": path})

@mcp.tool()
def create_material_network(ctx: Context, parent_path: str = "/obj",
                            name: str = "matnet") -> str:
    """Create a material network (matnet) node."""
    return _send_tool_command("create_material_network", {
        "parent_path": parent_path, "name": name,
    })

@mcp.tool()
def assign_material(ctx: Context, node_path: str, material_path: str) -> str:
    """Assign a material to a node by setting shop_materialpath."""
    return _send_tool_command("assign_material", {
        "node_path": node_path, "material_path": material_path,
    })

# ── Nodes expanded tools ──

@mcp.tool()
def copy_node(ctx: Context, path: str, destination_path: str) -> str:
    """Copy a node to a new parent network."""
    return _send_tool_command("copy_node", {"path": path, "destination_path": destination_path})

@mcp.tool()
def move_node(ctx: Context, path: str, destination_path: str) -> str:
    """Move a node to a new parent network."""
    return _send_tool_command("move_node", {"path": path, "destination_path": destination_path})

@mcp.tool()
def rename_node(ctx: Context, path: str, new_name: str) -> str:
    """Rename a node."""
    return _send_tool_command("rename_node", {"path": path, "new_name": new_name})

@mcp.tool()
def list_children(ctx: Context, path: str, recursive: bool = False) -> str:
    """List all children of a node, optionally recursive."""
    return _send_tool_command("list_children", {"path": path, "recursive": recursive})

@mcp.tool()
def find_nodes(ctx: Context, pattern: str, node_type: str = None,
               root_path: str = "/") -> str:
    """Find nodes matching a name pattern, optionally filtered by type."""
    params = {"pattern": pattern, "root_path": root_path}
    if node_type is not None:
        params["node_type"] = node_type
    return _send_tool_command("find_nodes", params)

@mcp.tool()
def connect_nodes_batch(ctx: Context, connections: List[Dict[str, Any]]) -> str:
    """
    Connect source-to-destination wires. For a single wire, pass a 1-element list.
    Use when wiring multi-input nodes (vellumsolver, switches, merges). For a linear SOP chain, prefer build_sop_chain.
    Args: connections (list; each: {"src_path", "dst_path", "dst_input_index", optional "src_output_index" default 0}).
    Pitfall: vellumsolver has 3 inputs with non-obvious semantics: input 0 = Vellum Geometry (cloth), input 1 = Constraint Geometry (the SAME node as input 0 in standard cloth, NOT collision), input 2 = Collision Geometry. Wiring the body to input 1 silently fails with "Invalid source ... load_a_field" errors.
    Example: vellum_cloth -> vellum_solver inputs 0 and 1; unpack_body -> input 2. Three entries; the first two share src_path and differ in dst_input_index.
    """
    return _send_tool_command("connect_nodes_batch", {"connections": connections})

# ── Geometry expanded tools ──

@mcp.tool()
def get_points(ctx: Context, node_path: str, start: int = 0,
               count: int = 100, attribs: List[str] = None) -> str:
    """Get point data with pagination. Returns positions and optional attrib values."""
    params = {"node_path": node_path, "start": start, "count": count}
    if attribs is not None:
        params["attribs"] = attribs
    return _send_tool_command("get_points", params)

@mcp.tool()
def get_prims(ctx: Context, node_path: str, start: int = 0,
              count: int = 100, attribs: List[str] = None) -> str:
    """Get primitive data with pagination."""
    params = {"node_path": node_path, "start": start, "count": count}
    if attribs is not None:
        params["attribs"] = attribs
    return _send_tool_command("get_prims", params)

@mcp.tool()
def get_attrib_values(ctx: Context, node_path: str, attrib_name: str,
                      attrib_class: str = "point") -> str:
    """Get all values of a geometry attribute. attrib_class: point, prim, detail."""
    return _send_tool_command("get_attrib_values", {
        "node_path": node_path, "attrib_name": attrib_name, "attrib_class": attrib_class,
    })

@mcp.tool()
def set_detail_attrib(ctx: Context, node_path: str, attrib_name: str, value: Any) -> str:
    """Set a detail (global) attribute value on geometry."""
    return _send_tool_command("set_detail_attrib", {
        "node_path": node_path, "attrib_name": attrib_name, "value": value,
    })

@mcp.tool()
def get_bounding_box(ctx: Context, node_path: str) -> str:
    """Get the bounding box of a node's geometry (min, max, size, center)."""
    return _send_tool_command("get_bounding_box", {"node_path": node_path})

@mcp.tool()
def batch(ctx: Context, operations: List[Dict[str, Any]] = []) -> str:
    """Execute multiple operations atomically in a single undo group.
    Each operation: {"type": "create_node", "params": {...}}."""
    return _send_tool_command("batch", {"operations": operations})

@mcp.tool()
def geo_export(ctx: Context, node_path: str, format: str = "obj",
               output: str = None) -> str:
    """Export geometry to a file. Formats: obj, gltf, glb, usd, usda, ply, bgeo.sc."""
    params = {"node_path": node_path, "format": format}
    if output is not None:
        params["output"] = output
    return _send_tool_command("geo_export", params)

@mcp.tool()
def render_flipbook(ctx: Context, frame_range: List[float] = None,
                    output: str = None, resolution: List[int] = None) -> str:
    """Render a flipbook sequence from the viewport."""
    params = {}
    if frame_range is not None:
        params["frame_range"] = frame_range
    if output is not None:
        params["output"] = output
    if resolution is not None:
        params["resolution"] = resolution
    return _send_tool_command("render_flipbook", params)

@mcp.tool()
def screenshot_viewport(ctx: Context, width: int = 800, height: int = 600,
                        viewport_name: str = None, pane_tab_name: str = None,
                        frame: int = None):
    """
    Capture the current SceneViewer viewport as a PNG and return it inline with JSON metadata.
    Use when visual confirmation is needed and numerical inspection is not enough: after a node chain build, after a Vellum sim, or after applying materials.
    Args: width (default 800, range 128-4096), height (default 600, same range, width*height <= 8000000), viewport_name (None = current, e.g. "front2"), pane_tab_name (None = first pane, e.g. "panetab1"), frame (None = current playbar frame).
    Pitfalls: OpenGL flipbook (fast preview), not Karma/Mantra (shading looks rough); in Single layout viewport_name must match the visible viewport; frame= does NOT move the playbar.
    Example: screenshot_viewport(width=1280, height=720, frame=10) returns the scene at frame 10 without changing the playbar.
    """
    params = {"width": width, "height": height}
    if viewport_name is not None:
        params["viewport_name"] = viewport_name
    if pane_tab_name is not None:
        params["pane_tab_name"] = pane_tab_name
    if frame is not None:
        params["frame"] = frame

    try:
        conn = get_houdini_connection()
        response = conn.send_command("screenshot_viewport", params)
    except ConnectionError as e:
        return f"Houdini unreachable: {e}"
    except Exception as e:
        logger.error(f"screenshot_viewport failed: {e}", exc_info=True)
        return f"screenshot_viewport failed: {e}"

    if response.get("status") == "error":
        origin = response.get("origin", "houdini")
        return f"Error ({origin}): {response.get('message', 'Unknown error')}"

    result = response.get("result", {})
    if not isinstance(result, dict):
        return f"Unexpected response: {json.dumps(response)[:500]}"
    if result.get("status") == "error":
        return f"Error ({result.get('origin', 'houdini')}): {result.get('message')}"
    if "image_base64" not in result:
        return f"Missing image data in response: {json.dumps(result)[:500]}"

    try:
        png_bytes = _base64.b64decode(result["image_base64"])
    except Exception as e:
        return f"Failed to decode image: {e}"

    metadata = {k: v for k, v in result.items()
                if k not in ("image_base64", "mime_type", "status")}
    return [Image(data=png_bytes, format="png"), json.dumps(metadata, indent=2)]


# ── DOP tools ──

@mcp.tool()
def get_simulation_info(ctx: Context, path: str) -> str:
    """Get simulation info from a DOP network."""
    return _send_tool_command("get_simulation_info", {"path": path})

@mcp.tool()
def list_dop_objects(ctx: Context, path: str) -> str:
    """List all DOP objects in a simulation."""
    return _send_tool_command("list_dop_objects", {"path": path})

@mcp.tool()
def step_simulation(ctx: Context, path: str, num_steps: int = 1) -> str:
    """Step a simulation forward by a number of frames."""
    return _send_tool_command("step_simulation", {"path": path, "num_steps": num_steps})

@mcp.tool()
def reset_simulation(ctx: Context, path: str) -> str:
    """Reset a simulation to its initial state."""
    return _send_tool_command("reset_simulation", {"path": path})

# ── Viewport tools ──

@mcp.tool()
def list_panes(ctx: Context) -> str:
    """List all pane tabs in the Houdini desktop."""
    return _send_tool_command("list_panes")

@mcp.tool()
def get_viewport_info(ctx: Context) -> str:
    """Get current viewport settings (camera, shading, etc.)."""
    return _send_tool_command("get_viewport_info")

@mcp.tool()
def set_viewport_camera(ctx: Context, camera_path: str) -> str:
    """Set the viewport camera. Accepts three path forms:

    - Object camera node path (e.g. ``/obj/cam1``).
    - LOP camera node path (e.g. ``/stage/camera1``) — the handler reads the
      node's ``primpath`` parm and auto-switches the SceneViewer into LOP
      context if needed. The return value's ``viewer_context_switched`` flag
      indicates whether a switch occurred.
    - Raw USD camera prim path (e.g. ``/cameras/cam1``) — only works when the
      SceneViewer is already in LOP context (otherwise Houdini silently
      no-ops); prefer passing the LOP node path so the auto-switch runs.

    For wrapped-HDA LOP cameras whose ``primpath`` parm is not promoted, pass
    the USD prim path string directly.
    """
    return _send_tool_command("set_viewport_camera", {"camera_path": camera_path})

@mcp.tool()
def set_viewport_display(ctx: Context, shading_mode: str = None,
                         guide: bool = None) -> str:
    """Set viewport display options (shading mode, guides)."""
    params = {}
    if shading_mode is not None:
        params["shading_mode"] = shading_mode
    if guide is not None:
        params["guide"] = guide
    return _send_tool_command("set_viewport_display", params)

@mcp.tool()
def set_viewport_renderer(ctx: Context, renderer: str) -> str:
    """Set the viewport renderer."""
    return _send_tool_command("set_viewport_renderer", {"renderer": renderer})

@mcp.tool()
def frame_view(ctx: Context, target: str = "all") -> str:
    """Frame the viewport. target: "all" (all geometry) or "selection" (current selection)."""
    cmd = "frame_selection" if target == "selection" else "frame_all"
    return _send_tool_command(cmd)

@mcp.tool()
def set_viewport_direction(ctx: Context, direction: str) -> str:
    """Set viewport direction: front, back, left, right, top, bottom, persp."""
    return _send_tool_command("set_viewport_direction", {"direction": direction})

@mcp.tool()
def set_current_network(ctx: Context, path: str) -> str:
    """Set the current network path in the network editor."""
    return _send_tool_command("set_current_network", {"path": path})

# ── Rendering expanded tools ──

@mcp.tool()
def list_render_nodes(ctx: Context) -> str:
    """List all ROP (render) nodes in the scene."""
    return _send_tool_command("list_render_nodes")

@mcp.tool()
def get_render_settings(ctx: Context, path: str) -> str:
    """Get render settings from a ROP node."""
    return _send_tool_command("get_render_settings", {"path": path})

@mcp.tool()
def set_render_settings(ctx: Context, path: str, settings: Dict[str, Any]) -> str:
    """Set render settings on a ROP node."""
    return _send_tool_command("set_render_settings", {"path": path, "settings": settings})

@mcp.tool()
def create_render_node(ctx: Context, render_type: str = "opengl",
                       name: str = None, parent_path: str = "/out") -> str:
    """Create a ROP (render) node."""
    params = {"render_type": render_type, "parent_path": parent_path}
    if name is not None:
        params["name"] = name
    return _send_tool_command("create_render_node", params)

@mcp.tool()
def start_render(ctx: Context, path: str, frame_range: List[float] = None) -> str:
    """Start a render from a ROP node."""
    params = {"path": path}
    if frame_range is not None:
        params["frame_range"] = frame_range
    return _send_tool_command("start_render", params)

@mcp.tool()
def get_render_progress(ctx: Context, path: str) -> str:
    """Get render progress from a ROP node."""
    return _send_tool_command("get_render_progress", {"path": path})

@mcp.tool()
def get_rop_output_path(ctx: Context, path: str,
                        picture_param: str = None,
                        frame: int = None,
                        expand: bool = True,
                        min_mtime: float = None) -> str:
    """Resolve a ROP node's primary output filepath with sequence + freshness metadata.

    Resolution tiers:
      1. picture_param= overrides everything (use for HDA / unknown engines).
      2. Known parm-name map per ROP type (karma→picture, ifd→vm_picture, etc.).
      3. FileReference write-tagged parm scan (sidecars filtered).

    Returns dict with: path_raw, path_resolved, frame_used, is_sequence,
    frame_range, frame_range_active, first_frame_path, last_frame_path,
    representative_path, category (image|mplay|usd|geometry|usd_render_via_settings|unknown),
    exists, mtime, size_bytes, warnings, param_used, param_source, tag_scan_candidates, hint.

    Pass min_mtime=time.time() before start_render() to poll for freshly-written
    output without false positives from stale prior renders. Set expand=False to
    keep $F/$HIP unresolved in path_raw (path_resolved becomes None).
    """
    params = {"path": path, "expand": expand}
    if picture_param is not None:
        params["picture_param"] = picture_param
    if frame is not None:
        params["frame"] = frame
    if min_mtime is not None:
        params["min_mtime"] = min_mtime
    return _send_tool_command("get_rop_output_path", params)

# ── Cache tools ──

@mcp.tool()
def list_caches(ctx: Context, root_path: str = "/obj") -> str:
    """List all nodes with cache data."""
    return _send_tool_command("list_caches", {"root_path": root_path})

@mcp.tool()
def get_cache_status(ctx: Context, path: str) -> str:
    """Get cache status for a file cache node."""
    return _send_tool_command("get_cache_status", {"path": path})

@mcp.tool()
def clear_cache(ctx: Context, path: str) -> str:
    """Clear cache on a file cache node."""
    return _send_tool_command("clear_cache", {"path": path})

@mcp.tool()
def write_cache(ctx: Context, path: str, frame_range: List[float] = None) -> str:
    """Write cache for a file cache node."""
    params = {"path": path}
    if frame_range is not None:
        params["frame_range"] = frame_range
    return _send_tool_command("write_cache", params)

@mcp.tool()
def list_lights(ctx: Context, path: str) -> str:
    """List all light prims in a USD stage."""
    return _send_tool_command("list_lights", {"path": path})

# ── Workflow template tools ──

@mcp.tool()
def setup_pyro_sim(ctx: Context, source_path: str, name: str = "pyro_sim",
                   parent_path: str = "/obj") -> str:
    """Set up a Pyro simulation from a source geometry."""
    return _send_tool_command("setup_pyro_sim", {
        "source_path": source_path, "name": name, "parent_path": parent_path,
    })

@mcp.tool()
def setup_rbd_sim(ctx: Context, source_path: str, name: str = "rbd_sim",
                  parent_path: str = "/obj") -> str:
    """Set up an RBD simulation from a source geometry."""
    return _send_tool_command("setup_rbd_sim", {
        "source_path": source_path, "name": name, "parent_path": parent_path,
    })

@mcp.tool()
def setup_flip_sim(ctx: Context, source_path: str, name: str = "flip_sim",
                   parent_path: str = "/obj") -> str:
    """Set up a FLIP fluid simulation from a source geometry."""
    return _send_tool_command("setup_flip_sim", {
        "source_path": source_path, "name": name, "parent_path": parent_path,
    })

@mcp.tool()
def setup_vellum_sim(ctx: Context, source_path: str, sim_type: str = "cloth",
                     name: str = "vellum_sim", parent_path: str = "/obj") -> str:
    """Set up a Vellum simulation (cloth, hair, grain)."""
    return _send_tool_command("setup_vellum_sim", {
        "source_path": source_path, "sim_type": sim_type, "name": name, "parent_path": parent_path,
    })

@mcp.tool()
def build_sop_chain(ctx: Context, parent_path: str,
                    nodes: List[Dict[str, Any]]) -> str:
    """
    Create a chain of SOP nodes wired in sequence under a parent geo node.
    Use for multi-stage geometry pipelines like file -> blast -> xform -> null, instead of calling create_node + connect_nodes_batch.
    Args: parent_path (parent geo, e.g. "/obj/garment_test"), nodes (ordered list of {"type": "<sop_type>", "name": "<optional>", "parameters": {...}}).
    Pitfall: parameters values are static, not expressions. For "$F" or ch(...) expressions, build the chain first, then set the expression via set_parameters.
    Example: build_sop_chain("/obj/garment", [{"type":"file","parameters":{"file":"C:/path/dress.obj"}}, {"type":"blast","parameters":{"group":"@shop_materialpath=*Satin*","negate":1,"grouptype":4}}, {"type":"xform","parameters":{"scale":0.001}}, {"type":"null","name":"OUT_DRESS"}]).
    """
    return _send_tool_command("build_sop_chain", {"parent_path": parent_path, "nodes": nodes})

@mcp.tool()
def setup_render(ctx: Context, camera_path: str = None,
                 render_engine: str = "karma", output_path: str = None) -> str:
    """Set up a render node in /out with camera and output path."""
    params = {"render_engine": render_engine}
    if camera_path is not None:
        params["camera_path"] = camera_path
    if output_path is not None:
        params["output_path"] = output_path
    return _send_tool_command("setup_render", params)

@mcp.tool()
def search_docs(ctx: Context, query: str, top_k: int = 5) -> str:
    """Search Houdini documentation offline using BM25.
    Returns ranked results with path, title, preview, and relevance score.
    Does NOT require a Houdini connection."""
    from houdini_rag import search_docs as _search
    results = _search(query, top_k)
    if isinstance(results, dict) and "error" in results:
        return f"Error: {results['error']}"
    return json.dumps(results, indent=2)

@mcp.tool()
def get_doc(ctx: Context, path: str) -> str:
    """Get the full content of a Houdini documentation page by its relative path
    (as returned by search_docs). Does NOT require a Houdini connection."""
    from houdini_rag import get_doc_content
    result = get_doc_content(path)
    if "error" in result:
        return f"Error: {result['error']}"
    return json.dumps(result, indent=2)


_RENDER_PROCESS_NAMES = ("husk", "mantra-bin")


def _find_render_processes() -> List[Dict[str, str]]:
    """Detect running husk/mantra-bin processes via OS process listing.

    Returns a list of dicts with keys: name, pid, cpu_time, command.
    Works on Linux/macOS (ps aux) and Windows (tasklist /FO CSV /V).
    """
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/V"],
            capture_output=True, text=True, timeout=10,
        )
        processes = []
        for line in result.stdout.splitlines()[1:]:  # skip header
            lower = line.lower()
            for name in _RENDER_PROCESS_NAMES:
                if name in lower:
                    parts = line.strip('"').split('","')
                    processes.append({
                        "name": parts[0] if parts else name,
                        "pid": parts[1] if len(parts) > 1 else "?",
                        "cpu_time": parts[7] if len(parts) > 7 else "?",
                        "command": parts[0] if parts else name,
                    })
        return processes

    # Linux / macOS
    result = subprocess.run(
        ["ps", "aux"], capture_output=True, text=True, timeout=10,
    )
    processes = []
    for line in result.stdout.splitlines()[1:]:  # skip header
        lower = line.lower()
        for name in _RENDER_PROCESS_NAMES:
            if name in lower:
                cols = line.split(None, 10)
                processes.append({
                    "name": name,
                    "pid": cols[1] if len(cols) > 1 else "?",
                    "cpu_time": cols[9] if len(cols) > 9 else "?",
                    "command": cols[10] if len(cols) > 10 else line.strip(),
                })
    return processes


@mcp.tool()
def monitor_render(ctx: Context, output_path: str = None) -> str:
    """Check if a Karma (husk) or Mantra (mantra-bin) render is still running.
    Optionally pass output_path to also report file existence and size.
    No Houdini connection needed — runs on the bridge side."""
    processes = _find_render_processes()
    info: Dict[str, Any] = {
        "rendering": len(processes) > 0,
        "process_count": len(processes),
        "processes": processes,
    }
    if output_path is not None:
        if os.path.exists(output_path):
            info["output_file"] = {
                "exists": True,
                "size_bytes": os.path.getsize(output_path),
            }
        else:
            info["output_file"] = {"exists": False}
    return json.dumps(info, indent=2)


@mcp.tool()
def undo(ctx: Context) -> str:
    """Undo the most recent operation in Houdini's global undo stack.

    Returns a dict with `performed` (bool) and either `undone_label` (the
    label that was just undone) or `reason` (why nothing happened).

    Note: Houdini's undo stack is process-global. This may undo a manual user
    action, or another connected client's operation. Inspect `undone_label`
    (entries created by this MCP are prefixed `MCP: `) to confirm what was
    affected.
    """
    return _send_tool_command("undo")


@mcp.tool()
def redo(ctx: Context) -> str:
    """Redo the most recently undone operation. No-op when the redo stack is empty.

    Returns a dict with `performed` (bool) and either `redone_label` or `reason`.
    """
    return _send_tool_command("redo")


@mcp.tool()
def get_undo_history(ctx: Context, limit: int = 20) -> str:
    """Return recent undo and redo stack labels (newest first; index 0 is the next target).

    `limit` (1-200) caps both lists; `undo_total` and `redo_total` give the full
    sizes. `current_head_label` is the label that the next `undo()` call would
    consume (or null when the stack is empty).
    """
    return _send_tool_command("get_undo_history", {"limit": limit})


@mcp.tool()
def get_scene_dossier(
    ctx: Context,
    include_node_tree: bool = True,
    include_errors: bool = True,
    include_undo_history: bool = True,
    include_rops: bool = True,
    include_materials: bool = True,
    include_cameras: bool = True,
    include_selection: bool = True,
    max_node_depth: int = 3,
    max_undo_entries: int = 20,
    max_children_per_node: int = 100,
) -> str:
    """One-shot snapshot of the current Houdini scene: contexts, node tree,
    errors, undo history, ROPs, materials, cameras, selection. Read-only;
    does not appear in undo history. Use this as the first call when
    starting work on an unfamiliar scene to avoid many small inspection
    calls. Use include_* flags to omit heavy sections when not needed.

    ROP output paths are returned in a slim form (path_raw + sequence/range
    metadata, no filesystem I/O). For resolved paths or freshness checks,
    call get_rop_output_path on the specific ROP.
    """
    return _send_tool_command("get_scene_dossier", {
        "include_node_tree": include_node_tree,
        "include_errors": include_errors,
        "include_undo_history": include_undo_history,
        "include_rops": include_rops,
        "include_materials": include_materials,
        "include_cameras": include_cameras,
        "include_selection": include_selection,
        "max_node_depth": max_node_depth,
        "max_undo_entries": max_undo_entries,
        "max_children_per_node": max_children_per_node,
    })


def main():
    """Run the MCP server on stdio."""
    mcp.run()

if __name__ == "__main__":
    main()
