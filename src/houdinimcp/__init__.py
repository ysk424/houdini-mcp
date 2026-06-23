import os
import hou
from .server import HoudiniMCPServer

def start_server():
    existing = getattr(hou.session, "houdinimcp_server", None)
    if (
        existing is not None
        and getattr(existing, "running", False)
        and getattr(existing, "socket", None) is not None
    ):
        print("Houdini MCP Server is already running.")
        return existing

    if existing is not None:
        try:
            existing.stop()
        except Exception:
            pass

    server = HoudiniMCPServer()
    hou.session.houdinimcp_server = server
    server.start()
    if not server.running or server.socket is None:
        hou.session.houdinimcp_server = None
        return None
    return server

def stop_server():
    server = getattr(hou.session, "houdinimcp_server", None)
    if server is not None:
        server.stop()
        hou.session.houdinimcp_server = None
    else:
        print("Houdini MCP Server is not running.")

# Optionally auto-start
def initialize_plugin():
    # Set up default session toggles if desired
    if not hasattr(hou.session, "houdinimcp_use_assetlib"):
        hou.session.houdinimcp_use_assetlib = False
    # Auto-start server if you want:
    start_server()

# Auto-load on import (skipped for headless — managed by headless_server.py)
if not os.environ.get("HOUDINIMCP_HEADLESS"):
    initialize_plugin()
