# OpenCode Integration

This repository provides an OpenCode-compatible config at `opencode.json`.

## What `opencode.json` contains

- `name`, `description`, `author`, `homepage`, `repository`, `license`, `keywords`
  - Sourced from `.claude-plugin/plugin.json` to keep metadata aligned.
- `version`
  - OpenCode config version (currently independent, set to `0.1.0`).
- `skills`
  - Set to `skills` so OpenCode can scan all skill folders.
- `skillPaths`
  - Enumerates all discovered skill directories from `skills/*/SKILL.md`.
- `contextFileName`
  - Defaults to `agents/AGENTS.md`, aligned with `gemini-extension.json` when present.
- `mcpServers`
  - Pulled from `.mcp.json` (fallback to `gemini-extension.json` MCP data when needed).

## Generation and validation

`opencode.json` is generated, not hand-edited.

Use:

```bash
uv run scripts/generate_opencode_config.py
```

Validate without writing:

```bash
uv run scripts/generate_opencode_config.py --check
```

Or run the full publish pipeline:

```bash
./scripts/publish.sh
./scripts/publish.sh --check
```

## Why this design

- Reuses existing single sources of truth for metadata and MCP settings.
- Keeps OpenCode integration in the same generation/check lifecycle as AGENTS/README/Cursor artifacts.
- Automatically tracks all skills under `skills/` with no manual list maintenance.
