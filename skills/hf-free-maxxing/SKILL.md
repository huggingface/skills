---
name: hf-free-maxxing
description: "Every Hugging Face free-tier capability, live-verified: 100 GB private + 8.7 TB public storage per entity, $0.10/mo inference credits with cheapest-lane pinning, ZeroGPU bursts (8 runs/24h), unlimited static hosting, quota-free media CDN, hosted dataset queries, OIDC identity, Docker pulls, webhooks. Use when the user wants free cloud storage, free static hosting or a free CDN, free GPU compute or image/video generation, cheap or free LLM API calls, or asks what the Hugging Face free tier includes, how far $0 goes, or how to avoid paying for AI infrastructure."
license: Apache-2.0
---

# HF Free-Maxxing — the verified $0 operating manual

What Hugging Face actually gives a free account, measured live (Sep–Oct 2026),
with the traps that cost money or hours if learned the hard way. Everything
here is actionable with the **official `hf` CLI, the official SDKs
(`huggingface_hub` / `@huggingface/hub` / `@huggingface/inference`), or plain
curl** — no custom tooling required.

## The free stack (per HF account, verified live)

| Capacity | Amount | Cost |
|---|---|---|
| Private storage | **100 GB** per entity (user + each org) | $0 |
| Public storage | **8.7 TB** per entity (best-effort) | $0 |
| Bandwidth / egress | 20 TB/mo (user) + 30 TB/mo per org, CloudFront-backed | $0 |
| ZeroGPU compute | 300 GPU-sec + **8 runs** per rolling 24h | $0 |
| LLM API | **$0.10/mo credits** ≈ 5M tokens on the cheapest pinned lane (Qwen3-4B:nscale, $0.01/$0.03 per 1M) | $0 |
| Static hosting | unlimited static Spaces, always-on, no cold start | $0 |
| Media CDN upload | `POST /uploads` — outside BOTH storage+bandwidth quotas, permanent | $0 |
| Data query engine | datasets-server filter/search/sort/stats + DuckDB SQL over auto-parquet | $0 |
| Identity provider | OIDC/OAuth2 (PKCE + device flow + RFC 7591 dynreg), no MAU cap | $0 |
| Docker registry | pull any public Docker Space image (registry.hf.space) | $0 |
| Webhooks / events | CRUD + replay + bucket change-feed SSE (1,000 triggers/24h each) | $0 |
| Social/content | discussions, collections, likes, markdown renderer | $0 |

**Orgs multiply pools**: each org is a fully separate 100 GB / 8.7 TB / 30 TB
entity (creation throttled to 2 per rolling 24h). Two or three real-project
orgs is the safe zone; org farming violates ToS.

**Not free** (route elsewhere — Cloudflare/Supabase/Netlify): dynamic compute
and serverless functions, cron schedulers, databases, transactional email,
custom domains, Jobs and sandboxes (prepaid wallet only — the $0.10 credits do
NOT count toward them), private dataset viewer (501), EU regions, Dev Mode
SSH, `app_build_command` static builds (credits-gated — they brick a static
Space).

## Setup (once, official tools only)

1. PAT at <https://huggingface.co/settings/tokens> — `read` for everything
   read-only, `write` for uploads/creation. `export HF_TOKEN=hf_...`
   (official SDKs and `hf` CLI pick it up automatically).
2. Official clients:
   ```bash
   pip install "huggingface_hub>=1.9,<2.0" gradio_client   # pin v1.x — v2 breaks APIs; + boto3 if you'll presign bucket URLs
   # JS/TS: @huggingface/hub + @huggingface/inference (typed; definitions double as API docs)
   ```
3. Optional `HF_JWT` (browser session cookie, from an authenticated tab)
   unlocks a few web-only surfaces: uploads-CDN attribution, markdown
   renderer, JWT mint. PATs do NOT work on those — cookie auth only.

## Quick wins (curl, official tools)

```bash
T="Authorization: Bearer $HF_TOKEN"

# 0. Where do I stand? (ALL quotas in one SSE: storage, credits, ZeroGPU, rate buckets)
#    The Accept header is REQUIRED — plain curl gets a JSON error back
curl -sN -H "$T" -H "Accept: text/event-stream" https://huggingface.co/api/settings/billing/usage/live | head -4

# 1. Durable file storage + public CDN URL (official CLI; or SDK upload_file)
hf upload <you>/my-files ./mymodel.bin --repo-type dataset
# → https://huggingface.co/datasets/<you>/my-files/resolve/main/mymodel.bin

# 2. Instant media hosting OUTSIDE all quotas (permanent! cookie or anonymous; PAT ignored)
curl -s -X POST -H "Cookie: token=$HF_JWT" -H "Content-Type: image/png" \
  --data-binary @./photo.png https://huggingface.co/uploads
# → https://cdn-uploads.huggingface.co/production/uploads/<id>/<key>.png

# 3. Free static site (create + upload; ALWAYS include sdk: static in README)
curl -s -X POST -H "$T" -H "Content-Type: application/json" \
  https://huggingface.co/api/repos/create \
  -d '{"type":"space","name":"my-site","sdk":"static","private":false}'
hf upload <you>/my-site ./site/ --repo-type space
# → https://<you>-my-site.static.hf.space (always-on)

# 4. Budget LLM call — provider PINNED (see rule 1)
curl -s -X POST https://router.huggingface.co/v1/chat/completions -H "$T" \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen3-4B-Instruct-2507:nscale","messages":[{"role":"user","content":"hi"}],"max_tokens":64}'
# SDK: InferenceClient(model="Qwen/Qwen3-4B-Instruct-2507", provider="nscale")  # Python pins in constructor
# SDK: await client.chatCompletion({...}, {provider: "nscale"})                  # JS option per call

# 5. Free GPU burst — preflight first (8 runs/24h is the binding limit)
curl -s -H "$T" https://huggingface.co/api/spaces/zero-gpu/quota
# then call any public ZeroGPU Space via gradio_client (Python) — inputs as base64 data-URIs (rule 4)

# 6. Query data without a database (any public dataset; ~2-3 min warm-up after upload)
curl -s "https://datasets-server.huggingface.co/rows?dataset=lhoestq%2Fdemo1&config=default&split=train&offset=0&length=5"
curl -s "https://datasets-server.huggingface.co/filter?dataset=lhoestq%2Fdemo1&config=default&split=train&where=%22star%22%3D5&limit=10"
# columns must be double-quoted in `where`/`orderby` (server SQL dialect: "col"=5, "col" desc)
```

## The rules that keep it free (all live-verified)

1. **PIN the provider on every inference call.** Never send an unsuffixed
   model id to the router: default routing (`auto`/`fastest`) is **price-blind**
   and lands on paid providers (an unsuffixed call once routed to a
   $0.06/$0.18 lane). Pin the suffix in the id
   (`"model": "...:nscale"`) or the SDK option
   (`provider: "nscale"`). Cheapest verified lane Sep 2026:
   `Qwen/Qwen3-4B-Instruct-2507:nscale` at $0.01/$0.03 per 1M tokens
   (≈5M tokens per monthly $0.10). Lane prices DRIFT — re-check the public
   catalog (`GET https://router.huggingface.co/v1/models`, prices under
   `providers[].pricing`) before long batches.
2. **Placeholder-billing burst mechanics.** EVERY router request books a
   $0.01 placeholder against the $0.10/mo cap; ~10 unsettled requests in
   flight → 402 "depleted" for 1–5 minutes until true-up. Failed requests
   are never billed. Pace loops; check standing with
   `GET /api/settings/billing/usage/live` (SSE — send `Accept: text/event-stream`, read
   `inference.usedNanoUsd`; the first event can be a partial snapshot — use
   the full one).
3. **Credits reset on the calendar month and DO NOT roll over** (verified
   live 2026-10-01: period rolled Sep→Oct, used reset to 0, $0.10 refilled,
   September's unspent balance vanished). Spend down before the 1st. Free
   plan `canPay=false`: no overage possible; the cap is hard.
4. **ZeroGPU: 8 runs / rolling 24h is the BINDING limit** (300 GPU-s rarely
   binds first). Account-global across ALL public ZeroGPU Spaces;
   headless calls need a PAT (anonymous is blocked). Preflight with
   `GET /api/spaces/zero-gpu/quota` — `current` = REMAINING GPU-seconds,
   not used. **Inputs must be base64 data-URIs**
   (`{"path": null, "url": "data:<mime>;base64,...", "meta":
   {"_type": "gradio.FileData"}}`) — remote URLs fail pre-GPU with a
   misleading "404".
5. **ZeroGPU outputs are tmp capability-URLs** — fetch them before the
   serving replica recycles (window 5.5–24 h). The local copy is the only
   durable one; anyone can fetch the URL while the replica lives.
6. **Storage is per-entity**: 100 GB private / 8.7 TB public (user + each
   org separately), max file 500 GB. Repo deletions keep quota in git
   history until LFS purge (Python SDK: `permanently_delete_lfs_files()`);
   bucket deletes free quota in ≤90 s. Dedup saves bandwidth, NOT quota.
7. **`create_bucket()` defaults to PUBLIC** (verified live on
   huggingface_hub 1.9.2 — the `private=True` param is easy to miss). Pass
   it explicitly, or flip after the fact:
   `PUT /api/buckets/{ns}/{name}/settings {"private":true}`.
   `delete_bucket` wants the full `"ns/name"` id (bare names 404).
8. **Presigned bucket share URLs must be SigV4** — default SigV2 presign
   gets 403. boto3: `Config(signature_version="s3v4")`.
9. **Uploads-CDN (`POST /uploads`) is PERMANENT** — no delete endpoint
   exists. Never upload anything sensitive. Magic-byte allowlist
   (images/video/audio only). PATs are ignored: web-session cookie
   (user-scoped URL) or anonymous (unattributed), raw body with the file's
   MIME type — not multipart.
10. **Static Spaces**: exact file paths only (no clean URLs/SPA fallback —
    use a hash router); CORS wide open; variables are injected into served
    HTML and are PUBLIC (secrets are write-only vaults). **Never upload a
    README.md without `sdk: static` front-matter** — it breaks the Space
    (the SDK's `space_sdk="static"` sets it on create; an overwrite clobbers it).
11. **Datasets as a backend**: public data only (private → 501 on free
    accounts); ~2–3 min conversion after upload (then a lazy index warms —
    expect "index is loading" for 2–15 min, poll, don't panic); page size
    cap 100; 5 GB first-chunk cap; filenames map to splits
    (`*_test.csv` → split `test`). DuckDB reads the auto-parquet URLs for
    full SQL incl. cross-repo JOINs (the signed parquet URLs behind the
    302 expire ~10 min — share `resolve/` URLs instead).
12. **Rate limits per 5-min window**: api 1000 · resolvers 5000 · pages 200
    · media 10000 · search 300 · sensitive 50 (anonymous = 2× worse).
    Parse `x-error-message` headers — they carry precise retry ETAs.
13. **Credentials**: `HF_TOKEN` (PAT) for everything everyday; web-session
    cookie for web-only surfaces. CI-safe router JWT:
    `GET /api/settings/jwt-inference-only` (cookie auth) → 1 h token,
    unlimited mints, inference-only blast radius — use the FULL
    `hf_jwt_`-prefixed `accessToken` and re-mint on any 401.
    OAuth RFC-7591 dynamic clients are **UN-DELETABLE** — register one per
    project, not per test. HF may enforce a security-checkup risk gate:
    credential pages start 302-ing to `/security-checkup` until a human
    completes it once in a browser (headless automation trips the score;
    the gate is selective — repo operations keep working).
14. **Anti-abuse posture**: keep `blockedPastWeek: 0` (check
    `GET /api/whoami-v2` → `.policy.blockedPastWeek`). Enforcement targets
    storage-pattern abuse and multi-accounting (suspension wave confirmed
    2026) — normal use and multi-org are the safe pattern. Don't farm orgs,
    don't mass-follow/mass-like.

## Routing: official SDK or raw endpoint?

The official SDKs are typed and HF-maintained — prefer them for repo/file
CRUD, listings, whoami, collections (Python does full CRUD incl. adding
items; JS cannot), discussions and webhook CRUD (Python), Space runtime ops
(pause/restart/sleep-time/hardware — Python), and raw inference calls.
Verified absent from BOTH SDKs (raw endpoints only): uploads-CDN,
datasets-server queries (except `list_dataset_parquet_files`), credits/budget
SSE, catalog pricing, ZeroGPU quota, JWT mint, bucket change-feed,
notifications, OIDC dynreg/device flows, registry.hf.space, the blog
markdown renderer, metrics SSE.

Python-only in the hub SDK: discussions, webhook CRUD, buckets,
`duplicate_repo`/`create_tag`, LFS purge, Space runtime actions, Space
variables/secrets. Language asymmetry verified 2026-09-30.

## Drift watch (re-check monthly)

- **Promo lanes appear and vanish**: a $0 lane (`Ling-3.0-flash-Fin:novita`)
  ran Sep 23–26 2026, then retired — a post-retirement probe settled
  $0.01815. Before trusting any "$0" claim, run one tiny call and read the
  settled `usedNanoUsd`. Placeholder "$0.01" entries that never settle
  (together.ai Ternary lanes) are traps, not deals — the placeholder
  reverses after ~30 min but burns burst headroom while it sits.
- **Pricing schema drifts**: the catalog moved to `providers[].pricing` +
  `is_free` flags (2026-09-28); embeddings repriced ~100× the same day.
  Re-parse before relying.
- **Endpoints retire silently**: `/api/settings/inference-providers/usage-limits`
  404s since ~Sep 2026 — billing truth is `GET /api/settings/billing/usage/live`.
- **Feature gates flip**: containers repo-type appeared then vanished from
  the creation schema (Oct 2026: not even a valid discriminator); ZeroGPU
  hosting unlocks at account age 30 days; blog publishing has an
  age/follower gate (`GET /api/blog` → `.canCreateBlog`).

## Provenance

Every number, endpoint, and trap above was live-verified Sep–Oct 2026 by the
hf-free-maxxing research project (probe transcripts and raw evidence:
<https://huggingface.co/landogayatri/hf-free-maxxing>). Numbers move in real
time — the quota SSE (`/api/settings/billing/usage/live`) and
`/api/spaces/zero-gpu/quota` are always the source of truth for current
state.
