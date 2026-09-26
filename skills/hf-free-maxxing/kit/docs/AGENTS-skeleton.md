# AGENTS.md — HuggingFace Free-Maxxing Kit (consumer agent onboarding)

> **You are a consumer agent (or human) who wants FREE cloud capacity for a side
> project.** This kit gives you verified, measured, working access to every free
> resource HuggingFace offers — storage, bandwidth, CDN, static hosting, GPU
> bursts, $0 LLM inference, data querying, OAuth identity, a Docker pull-library
> and more — through ONE CLI: `kit/bin/hfx` (alias `hfx` below).
>
> Everything here was **live-verified and measured** (Sep 2026) by the
> hf-free-maxxing research project. **Evidence links** (findings/, playbooks/,
> RESOURCE-MAP.md) live in the parent research repo — if you received only the
> kit/ directory, treat them as provenance pointers, not required reading; every
> command and number you need is in this file or in `--help`. Nothing in this
> kit costs money or violates ToS when used as documented.

## Contents
1. [TL;DR — the free stack](#tldr--the-free-stack-you-get-per-hf-account-numbers-verified-live)
2. [Prerequisites](#prerequisites-5-minutes-once)
3. [Quick wins](#quick-wins-copy-paste--most-land-in-under-a-minute-data-queries-warm-up-for-a-few-minutes)
4. [Command reference](#command-reference) — status · store · cdn · host · infer · gpu · mcp · etl · oauth · registry · token · watch · social · md · monitor
5. [The rules that keep it free](#the-rules-that-keep-it-free-gotchas-distilled--read-once-save-hours)
6. [Capacity map & limits](#capacity-map--limits-the-full-verified-numbers)
7. [The 30-day age-gate unlock](#the-30-day-age-gate-unlock)
8. [Evidence & deeper docs](#evidence--deeper-docs)

**Shell alias (recommended):** `alias hfx='bash /path/to/kit/bin/hfx'`

## TL;DR — the free stack you get (per HF account, numbers verified live)

| Capacity | Amount | Cost | Evidence |
|---|---|---|---|
| Private storage | **100 GB** per entity (user + each org) | $0 | findings/quota-baseline.md |
| Public storage | **8.7 TB** per entity (best-effort) | $0 | findings/quota-baseline.md |
| Entity pools you control | 1 user + each org you create — every entity is its own 100 GB / 8.7 TB pool | $0 | findings/orgs-multiplication.md |
| Bandwidth / egress | 20 TB/mo (user) + 30 TB/mo per org, CloudFront | $0 | findings/orgs-probe.md |
| ZeroGPU compute | 300 GPU-sec + **8 runs** / rolling 24h | $0 | findings/spaces-probe.md |
| LLM API | $0 lane (Ling-3.0-flash-Fin:novita) + $0.10/mo credits | $0 | findings/zero-cost-models.md |
| Static hosting | unlimited static Spaces, always-on, no cold start | $0 | playbooks/static-hosting.md |
| Media CDN upload | `POST /uploads` — outside BOTH quotas, permanent | $0 | findings/uploads-cdn-probe.md |
| Data query engine | datasets-server filter/search/sort/stats, no rate limit | $0 | findings/datasets-etl-final.md |
| Identity provider | OIDC/OAuth2 (PKCE + device + RFC7591), no MAU cap | $0 | findings/oauth-idp.md |
| Docker registry | pull any public Space image (registry.hf.space) | $0 | findings/containers-registry.md |
| Webhooks / events | CRUD + replay + bucket change-feed SSE | $0 | findings/infra-probe.md |
| Social/content APIs | discussions, collections, likes, markdown renderer | $0 | findings/review-identity-infra-cluster.md |

**What HF does NOT give you free** (route these to Cloudflare/Supabase/Netlify):
dynamic compute/serverless functions, cron/schedulers, any database for user
data (SQL/NoSQL/vector), transactional email, custom domains, screenshot/PDF
rendering, message queues. Full negative matrix: findings/review-stone-taxonomy.md.

---

## Prerequisites (5 minutes, once)

1. **A HuggingFace account + token.** Create a PAT at
   <https://huggingface.co/settings/tokens> — role `read` for everything
   read-only, `write` for `store`/`host`/`etl` writes. Put it in the
   environment (`export HF_TOKEN=hf_...`) or in a `.env` file next to the kit's
   parent repo root (the kit auto-loads `kit/.env` then `<repo>/.env`).
2. **Python deps** (verify with `hfx doctor`):
   ```bash
   pip install --user "huggingface_hub<2.0" boto3 gradio_client
   # PEP-668 box refuses --user? use a venv:
   python3 -m venv ~/hfx-venv && ~/hfx-venv/bin/pip install "huggingface_hub<2.0" boto3 gradio_client
   ```
   ⚠️ **PIN `huggingface_hub` to v1.x** — v2.0.0 (released 2026-09-24) has
   breaking changes (httpx2 rewrite). The kit is tested against 1.9.x.
3. **Optional web-session cookie** (`HF_JWT`) unlocks a few extra surfaces
   (uploads with user attribution, markdown renderer, billing page balance).
   Extract from an authenticated browser session (cookie named `token`). Most
   kit commands do NOT need it.
4. **Verify:** `hfx status` should print quotas for every entity. If it errors,
   `hfx doctor` diagnoses.

### One-time browser step you may hit (security checkup)
HF periodically enforces a **password security-checkup** on credential
management pages (`/settings/tokens`, app management). While active, headless
minting of NEW tokens is blocked (existing tokens and `hfx token mint-jwt`
keep working). Fix once in a browser: visit
<https://huggingface.co/security-checkup> and complete the checkup.

---

## Quick wins (copy-paste — most land in under a minute; data queries warm up for a few minutes)

```bash
# 0. Where do I stand?
hfx status                                    # quotas across ALL entities

# 1. Store a file durably + get a public CDN URL (uses a public dataset repo)
hfx store put ./mymodel.bin --repo my-files --public
# → https://huggingface.co/datasets/<you>/my-files/resolve/main/mymodel.bin

# 2. Instant image/media hosting (OUTSIDE all quotas, permanent, CORS-open)
hfx cdn put ./photo.png
# → https://cdn-uploads.huggingface.co/production/uploads/<id>/<random-key> (PERMANENT — no delete)

# 3. Host a static site (free, always-on; use a test/kit-style name so `hfx host rm` can clean it up)
hfx host deploy ./mysite -n my-site-test
# → https://<you>-<my-site-test>.static.hf.space

# 4. Free LLM call (the $0 lane — PIN the :novita suffix!)
hfx infer chat "Summarize: the quick brown fox..." --free
# (or: curl https://router.huggingface.co/v1/chat/completions ... model=inclusionAI/Ling-3.0-flash-Fin:novita)

# 5. Free GPU burst (check budget first — 8 runs/24h is the binding limit)
hfx gpu preflight                             # quota + live GPU availability
hfx gpu run mrfakename/Z-Image-Turbo --fn generate_image --arg '"a cat astronaut"' --arg 1024 --arg 1024 --arg 4 --arg 42 --arg false --out ./out

# 6. Query data without a database
hfx etl filter <you>/my-dataset --where "score>0.5" --orderby "score desc" --limit 100
```

## Command reference

Every command supports `--help`; most support `--json` (usable before OR after
the subcommand). Numbers move in real time — `hfx status` is the source of
truth for current quota state. Note: credits shown by `status` include
UNSETTLED $0.01 placeholders (`hfx infer budget` shows settled truth), and
concurrent sessions share the same pools — numbers can shift between reads.

<!-- SECTION:status -->
<!-- SECTION:store -->
<!-- SECTION:cdn -->
<!-- SECTION:host -->
<!-- SECTION:infer -->
<!-- SECTION:gpu -->
<!-- SECTION:mcp -->
<!-- SECTION:etl -->
<!-- SECTION:oauth -->
<!-- SECTION:registry -->
<!-- SECTION:token -->
<!-- SECTION:watch -->
<!-- SECTION:social -->
<!-- SECTION:md -->
<!-- SECTION:monitor -->

---

## The rules that keep it free (gotchas distilled — read once, save hours)

**Billing mechanics (router/inference):**
1. Every router request instantly books a **$0.01 placeholder**; settled truth
   lands ~5 min later. More than **10 unsettled requests in flight** → 402
   "depleted" until placeholders settle (~2-5 min). Pace rapid-fire calls.
2. The $0 lane (`inclusionAI/Ling-3.0-flash-Fin:novita`) settles at literally
   $0 — but still consumes placeholder slots. **Always pin `:novita`**;
   unsuffixed routes to `:fastest` → paid provider.
3. Failed requests are never billed. `usage.estimated_cost` in each response
   shows the per-call cost.
4. $0.10/mo included credits reset **calendar-month** (Oct 1).

**ZeroGPU:**
5. **8 runs / rolling 24h is the BINDING limit** (300 GPU-s is rarely the
   constraint). Account-global across ALL public ZeroGPU spaces.
6. Inputs to ZeroGPU spaces must be **base64 data-URIs** (or same-repo assets);
   remote URLs fail pre-GPU with a misleading "404" (at $0 charge).
7. Outputs are **session-bound**: fetch them in the same client session
   (gradio_client does this automatically); raw URLs 403 later. Fetch
   immediately; public access window dies with the serving replica
   (between 5.5h and 24h).
8. Errored runs still consume a run slot **with counter lag** (immediate quota
   reads lie — recheck at +30 min).

**Storage:**
9. **Public vs private bucket trap:** SDK/rclone `mkdir` creates buckets
   **PUBLIC by default**. Flip: `PUT /api/buckets/{ns}/{name}/settings
   {"private":true}`. (The kit's `store` command handles this.)
10. **Repos vs buckets:** repo files (LFS/Xet) are versioned and permanent;
    bucket objects are deletable and quota-frees within ~90s. Use buckets for
    scratch/deletable, repos for durable/CDN-served.
11. Xet dedup saves **upload bandwidth** (13.7× faster re-uploads of identical
    content) but NOT quota; identical content in different repos counts twice.
    The duplicate API copies whole repos near-instantly (341 MB in 0.82 s).
12. Private sharing: **presigned URLs must be SigV4** (default SigV2 presign →
    403). `hfx store share` handles this.
13. Upload path choice (measured): <10 MB → hub `upload_file`; 10MB–5GB → hub +
    `HF_XET_HIGH_PERFORMANCE=1`; >5GB → S3 auto-multipart. `hf_transfer` is a
    deprecated no-op — don't bother.

**Static hosting:**
14. No clean URLs (use a hash-router), no SPA fallback, no custom 404; CORS is
    wide open (`*`) = free asset CDN; `Cache-Control` absent on HTML (ETag/304
    only); secrets in static Spaces are **write-only vaults — values are NEVER
    injected into served HTML** (variables ARE injected but PUBLIC — treat as
    config, not secrets).

**Uploads CDN (`hfx cdn`):**
15. Type allowlist (magic-byte sniffed): GIF/JPEG/PNG/WEBP/MP4/MOV/WEBM/WAV/
    MP3/MPGA/QT. ≥5 MiB verified. **Permanent — no delete endpoint exists.**
    Outside storage AND bandwidth quotas. Anonymous uploads possible
    (`/production/uploads/noauth/`) — cookie auth gives user-scoped URLs.

**Rate limits (per 5-min window, per account):**
16. api 1000 · resolvers 5000 · pages 200 · media 10000 · search 300 ·
    sensitive 50. datasets-server has **no observed rate limit** (but the
    huggingface.co resolver bucket applies to parquet downloads). Parse
    `x-error-message` headers — they carry precise retry ETAs.

**ToS posture (stay safe, stay free):**
17. Don't farm orgs (2-3 real-project orgs is the safe zone; each new org =
    its own pools, creation throttled to 2/rolling-24h). Don't mass-follow/
    mass-like. Keep `blockedPastWeek=0` (`hfx status` shows it). Uploads-CDN
    files are permanent — never upload anything sensitive. Enforcement waves
    target storage-pattern abuse (retry loops, multi-TB dumps), not normal use.

---

## Capacity map & limits (the full verified numbers)

- **Storage per entity:** 100 GB private / 8.7 TB public (100 GB = 93.13 GiB;
  public is best-effort, safe envelope ≤~1 TB of real carded content per
  namespace). Max file 500 GB. Buckets share the same pool.
- **Bandwidth:** 20 TB/mo user, 30 TB/mo per org (CloudFront, no per-GB fee).
- **ZeroGPU:** 300 GPU-s + 8 runs per rolling 24h from first use; RTX Pro 6000
  class; pre-flight live GPU count via api.hf.space events SSE.
- **Inference credits:** $0.10/mo included (user account only; orgs get $0);
  cheapest long-tail provider: featherless-ai (~$0.039/1M in). SD3-medium
  image ≈ $0.00007 on credits (~1400/mo). Embeddings ≈ $0.0000003/call.
- **Datasets-server:** filter (WHERE + `orderby="col [asc|desc]"`, single col)
  / search (token-match, 100% recall) / rows (pagination 100/page, works at
  6.4M rows) / statistics / first-rows; 5 GB conversion cap; cold start on
  idle datasets can take minutes; NO rate limit observed. DuckDB reads the
  parquet URLs directly = full SQL incl. cross-repo JOINs, client-side.
- **OAuth IdP:** PKCE + device flow + RFC7591 anonymous dynamic registration;
  21 scopes; access tokens 8h, refresh rotates; every user needs an HF account.
- **Webhooks:** CRUD + replay, 1000 triggers/24h, no scheduler (pair with
  external cron). Bucket change-feed SSE available.
- **Transformers.js:** run inference in the VISITOR's browser (WASM/WebGPU) —
  unlimited, zero quota. Ship it as a static Space (`hfx host deploy` + the
  `@huggingface/transformers` CDN build) — no quota touched, ever.

## The 30-day age-gate unlock
Accounts younger than **30 days** cannot create ZeroGPU Spaces (402 on
create — verified). On day 30 the gate lifts: a free personal account may
create **2 ZeroGPU Spaces** = its own always-wakeable free GPU API endpoints
(think: media-gen gateway + LLM proxy). Community-blog publishing eligibility
(`canCreateBlog`) likely unlocks around the same mark (~30d + follower count;
watch `GET /api/blog` → `.canCreateBlog`). Kit commands gain
`hfx host zero-gpu` then.

## Evidence & deeper docs
- Master map: `RESOURCE-MAP.md` · Research findings: `findings/*.md`
- Playbooks: `playbooks/{inference,media-gen,storage,static-hosting}-maxxing.md`
- The no-stone-unturned negative matrix: `findings/review-stone-taxonomy.md`
- Research meta (how all this was verified): `.agents/SKILL.md` (project agents)
