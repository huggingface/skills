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
<!-- /SECTION:gpu -->
