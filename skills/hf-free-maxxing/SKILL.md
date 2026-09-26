---
name: hf-free-maxxing
description: "Every free Hugging Face capability in one CLI (hfx): storage, static hosting, CDN, $0 LLM inference, GPU bursts, data queries, OAuth identity, Docker pulls, webhooks — all live-verified. Use when the user wants free cloud storage, free static hosting or a free CDN, free GPU compute or image/video generation, $0 LLM API calls, or asks what the Hugging Face free tier includes or how to avoid paying for AI infrastructure."
license: Apache-2.0
compatibility: "Requires a Hugging Face account + access token, Python 3.10+, and 'huggingface_hub<2.0' boto3 gradio_client. Bash on Linux/macOS; the CLI is pure Python (stdlib + those deps)."
metadata:
  author: landogayatri
  source: https://huggingface.co/landogayatri/hf-free-maxxing
  version: "1.0.0"
  verified: "2026-09"
---

# HF Free-Maxxing — every free Hugging Face capability, one CLI

This skill gives an agent (or human) verified, measured, working access to
**everything HuggingFace offers for $0** through one CLI: `kit/bin/hfx`.
Every command, quota number, and gotcha below was live-verified in Sep 2026
by the hf-free-maxxing research project. The full 1200-line reference is
bundled at [kit/AGENTS.md](kit/AGENTS.md) — this file is the distilled
operating manual.

**What HF does NOT give free** (route elsewhere — Cloudflare/Supabase/Netlify):
dynamic compute/serverless functions, cron schedulers, databases (SQL/NoSQL/vector),
transactional email, custom domains, screenshot/PDF rendering, message queues.

## The free stack (per HF account, numbers verified live)

| Capacity | Amount | Cost |
|---|---|---|
| Private storage | **100 GB** per entity (user + each org) | $0 |
| Public storage | **8.7 TB** per entity (best-effort) | $0 |
| Bandwidth / egress | 20 TB/mo (user) + 30 TB/mo per org, CloudFront | $0 |
| ZeroGPU compute | 300 GPU-sec + **8 runs** per rolling 24h | $0 |
| LLM API | $0 lane (`inclusionAI/Ling-3.0-flash-Fin:novita`) + $0.10/mo credits | $0 |
| Static hosting | unlimited static Spaces, always-on, no cold start | $0 |
| Media CDN upload | `POST /uploads` — outside BOTH storage+bandwidth quotas, permanent | $0 |
| Data query engine | datasets-server filter/search/sort/stats, no rate limit | $0 |
| Identity provider | OIDC/OAuth2 (PKCE + device + RFC7591), no MAU cap | $0 |
| Docker registry | pull any public Docker Space image (registry.hf.space) | $0 |
| Webhooks / events | CRUD + replay + bucket change-feed SSE | $0 |
| Social/content | discussions, collections, likes, markdown renderer | $0 |

**Orgs multiply pools**: each org is a fully separate 100 GB / 8.7 TB / 30 TB
entity. 2–3 real-project orgs is the safe zone (creation throttled to 2 per
rolling 24h; don't farm — see ToS posture below).

## Setup (5 minutes, once)

1. **Install this skill** (any agentskills.io-compatible layout):

   ```bash
   # from the Hugging Face Hub:
   hf download landogayatri/hf-free-maxxing --local-dir .agents/skills/hf-free-maxxing
   # or: git clone https://huggingface.co/landogayatri/hf-free-maxxing .agents/skills/hf-free-maxxing
   # (once listed in the huggingface/skills marketplace: hf skills add hf-free-maxxing)
   ```

2. **Python deps** (⚠️ **PIN `huggingface_hub` to v1.x** — v2.0.0+ has breaking
   changes; the kit is tested against 1.9.x):

   ```bash
   pip install --user "huggingface_hub<2.0" boto3 gradio_client
   ```

3. **Token**: create a PAT at <https://huggingface.co/settings/tokens>
   (`read` for everything read-only, `write` for store/host/etl writes) and
   `export HF_TOKEN=hf_...`. Optional: `HF_JWT` (browser session cookie)
   unlocks a few web-only surfaces (uploads attribution, markdown renderer).

4. **Alias + verify**:

   ```bash
   alias hfx='bash <skill-dir>/kit/bin/hfx'
   hfx doctor        # credential/deps/endpoint check-up (exit 1 on any FAIL)
   hfx status        # quotas across ALL your entities in ~10s
   ```

If HF enforces its password **security-checkup** gate (credential pages start
302-ing to `/security-checkup`), complete it once in a browser:
<https://huggingface.co/security-checkup>.

## Quick wins (copy-paste — most land in under a minute)

```bash
# 0. Where do I stand?
hfx status                                    # quotas across ALL entities

# 1. Store a file durably + get a public CDN URL (public dataset repo)
hfx store put ./mymodel.bin --repo my-files --public
# → https://huggingface.co/datasets/<you>/my-files/resolve/main/mymodel.bin

# 2. Instant image/media hosting (OUTSIDE all quotas, permanent, CORS-open)
hfx cdn put ./photo.png
# → https://cdn-uploads.huggingface.co/production/uploads/<id>/<key>.png

# 3. Host a static site (free, always-on; use a test/kit-style name so `hfx host rm` can clean it up)
hfx host deploy ./mysite -n my-site-test
# → https://<you>-<my-site-test>.static.hf.space

# 4. Free LLM call (the $0 lane — ALWAYS pin the :novita suffix!)
hfx infer chat "Summarize: the quick brown fox..." --free

# 5. Free GPU burst (8 runs/24h is the binding limit — preflight first)
hfx gpu preflight
hfx gpu run mrfakename/Z-Image-Turbo --fn generate_image \
    --arg '"a cat astronaut"' --arg 1024 --arg 1024 --arg 4 --arg 42 --arg false --out ./out

# 6. Query data without a database (upload → wait ~2-3 min → query)
hfx etl upload ./leads.csv
hfx etl filter <you>/hf-free-maxxing-kit-etl --where "score>0.5" --orderby "score desc" --limit 100
```

## The rules that keep it free (memorize these)

1. **PIN the $0 lane**: never send an unsuffixed chat model id — default
   routing is `:fastest` which ignores price (unsuffixed Ling-Fin goes to a
   paid provider). `hfx infer` refuses unsuffixed ids. Pin `:novita` (free),
   `:nscale`, or `:cheapest`.
2. **Router burst mechanics**: EVERY router request (even $0-lane) books a
   $0.01 placeholder against the $0.10/mo cap; >10 unsettled in flight → 402
   until true-up (~1-5 min). Failed requests are never billed. Credits reset
   calendar-month.
3. **ZeroGPU: 8 runs / rolling 24h is the BINDING limit** (300 GPU-s rarely
   binds first). Account-global across ALL public ZeroGPU Spaces. Preflight
   before every batch.
4. **ZeroGPU inputs must be base64 data-URIs** (or same-repo assets) — remote
   URLs fail pre-GPU with a misleading "404". `hfx gpu run` auto-converts.
5. **ZeroGPU outputs are session-bound** — fetch them in the same client
   session (`--out` does); raw URLs 403 later and the public window dies with
   the replica (5.5-24h).
6. **Storage**: 100 GB private / 8.7 TB public **per entity**; max file
   500 GB. Repo files keep quota in git history until `store rm --purge-lfs`;
   bucket objects free quota ≤90s after delete. SDK/rclone `mkdir` creates
   buckets PUBLIC by default — `hfx store` force-flips private.
7. **Presigned share URLs must be SigV4** (default SigV2 presign → 403) —
   `hfx store share` handles it.
8. **Uploads CDN is PERMANENT** — no delete endpoint exists; never upload
   anything sensitive. Magic-byte type allowlist (images/video/audio only).
9. **Static Spaces**: exact file paths only (no clean URLs/SPA fallback — use
   a hash router); CORS is wide open (free asset CDN); variables injected
   into served HTML are PUBLIC (secrets are write-only vaults).
10. **Datasets as a backend**: public data only (private → 501 on free
    accounts); ~2-3 min conversion after upload + lazy index warm-up; page
    size cap 100; 5 GB first-chunk cap for conversion/indexes; DuckDB reads
    the auto-parquet URLs for full SQL incl. cross-repo JOINs.
11. **Rate limits per 5-min window**: api 1000 · resolvers 5000 · pages 200 ·
    media 10000 · search 300 · sensitive 50. Parse `x-error-message` headers —
    they carry precise retry ETAs.
12. **ToS posture**: don't farm orgs, don't mass-follow/mass-like, keep
    `blockedPastWeek=0` (`hfx status` shows it). Enforcement targets
    storage-pattern abuse, not normal use. Never multi-account (suspension
    wave confirmed) — multi-org is the safe pattern.
13. **Credentials**: `HF_TOKEN` (PAT) for everything everyday; `HF_JWT`
    (cookie) for web-only surfaces. `hfx token mint-jwt` mints 1h
    router-only JWTs — CI-safe (leaked JWT can run inference but cannot
    touch repos). OAuth RFC-7591 clients are UN-DELETABLE — one per project.

## Command map (every command has `--help`; most have `--json`)

| Command | What it does |
|---|---|
| `hfx status` | quotas across every entity (user + orgs) |
| `hfx store` | put/get/ls/rm/share/cp-repo/tag — durable storage (repos + S3 buckets) |
| `hfx cdn` | instant permanent media hosting, outside all quotas |
| `hfx host` | deploy/ls/rm static-site Spaces (unlimited, always-on) |
| `hfx infer` | $0-lane LLM chat, model catalog scan, budget, embeddings |
| `hfx gpu` | ZeroGPU preflight/spaces/run (direct Gradio, 2000+ Spaces) |
| `hfx mcp` | hosted MCP server (huggingface.co/mcp): 11 tools + 155 skill:// docs |
| `hfx etl` | upload CSV → hosted filter/search/rows/stats/SQL (DuckDB lane) |
| `hfx oauth` | HF as OIDC IdP: register, authorize-url, token, device flow |
| `hfx registry` | docker login-cmd + manifest for public Space images |
| `hfx token` | token info + mint-jwt (CI-safe disposable credential) |
| `hfx watch` | webhooks CRUD, bucket change-feed SSE, notifications |
| `hfx social` | discussions, collections, likes (comment/curation layer) |
| `hfx md` | markdown→HTML renderer (HF blog engine, cookie-auth) |
| `hfx monitor` | live account metrics SSE + any public Space's runtime/metrics |
| `hfx doctor` | one-shot credential/deps/endpoint check-up |

## Where the deep docs live (bundled in this skill)

- **[kit/AGENTS.md](kit/AGENTS.md)** — the full 1200-line consumer reference:
  every command's exact syntax, limits tables, measured benchmarks, and
  per-capability gotchas with evidence pointers. Read the section you need
  when a task touches that capability.
- **kit/docs/sections/*.md** — the same content as per-topic fragments
  (status, store, cdn, host, infer, gpu, mcp, etl, oauth, registry, token,
  watch, social, md, monitor).
- **kit/bin/hfx** + **kit/lib/** — the CLI itself (pure Python; `run(argv,
  ctx) -> int` convention, exit codes 0/1/2/3: ok/fail/usage-refused/safety).
- **kit/tools/splice_agents_md.py** — rebuilds kit/AGENTS.md from the
  skeleton + sections (edit fragments, never AGENTS.md directly, then splice).

## Provenance

Produced by the hf-free-maxxing research project (Sep 2026): every quota,
endpoint, and gotcha above was live-verified and measured; evidence
transcripts live in the project repo (findings/, playbooks/, data/kit-tests/).
Numbers move in real time — `hfx status` and `hfx infer budget` are always
the source of truth for current quota state.
