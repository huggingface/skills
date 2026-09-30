## infer — LLM calls via the router (cheapest pinned lane + $0.10/mo credits)

> **SDK parity:** chat/embed = PARTIAL (both InferenceClients) · models/budget = UNIQUE (no SDK pricing/credits surface) — [hfx vs the official SDKs](#hfx-vs-the-official-sdks-when-a-typed-sdk-is-the-better-tool).

The kit's chat default is the **cheapest pinned lane**:
`Qwen/Qwen3-4B-Instruct-2507:nscale` — $0.01/$0.03 per 1M tokens (≈ **5M blended
tokens per $0.10/mo**), 262k ctx, tools+structured-output✅. Everything runs through
`https://router.huggingface.co/v1` (OpenAI-compatible) with your `HF_TOKEN`.

> **Drift log (the lane story — promotions die):** a true $0/$0 lane
> (`inclusionAI/Ling-3.0-flash-Fin:novita`) existed 2026-09-23→26 and settled
> $0.00 across 24 lifetime calls; the promo **retired ~2026-09-28** — a live
> probe then settled **$0.01815 for 97 tokens** (also: not proportional per-1M
> billing on that lane; ~5 such calls would exhaust a fresh $0.10). $0 promos
> may return — re-check monthly with `hfx infer models --free-only` (30 s, free).

```bash
hfx infer chat "Summarize: ..."            # default lane, prints content + cost + budget note
hfx infer chat "hi" --max-tokens 300       # budget answers in ~64-300 tokens
hfx infer chat "hi" --free                 # searches for a TRUE $0 lane; REFUSES (exit 3) if none today
hfx infer models --free-only               # true $0 lanes (is_free flag); trap lanes flagged, never called
hfx infer models --pattern llama           # price-scan any model (public, free)
hfx infer budget                           # credits used/left + burst headroom (read-only)
hfx infer embed --text "hello world"       # 384-dim vector, ~$0.0000003-6 (NOT free)
```

### The PIN rule (memorize this one)

**Never send an unsuffixed chat model id.** Default router routing is `:fastest`,
which **ignores price** — unsuffixed Ling-Fin routes to deepinfra at $0.06/$0.18
(3 accidental calls cost this project 6,480 nanoUsd). `hfx infer` **refuses**
unsuffixed ids (exit 2). Pin always: `:nscale`, `:novita`, or `:cheapest`
(picks the lowest input price — non-deterministic under drift; prefer an
explicit pin in scripts).

### The budget lane table (prices re-verified 2026-09-28)

| Lane | $/1M in·out | per $0.10/mo | Notes |
|---|---|---|---|
| `Qwen/Qwen3-4B-Instruct-2507:nscale` | $0.01/$0.03 | **≈5M blended tok** | Kit default; tools✅; 262k ctx |
| `Qwen/Qwen2.5-Coder-3B-Instruct:nscale` | $0.01/$0.03 | ≈5M | code tasks |
| `meta-llama/Llama-3.1-8B-Instruct:deepinfra` | $0.02/$0.05 | ≈2.9M | |
| `gpt-oss-120b:novita` | $0.05/$0.25 | ≈667k | cheapest 120B big-brain |
| `inclusionAI/Ling-3.0-flash-Fin:novita` | ~$0.075/$0.22 | ≈190k | ex-$0 promo lane (retired 2026-09-28); reasoning model — needs `max_tokens ≥512` or content comes back empty |
| featherless-ai long tail | **unpriced** (pricing:null, 2026-09-28) | unknown | ~76 lanes currently — the catalog omits them from price scans; treat as pay-per-use, verify with 1 tiny call + `hfx infer budget` (historically ~$0.039/$0.108 per 1M) |
| `prism-ml/Ternary-Bonsai-*:together` | "$0/$0" | **TRAP** | books $0.01 flat that reverses (~30 min); unreliable — the kit flags and never recommends it |

Reasoning-model gotcha (Ling-Fin and other reasoning lanes): with small
`max_tokens` the reply returns **empty `content`** and the text lands in
`reasoning_content` — `hfx infer chat` surfaces both and auto-retries once at
3× **only on true $0 lanes** (a retry on a paid lane would double cost).

### Burst mechanics (why 402s happen at low spend)

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
| Credits reset | **calendar month** (unused credits do NOT roll over — spend down before the 1st) |

`usage.estimated_cost` appears per-call on **deepinfra** responses only (matches
settled billing exactly); other providers omit it — the kit prints the catalog
estimate and you can confirm settled truth with `hfx infer budget` (read the SSE
≥2 min after a burst for settled numbers).

### Embeddings (NOT free — spends credits; REPRICED 2026-09-28)

The router has **no `/v1/embeddings`** (live-probed → 404). Use the hf-inference
passthrough (what `hfx infer embed` does): `BAAI/bge-small-en-v1.5`, 384 dims.
⚠️ **Drift #2 (2026-09-28): settled 48,443 nanoUsd/call** on 2 identical warm
calls — ~100× the 242-601 nU measured Sep 23-26 (the hf-inference passthrough
repriced). At the current rate: **~2,065 calls per $0.10**. Verify with one
call + `hfx infer budget` before batch work — embed pricing has already moved
once.

Evidence: findings/zero-cost-models.md · findings/inference-probe.md ·
findings/review-cost-catalog.md · playbooks/inference-maxxing.md ·
live test evidence: data/kit-tests/infer-token/ ·
drift event: data/zero-models/ (catalog snapshots) — retirement documented in
findings/zero-cost-models.md §8 (2026-09-28)
