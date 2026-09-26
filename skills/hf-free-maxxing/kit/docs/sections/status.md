### status — quotas across every entity

```bash
hfx status                 # human table: user + every org
hfx status --json          # machine-readable
hfx status --entity <you>   # one entity only
```

Reads three free endpoints (no writes, ~$0, a few seconds): per-entity
billing usage/live SSE (storage private/public used, credits) and — user only —
ZeroGPU quota (GPU-seconds + runs remaining, rolling 24h).

What to look at:

| Row | Meaning | Free ceiling |
|---|---|---|
| storage/TOTAL private | counts against the hard cap | 100 GB per entity |
| storage/TOTAL public | best-effort pool | 8.7 TB per entity (safe envelope ≤~1 TB) |
| credits | inference-providers spend | $0.10/mo included, user account only |
| ZeroGPU runs | **the binding GPU limit** | 8 per rolling 24h (300 GPU-s secondary) |

Notes:
- Each **org is a fully separate pool** (own 100 GB + 8.7 TB + 30 TB/mo
  bandwidth) — that's the multiplication finding; orgs get $0 credits and no
  ZeroGPU.
- Quota frees asynchronously after deletes: buckets ~90 s, LFS history only
  after `store rm --purge-lfs`.
- The first SSE event can be a partial snapshot — the kit waits for the last
  complete event (research gotcha #6).
- Evidence: findings/quota-baseline.md, findings/orgs-multiplication.md.
