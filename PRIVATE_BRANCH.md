# private/multi-client — branch purpose

This branch exists **only on `ysk424/houdini-mcp`** and is intentionally **not** for upstream PR.

## What it changes

`src/houdinimcp/server.py` accepts multiple concurrent TCP clients on port 9876.
Each client has its own receive buffer; command execution stays serial on the
Houdini main thread (matching `hou`'s threading model).

Previous behavior: single-client lock — second connection hung indefinitely.

## Why this branch is private

The single-client lock in upstream is a deliberate design choice tied to
assumptions about undo grouping, per-client state isolation, and the
plugin's `single-threaded listener` documentation. Lifting that lock without
addressing those assumptions could regress upstream users who rely on the
exclusivity guarantee — see `BEST_PRACTICES.md` references to
`houdini_mcp_exclusive_lock`.

For *this user's* workflow the tradeoffs are acceptable:

- **Claude Code** — primary writer of scene mutations.
- **Claude Desktop** — advisor that inspects scene state, answers structural
  and configuration questions, and helps decide direction. Does not mutate.

Concurrent reads from Desktop while Code is mid-edit work fine because
dispatch is serial. UNDO interleaving is acknowledged and accepted (Code is
the only writer, so practical impact is minimal).

## Deployment

Edits to `src/houdinimcp/` do **not** auto-reach Houdini. After modifying:

```bash
python scripts/install.py
```

This copies the updated plugin into
`~/Documents/houdini21.0/scripts/python/houdinimcp/`, which is what Houdini
actually loads. Then restart Houdini (or reload the `houdinimcp.server`
module and restart the server instance) to pick up changes.

## Verification

After restart, `mcp__houdini__ping` returns a `client_count` field. Old
single-client builds return only `has_client`.

## Tracking upstream

```bash
git fetch upstream
git rebase upstream/main   # or merge — both fine, branch is private
```

The change footprint is small (~120 lines, one source file plus tests) so
conflicts on upstream pulls should be rare.
