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
