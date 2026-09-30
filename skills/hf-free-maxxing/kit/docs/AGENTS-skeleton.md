# AGENTS.md — HuggingFace Free-Maxxing Kit (consumer agent onboarding)

> **You are a consumer agent (or human) who wants FREE cloud capacity for a side
> project.** This kit gives you verified, measured, working access to every free
> resource HuggingFace offers — storage, bandwidth, CDN, static hosting, GPU
> bursts, budget LLM inference, data querying, OAuth identity, a Docker pull-library
> and more — through ONE CLI: `kit/bin/hfx` (alias `hfx` below).
>
> Everything here was **live-verified and measured** (Sep 2026) by the
> hf-free-maxxing research project. **Evidence links** (findings/, playbooks/,
> RESOURCE-MAP.md) live in the parent research repo — if you received only the
> kit/ directory, treat them as provenance pointers, not required reading; every
> command and number you need is in this file or in `--help`. Nothing in this
> kit costs money or violates ToS when used as documented.
>
> **Claim labels:** ✅ = live-verified on our account · 📄 = official-docs only ·
> ⏳ = time-gated (date attached) · ⚠️ = trap/caveat. Volatile numbers
> (prices, lane lists, quotas) carry a **re-verified date** — catalogs drift;
> re-run the quoted check before relying on them.

## When to use this kit

Free storage/CDN/media at absurd scale (100 GB private + 8.7 TB public per
entity, 20-30 TB/mo egress), always-on static hosting, GPU bursts (image/video/
TTS/OCR/3D via 100+ Spaces), a small budget LLM lane, a free SQL-ish query
engine over public data, and OAuth identity. NOT for: serverless functions,
cron, databases, email, or custom domains — pair with Cloudflare/Supabase/GitHub
(see the allocation table under Capacity map). New here? Run `kit/QUICKSTART.md`
(15 min, one composed mini-project, ≤$0.001 total spend).

## hfx vs the official SDKs (when a typed SDK is the better tool)

This kit does **not** replace `@huggingface/hub` / `huggingface_hub` /
`@huggingface/inference` — those are typed, HF-maintained, and their
definitions double as a quick API doc. Audited live against `@huggingface/hub`
2.17.5, `@huggingface/inference` 4.13.30 and `huggingface_hub` 1.9.2
(2026-09-30): **14 of 16 hfx commands wrap at least one surface the SDKs do
not expose at all** — uploads-CDN, datasets-server queries, credits/budget,
catalog pricing, ZeroGPU, JWT mint, bucket change-feed, notifications, OIDC
flows, registry.hf.space, the blog renderer, metrics SSE. For everything else
the SDK is the better tool. Route per table; the last column lists the
gotchas that bite SDK users just as hard (they come from HF's server
behavior, not from any client).

**Surface:** UNIQUE = no SDK equivalent · PARTIAL = SDK covers part of it ·
PARITY = SDK fully covers it (hfx = bash convenience + the trap-guard listed).

| hfx | Surface | Typed pointer (JS · Python) | hfx adds | Gotcha that bites SDK users too |
|---|---|---|---|---|
| `store put/get/ls/rm` (repo) | PARITY | `uploadFiles`/`downloadFile`/`listFiles`/`deleteFile` · `upload_file`/`upload_folder`/`list_repo_tree`/`delete_file` | size-based path + `HF_XET_HIGH_PERFORMANCE` + measured speed table | deleting a file keeps quota in git history (Py: `permanently_delete_lfs_files()`); dedup saves wire, not quota |
| `store --bucket`/`rm-bucket`/`share` | PARTIAL | — · `create_bucket(private=True)`/`delete_bucket("ns/name")`/`list_buckets`/`list_bucket_tree` | default-safe create + private flip-verify + SigV4 presign | **`create_bucket` defaults PUBLIC** (live-verified 1.9.2) · `delete_bucket` wants the `"ns/name"` id, bare names 404 · presign must be SigV4 (`boto3 Config(signature_version="s3v4")`), SigV2 → 403 |
| `store cp-repo`/`tag` | PARITY | — · `duplicate_repo`/`create_tag` | entity flag + visibility default handling | duplicates count toward quota; SDK duplicate defaults public |
| `host deploy`/`ls`/`rm` | PARITY | `createRepo({type:"space"})`+`uploadFiles`+`listSpaces` · `create_repo`+`upload_folder`+`list_spaces` | README `sdk:`-guard, dotfile skip, rm name-safety | **uploading your own README.md without `sdk: static` front-matter breaks the static Space** — never `upload_folder` a README over it |
| `infer chat` | PARTIAL | `InferenceClient.chatCompletion({provider:"nscale"})` · `InferenceClient(model=…, provider="nscale")` | PIN enforcement (refuses unsuffixed ids), per-call cost display, pacing, $0-lane-only reasoning retry | **`provider` defaults to "auto" = price-blind routing** (the deepinfra $0.06/$0.18 trap) · every router request books a **$0.01 placeholder** — ~10 unsettled in flight → 402 "depleted" for minutes · reasoning lanes return **empty `content`** at small `max_tokens` (text lands in `reasoning_content`) |
| `infer embed` | PARTIAL | `featureExtraction` · `feature_extraction` | hf-inference passthrough choice + per-call cost | embeds REPRICED ~100× on 2026-09-28 (≈$0.000048/call) — one call + budget check before batches |
| `infer models` | UNIQUE | — (`list_inference_catalog` = inference-ENDPOINTS catalog, no prices; `getInferenceProviderMapping` = availability only) | price tables, `is_free` flags, trap-lane flags, **drift sentinel** | catalog schema itself drifts (moved to `providers[].pricing` + `is_free`, 2026-09-28) — re-parse before relying |
| `infer budget` | UNIQUE | — | credits standing + burst/placeholder math + settle semantics | — |
| `gpu preflight`/`spaces`/`run` | UNIQUE | — (`gradio_client` does direct calls; no quota/preflight anywhere) | quota semantics, run-refusal, base64 conversion, audit sidecar, MCP-Space catalog | quota `current` = REMAINING, not used · inputs must be **base64 data-URIs** (`{"path":null,"url":"data:<mime>;base64,…","meta":{"_type":"gradio.FileData"}}`) — remote URLs fail pre-GPU with a misleading 404 · duplicate fns (`fn_1`,`fn_2` = same fn) · outputs are tmp capability-URLs that die with the replica |
| `etl upload`/`rm` | PARITY | `createRepo`+`uploadFiles`+`deleteRepo` · `create_repo`+`upload_file`+`delete_repo` | flow glue + dry-run/exit-3 + 404-verify | private datasets 501 on free accounts · filename→split-name trap (`*_test.csv` becomes split `test`) |
| `etl filter`/`search`/`rows`/`stats`/`splits`/`sql` | UNIQUE | — | `--wait` index orchestration + auto-namespace | page cap 100 · 5 GB first-chunk cap · fresh datasets 500 "index is loading" for 2-15 min — poll, don't panic |
| `etl parquet` | PARTIAL | — · `list_dataset_parquet_files` | copy-paste DuckDB one-liner | signed CDN URLs behind the 302 expire ~10 min — share `resolve/` URLs |
| `token info` | PARITY | `whoAmI` · `whoami` | masking | — |
| `token mint-jwt` | UNIQUE | — | the whole JWT surface + verify probe | use the FULL `accessToken` incl. `hf_jwt_` prefix (bare JWT 401s) · mint fresh per CI step, re-mint on any 401 · endpoint 302s when the checkup gate is enforced |
| `token doctor` | UNIQUE | — | scoped mint probe (alias of `hfx doctor`) | — |
| `oauth discovery`/`register`/`authorize-url`/`token`/`device` | UNIQUE | (`oauthLoginUrl`/`oauthHandleRedirect` = browser login INTO HF — the opposite direction) | RFC 7591 dynreg + PKCE + device flow + exchange + rotation/deny semantics | dynreg clients are UN-DELETABLE (one per project) · refresh tokens ROTATE (persist every exchange) · id_token is RS256, only 1 h |
| `registry login-cmd`/`manifest` | UNIQUE | — | Basic-auth token mint + manifest read | image names are hyphenated (`owner/space` → `owner-space`) · only Docker-SDK spaces have images (`GET /api/spaces/{id}` → `.sdk=="docker"`) |
| `watch webhooks` | PARITY | — · `create_webhook`/`list_webhooks`/`update_webhook`/`delete_webhook` (JS: none) | bash convenience | HF's delivery workers cannot resolve webhook.site (DNS) — use ntfy.sh or your own endpoint · replay is HTML-page-only |
| `watch bucket`/`notifications` | UNIQUE | — | SSE change-feed + notification feed | `reset` = cursor older than the ~15-min buffer — re-list |
| `social discuss` | PARITY | — · `create_discussion`/`comment_discussion`/`get_repo_discussions` (JS: none) | bash convenience | — |
| `social collect` | PARTIAL | `createCollection`/`listCollections`/`deleteCollection` (JS **cannot add items** — not exported) · Python full CRUD `add_collection_item`/`update_collection_item`/`delete_collection_item` | bash convenience | keep the full slug incl. `-<id>` suffix — every follow-up call wants it |
| `social like`/`unlike` | unlike PARITY (`unlike` · `unlike`) | like: — in both | csrf recipe | `like` needs the web cookie **plus a `{"csrf":…}` JSON body** (PAT → 401; token scraped from the homepage) |
| `mcp tools`/`call`/`resources` | PARTIAL | any MCP client speaks to `huggingface.co/mcp` | hosted-endpoint gotchas + arg marshaling | `parameters` must be a **JSON-encoded STRING**, not a nested object · every `dynamic_space` invoke = 1 of your 8 ZeroGPU runs |
| `md render` | UNIQUE | — | cookie+Origin recipe | PATs get 401 — web-session cookie + Origin/Referer headers required |
| `monitor live`/`space` | UNIQUE | — | SSE parse + rate-limit counters + static-space stale-vs-healthy verdict | first SSE event can be a partial snapshot — wait for the last complete one |
| `status` | UNIQUE (aggregation) | `whoAmI` · `whoami` only | billing-usage SSE parse + ZeroGPU read + per-entity aggregation + fast mode | same partial-snapshot rule; `--storage-only` semantics matter in loops |
| `doctor` | UNIQUE (meta) | — | kit env + deps + **default-lane drift sentinel** | — |

**If you go SDK-native, the four rules that still apply to you** (full list in
the next section — they describe HF's server behavior, not hfx):
1. **Pin the provider** — JS `provider:"nscale"` option / Py
   `InferenceClient(provider="nscale")`. Never rely on the default: "auto"
   routes for speed and **ignores price**.
2. **Burst mechanics** — every router call books a $0.01 placeholder against
   the $0.10/mo cap; ~10 unsettled in flight → 402 for minutes. Pace loops;
   re-check with `GET /api/settings/inference-providers/usage-limits` (or
   `hfx infer budget`).
3. **`create_bucket(private=True)`** — the default is PUBLIC (verified live).
   And presign with SigV4, not SigV2.
4. **Uploads-CDN + datasets-server + ZeroGPU + JWT + OIDC + registry have no
   SDK functions** — use the raw endpoints (Raw API quick reference, §9) or hfx.

**Language-lane asymmetry** (verified 2026-09-30): Python-only in the hub SDK —
discussions, webhook CRUD, buckets, `duplicate_repo`/`create_tag`, LFS purge,
Space runtime actions (`pause_space`/`restart_space`/`set_space_sleep_time`/
`request_space_hardware`), Space variables/secrets. JS-only — nothing
load-bearing. Neither — the 12 UNIQUE surfaces above (that's what hfx is for).
Both SDKs also expose **Jobs APIs — prepaid-credits-only, out of $0 scope**
(the free $0.10 inference credit does NOT count toward Jobs/sandboxes).

## Contents
1. [TL;DR — the free stack](#tldr--the-free-stack-you-get-per-hf-account-numbers-verified-live)
2. [hfx vs the official SDKs](#hfx-vs-the-official-sdks-when-a-typed-sdk-is-the-better-tool) — when a typed SDK is the better tool
3. [Prerequisites](#prerequisites-5-minutes-once)
4. [Quick wins](#quick-wins-copy-paste--most-land-in-under-a-minute-data-queries-warm-up-for-a-few-minutes)
5. [Command reference](#command-reference) — status · store · cdn · host · infer · gpu · mcp · etl · oauth · registry · token · watch · social · md · monitor
6. [The rules that keep it free](#the-rules-that-keep-it-free-gotchas-distilled--read-once-save-hours)
7. [Capacity map & limits](#capacity-map--limits-the-full-verified-numbers)
8. [The 30-day age-gate unlock](#the-30-day-age-gate-unlock)
9. [Raw API quick reference](#raw-api-quick-reference-no-python-needed)
10. [Evidence & deeper docs](#evidence--deeper-docs)

**Shell alias (recommended):** `alias hfx='bash /path/to/kit/bin/hfx'`

## TL;DR — the free stack you get (per HF account, numbers verified live)

| Capacity | Amount | Cost | Evidence |
|---|---|---|---|
| Private storage | **100 GB** per entity (user + each org) | $0 | findings/quota-baseline.md |
| Public storage | **8.7 TB** per entity (best-effort) | $0 | findings/quota-baseline.md |
| Entity pools you control | 1 user + each org you create — every entity is its own 100 GB / 8.7 TB pool | $0 | findings/orgs-multiplication.md |
| Bandwidth / egress | 20 TB/mo (user) + 30 TB/mo per org, CloudFront | $0 | findings/orgs-probe.md |
| ZeroGPU compute | 300 GPU-sec + **8 runs** / rolling 24h | $0 | findings/spaces-probe.md |
| LLM API | $0.10/mo credits ≈ **5M tok** (cheapest pinned lane, re-verified 2026-09-28) · $0 promos appear & vanish — recheck monthly | $0 | findings/zero-cost-models.md |
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

# 4. Budget LLM call (default = cheapest pinned lane; --free searches for a
#    true $0 lane and REFUSES if none exists today)
hfx infer chat "Summarize: the quick brown fox..."
# (or: curl https://router.huggingface.co/v1/chat/completions ... model=Qwen/Qwen3-4B-Instruct-2507:nscale)

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
2. **PIN the `:provider` suffix on EVERY chat id.** Default routing is
   `:fastest`, which ignores price — unsuffixed Ling-Fin routed to deepinfra
   $0.06/$0.18 (3 accidental calls = 6,480 nU). The kit refuses unsuffixed
   ids (exit 2). Lane prices DRIFT: the Ling-Fin `:novita` $0 promo ran
   Sep 23→26 2026, then retired (a 97-token probe settled $0.01815).
   **SDK form of the same rule:** never leave provider on "auto" — JS
   `chatCompletion(…, {provider: "nscale"})`, Python
   `InferenceClient(model=…, provider="nscale")`.
   ```
   hfx infer chat "hi" --model Ling-3.0-flash-Fin        # ❌ exit 2: refused (price-blind)
   hfx infer chat "hi" --model Qwen/Qwen3-4B-Instruct-2507:nscale   # ✅ pinned, ~$0.000001
   ```
3. Failed requests are never billed. `usage.estimated_cost` appears in each
   response **on deepinfra only** (matches settled billing); other providers
   omit it — the kit prints the catalog estimate instead.
4. $0.10/mo included credits reset **calendar-month** (unused credits do NOT
   roll over — spend down before the 1st; SD3 image batches are the classic
   month-end burn).

**ZeroGPU:**
5. **8 runs / rolling 24h is the BINDING limit** (300 GPU-s is rarely the
   constraint). Account-global across ALL public ZeroGPU spaces. Raw check
   (no kit): `GET /api/spaces/zero-gpu/quota` — `current` = REMAINING GPU-s.
6. Inputs to ZeroGPU spaces must be **base64 data-URIs** (or same-repo assets);
   remote URLs fail pre-GPU with a misleading "404" (at $0 charge).
7. Outputs are **tmp capability-URLs**: fetch them in the same client session
   (gradio_client does; `--out` copies immediately). They are fetchable by
   anyone while the replica lives, then die with it (window closes between
   5.5 h and 24 h) — treat the local copy as the only durable one.
8. Errored runs still consume a run slot **with counter lag** (immediate quota
   reads lie — recheck at +30 min).

**Storage:**
9. **Public vs private bucket trap:** SDK/rclone `mkdir` creates buckets
   **PUBLIC by default** (`create_bucket` with `private=None` verified PUBLIC
   live on 1.9.2). Flip: `create_bucket(private=True)` or
   `PUT /api/buckets/{ns}/{name}/settings {"private":true}`.
   (The kit's `store` command handles this.)
10. **Repos vs buckets:** repo files (LFS/Xet) are versioned and permanent;
    bucket objects are deletable and quota-frees within ~90s. Use buckets for
    scratch/deletable, repos for durable/CDN-served.
11. Xet dedup saves **upload bandwidth** (13.7× faster re-uploads of identical
    content) but NOT quota; identical content in different repos counts twice.
    The duplicate API copies whole repos near-instantly (341 MB in 0.82 s;
    Python: `duplicate_repo`).
12. Private sharing: **presigned URLs must be SigV4** (default SigV2 presign →
    403). `hfx store share` handles this; raw boto3:
    `Config(signature_version="s3v4")`.
13. Upload path choice (measured): <10 MB → hub `upload_file`; 10MB–5GB → hub +
    `HF_XET_HIGH_PERFORMANCE=1`; huge → S3 multipart via `store put --bucket`
    (**explicit --bucket — not auto-selected**; no ceiling found — 10.2 GB
    verified at 20.2 MiB/s). `hf_transfer` is a deprecated no-op.
    ⚠️ The S3 gateway is a *path*, not extra capacity — buckets draw the same
    100 GB/8.7 TB entity pool; there is no separate S3 quota.

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
    its own pools, creation throttled to 2/rolling-24h, window anchored to the
    NEWEST creation). Don't mass-follow/mass-like. Keep `blockedPastWeek=0`
    (`hfx status` shows it; raw: `GET /api/whoami-v2` → `.policy.blockedPastWeek`,
    or the `GET /api/settings/metrics/live` SSE). Uploads-CDN files are
    permanent — never upload anything sensitive. Enforcement waves target
    storage-pattern abuse (retry loops, multi-TB dumps), not normal use.
18. **Credential-management routes are checkup-gated** (mint/delete tokens, org
    create/delete, app pages): if they 302 to `/security-checkup`, complete it
    once in a browser → ~48-72h headless window (model verified 3×, Sep 2026).
    Probe: `curl -I -H "Cookie: token=$HF_JWT" https://huggingface.co/settings/tokens`
    → 200 = window open, 302 = browser checkup needed. Everything else
    (storage, inference, Spaces, JWT mint, token *delete*) keeps working
    regardless.

---

## Capacity map & limits (the full verified numbers)

- **Storage per entity:** 100 GB private / 8.7 TB public (100 GB = 93.13 GiB;
  public is best-effort, safe envelope ≤~1 TB of real carded content per
  namespace). Max file 500 GB. Buckets share the same pool.
- **Bandwidth:** 20 TB/mo user, 30 TB/mo per org (CloudFront, no per-GB fee).
- **ZeroGPU:** 300 GPU-s + 8 runs per rolling 24h from first use; RTX Pro 6000
  class; pre-flight live GPU count via api.hf.space events SSE. In the quota
  JSON, **`current` = REMAINING GPU-s** (not used) — proven by delta probes.
- **Inference credits:** $0.10/mo included (user account only; orgs get $0);
  budget lane $0.01/$0.03 per 1M (≈5M tok/mo, re-verified 2026-09-28);
  cheapest long-tail provider: featherless-ai (currently UNPRICED in the
  catalog — verify with a tiny call). SD3-medium image ≈ $0.00007 on credits
  (~1400/mo). Embeddings REPRICED 2026-09-28: ~$0.000048/call (~2,065 per
  $0.10; was ~$0.0000003 until Sep 27 — verify before batch work).
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

### What goes where (the free stack beyond HF)

| Need | Use | Why |
|---|---|---|
| Static site / assets | **HF static Space** (this kit) | unlimited, always-on, CORS `*` |
| Serverless functions | Cloudflare Workers (100k req/day) | HF has none free |
| SQL database | Supabase (Postgres 500MB) or CF D1 | HF has none free |
| Cron / schedules | GitHub Actions (public repos) → OIDC trusted publishers → HF | HF Jobs are prepaid-only |
| Custom domain | Cloudflare Pages in front of an HF-hosted site | HF domains are PRO-only |
| LLM / GPU bursts / media gen | **HF router credits + ZeroGPU** (this kit) | nobody else gives these free |
| Bulk storage / CDN origin | **HF public repo or bucket** (this kit) | 8.7 TB/entity + 20-30 TB/mo egress |

### Entity (org) lifecycle — documented recipe, never automated

Orgs multiply every pool (see TL;DR). Creation/deletion are **web-form,
checkup-gated flows by design** — the kit will NEVER automate them (scripted
form-POST org creation is the highest-risk ToS signature; scripted
observation is fine). Recipe when you genuinely need a 2nd/3rd entity:
1. Complete `/security-checkup` in a browser if credential routes 302 (rule 18).
2. Create at https://huggingface.co/organizations/new (browser; 2 per rolling
   24h, anchored to the NEWEST creation — `x-error-message` carries the ETA).
3. Put REAL distinct content in it fast — an empty shell org is itself a mild
   risk signal; `hfx status --entity <org>` shows what's standing.
4. Deletion (round-trip verified): `DELETE /api/organizations/<org>` with
   session cookie + browser UA inside a checkup window → 200; cascades all org
   repos; name instantly reusable. Slots free on the same 2/24h clock.

## The 30-day age-gate unlock
Accounts younger than **30 days** cannot create ZeroGPU Spaces (402 on
create — verified). On day 30 the gate lifts: a free personal account may
create **2 ZeroGPU Spaces** = its own always-wakeable free GPU API endpoints
(think: media-gen gateway + LLM proxy). Day-30 playbook (all mechanics
live-verified, no account-specific tuning):
1. **Probe first — a 402 costs nothing:** `POST /api/repos/create` with
   `sdk:gradio, hardware:zero-a10g`; still 402 → wait, retry later that day.
2. **Claim BOTH slots immediately** (deletion frees a slot instantly — claim
   then iterate).
3. **Validate cheap:** one minimal preset per Space; budget 2 runs + 15-20
   GPU-s total; `hfx gpu quota` after each (counters lag on errors).
A minimal hello-world ZeroGPU Space is ~20 lines (README front-matter + gradio
+ `@spaces.GPU` decorator) — reference implementations live in the research
repo (`spaces/`). Community-blog publishing eligibility (`canCreateBlog`)
likely unlocks around the same mark (~30d + follower count; watch
`GET /api/blog` → `.canCreateBlog`).

## Raw API quick reference (no Python needed)

The kit wraps these; raw curls work anywhere (always send a token — anonymous
limits are 2× worse):

```bash
T="Authorization: Bearer $HF_TOKEN"
# who am I (account, orgs, token role)
curl -s -H "$T" https://huggingface.co/api/whoami-v2
# ALL quotas in one SSE (storage, credits, ZeroGPU, rate buckets)
curl -sN -H "$T" https://huggingface.co/api/settings/billing/usage/live | head -4
# ZeroGPU quota (current = REMAINING GPU-s; runs.remaining = runs left today)
curl -s -H "$T" https://huggingface.co/api/spaces/zero-gpu/quota
# create + delete a static Space
curl -s -X POST -H "$T" -H "Content-Type: application/json" \
  https://huggingface.co/api/repos/create \
  -d '{"type":"space","name":"my-site","sdk":"static","private":false}'
curl -s -X POST -H "$T" -H "Content-Type: application/json" \
  https://huggingface.co/api/repos/delete \
  -d '{"type":"space","organization":"<you>","name":"my-site"}'
# make a bucket private (SDK/rclone mkdir creates PUBLIC by default!)
curl -s -X PUT -H "$T" -H "Content-Type: application/json" \
  https://huggingface.co/api/buckets/<ns>/<bucket>/settings -d '{"private":true}'
# router: cheapest pinned chat + public catalog
curl -s https://router.huggingface.co/v1/models | jq '[.data[].providers[]? | select(.is_free)] | length'
curl -s -X POST https://router.huggingface.co/v1/chat/completions -H "$T" \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen3-4B-Instruct-2507:nscale","messages":[{"role":"user","content":"hi"}],"max_tokens":64}'
# datasets-server: free query engine on ANY public dataset
curl -s "https://datasets-server.huggingface.co/rows?dataset=lhoestq%2Fdemo1&config=default&split=train&offset=0&length=5"
# OIDC: discovery + a code→token exchange (PKCE flow for your own app)
curl -s https://huggingface.co/.well-known/openid-configuration
# registry.hf.space: pull-token for any public Docker Space image
curl -s -H "$T" "https://huggingface.co/api/spaces/<owner>/<space>/registry-auth-check"
```

## Evidence & deeper docs
- Master map: `RESOURCE-MAP.md` · Research findings: `findings/*.md`
- Playbooks: `playbooks/{inference,media-gen,storage,static-hosting}-maxxing.md`
- The no-stone-unturned negative matrix: `findings/review-stone-taxonomy.md`
- Research meta (how all this was verified): `.agents/SKILL.md` (project agents)
