<p align="center">
  <img src="logos/banner_light.svg" alt="HoudiniMCP — Talk to Houdini." width="700"/>
</p>

<p align="center">
  <a href="https://github.com/ysk424/houdini-mcp/blob/main/LICENSE"><img src="https://img.shields.io/github/license/ysk424/houdini-mcp?color=blue" alt="License: MIT"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-compatible-green?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJ3aGl0ZSI+PHBhdGggZD0iTTEyIDJDNi40OCAyIDIgNi40OCAyIDEyczQuNDggMTAgMTAgMTAgMTAtNC40OCAxMC0xMFMxNy41MiAyIDEyIDJ6Ii8+PC9zdmc+" alt="MCP Compatible"/></a>
  <a href="https://www.sidefx.com/"><img src="https://img.shields.io/badge/Houdini-22.0-orange?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJ3aGl0ZSI+PGNpcmNsZSBjeD0iMTIiIGN5PSIxMiIgcj0iMTAiLz48L3N2Zz4=&logoColor=white" alt="Houdini 22.0"/></a>
  <a href="https://github.com/ysk424/houdini-mcp/commits/main"><img src="https://img.shields.io/github/last-commit/ysk424/houdini-mcp" alt="Last Commit"/></a>
  <a href="https://github.com/ysk424/houdini-mcp/issues"><img src="https://img.shields.io/github/issues/ysk424/houdini-mcp" alt="Issues"/></a>
  <a href="https://github.com/ysk424/houdini-mcp/network/members"><img src="https://img.shields.io/github/forks/ysk424/houdini-mcp?style=social" alt="Forks"/></a>
  <a href="https://github.com/ysk424/houdini-mcp/watchers"><img src="https://img.shields.io/github/watchers/ysk424/houdini-mcp?style=social" alt="Watchers"/></a>
  <a href="https://github.com/ysk424/houdini-mcp/stargazers"><img src="https://img.shields.io/github/stars/ysk424/houdini-mcp?style=social" alt="GitHub Stars"/></a>
</p>

<p align="center">
  <strong>88 MCP tools</strong> &middot; <strong>30,000+ searchable documents</strong> &middot; <strong>Simulation and capture focused</strong>
</p>

---

Control **SideFX Houdini** from **Claude** using the **Model Context Protocol**. HoudiniMCP connects to your running Houdini instance — your license, your scene, your tools. The bridge talks to Houdini's Python API over a local TCP socket, so everything runs on your machine against your own installation. If no Houdini GUI is running, the bridge auto-launches a headless `hython` session so you can work without opening the UI.

- **88 MCP tools** — focused on simulation, viewport capture, rendering, node operations, parameters, animation, geometry, cache, docs, and undo/redo
- **30,000+ searchable documents** — Houdini docs + patterns extracted from your Houdini install's example files

## Get Started

**Prerequisites:** git and Python 3.10+. Houdini is optional at setup time.

**Linux / macOS:**
```bash
curl -sSL https://raw.githubusercontent.com/ysk424/houdini-mcp/main/bootstrap.sh | bash
```

**Windows (PowerShell):**
```powershell
powershell -c "irm https://raw.githubusercontent.com/ysk424/houdini-mcp/main/bootstrap.bat -OutFile bootstrap.bat; .\bootstrap.bat"
```

The bootstrap script clones the repo, installs [uv](https://docs.astral.sh/uv/), creates a venv, installs deps, sets up the Houdini plugin, optionally downloads offline docs, and configures your MCP client. Re-run from inside the repo at any time — it's idempotent. Full install is ~1 GB (mostly the documentation corpus).

<details>
<summary><strong>Manual setup (step by step)</strong></summary>

#### 1. Install the Houdini Plugin

```bash
# Install for Houdini 22
python scripts/install.py

# Or point at a prefs directory explicitly
python scripts/install.py --prefs-dir ~/Documents/houdini22.0

# Preview without changing anything
python scripts/install.py --dry-run
```

This creates a packages JSON in your Houdini preferences directory that puts this repo's `src/` on Houdini's `PYTHONPATH`, and adds a UI-ready startup hook (`python3.13libs/uiready.py`) so the MCP server starts automatically after Houdini's GUI is ready.

The plugin runs from this checkout — the sources are not copied into the prefs directory, so edits here take effect on the next Houdini restart with no reinstall. Only `ClaudeTerminal.pypanel` and `houdinimcp.shelf` are copied, since Houdini only scans for those under the prefs directory.

#### 2. Install MCP Dependencies

```bash
# Using uv (recommended)
cd /path/to/houdini-mcp
uv sync

# Or using pip
pip install "mcp[cli]"
```

#### 3. Configure Your MCP Client

**Claude Code (CLI):**
```bash
claude mcp add --transport stdio houdini -- uv --directory /path/to/houdini-mcp run python houdini_mcp_server.py
```

**Claude Desktop:** Go to **File > Settings > Developer > Edit Config** and add:

```json
{
  "mcpServers": {
    "houdini": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/houdini-mcp",
        "run",
        "python",
        "houdini_mcp_server.py"
      ]
    }
  }
}
```

### Codex

Register the bridge in `~/.codex/config.toml` while installing the Houdini
plugin:

```bash
python scripts/install.py --codex
```

Restart Codex after installation so the `mcp__houdini__*` tools are loaded.
The installer uses the repository virtual environment's Python executable,
avoiding reliance on `uv` being present in Codex's startup `PATH`.

**ChatGPT Desktop:** ChatGPT only supports remote (HTTP) MCP servers, not local stdio. You'll need to wrap the bridge in an HTTP transport and expose it via a tunnel:

```bash
# 1. Run the MCP server with HTTP transport (requires mcp[cli])
uv --directory /path/to/houdini-mcp run fastmcp run houdini_mcp_server.py --transport http --port 8080

# 2. Expose it with ngrok (or Cloudflare Tunnel, etc.)
ngrok http 8080
```

Then in ChatGPT: **Settings > Connectors > Create** — paste the ngrok HTTPS URL as the Connector URL.

**Ollama (local LLM):** Ollama doesn't have a built-in MCP client. Use [ollama-mcp-bridge](https://github.com/jonigl/ollama-mcp-bridge) to connect:

```bash
pip install ollama-mcp-bridge
```

Create `mcp-config.json`:

```json
{
  "mcpServers": {
    "houdini": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/houdini-mcp",
        "run",
        "python",
        "houdini_mcp_server.py"
      ]
    }
  }
}
```

```bash
ollama-mcp-bridge --config ./mcp-config.json
```

The bridge proxies Ollama's API and routes tool calls to HoudiniMCP automatically.

#### 4. Set Up Documentation Search

```bash
# Downloads Houdini docs and builds the BM25 index (~1 GB)
python scripts/fetch_houdini_docs.py
```

This enables the `search_docs` and `get_doc` tools — they work offline without a Houdini connection.

</details>

## What You Get

HoudiniMCP exposes 88 tools, 8 resources, and 6 prompts over MCP, with the default surface focused on simulation, viewport capture, rendering, node operations, parameters, animation, geometry, cache, workflow templates, undo/redo, and documentation search. The bridge runs as a separate process (`houdini_mcp_server.py`) and talks to the Houdini plugin over TCP.

```
Claude (MCP stdio) → houdini_mcp_server.py (Bridge) → TCP:9876 → server.py (Houdini Plugin) → hou API
                   ↘ houdini_rag.py (BM25 search — docs + patterns, local-only)
                   ↖ scripts/ingest_hips.py (pattern extraction from .hip files)

No Houdini running? Bridge auto-launches hython → headless_server.py → server.py → hou API
```

<details>
<summary><strong>Default MCP Tool Surface</strong></summary>

The default tool set is intentionally smaller than the full Houdini command
handler set. It keeps the tools needed for simulation and capture work visible,
while leaving infrequent PDG, HDA, COP, event, and low-level USD operations
available through `execute_houdini_code` when needed.

Core areas:

- Scene and node inspection
- Node create, modify, delete, copy, move, rename, selection, flags, layout, and batch wiring
- Parameter get/set/schema, expressions, keyframes, frame range, and playbar control
- VEX wrangles and validation
- Materials, geometry summaries, sampled geometry data, bounding boxes, attributes, and export
- Simulation status, DOP objects, stepping, reset, cache list/status/clear/write
- Viewport screenshots, viewport camera/display controls, flipbooks, render setup, render launch, output path checks, and render monitoring
- Workflow templates for Pyro, RBD, FLIP, Vellum, SOP chains, and render setup
- Documentation search, undo, redo, undo history, and scene dossier

</details>

## Shelf Tools

The installer adds a **HoudiniMCP** shelf with a **Toggle MCP Server** button that starts or stops the TCP server on localhost:9876.

## Headless Mode

If no Houdini GUI is running when the MCP bridge starts, it automatically launches a headless `hython` session with the TCP server. This means Claude can work with Houdini's Python API (nodes, geometry, parameters, USD, PDG, rendering, etc.) without opening the UI.

- **Auto-detected**: the bridge probes port 9876 on first tool call — if nothing is listening, it finds `hython` and starts it
- **Transparent**: same tools, same API — just no viewport or interactive UI
- **Cleanup**: the hython process is terminated when the MCP bridge shuts down
- **Disable**: set `HOUDINIMCP_NO_HEADLESS=1` to prevent auto-launch

hython is found only from Steam Houdini Indie: `$HFS` is accepted when it points at the Steam install, otherwise the bridge probes `C:\Program Files (x86)\Steam\steamapps\common\Houdini Indie`. Set `HOUDINIMCP_STEAM_HOUDINI_DIR` if your Steam library is elsewhere.

> **Note:** GUI-only tools (viewport, screenshots, flipbook) won't work in headless mode. All node, geometry, parameter, rendering, USD, PDG, HDA, and code execution tools work normally.

<details>
<summary><strong>Ingest Pipeline</strong></summary>

The ingest pipeline extracts reusable patterns from Houdini's own example `.hip` files and HDA definitions, then indexes them alongside the documentation corpus for BM25 search.

```bash
# Run the full pipeline (discover → parse → extract HDAs → extract patterns → index)
python scripts/ingest_hips.py all

# Or run individual stages
python scripts/ingest_hips.py discover    # Find .hip files in Houdini install
python scripts/ingest_hips.py parse       # Parse .hip files (cpio format, no Houdini needed)
python scripts/ingest_hips.py extract-hdas # Extract HDA networks (requires hython)
python scripts/ingest_hips.py extract     # Extract patterns (scene graphs, subgraphs, recipes)
python scripts/ingest_hips.py index       # Build combined BM25 index (docs + patterns)
```

Pattern types extracted:
- **Scene graphs** — full node hierarchies from each .hip file
- **Subgraphs** — connected node clusters, deduplicated by topology
- **Recipes** — individual node configurations with parameter values

The combined index feeds the same `search_docs` and `get_doc` MCP tools used for documentation search.

</details>

<details>
<summary><strong>Documentation & Guides</strong></summary>

- [Best Practices](BEST_PRACTICES.md) — hard-won lessons from production use (COP pitfalls, diagnostics, etc.)
- [Getting Started](docs/GUIDE_GETTING_STARTED.md) — first-time setup walkthrough
- [Tools Reference](docs/GUIDE_TOOLS.md) — detailed tool documentation with examples
- [Events Guide](docs/GUIDE_EVENTS.md) — event system setup and usage
- [Troubleshooting](docs/TROUBLESHOOTING.md) — common issues and fixes
- [.hip Format Reference](docs/hip_format.md) — cpio-based .hip file format internals

</details>

## Skills

Skills are multi-step workflow guides that define how Claude should approach
complex, repeatable production tasks using HoudiniMCP. Unlike single tool calls,
skills orchestrate sequences of MCP tools, filesystem queries, and user
confirmation gates to complete high-level operations safely.

Skills live in the [`skills/`](skills/) folder. Invoke one by describing the task
to Claude — it will recognise the workflow and follow the skill's phases.

| Skill | Description |
|---|---|
| [`retarget-fx-shot`](skills/retarget-fx-shot.md) | Duplicate an FX rig network and remap all file references from one shot's sequences to another's |

---

## Best Practices — The Recipe Book

Houdini is deep software, and the best way to learn it is from someone who's already been there. [**BEST_PRACTICES.md**](BEST_PRACTICES.md) is a growing collection of practical recipes — the kind of knowledge that saves you hours.

Every entry follows the same format: **what we tried, what surprised us, and what works.** Tagged with the Houdini version so you know what applies to you.

This file is baked into Claude's context, so the AI builds on previous experience instead of starting from scratch. The more you use HoudiniMCP, the smarter it gets.

**Got recipes to share?** As you work with HoudiniMCP, your AI will add entries to its own `BEST_PRACTICES.md`. If you've accumulated useful ones, [open an issue](https://github.com/ysk424/houdini-mcp/issues/new?labels=best-practice&title=Best+Practices+Contribution&body=Paste+your+BEST_PRACTICES.md+contents+below%0A%0A---%0A%0A) and paste your file — we'll merge the good stuff in for everyone.

## Under the Hood

- **Zero external deps for search** — BM25 engine is pure stdlib Python, no numpy/scipy/nltk
- **Cpio parser for .hip files** — reads Houdini's binary scene format without Houdini installed
- **19,000+ patterns** extracted from Houdini's own example files, searchable alongside 11,000+ doc pages
- **Event deduplication** collapses rapid-fire callbacks (same type + path within 100ms)
- **Undo groups** wrap all mutating commands, dangerous code patterns blocked by default
- **256 tests**, all run without a Houdini instance

## What this fork adds

On top of [kleer001/houdini-mcp](https://github.com/kleer001/houdini-mcp), this fork:

- **Concurrent client connections** — the Houdini-side TCP server accepts multiple clients at once
- **`screenshot_viewport` tool** — capture the current viewport directly
- **New handlers** — scene dossier, node-type introspection, and undo/redo, plus handler refactors and expanded tests
- **Enriched tool docstrings** — generated from the descriptions registry
- **Vellum (cloth & hair) best practices** — a new section in [`BEST_PRACTICES.md`](BEST_PRACTICES.md) covering the silent-failure landmines from a 60+-attempt production sim

## Acknowledgements

This repository is a fork of [kleer001/houdini-mcp](https://github.com/kleer001/houdini-mcp)
by kleer001, which is itself derived from the original
[HoudiniMCP](https://github.com/capoomgit/houdini-mcp) by Capoom (MIT). The bulk of the
current feature set — the MCP bridge, command handlers, the BM25 docs engine, the cpio `.hip` parser,
and the event system — comes from kleer001's work. This fork keeps the focused default tool surface and adds the
changes listed under [What this fork adds](#what-this-fork-adds). The original copyright is
retained in [`LICENSE`](LICENSE); this fork is published under the same MIT license.

HoudiniMCP builds on the work of several open-source projects:

- [kleer001/houdini-mcp](https://github.com/kleer001/houdini-mcp) by kleer001 — **direct upstream** of this fork; the current full-featured implementation
- [blender-mcp](https://github.com/ahujasid/blender-mcp) by ahujasid — architectural inspiration (MCP bridge + TCP socket pattern)
- [capoomgit/houdini-mcp](https://github.com/capoomgit/houdini-mcp) by Capoom — original HoudiniMCP and the retained MIT copyright holder
- [eetumartola/houdini-mcp](https://github.com/eetumartola/houdini-mcp) by eetumartola — early Houdini MCP implementation
- [Houdini21MCP](https://github.com/orrzxz/Houdini21MCP) by orrzxz — documentation search engine
- [fxhoudinimcp](https://github.com/healkeiser/fxhoudinimcp) by healkeiser — comprehensive Houdini MCP with 167 tools across 19 categories (MIT license)

## License

MIT

---

<sub>HoudiniMCP is an independent community project and is not affiliated with, endorsed by, or sponsored by SideFX Software. Houdini and SideFX are trademarks of SideFX Software Inc.</sub>
