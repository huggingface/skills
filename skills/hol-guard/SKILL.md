---
name: hol-guard
description: Use when protecting a local coding agent that uses Hugging Face Skills or the hf CLI with HOL Guard, reviewing Guard approvals or receipts, or scanning Agent Skills and MCP packages before use or release.
license: Apache-2.0
---

# HOL Guard

HOL Guard protects local AI harnesses before tools run. Use this skill when the user wants AI antivirus behavior, local approval review, Codex protection, Claude Code protection, MCP safety checks, skill/package verification, or release gates from `hol-guard` and `plugin-scanner`.

## Hard Rules

- Never read `.env` files.
- Never bypass Guard approvals.
- Do not mark a workspace protected until a Guard command proves status.
- Prefer reversible Guard commands over direct harness config edits.
- Do not mutate user-level harness config unless the `hol-guard` command owns that mutation.
- Treat scanner failures as real until inspected.
- Preserve existing user changes and inspect `git status --short` before edits in a repo.

## Install Check

Check both CLIs independently by invoking them directly so the check works across supported shells:

```bash
hol-guard --version
plugin-scanner --version
```

If `hol-guard` is missing and the user asked for runtime setup, prefer:

```bash
pipx install hol-guard
```

If `plugin-scanner` is missing and the user asked for scanning, install the separate scanner distribution:

```bash
pipx install plugin-scanner
```

Do not assume the `hol-guard` distribution provides the `plugin-scanner` command. If `pipx` is unavailable, explain that isolated CLI installation is recommended rather than silently changing the user's Python environment.

After runtime installation:

```bash
hol-guard status
hol-guard detect --json
```

## Use With Hugging Face Skills

HOL Guard protects the local agent harness, not the Hugging Face service. Before giving a supported coding agent access to Hugging Face Skills or `hf` CLI operations, install Guard on that harness and confirm protection:

```bash
hol-guard install <harness>
hol-guard run <harness> --dry-run
hol-guard run <harness>
hol-guard status
```

Then install or use Hugging Face Skills normally, for example:

```bash
hf skills add <skill-name>
```

If reviewing a downloaded or contributed Agent Skill before use or release, scan its package directory with `plugin-scanner` as described below. Never claim this creates a server-side Hugging Face security integration; the enforcement boundary is the supported local harness.

## Protect A Local Harness

Use `hol-guard detect --json` as the source of truth for current harness support. Select the exact identifier returned for the local harness the user intends to run. Do not maintain or rely on a static support list. If the requested harness is absent or ambiguous, stop rather than substituting another detected harness.

```bash
hol-guard bootstrap
hol-guard install <detected-harness>
hol-guard run <detected-harness> --dry-run
hol-guard doctor <detected-harness> --json
hol-guard run <detected-harness>
hol-guard status
```

Use harness-specific bootstrap when the detected target requires it. For Hermes:

```bash
hol-guard hermes bootstrap
```

### Claude Code

Use this when the workspace has `.claude/settings.local.json`, `.claude/agents`, Claude hooks, `.mcp.json`, or Claude-managed tool approval surfaces.

```bash
hol-guard install claude-code
hol-guard run claude-code --dry-run
hol-guard run claude-code
hol-guard doctor claude-code --json
```

Claude Code is a first-class Guard target. Prefer Guard-owned Claude hooks over direct manual edits to Claude config.

### Codex

Use this when the workspace has Codex config, `.codex/hooks.json`, Codex MCP servers, or Codex App/CLI tool flows.

```bash
hol-guard install codex
hol-guard run codex --dry-run
hol-guard run codex
hol-guard doctor codex --json
```

Codex supports Guard-owned `PreToolUse` Bash hooks and same-chat MCP elicitation where available.

## Approval Work

If Guard blocks or queues work:

```bash
hol-guard approvals
hol-guard approvals open <request-id>
hol-guard receipts
hol-guard diff <detected-harness>
```

`hol-guard approvals open` requires the pending request ID shown by `hol-guard approvals`. Do not invent or omit that ID.

For terminal-only resolution:

```bash
hol-guard approvals approve <request-id>
hol-guard approvals deny <request-id>
```

Only approve after reading the risk reason and understanding the requested scope.

## Evidence Work

Use evidence commands when user needs proof, audit trail, or handoff artifacts:

```bash
hol-guard receipts
hol-guard inventory
hol-guard abom --format json
hol-guard events
hol-guard explain <artifact-id>
```

For cloud sync, keep it optional and user-directed:

```bash
hol-guard connect
hol-guard connect status
hol-guard connect repair
hol-guard sync
```

## Scan A Plugin Or Skill Package

Use scanner mode for Codex plugins, Claude Code project surfaces, `.agents` marketplaces, skills, MCP server configs, and release gates.

```bash
plugin-scanner lint .
plugin-scanner verify .
```

If scanning a specific package:

```bash
plugin-scanner lint <path>
plugin-scanner verify <path>
```

If the target is a Codex marketplace root with `.agents/plugins/marketplace.json`, scan the repo root so local plugin entries can be discovered.

Scanner target guidance:

- Codex plugin: scan the repo root or plugin folder containing `.codex-plugin/plugin.json`.
- Codex marketplace: scan the repo root containing `.agents/plugins/marketplace.json`.
- Claude Code project: scan the workspace root containing `.claude/`, `.mcp.json`, hooks, or agent folders.
- MCP server package: scan the package root containing server config and package metadata.
- Skill package: scan the folder containing `SKILL.md`.
- Mixed agent workspace: scan the repo root so local plugin, skill, MCP, and harness config surfaces are discovered together.

## Common Debug Commands

```bash
hol-guard doctor
hol-guard doctor <harness> --json
hol-guard detect --json
hol-guard settings show
hol-guard explain install-connect
plugin-scanner verify . --json
```

## Response Pattern

When using Guard, report:

- What command ran.
- What Guard found.
- What remains blocked or risky.
- What proof exists.
- Exact next command if user must act.

Do not claim protection, approval, or release readiness without command output proving it.
