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

### status — quotas across every entity

```bash
hfx status                 # human table: user + every org (~25-30s)
hfx status --storage-only  # FAST mode (~3x): storage/bucket standing only
hfx status --json          # machine-readable
hfx status --entity <you>   # one entity only
```

Reads three free endpoints (no writes, ~$0): per-entity billing usage/live
SSE (storage private/public used, credits) and — user only — ZeroGPU quota
(GPU-seconds + runs remaining, rolling 24h).

`--storage-only` skips the ZeroGPU call and the credits read, and gives each
entity's SSE a short window — same storage numbers as full mode (back-to-back
verified identical; measured 13s vs 28s on the 3-entity kit account). Use it
in scripts/loops that only care about storage standing; the SSE stream stays
open server-side, so the full mode's 8s/entity window is mostly wait time.

What to look at:

| Row | Meaning | Free ceiling |
|---|---|---|
| storage/TOTAL private | counts against the hard cap | 100 GB per entity |
| storage/TOTAL public | best-effort pool | 8.7 TB per entity (safe envelope ≤~1 TB) |
| credits | inference-providers spend | $0.10/mo included, user account only |
| ZeroGPU runs | **the binding GPU limit** | 8 per rolling 24h (300 GPU-s secondary) |

**`--json` shape** (stable; `--storage-only` = same shape minus the skipped
keys):

```json
{"entities": [
   {"name": "<user>", "kind": "user",
    "storage": {"used", "usedPrivate", "usedPublic",
                "privateStorageLimit", "publicStorageLimit",
                "summary": {"dataset|space|model|bucket":
                            {"used", "usedPrivate", "usedPublic", "count"}}},
    "inference_credits": {"used", "limit", "included"},   // omitted: --storage-only
    "zero_gpu": {"base", "current", "runs", "resetsAt"}},  // user only; omitted: --storage-only
   {"name": "<org>", "kind": "org", "storage": {…}}],
 "generated": "2026-09-26T…Z"}
```

Notes:
- Each **org is a fully separate pool** (own 100 GB + 8.7 TB + 30 TB/mo
  bandwidth) — that's the multiplication finding; orgs get $0 credits and no
  ZeroGPU.
- Quota frees asynchronously after deletes: buckets ~90 s, LFS history only
  after `store rm --purge-lfs`.
- The first SSE event can be a partial snapshot — the kit waits for the last
  complete event (research gotcha #6).
- `--storage-only` uses a 3s SSE window per entity (vs 8s): the first
  complete event lands ~instantly; on an empty fast window the kit retries
  once with the patient window before failing.
- Evidence: findings/quota-baseline.md, findings/orgs-multiplication.md.

<!-- SECTION:store -->

### store — durable storage & sharing

```bash
# durable upload — fastest path auto-selected by size (measured)
hfx store put ./mymodel.bin                      # private repo hfx-store (100GB pool)
hfx store put ./mymodel.bin --public             # public repo hfx-store-public (8.7TB pool)
# → https://huggingface.co/datasets/<you>/hfx-store-public/resolve/main/mymodel.bin  (anon CDN URL)
hfx store put ./big.bin --bucket my-bucket       # S3 bucket (created PRIVATE on demand)

# get it back (repo id, full resolve URL, or bucket key)
hfx store get <you>/hfx-store mymodel.bin --out mymodel.bin
hfx store get mymodel.bin --bucket my-bucket --out mymodel.bin

# list / delete
hfx store ls                                     # every repo + bucket in your namespace
hfx store ls --repo hfx-store                    # files (dataset repos)
hfx store ls --bucket my-bucket                  # objects (S3)
hfx store rm mymodel.bin --repo hfx-store --purge-lfs   # ALSO reclaims quota (history rewrite)
hfx store rm mymodel.bin --bucket my-bucket              # bucket delete frees quota ≤90s
hfx store rm-bucket my-bucket                     # delete the whole bucket (refuses if not empty)
hfx store rm-bucket my-bucket --force             # …or empty it first, then delete

# private sharing (expiring, anonymous-fetchable)
hfx store share mymodel.bin --bucket my-bucket --ttl 3600   # SigV4 presigned URL

# instant copy (server-side Xet migration — 341MB in 0.82s) + versioned pins
hfx store cp-repo src-repo dst-repo [--private]
hfx store tag hfx-store v1.0.0                   # → resolve/v1.0.0/<path> asset URLs
```

Path selection is automatic (`put`): <10MB → hub `upload_file` (Xet); ≥10MB → same
+ `HF_XET_HIGH_PERFORMANCE=1` (1.36× measured); `--bucket` → boto3 `upload_file`
(auto-multipart ≥8MB, 8MB×10 threads). `hf_transfer` is a deprecated no-op —
don't install it.

| Scenario | Winner | Measured | Gotchas |
|---|---|---|---|
| Small file public (<10MB) | hub `upload_file` | 10MB in 6.8s | ~4–5s fixed overhead; served on CDN instantly |
| Large public (10MB–5GB) | hub + `HF_XET_HIGH_PERFORMANCE=1` | 100MB in 22.6s (4.6MB/s) | hf_transfer never engages in hub ≥1.x |
| Huge (5–500GB) | S3 bucket + boto3 `upload_file` | 100MB in 30.3s | endpoint `https://s3.hf.co/<ns>` (per-namespace); `request_checksum_calculation='when_required'` |
| Private store | bucket via Hub API (forced private) | 10MB PUT 7.7s | SDK/rclone mkdir = PUBLIC — `hfx store` flips it |
| Private share | SigV4 presigned URL | anon 8.8MB/s via CDN | SigV2 presign → 403; expiry enforced |
| Instant copy | duplicate API (`cp-repo`) | 341MB in 0.82s | counts toward quota; default visibility public |
| Public serve | resolve URL on public repo | 6.8MB/s; 1MB range in 1.3s | anon 3000/5min per-IP; `?download=true` |
| Deletable storage | bucket (`rm --bucket`) | quota freed ≤90s | repo files need `--purge-lfs` to reclaim |
| Bucket teardown | `rm-bucket` (empty) / `rm-bucket --force` | delete → 204; quota ≤90s | refuses non-empty buckets unless `--force` (deletes objects first) |

**Limits:** 100GB private / 8.7TB public (best-effort) **per entity** (user + each
org — `hfx status` shows all pools). Max file 500GB. Buckets share the same pool.

**Gotchas (all handled by `hfx store`):**
1. **Public-bucket trap** — SDK/rclone `mkdir` creates buckets PUBLIC. The kit
   creates via Hub API and force-flips `PUT /api/buckets/{ns}/{name}/settings
   {"private":true}`, then verifies.
2. **Dedup ≠ quota** — Xet chunk dedup saves upload wire (13.7× re-uploads), but
   identical content in different repos/buckets bills separately (within one
   repo, identical LFS content counts once).
3. **Presigned URLs are SigV4-only** — boto3's default SigV2 presign gets 403
   `SignatureDoesNotMatch`. (`hfx store share` forces s3v4.)
4. **LFS history keeps quota** — `rm` on a repo file only deletes the tip; bytes
   stay in git history. `--purge-lfs` batch-deletes the LFS objects with
   `rewriteHistory:true` (quota back in ~25–80s). Whole-repo delete = `hfx etl rm`
   (≤60s); whole-bucket delete = `hfx store rm-bucket` (≤90s).
5. S3 creds: generate at settings/tokens → "Generate S3 credentials" (web
   session) → `HF_S3_ACCESS_KEY_ID`/`HF_S3_SECRET_ACCESS_KEY` in env or `.env`.

**Evidence:** findings/storage-upload-benchmark.md (all speeds) ·
findings/storage-probe.md (S3 gateway, duplicate API) ·
findings/review-storage-cluster.md (multipart, tags, LFS batch delete) ·
live-test transcripts: data/kit-tests/store/ (SUMMARY.md = verdict matrix)

<!-- SECTION:cdn -->

## cdn — instant media hosting (quota-free, PERMANENT)

`hfx cdn put FILE` → one POST to the web editor's `POST /uploads` surface →
a permanent CDN URL on `cdn-uploads.huggingface.co` (S3 + CloudFront) that is
**outside both the storage AND bandwidth quotas**. CORS `*`, HTTP Range
(video seeking works), content-type preserved, byte-identical downloads.

```bash
hfx cdn put ./photo.png
# → https://cdn-uploads.huggingface.co/production/uploads/<userId>/<key>.png

hfx cdn put ./clip.mp4 --json        # {"url": ..., "bytes": ..., "type": "video/mp4"}
hfx cdn put ./maybe.webm --check     # dry-run: sniff magic bytes, upload nothing
hfx cdn put ./doc.pdf                # → rejected LOCALLY (exit 2), zero rate-limit cost
```

| Limit | Value |
|---|---|
| Type allowlist (magic-byte sniffed, client **and** server) | GIF · JPEG/JPG · MOV · MP3 · MP4 · MPGA · PNG · QT · WAV · WEBM · WEBP |
| Size | ≥5 MiB verified (floor, not cap) — be a good citizen, self-cap ~5 MB |
| Auth | `HF_JWT` cookie → user-scoped URLs (`/production/uploads/<userId>/`); **no cookie = ANON lane** (`/production/uploads/noauth/`) — works without any account; a PAT is ignored (≠ web auth) |
| Rate limit | `pages` bucket: **200/5min** (cookie) · **100/5min** (anon); each upload ≈1–2 units; even server-rejected 415s cost a unit → the kit sniffs client-side FIRST |
| Lifetime | **PERMANENT — no delete endpoint exists. Never upload anything sensitive.** |
| URL shape | random 22-char key + extension; no custom names; identical re-uploads mint NEW URLs |

Notes:
* The server re-sniffs magic bytes — declaring `Content-Type: image/png` on
  random data gets a 415 (you can't smuggle arbitrary files).
* No `Cache-Control` (CloudFront default TTL) — treat URLs as immutable.
* Best for: blog/social images, generated media, static-site assets.
  For arbitrary files (zip/pdf/binaries) use `hfx store put` instead.

Evidence: findings/uploads-cdn-probe.md · live test: data/kit-tests/cdn-host-md/

<!-- SECTION:host -->

## host — free static-site hosting (Spaces, sdk: static)

`hfx host deploy DIR -n NAME` creates (if absent) a **public static Space**
and uploads every non-dotfile in `DIR` recursively via `huggingface_hub`.
Always-on from birth, no cold start, free within the 20 TB/mo bandwidth quota,
unlimited site count, and **CORS `*` on every response** (any site can fetch
your assets — a free JSON/asset CDN in its own right).

```bash
hfx host deploy ./mysite -n my-site
# → LIVE: https://<you>-my-site.static.hf.space

hfx host deploy ./site -n my-site --entity my-org    # org namespace (orgs multiply hosting)
hfx host ls                                           # your spaces
hfx host ls --entity my-org
hfx host rm my-site --dry-run                         # show what WOULD be deleted
hfx host rm my-site --yes                             # actually delete (kit/test names only)
```

What deploy does: `POST /api/repos/create {"type":"space","sdk":"static",
"private":false}` → `upload_file` per file. Your `README.md` is **skipped
unless it carries `sdk:` front-matter** (the auto-generated one is what keeps
the Space a static Space — clobbering it breaks the site). Dotfiles are never
uploaded.

| Limit / gotcha | Detail |
|---|---|
| Routing | **exact file paths only** — no clean URLs, no dir index, no SPA fallback, no custom 404 (`404.html` is decorative). Bare `GET /` works (302 → `/index.html`); for multi-page sites either link FULL file paths (`/about.html`) or use a hash router (`/#/about`); trailing-slash links bounce visitors to huggingface.co |
| Caching | ETag/304 on assets, **no `Cache-Control`**, no gzip → version assets (`app.js?v=2`) and pre-minify |
| Privacy | everything in a public Space is world-readable (it's a public git repo); `.md` files serve as RENDERED HTML |
| Variables | injected into served HTML as `window.huggingface.variables` → **public by design**; secrets exist but are write-only and useless (no backend) |
| Not free/absent | custom domains = PRO $9/mo; `app_build_command` builds are credits-gated (build in CI, upload `dist/`); private Spaces are not web-servable as a site |
| Safety | `hfx host rm` refuses names without "test"/"kit" (exit 3) and asks y/N unless `--yes` |

`rm` uses `DELETE /api/repos/delete` (verified; the plausible-looking
`DELETE /api/spaces/{ns}/{name}` is a 404 route).

Evidence: playbooks/static-hosting.md · live test: data/kit-tests/cdn-host-md/

<!-- SECTION:infer -->

## infer — free LLM calls via the router ($0 lane + $0.10/mo credits)

The kit's chat default is the **$0 lane**: `inclusionAI/Ling-3.0-flash-Fin:novita`
($0/$0 per 1M tokens, 262k ctx, ~250 tok/s, tools✅ — verified across 39+ lifetime
calls, every one settled at 0 nanoUsd). Everything runs through
`https://router.huggingface.co/v1` (OpenAI-compatible) with your `HF_TOKEN`.

```bash
hfx infer chat "Summarize: ..."            # $0 lane, prints content + cost + budget note
hfx infer chat "hi" --max-tokens 300       # the lane is a REASONING model — see below
hfx infer chat "hi" --model Qwen/Qwen3-4B-Instruct-2507:nscale   # paid: warns "this call costs ~$X"
hfx infer models --free-only               # the 3 $0/$0 lanes (public catalog, free)
hfx infer models --pattern llama           # price-scan any model
hfx infer budget                           # credits used/left + burst headroom (read-only)
hfx infer embed --text "hello world"       # 384-dim vector, ~$0.0000003-6 (NOT free)
```

### The PIN rule (memorize this one)

**Never send an unsuffixed chat model id.** Default router routing is `:fastest`,
which **ignores price** — unsuffixed Ling-Fin routes to deepinfra at $0.06/$0.18
(3 accidental calls cost this project 6,480 nanoUsd). `hfx infer` **refuses**
unsuffixed ids (exit 2). Pin always: `:novita`, `:nscale`, or `:cheapest`
(verified to actually pick the cheapest provider).

The catalog's only $0/$0 lanes (re-verified 2026-09-26 — exactly 3):

| Lane | Verdict |
|---|---|
| `inclusionAI/Ling-3.0-flash-Fin:novita` | **THE free lane** — settles at literally $0. Kit default. |
| `prism-ml/Ternary-Bonsai-27B-gguf:together` | ⚠️ $0.01 placeholder that reverses (~30 min); unreliable — don't build on it |
| `prism-ml/Ternary-Bonsai-27B-AWQ-4bit:together` | ⚠️ same trap |

Reasoning-model gotcha: with small `max_tokens` the free lane returns **empty
`content`** and the text lands in `reasoning_content` — `hfx infer chat` surfaces
both, auto-retries once at 3× on the free lane (default 1200 — raise it for long answers).

### Burst mechanics (why 402s happen at $0 spend)

Every router request — **including $0-lane ones** — instantly books a **$0.01
placeholder** against the $0.10/mo credit cap; a true-up job (~every minute)
replaces it with the real cost.

| Rule | Number |
|---|---|
| Placeholder per request | $0.01 (10,000,000 nanoUsd) |
| 402 condition | `usedNanoUsd + $0.01 > limitNanoUsd` ($0.10) |
| Max unsettled in flight | `floor(($0.10 − settled) / $0.01)` ≈ 10 |
| Self-heal after 402 | ~1-5 min (true-up); 402s are never billed |
| Kit pacing | 2.2 s between router calls in-process; on 402 → friendly hint, exit 3 |
| Credits reset | calendar month (Oct 1) |

`usage.estimated_cost` appears per-call on **deepinfra** responses only (matches
settled billing exactly); novita omits it — the kit prints the catalog estimate
($0 for the free lane) and you can confirm settled truth with `hfx infer budget`.

### Embeddings (NOT free — spends credits)

The router has **no `/v1/embeddings`** (live-probed → 404). Use the hf-inference
passthrough (what `hfx infer embed` does): `BAAI/bge-small-en-v1.5`, 384 dims,
**242-601 nanoUsd/call** (compute-second dependent; the kit's own live test
settled at 242) → ~166k-413k calls per $0.10.

Cheapest paid chat fallback if the promo dies: `Qwen/Qwen3-4B-Instruct-2507:nscale`
($0.01/$0.03, 262k ctx, tools+structured✅; 5M blended tokens per $0.10).

Evidence: findings/zero-cost-models.md · findings/inference-probe.md ·
findings/review-cost-catalog.md · playbooks/inference-maxxing.md ·
live test evidence: data/kit-tests/infer-token/

<!-- SECTION:gpu -->

## GPU — free ZeroGPU bursts (8 runs + 300 GPU-s per rolling 24h)

ZeroGPU gives your account **8 runs + 300 GPU-seconds per rolling 24h window**
(account-global across ALL public ZeroGPU Spaces — MCP calls, direct Gradio
calls, and web UI share the same budget). RTX Pro 6000-class GPUs, $0, no
credit card. Verified: findings/spaces-probe.md, findings/wan22-measurement.md.

```bash
hfx gpu preflight                          # quota GO/NO-GO (exit 0/3)
hfx gpu preflight --space owner/name       # + LIVE free-GPU-slot count
hfx gpu spaces                             # the MCP-enabled Space catalog
hfx gpu spaces --pattern image             # narrow it
hfx gpu run owner/name                     # LIST a Space's fns (FREE)
hfx gpu run owner/name --fn generate --arg '"a cat"' --arg 4 --arg false
hfx gpu run owner/name --fn infer --arg ./photo.png     # file auto-converts
```

**Quickstart recipe (U4-proven, copy-paste verbatim)** — one 1024² image on
the flagship ZeroGPU image Space, ~3 GPU-s, 1 run slot:

```bash
hfx gpu preflight && hfx gpu run mrfakename/Z-Image-Turbo --fn generate_image --arg '"a cat astronaut"' --arg 1024 --arg 1024 --arg 4 --arg 42 --arg false --out ./out
```

`--out ./out` receives the artifact under the Space's own filename
(`image.png`, `video.mp4`, …) **plus a `run-*.json` audit sidecar**
(quota before/after, GPU-s charged, runs consumed, wall time, output URLs —
the durable evidence trail; the run log path is printed at the end).

**The three rules that save your budget:**

1. **8 runs/24h is the BINDING limit** — light calls cost 3–5 GPU-s, so 300
   GPU-s almost never binds first. Preflight before every batch.
2. **The base64 input contract** — ZeroGPU Spaces cannot fetch remote URLs
   server-side: a URL input fails pre-GPU with a misleading "404" ($0, but a
   wasted submit). `hfx gpu run` auto-converts local media file args to
   `{"path": null, "url": "data:<mime>;base64,…", "meta":
   {"_type": "gradio.FileData"}}` — the shape verified working in
   findings/wan22-measurement.md (base64 data-URIs in `url` ALWAYS work, and
   bypass broken Space egress entirely).
3. **Outputs are session-bound** — the returned tmp URLs 403 from any later or
   foreign session, and die with the serving replica (public window closes
   somewhere between 5.5 h and 24 h). `hfx gpu run` fetches outputs in the
   same client session and copies them to `--out` immediately; treat that copy
   as the only durable one (re-host with `hfx cdn put` for sharing).

**Billing states (all measured, findings/wan22-measurement.md):**

| Outcome | GPU-s | Run slot | Notes |
|---|---|---|---|
| Pre-GPU rejection (bad URL/arg shape) | $0 | no | gradio argument-binding fails before GPU attach |
| Error inside the function | ~duration booked instantly, **~half refunded** | **YES** | runs counter LAGS — an immediate post-error quota read lies; recheck at +30 min |
| Success | exact actual usage, charged immediately | yes | no lag, no refund drift |

**Measured reference costs:** image gen (Z-Image-Turbo, steps 4, 1024²) =
**3.09 GPU-s / 14 s wall** (K5 live test, data/kit-tests/gpu-mcp/); image gen
at default steps 8 = 3.48 (MCP) / 5.38 (direct); TTS = 3.76; OCR (Tiny) =
3.39; video (Wan2.2 smallest 4-step 0.5 s) = 9.35; typical video 35–45.

**Quota GET semantics:** `/api/spaces/zero-gpu/quota` returns
`{base: 300, current: REMAINING GPU-s, runs: {used, limit, remaining}}`.
`current` is what's LEFT, not what's used (288.79 → 276.27 after 12.53 spent
— findings/mcp-dynamic-spaces.md §5). `resetsAt: null` = window inactive,
full budget. `hfx gpu run` refuses to submit (exit 3) when the budget is
exhausted, unless `--force`.

**Preflight truthiness:** the quota GET is AUTHORITATIVE. The api.hf.space
events SSE (`zero-gpu-count`, `gcTimeout`) is advisory — coverage is partial,
the count fluctuates by the second, and it can be stale at the reset boundary.
`zero-gpu-count: 0` just means your run will QUEUE (wall-clock, not quota).

**The catalog:** `hfx gpu spaces` enumerates the `mcp-server` hub tag —
**2000+ MCP-enabled Spaces (774 on ZeroGPU hardware at last count)**, not just
the 16 curated ones: video (Wan2.2, LTX), 3D (TRELLIS, Shap-E), STT
(whisper-large-v3), lip-sync, upscaling, captioning… every one scriptable via
`hfx gpu run` (direct Gradio) or `hfx mcp call dynamic_space` (see the MCP
section). The budget does NOT grow with the menu.

**Dep:** `pip install --user gradio_client` (kit tested against **2.0.3**).

**Gotchas:** anonymous headless calls are blocked (PAT Bearer always);
view_api//info/discover/view_parameters are FREE — inspect before you spend;
the fn listing annotates **duplicate endpoints** (gradio re-exports a
re-registered fn as `<base>_1`, `<base>_2`… with an identical signature —
`generate_image` vs `generate_image_1` are the same fn; prefer the base
name so you don't burn a run slot on a guess);
non-MCP Spaces (no `mcp-server` tag) are rejected by dynamic_space ("The space
MUST be an MCP enabled space") but still callable via `hfx gpu run`;
per-Space invoke quirks exist (e.g. BFL Kontext-Dev invoke 404s via MCP
despite view_parameters working — treat new Spaces as UNVERIFIED until one
successful invoke).

**Evidence:** findings/wan22-measurement.md (input contract + billing states)
· findings/mcp-arbitrary-spaces.md (arbitrary-Space verdict, preflight)
· findings/infra-probe.md §D (api.hf.space SSE) · findings/mcp-dynamic-spaces.md
(measured costs, 16 curated Spaces) · data/kit-tests/gpu-mcp/ (live K5 tests).

<!-- SECTION:mcp -->

## MCP — the hosted agent API (huggingface.co/mcp)

HuggingFace hosts an MCP server at `https://huggingface.co/mcp` — plain
JSON-RPC 2.0 over POST, PAT Bearer auth (anonymous works for 4 read-only
tools, at lower rate limits). It is the single-protocol gateway to Hub search,
the Hub filesystem, **and free media compute** (ZeroGPU Spaces). Verified:
findings/mcp-probe.md, findings/review-compute-cluster.md.

```bash
hfx mcp tools                     # initialize + tools/list (the tool table)
hfx mcp call hf_whoami            # who am I / token role (free)
hfx mcp call dynamic_space --args-json '{"operation":"discover"}'
hfx mcp call dynamic_space --args-json '{"operation":"view_parameters","space_name":"ResembleAI/Chatterbox"}'
hfx mcp call dynamic_space --args-json '{"operation":"invoke","space_name":"mcp-tools/DeepSeek-OCR-experimental","parameters":"{\"image\":\"https://…/ocr.png\",\"model_size\":\"Tiny\",\"task_type\":\"Free OCR\"}"}'
hfx mcp resources                 # 155 skill:// Agent-Skills docs
hfx mcp resources --uri skill://huggingface-zerogpu/references/how-quota-works.md
```

**The 11-tool surface** (this account, all built-ins enabled; toggle at
<https://huggingface.co/settings/mcp> — the tool set applies to new sessions
immediately):

| Tool | Free? | What it does |
|---|---|---|
| `hf_whoami` | ✅ | auth context: account, orgs, credential role |
| `hf_fs` | ✅ | Hub filesystem: ls/cat/find/search over `hf://models\|datasets\|spaces\|collections\|papers\|docs`, 30 ops/call |
| `hub_repo_search` | ✅ | search models/datasets/Spaces with filters |
| `hub_repo_details` | ✅ | repo details + dataset structure/preview |
| `dynamic_space` | ✅ metadata / ⚠ invoke | discover (16 curated Spaces) + view_parameters are FREE; **every invoke = 1 ZeroGPU run (8/24h account-global — the binding limit)**; accepts ANY `mcp-server`-tagged Space, not just the curated ones |
| `hf_fs_write` | ✅ | put/rm files in repos+buckets, `--create-pr` (needs PAT write) |
| `hf_sandbox` | ❌ 402 | sandbox CRUD — needs PREPAID credits (free $0.10 inference credit does NOT count) |
| `hf_sandbox_exec` / `hf_sandbox_fs` | ❌ | shell + files INSIDE a (paid) sandbox |
| `hf_jobs` | ❌ 402 | Jobs API incl. cron scheduling — prepaid credits only |
| `gr1_z_image_turbo_generate` | ✅ quota-metered | Z-Image-Turbo image gen (account Space tool; measured 3.48 GPU-s/run) |

**Invoke gotchas (the #1 bugs):** `parameters` must be a **JSON-encoded
STRING**, not a nested object; file inputs are public URLs (HF dataset
`resolve/` URLs verified) or base64 data-URLs; unknown kwargs are
warned-then-passed-through and rejected at argument binding BEFORE GPU attach
($0, no run); outputs arrive as content blocks — download URL outputs
IMMEDIATELY (same session-bound rules as the GPU section).

**The sandbox verdict** (why hf_sandbox is ❌): `create` → 402 Payment
Required; the underlying Jobs API wants a prepaid balance. With credits it
would be the cheapest full-Linux agent compute on HF ($0.01/h cpu-basic,
per-minute billing) — but it is not free.

**skill:// resources** — 155 Agent-Skills docs (hf-cli, zerogpu quota
mechanics, training/eval recipes, AWS SageMaker deploy skills…) readable
with `hfx mcp resources --uri skill://…`. Free goldmine for any MCP client.

**Budget note:** MCP `dynamic_space` invokes and `hfx gpu run` hit the SAME
account-global ZeroGPU budget (8 runs + 300 GPU-s / rolling 24h — see the
GPU section). `$0` in inference credits either way.

**Evidence:** findings/mcp-probe.md (handshake, tool catalog, sandbox 402s,
skill:// resources) · findings/mcp-dynamic-spaces.md (16 curated Spaces +
measured costs) · findings/mcp-arbitrary-spaces.md (arbitrary-Space verdict,
mcp-server tag enumeration) · data/kit-tests/gpu-mcp/ (live K5 tests: 11
tools, 155 resources, discover).

<!-- SECTION:etl -->

## etl — datasets as a free queryable data backend

> **You have data, no database.** Push a CSV to a public dataset repo and
> HuggingFace gives you — for $0 — a hosted REST API over it: SQL-ish WHERE +
> ORDER BY, full-text search, paginated rows, per-column statistics, and
> auto-converted parquet that DuckDB can query directly over HTTPS (yes,
> including cross-repo JOINs). Writes are git commits; reads are CDN-cached.
> Live-verified end-to-end: `data/kit-tests/etl/` (10/10 ground-truth checks).

**The flow: upload → (wait ~2–3 min) → query.**

```bash
# 1. Push data (csv/tsv/json/jsonl/parquet; creates the repo if needed)
hfx etl upload ./leads.csv                  # default repo: <you>/hf-free-maxxing-kit-etl
                                             # (namespace resolved from your token)
hfx etl upload ./leads.csv --repo myuser/leads --path data.csv

# 2. Wait for auto-parquet conversion (event-driven, ~2-3 min)
hfx etl splits myuser/leads --wait 180      # polls until READY, then probes /rows:
                                             # reports "READY but still warming" if the
                                             # query indexes aren't up yet (~+1-2 min)

# 3. Query it — server-side, no download
hfx etl filter myuser/leads --where "score>0.5 AND name LIKE '%acme%'" \
                          --orderby "score desc" --limit 100
hfx etl filter myuser/leads --where "score>0.5" --wait 300   # COLD dataset:
                          # polls every 20s until the filter index is queryable,
                          # then prints the result (exit 1 + last state on timeout)
hfx etl search myuser/leads --query "acme"          # token match, 100% recall
hfx etl rows   myuser/leads --offset 5000 --limit 100   # deep offsets OK (6.4M rows verified)
hfx etl stats  myuser/leads                          # free describe(): mean/median/std/histograms

# 4. Full SQL (GROUP BY, JOIN, window functions) — local DuckDB over the parquet URL
hfx etl parquet myuser/leads                        # prints the URLs + a copy-paste one-liner
hfx etl sql myuser/leads --query "SELECT name, count(*) n, avg(score) s \
                                  FROM data GROUP BY name ORDER BY s DESC"   # EXPERIMENTAL

# 5. Teardown — delete the whole repo (files + history + server views)
hfx etl rm myuser/leads                     # dry-run: shows what would go (exit 3)
hfx etl rm myuser/leads --yes               # DELETE /api/repos/delete + authed 404 verify
```

Works from browsers too — datasets-server CORS is `*`, so a static site can
`fetch()` your data with zero backend (pair with `hfx host`).

### Capability matrix (endpoint / syntax / limits)

| Command | Endpoint | Syntax | Limits & notes |
|---|---|---|---|
| `filter` | `/filter` | `--where "\"col\"=25"` · `"col">5` · `"col" LIKE '%x%'` · `AND`/`OR` + parens · `--orderby "\"col\" desc"` (single column, default asc) | page ≤ 100 · index = **first 5 GB** · `num_rows_total` = match count when `where` present · bare column names are auto-quoted by the kit · **`--wait SECONDS`** polls until queryable: fresh uploads 404 until processed (~2-3 min), idle datasets 500 "index is loading" — retries every 20s (each poll ≤ 30s), exit 1 with the last observed state on timeout · `--json` adds a `wait` key `{waited_s, attempts, queryable}` |
| `search` | `/search` | `--query "token"` | token match, 100% recall (7/7 verified) · first 5 GB · index builds LAZILY — can 500 for minutes on fresh/idle datasets |
| `rows` | `/rows` | `--offset N --limit ≤100` | offset-past-end → 200 + empty; length clamps at end; deep offsets fine (6.5s @ 6.4M rows) |
| `stats` | `/statistics` | — | min/max/mean/median/std/histograms per column; std is **sample** (ddof=1); text cols → length stats; labels → frequencies |
| `parquet` | `/parquet` | — | lists `refs/convert/parquet` URLs; conversion = first 5 GB (`partial:true` beyond) |
| `splits` | `/splits` (+`/size`) | `--wait SECONDS` polls until READY, then probes `/rows?length=1` | READY ≠ queryable: the probe reports "READY but still warming" while the query indexes catch up (~+1-2 min) · `/size` (rows/numBytes) lags conversion by minutes |
| `sql` | local DuckDB | `--query "SELECT ... FROM data"` | EXPERIMENTAL · full ANSI SQL incl. cross-repo JOINs · your CPU + the resolver rate bucket |
| `rm` | `DELETE /api/repos/delete` | `hfx etl rm <ns>/<repo> --yes` | teardown: whole repo + history + server views go; without `--yes` = dry-run + exit 3 · quota reclaims ~1-2 min |

DuckDB one-liner (the pattern `hfx etl parquet` prints):

```bash
python3 -c "import duckdb; print(duckdb.sql(\"SELECT * FROM 'https://huggingface.co/datasets/<you>/<repo>/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet' LIMIT 10\"))"
```

The two lanes compose: **/filter+/rows for quick lookups and app previews,
parquet+DuckDB for analytics** (GROUP BY/JOIN verified: 37-row cross-repo
JOIN in 1.29s, 420MB shard columnar-read at ~6.4MB/s).

### Limits & gotchas (all live-verified)

1. **Public data only.** Private datasets → 501 on free accounts (PRO $9/mo).
   Never upload anything sensitive — public means public.
2. **Cold start.** Idle/fresh datasets 500 with "index is loading" or "busier
   than usual" — `filter`/`search`/`rows`/`stats` now note it on stderr and
   **auto-retry once after 60s**; a second failure exits 1 with the warming
   message. Budget ~2–3 min for conversion after upload, ~5 min for the filter
   index on first-ever touch. For a hands-off wait use
   `hfx etl filter … --wait 300` (polls every 20s until queryable — the failed
   calls themselves take ~20s each, so a warming window burns few requests).
   Writes are eventually-consistent (no transactions, no instant read-after-write).
3. **Page size hard cap 100** on every endpoint (client-side enforced too).
4. **5 GB first-chunk cap** for conversion + filter/search/statistics indexes
   (`partial:true` beyond; splits named `partial-*`).
5. **One data file per repo** unless you add a `configs:` YAML — heterogeneous
   multi-file repos can FAIL conversion. Same `--path` = replace (new commit).
6. **Filename → split name**: `k6_test_data.csv` became split **test** (the
   `_test` suffix convention). Use `data.csv` (or any keyword-free name) for
   the default `train` split. Same trap for `_train`/`_validation`.
7. **No rate limit observed** on datasets-server (12-call burst, flat latency)
   — but be polite; bulk extraction = parquet download lane (resolver bucket:
   5000/5min authed, 3000 anon). Anonymous reads get the shared 120s CDN cache;
   authed reads bypass it.
8. `/filter` can't do multi-key ORDER BY (422), aggregates, JOINs, or
   projections — that's the DuckDB lane.
9. Response cache is 120s (`x-revision` header detects staleness); signed CDN
   URLs behind the parquet 302 expire ~10 min — share resolve URLs, not signed ones.

### Teardown (delete the whole dataset repo)

Test/experiment datasets are disposable — clean them up so the 100GB private /
8.7TB public pools stay honest (public repos count against the public pool):

```bash
hfx etl rm myuser/leads            # dry-run: prints what would be deleted, exit 3
hfx etl rm myuser/leads --yes      # deletes repo + history + datasets-server views,
                                   # verifies with an authed GET -> 404
hfx store ls                       # confirm your namespace is clean
```

Quota reclaims within ~1-2 min. Programmatic (non-CLI) scripts must load the
token via the kit (`import hfx; hfx.load_env()`) — ambient `HF_TOKEN` is empty
in a fresh shell.

**Evidence:** `findings/datasets-etl-final.md` (the full verified matrix) ·
`data/kit-tests/etl/` (this kit's live test: 25 calls, 10/10 ground-truth
checks, conversion latencies, 4 new gotchas in `calls.log`).

<!-- SECTION:oauth -->

## oauth — HuggingFace as a FREE OIDC identity provider

"Sign in with HF" for your side project, $0, no MAU cap (every end-user needs
an HF account). Full OIDC: discovery doc, PKCE S256 auth-code, RFC 8628 device
flow, refresh tokens, RFC 7591 **anonymous dynamic client registration** (no
dashboard!). Killer feature vs Auth0/Firebase free tiers: users can grant your
app `inference-api` — **GPU spend lands on THEIR credits, not yours**.

```bash
hfx oauth discovery          # endpoints + the 21-scope kit-verified list
hfx oauth register --name myapp --redirect-uri http://localhost:3000/callback \
    --out myapp-client.json  # RFC 7591 dynamic client (⚠️ read the warning)
hfx oauth authorize-url --client-id ID --redirect-uri http://localhost:3000/callback
    # default --scope "openid profile email" — SAME as register (email
    # included, so userinfo returns it; pass --scope to narrow)
hfx oauth token --client-id ID --code CODE --verifier VERIFIER \
    --redirect-uri http://localhost:3000/callback --out tokens.json
    # (+ --refresh-token R to refresh; --out saves chmod 600 like register)
hfx oauth device --client-id ID    # TV/CLI login: user_code + poll command
```

### PKCE auth-code flow, step by step (all kit-automated except the consent click)

1. **Register once** (`register`) → `client_id` (public client, no secret).
   ⚠️ **RFC 7591 clients are UN-DELETABLE** — no DELETE endpoint (404),
   invisible in `/settings/applications`. One per project, never per test run.
   The server force-adds `device_code` + `refresh_token` grants to every
   dynreg client.
2. **`authorize-url`** prints the S256 authorize URL **and the
   `code_verifier`** — keep it; it's needed for the exchange.
3. User opens the URL in a browser where they're logged in to HF → first time
   a one-time consent click → HF 303s to your redirect_uri with
   `?code=…&state=…` (verify state round-trips). Later grants **auto-approve**
   for the same (user, app, scope-set).
4. **`token`** exchanges code+verifier → `access_token` (`hf_oauth_…` EdDSA,
   8 h), `id_token` (RS256, **only 1 h** — don't cache past that),
   `refresh_token` (grant rotates, same sessionId). Works as Bearer on the hub
   API **and** the router.

### Device flow (CLIs, TVs, headless)

`hfx oauth device` → `user_code XXXX-XXXX` + `https://hf.co/oauth/device`
(TTL 300 s). User logs in to HF, enters the code, clicks Authorize (consent
**re-prompts every device grant**, unlike auth-code). Poll
`POST /oauth/token` with `grant_type=urn:ietf:params:oauth:grant-type:device_code`
every ≥5 s (no `interval` in the response).

### What app tokens can do (live-verified scope matrix)

`whoami-v2` (any) · `userinfo` incl. verified email (`openid profile email`) ·
`read-billing` (usage-v2 + live SSE) · `jobs` · `inference-api` (router calls,
**billed to the user**). 21 scopes total — `hfx oauth discovery` prints the
kit-verified scope list (server discovery has no `scopes_supported` field,
so the list is kit-maintained and can lag server reality).

### App integration (web-app wiring beyond the CLI)

**(a) The raw token exchange** — `POST /oauth/token` is **form-encoded**
(any language, no kit needed):

```bash
curl -s -X POST https://huggingface.co/oauth/token \
  -d grant_type=authorization_code -d client_id=$CLIENT_ID \
  -d code=$CODE -d redirect_uri=http://localhost:3000/callback \
  -d code_verifier=$VERIFIER
# → {"access_token":"hf_oauth_…","id_token":"eyJ…","refresh_token":"…",
#     "token_type":"bearer","expires_in":28800,"scope":"openid profile email"}
```

**(b) Callback-handler sketch** (Flask; extract `code`+`state`, exchange via
the kit, keep the rotated refresh token):

```python
@app.get("/callback")
def callback():
    if request.args.get("state") != session["state"]:
        return "state mismatch — reject", 401            # CSRF guard
    subprocess.run(["hfx", "oauth", "token", "--client-id", CLIENT_ID,
                    "--code", request.args["code"], "--verifier", session["verifier"],
                    "--redirect-uri", REDIRECT_URI, "--out", "tokens.json"],
                   check=True)                            # chmod-600 JSON
    tok = json.load(open("tokens.json"))
    session["refresh_token"] = tok["refresh_token"]      # ROTATES — see (e)
    return "logged in"
```

**(c) Verify the id_token (RS256) before trusting its claims** — the kit only
*decodes* claims for display, it does **not** verify signatures. In your app:
issuer must be `https://huggingface.co`; fetch the discovery doc's `jwks_uri`
(`https://huggingface.co/oauth/jwks`), match the token's `kid` header to a JWK,
and verify RS256 with any JWT lib (e.g. PyJWT:
`jwt.decode(id_token, jwt.PyJWK.from_dict(jwk), algorithms=["RS256"],
audience=CLIENT_ID)`).

**(d) Sample `GET /oauth/userinfo` fields** (Bearer access_token; build your
User model from these): `sub`, `name`, `preferred_username`, `profile`,
`picture`, `isPro`, `orgs[]` — plus `email`, `email_verified` (and `canPay`,
`billingMode`) when the `email` scope was granted.

**(e) Refresh tokens ROTATE**: every `refresh_token` grant returns a NEW
refresh_token (the old one dies; same `sessionId` continues). Persist the new
value on EVERY exchange — lose it and the user's session cannot be refreshed
(there is no revocation endpoint either, so treat refresh tokens as secrets).

**(f) When the user DENIES consent** (redirect shapes live-verified 2026-09-26
on the kit's own K7 client — deny is a normal, recoverable path, not an error
to fear):
- **Auth-code flow**: the consent page's Deny button 303s back to YOUR
  redirect_uri with
  `?error=access_denied&error_description=The+user+denied+the+request&state=<your state>`
  — `state` still round-trips, so verify it, then render a "login cancelled"
  page. There is no `code` to exchange; do not call /oauth/token.
- **Device flow**: the user lands on a "denied" page; your token poll gets
  `400 {"error":"access_denied","error_description":"Device code denied"}` —
  stop polling (RFC 8628 terminal error).
- **Retry is free**: a deny is NOT cached — send the user through
  `hfx oauth authorize-url` (or a fresh device grant) and the consent form
  shows again. Auto-approve only exists AFTER a grant, per (user, app,
  scope-set) — so a denied user simply re-runs the same login link.

**(g) Logout & disconnect** — no `/oauth/revoke` exists, so:
- Your app's logout = drop the LOCAL session + refresh token (access tokens
  live ≤ 8 h; refresh TTL undisclosed — treat both as secrets either way).
- HF-side logout is the user's browser business (`POST /logout`, the
  account-menu button; anonymous `GET /logout` is a 404). Whether it kills
  already-issued app tokens is unverified — your app's session is the
  source of truth for who is logged in.
- Full disconnect: the user revokes your app at
  <https://huggingface.co/settings/connected-applications> (per-app Revoke).
- Denied because they were in the WRONG HF account? Have them log out of HF
  in the browser, then retry the authorize URL — fresh consent under the
  right account.

Gotchas:
- **No token revocation endpoint** — a leaked refresh token is compromised
  until it expires; treat it like a password.
- Any OIDC client lib (authlib, next-auth, passport…) works with
  `issuer=https://huggingface.co`.
- Rate-limit hops count in the `pages` bucket (200/5 min) — fine for normal
  login flows, don't loop authorize pages.
- `hfx oauth register/token` print full secrets BY DESIGN (that's their job) —
  mind scrollback/logs.

Evidence: findings/oauth-idp.md (PKCE e2e, device flow, RFC 7591, scope
matrix, Auth0/Firebase comparison) · live tests: data/kit-tests/k7/
(one dynamically-registered research client: un-deletable, kept as evidence).

<!-- SECTION:registry -->

## registry — the free Docker pull-library (registry.hf.space)

Every **public Docker-SDK Space's built image** is pullable by any logged-in
user from `registry.hf.space` — a read-only mirror of Space builds. Think of
it as a free prebuilt-environment library: skip hours of Dockerfile builds by
pulling e.g. `enzostvs-deepsite` (426 MB, 9 layers) directly.

```bash
hfx registry login-cmd      # mints a 600s token + prints ready-to-run:
#   docker login registry.hf.space -u <you> -p <TOKEN>
#   docker pull registry.hf.space/enzostvs-deepsite:<tag>
hfx registry manifest enzostvs/deepsite   # tags, digest, config + layer sizes
```

`login-cmd` output (copy-paste):

```bash
docker login registry.hf.space -u <you> -p <minted-600s-token>
docker pull registry.hf.space/enzostvs-deepsite:cpu-0165c57
# prefer shell-history-safe:  docker login … --password-stdin <<< <token>
```

The token comes from the hub's Basic-auth mint endpoint
(`GET /api/registry/token?service=registry.hf.space`, **Basic** `:PAT` —
Bearer is 401, cookie silently mints an anonymous token). Your **PAT also
works directly as the docker password** (the registry realm echoes it back) —
handy for sessions longer than the token's 600 s.

Gotchas (all live-verified):
- **Read-only**: pushes 404 (`allow: GET,HEAD,OPTIONS`). You cannot host your
  own images here — for HF-built images, create a Docker Space (PRO-gated for
  young accounts; the kit's `host` module covers static instead).
- **Login mandatory even for public images** (anon → 401 everywhere).
- Image names are **hyphenated**: `owner/space` → `owner-space`. Tags look
  like `cpu-<shortsha>` (+ PR-build suffixes); `latest` usually doesn't exist
  — get one from `hfx registry manifest`.
- **Static and Gradio/ZeroGPU spaces have no images** (404 on tags/list);
  **secret-bearing Docker spaces 401** for non-authors. The 404 error carries
  a recovery hint (known-good example: `hfx registry manifest
  enzostvs/deepsite`). The real pre-flight is the Space's **sdk field**:
  `GET /api/spaces/{id}` → `.sdk == "docker"` ⇒ image exists;
  `gradio`/`static` ⇒ none. (`GET /api/spaces/{id}/registry-auth-check`
  only answers the secrets gate — `{"imageHasSecrets":false}` — and returns
  the same answer for a gradio Space that has no image at all.)
- Blob pulls 307 to 20-min presigned S3 URLs — don't cache them; images are
  ephemeral per Jobs docs ("can be lost to registry maintenance or a region
  move").
- The *containers product* (`registry.hf.co`, container repo type) is still
  dark-launched globally (flag `containers:false`, creation 403, dead DNS) —
  `login-cmd` targets the LIVE registry only.

Evidence: findings/containers-registry.md (auth matrix, pull round-trip,
availability matrix) · live tests: data/kit-tests/k7/
(login-cmd verified against `GET /v2/` ✓, deepsite manifest + static-404
negative ✓).

<!-- SECTION:token -->

## token — credentials: identity + the CI-safe disposable JWT

Two credentials, two jobs:

| Credential | What it is | Use |
|---|---|---|
| `HF_TOKEN` | PAT (role `read`/`write`) | everything everyday: hub API, router, store/host writes |
| `HF_JWT` | browser session cookie (name `token`) | web-app surfaces (billing page, uploads attribution) — **and JWT minting below** |

```bash
hfx token info            # whoami-v2: account, token role, orgs (token masked to 8 chars)
hfx token mint-jwt        # mint + decode a 1h inference-only JWT (prints the JWT — that's the point)
hfx token mint-jwt --verify    # + ONE $0-lane probe proving the router accepts it RIGHT NOW
hfx token mint-jwt --ttl-note  # + the mint-per-CI-run TTL strategy note
hfx doctor                # full credential/deps/endpoint check-up
```

### mint-jwt — THE CI-safe disposable credential

`GET /api/settings/jwt-inference-only` (auth: `Cookie: token=$HF_JWT`) mints a
**fresh JWT on every call, no visible cap**. Claims (decoded for you):
`scope: inference.serverless.write`, `sub: router.huggingface.co`,
**exp − iat = 3600 s**. Properties that make it CI-perfect:

- **Router-only**: works as `Authorization: Bearer <jwt>` on
  `https://router.huggingface.co/v1/*`; **hub writes 401** with it — a leaked
  CI JWT can run inference on your credits but cannot touch your repos.
- **1-hour TTL** (claims): expiry is fail-safe; mint a fresh one per run
  instead of storing it. Unlimited mints (verified: back-to-back calls →
  unique `jti`). Observed live (U7): the *practical* acceptance window can
  be much shorter than the claimed 3600 s (401s minutes after mint) — **mint
  fresh per CI step and re-mint on any 401**; `--verify` catches it at mint
  time (prints PASS/FAIL, exit 1 on FAIL; `--json` carries the raw token +
  decoded claims + `verify` result).
- **Format note**: use the FULL `accessToken` value including the `hf_jwt_`
  prefix — a bare JWT (header.payload.signature only) 401s.

```bash
JWT=$(hfx token mint-jwt --json | jq -r .jwt)
curl -s https://router.huggingface.co/v1/chat/completions \
  -H "Authorization: Bearer $JWT" -H 'Content-Type: application/json' \
  -d '{"model":"inclusionAI/Ling-3.0-flash-Fin:novita","messages":[{"role":"user","content":"hi"}],"max_tokens":300}'
```
(max_tokens ≥300 — the free lane is a reasoning model; tiny budgets return
empty `content` with the text in `reasoning_content`.)

Gotchas:
- Missing `HF_JWT` → exit 2 with extraction hint (devtools → Application →
  Cookies → `token`). It's optional — most commands need only `HF_TOKEN`.
- Endpoint **302s to `/security-checkup`** when HF enforces its password
  security-checkup gate → the kit prints the fix: complete
  <https://huggingface.co/security-checkup> once in a browser (existing tokens
  and minting usually keep working meanwhile).
- Per-token rate limits are **account-level** (all tokens share one bucket) —
  extra tokens are for blast-radius segregation, never quota multiplication.
- Never print full credentials in scripts; `hfx token info` masks to 8 chars
  (mint-jwt prints the JWT itself — that's its purpose, and it expires in 1h).

### doctor

`hfx doctor` checks it all and exits 1 on any FAIL: HF_TOKEN (whoami), HF_JWT
valid (mint endpoint — note this proves the MINT works; router acceptance of
minted JWTs: verify with `hfx token mint-jwt --verify`), `huggingface_hub`
version (**WARN if ≥2.0 — PIN `<2.0`, v2 has breaking changes**), boto3,
gradio_client, router reachable (+ free-lane presence), datasets-server
reachable, quota snapshot (usage/live SSE). Fix hints inline; deps one-liner:
`pip install --user "huggingface_hub<2.0" boto3 gradio_client`.

Evidence: findings/tokens-matrix.md (§7 mint, §5 rate limits) ·
findings/infra-probe.md §C · findings/webapp-endpoints.md ·
live test evidence: data/kit-tests/infer-token/

<!-- SECTION:watch -->

## watch — events: webhooks, bucket change-feed, notifications

Three event surfaces, all free:

```bash
hfx watch webhooks ls        # your webhook inventory (PAT)
hfx watch webhooks add --url https://ntfy.sh/my-topic \
    --watch <you>/my-space          # PAT, no CSRF; rm --id N to delete
hfx watch bucket <you>/my-bucket --duration 30   # live change-feed SSE
hfx watch notifications     # your notification feed (PAT; --mark-all-read)
```

### Webhooks (CRUD + replay, 1000 triggers/24h per webhook)

`add` posts `{watched: [{type, name}], url, domains}` to
`POST /api/settings/webhooks` — watch **any** repo (not just yours); type
autodetected, or force with `--type space|model|dataset|bucket`; domains
`repo,discussion`. **Payload v3** on commit-style events:

```json
{"event":{"action":"update","scope":"repo.content"},
 "repo":{"type":"space","name":"…","url":{…},"headSha":"…"},
 "webhook":{"id":"…","version":3},
 "updatedRefs":[{"ref":"refs/heads/main","oldSha":"…","newSha":"…"}]}
```

- Receiver gotcha: HF's delivery workers **cannot resolve webhook.site**
  (DNS ENOTFOUND) — use ntfy.sh (verified) or your own endpoint. Read ntfy
  deliveries: `curl https://ntfy.sh/<topic>/json?poll=1&since=15m`.
- Failed deliveries auto-retry with backoff to the CURRENT url; replay needs
  the HTML-only activity page (`/settings/webhooks/{id}/activity`, cookie) —
  `logId` from there feeds `POST …/{id}/replay/{logId}`.
- Trigger one: `POST /api/spaces/{repo}/commit/main` (NDJSON, no `eof` record).

### Bucket change-feed (SSE — stop polling /tree)

`hfx watch bucket NS/NAME` streams `GET /api/buckets/{ns}/{name}/events`:
`ready {cursor}` first (replay done), then `changes {cursor, changes:
[{path, op: add|update|delete, size?, xetHash?}]}` — batches coalesced over
~200 ms, **~6-10 s after the actual upload**. `reset` = your `--cursor` is
older than the ~15-min server buffer (re-list); `reconnect` = server
restart/20-min mark — reconnect with the last cursor. A `: ping` comment
every 30 s. (Live demo: upload via S3 `s3.hf.co/<ns>` mid-stream → the change
lands in the window.)

### Notifications

`GET /api/notifications` (PAT works; cookie fallback) →
`{notifications[], count{view,all,unread}}` — discussion events, bot threads
(e.g. parquet-converter), job status. `--mark-all-read` →
`POST /api/notifications/mark-as-read`. Per-category settings exist but are
write-only (`PATCH /api/settings/notifications`, ≥20 booleans).

Evidence: findings/infra-probe.md §B (webhook CRUD/replay/payload, ntfy
recipe) · findings/storage-probe.md §4a (bucket SSE) ·
findings/review-identity-infra-cluster.md §C7 (notifications) ·
live tests: data/kit-tests/k7/ (add→ls→rm cycle on the test space ✓,
bucket SSE with a live S3-upload change event ✓, notifications 2 unread ✓).

<!-- SECTION:social -->

## social — discussions, collections, likes (free content layer)

Thin wrappers over the community APIs — free "comments + curation + applause"
for any project living on HF repos. Discussions and collections take a PAT
(no CSRF); **likes need the web-session cookie** (`HF_JWT`).

```bash
hfx social discuss <you>/my-space            # list discussions
hfx social discuss <you>/my-space --create \
    --title "Feedback" --body "Say hi"              # → prints the URL; --rm N
hfx social collect ls                               # your collections
hfx social collect create --title "My reading list" # → slug ns/name-<id>
hfx social collect add --slug <slug> --item owner/repo --note "why"
hfx social collect rm --slug <slug>
hfx social like owner/repo        # cookie required; unlike to undo
```

### Discussions = a free comment/feedback/kanban layer

Full CRUD on any repo you can see (public, or your private ones): create,
comment, **12 reactions** (🔥 🚀 👀 ❤️ 🤗 😎 ➕ 🧠 👍 🤝 😔 🤯), plus
merge/pin/status/ignore/hide per the openapi. Bot threads (parquet-converter)
show up in notifications — a repo discussion thread is the closest thing HF
has to free hosted comments; embed it under your demo Space. Deleting via
`--rm N` works for your own discussions (verified on the kit test repo).

### Collections = free public curation/read-lists

`POST /api/collections {title, namespace, item?}` — the slug gets a
`-<id>` suffix (keep it: every follow-up call wants the FULL slug). Items:
`space|model|dataset|bucket|paper|collection` + optional ≤500-char note.
Public page at `https://huggingface.co/collections/<slug>` with upvotes —
use as a shareable reading list, changelog, or "awesome-list" for your
project. (No `/like` route on collections — 404, upvote is web-only.)

### Likes (cookie-only) — the 2026-09 drift

`POST/DELETE /api/{type}s/{repo}/like`. PAT → 401, always cookie. The POST
now additionally needs a **`{"csrf": …}` JSON body** (token scraped from the
homepage `authLight.csrfToken` — the kit does this for you) — cookie+Origin
alone 403s `CSRF token not provided`; DELETE needs no csrf. →
`{likes, isLikedByUser}`; 409 = already liked. Don't mass-like: ToS-wise
keep `blockedPastWeek=0`.

Evidence: findings/review-identity-infra-cluster.md §C1-C3 (discussions,
collections, likes/follow) · live tests: data/kit-tests/k7/
(discussion create→list→delete ✓, collection create→add→ls→delete ✓,
like→unlike with the csrf recipe ✓).

<!-- SECTION:md -->

## md — free markdown→HTML renderer

`hfx md render FILE_OR_TEXT` renders markdown through the community-blog
preview API (`POST /api/blog/preview {"content": ...}` → `{"html": ...}`) —
the same renderer the HF blog editor uses. Costs nothing (`api` bucket,
1000/5min).

```bash
hfx md render "**bold** and a list"
# → <p><strong>bold</strong> and a list</p>

hfx md render README.md            # file input
hfx md render - < notes.md         # stdin
hfx --json md render "# hi"        # {"html": "<h1 ...>...</h1>\n"}
```

| Limit | Detail |
|---|---|
| Auth | **web-session cookie only** (`HF_JWT`) — PATs get 401, anonymous gets 401; Origin/Referer headers required (the kit sends them) |
| Math | **no KaTeX** — `$E=mc^2$` passes through unrendered |
| Output | headings with anchor links, bold, inline `code`, fenced blocks (`<pre><code class="language-x">`), links (rel=nofollow), images, lists, blockquotes — wrapped in HF blog Tailwind classes |

Pairs with `hfx cdn put` (upload image → embed the returned URL) and
`hfx host deploy` (ship rendered HTML to a static Space).

Evidence: findings/blog-publish-probe.md §4 · live test: data/kit-tests/cdn-host-md/

<!-- SECTION:monitor -->

## monitor — live usage metrics + the poor-man's uptime probe

```bash
hfx monitor live --duration 15        # YOUR account dashboard stream (PAT)
hfx monitor space black-forest-labs/FLUX.1-schnell   # any public Space (anon)
hfx monitor space myuser/my-space --metrics          # per-second cpu/mem/net
```

### `monitor live` — /api/settings/metrics/live (SSE)

One stream, everything about your account: storage (used/limits + per-repo
summary), **inference spend per provider** (`providerDetails[]`: requests,
cost, duration — watch novita settle at $0.000000), jobs micro-USD, live
**rate-limit counters** (`api 67/1000`, resolvers, pages, search, media,
sensitive) and `blockedPastWeek` — the ToS-health number. `count` events are
keep-alives; `usage` events are the payload (~1 per 10 s). Org variant:
`/api/organizations/<org>/billing/usage/live`. Static snapshot: `hfx status`.

### `monitor space` — api.hf.space (anonymous, any public Space)

Two streams (public API, exactly two paths):
- **events** (default): `stage` transitions (RUNNING/BUILDING/…),
  **`zero-gpu-count`** — live available ZeroGPU slots, watched before burning
  one of your 8 runs/24h — and a full `space` runtime object: sdk+version,
  hardware flavor (e.g. `zero-a10g` = 16 vCPU/96 GB), region, ready/target
  replicas, service domains. ZeroGPU spaces emit zero-gpu-count **changes**
  (observed 0→1 in a 10 s window).
- **`--metrics`**: ~1/s `metric` events — cpu %/millicores, memory used/total,
  rx/tx bps, replica id, `gpus{}` when attached.

Static Spaces (like the kit's tjs demo): live-metrics 406s "Space is stale"
(no compute container) and events show `stage: CONFIG_ERROR /
"Static SDK is not supported"` while the **static domain itself stays READY**
— serving bypasses the compute runtime; that's healthy, not an outage.
For static Spaces the CLI footer says exactly that (and prints the static
domain + a `curl` health-check recipe) instead of the alarming
RUNNING/replicas heuristic.
Cron a 30 s window per space = free uptime monitoring for everything you
host (external pingers still needed for the URL itself).

Evidence: findings/review-stone-taxonomy.md #① (metrics/live) ·
findings/infra-probe.md §D (api.hf.space catalog, zero-gpu-count) ·
live tests: data/kit-tests/k7/ (live 2 usage events w/ provider breakdown ✓,
ZeroGPU space: RUNNING + zero-gpu-count 0→1 + full runtime ✓,
tjs static: stale/metrics negative + READY domain ✓).


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
