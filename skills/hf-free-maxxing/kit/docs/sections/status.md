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
