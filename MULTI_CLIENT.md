# Multi-client connections — design note

This fork lets the Houdini-side TCP server accept **multiple concurrent clients**
on port 9876. This note records the design and its tradeoffs.

## What it changes

`src/houdinimcp/server.py` accepts multiple concurrent TCP clients. Each client
has its own receive buffer; command execution stays serial on the Houdini main
thread (matching `hou`'s threading model).

Previous behavior (upstream): single-client lock — a second connection hung
indefinitely.

## Why upstream kept a single-client lock

The single-client lock upstream is a deliberate design choice tied to
assumptions about undo grouping, per-client state isolation, and the plugin's
"single-threaded listener" documentation. Lifting that lock without addressing
those assumptions could regress users who rely on the exclusivity guarantee —
see `BEST_PRACTICES.md` references to `houdini_mcp_exclusive_lock`. This fork
accepts the tradeoffs below rather than upstreaming the change.

## Tradeoffs accepted in this fork

A typical two-client setup:

- **Claude Code** — primary writer of scene mutations.
- **Claude Desktop** — advisor that inspects scene state, answers structural
  and configuration questions, and helps decide direction. Does not mutate.

Concurrent reads from Desktop while Code is mid-edit work fine because dispatch
is serial. UNDO interleaving is acknowledged and accepted (when only one client
writes, the practical impact is minimal).

## Deployment

Edits to `src/houdinimcp/` do **not** auto-reach Houdini. After modifying:

```bash
python scripts/install.py
```

This copies the updated plugin into
`~/Documents/houdini21.0/scripts/python/houdinimcp/`, which is what Houdini
actually loads. Then restart Houdini (or reload the `houdinimcp.server` module
and restart the server instance) to pick up changes.

## Verification

After restart, `mcp__houdini__ping` returns a `client_count` field. Old
single-client builds return only `has_client`.
