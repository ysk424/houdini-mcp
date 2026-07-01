# Bug Report: Houdini MCP screenshot capture failures and unstable viewer targeting

## Summary
Screenshot capture through MCP in Houdini sessions occasionally fails with viewport API mismatches and ambiguous viewer selection, especially in USD/Solaris-centric scenes. Some capture paths work only with a specific panel keypath (for example: `Solaris.panetab7.solaris.persp1`), while generic names often fail.

## Environment
- Project path: `C:\Users\azoo\git\houdini-mcp`
- OS: Windows (user working in PowerShell)
- Houdini: recent branch (user-reported as 2026)
- MCP flow: Houdini MCP tool invoking viewport screenshot operations

## Repro Steps
1. Open a Houdini scene with Solaris context.
2. Trigger screenshot capture by MCP command using a generic viewer reference (for example just `persp` / implicit current viewport).
3. Observe return/exception from MCP.
4. Retry with explicit panel path targeting a Solaris pane (`Solaris.panetab7.solaris.persp1` equivalent).
5. Compare results between first/second attempts.

## Expected
- MCP screenshot should reliably capture the active / explicitly selected viewport without requiring hard-coded pane IDs.
- Error messages should guide the user to a valid target when multiple viewers match.

## Actual
- Observed errors include:
  - Method mismatch (`SceneViewer.saveImage` unavailable).
  - Invalid signature/use of `flipbook()` path.
  - “Too many viewers match” when using non-specific/ambiguous viewer names.
- Practical workaround is to use `viewwrite` with an exact viewer path, but this is brittle and non-portable across layouts.

## Impact
- Makes automated capture/debugging workflows unreliable.
- Breaks smooth MCP-first workflow since users are forced to probe panel names manually.

## Suggested Fix
- Normalize screenshot command to resolve an active viewport reliably when none is provided.
- Add deterministic panel selection (e.g. first matching viewer of expected type with explicit conflict handling).
- Fall back to a robust command path like `viewwrite` with fallback target discovery and clear error when ambiguous.
- Update docs/error text with required panel identifier format and typical examples.

## Notes
- This is user-reported behavior in a practical pipeline: MCP is usable, but screenshot capture still requires manual panel-name workarounds in current version.
