---
license: apache-2.0
tags:
- agent-skills
- agent-skill
- huggingface
- cli
- free-tier
- agentskills.io
---

# hf-free-maxxing — an Agent Skill for the free Hugging Face tier

An [Agent Skills](https://agentskills.io)-format skill (installable folder with
a `SKILL.md`) that gives any compatible coding agent — Claude Code, Codex,
Cursor, Gemini CLI, OpenCode, … — **verified, measured access to every FREE
Hugging Face capability** through one CLI (`hfx`):

- **Storage**: 100 GB private + 8.7 TB public *per entity* (user + each org), max file 500 GB
- **Bandwidth**: 20 TB/mo (user) + 30 TB/mo per org on CloudFront
- **Static hosting**: unlimited always-on static Spaces, CORS `*`
- **Media CDN**: permanent uploads outside *both* storage and bandwidth quotas
- **LLM API**: $0.10/mo credits ≈ 5M tokens on the cheapest pinned lane ($0 promos appear & vanish — monthly re-check built in)
- **GPU**: ZeroGPU bursts — 8 runs + 300 GPU-s per rolling 24h (2000+ MCP-enabled Spaces)
- **Data backend**: SQL-ish filter/search/stats over dataset repos + DuckDB full-SQL lane
- **Identity**: full OIDC/OAuth2 provider (PKCE, device flow, RFC 7591), no MAU cap
- **Docker**: read-only pull library of every public Docker Space image
- **Events**: webhooks CRUD + replay, bucket change-feed SSE, notifications

Every quota number, endpoint, and gotcha was **live-verified in Sep 2026** by
the [hf-free-maxxing](https://github.com/landogayatri/hf-free-maxxing)
research project; the skill distills it into an agent-loadable operating
manual + a 16-command CLI (`kit/bin/hfx`).

## Install

Into any skills directory (`.agents/skills/` is the cross-agent standard):

```bash
# with the hf CLI (v1.x):
hf download landogayatri/hf-free-maxxing --local-dir .agents/skills/hf-free-maxxing

# or plain git:
git clone https://huggingface.co/landogayatri/hf-free-maxxing .agents/skills/hf-free-maxxing

# once merged into the huggingface/skills marketplace:
hf skills add hf-free-maxxing
```

Then follow `SKILL.md` (or just mention the skill to your agent). Deps:
`pip install "huggingface_hub<2.0" boto3 gradio_client` and an HF token in
`HF_TOKEN`. Verify with `bash kit/bin/hfx doctor`.

## Layout

```
hf-free-maxxing/
├── SKILL.md      # agent-facing skill instructions (start here)
├── kit/          # the hfx CLI + full consumer docs
│   ├── AGENTS.md # 1200-line verified reference (per-capability deep docs)
│   ├── bin/hfx   # the CLI (16 commands, --help everywhere)
│   ├── lib/      # pure-Python modules
│   └── docs/     # AGENTS.md skeleton + per-topic fragments
└── LICENSE       # Apache-2.0
```

## Provenance

Live-verified Sep 2026; evidence transcripts (findings/, playbooks/,
data/kit-tests/) live in the
[research repo](https://github.com/landogayatri/hf-free-maxxing). Quotas move
in real time — `hfx status` / `hfx infer budget` are the source of truth.
