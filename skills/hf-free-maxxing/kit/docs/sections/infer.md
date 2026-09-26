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
