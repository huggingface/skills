#!/usr/bin/env python3
"""hfx infer — LLM calls on the HF router, cheapest-pinned-lane-first.

Ground truth (VERIFIED live, findings/zero-cost-models.md + review-cost-catalog.md):
  * The $0-lane era ENDED 2026-09-28: the Ling-Fin:novita $0 promo retired
    (a 97-token probe settled $0.01815). Default = cheapest pinned lane
    (Qwen3-4B-Instruct-2507:nscale, $0.01/$0.03 per 1M ≈ 5M tok per $0.10).
    `--free` searches for a true is_free lane and REFUSES (exit 3) if none.
  * NEVER send unsuffixed chat ids: default routing is :fastest which IGNORES
    price (unsuffixed Ling-Fin -> deepinfra $0.06/$0.18 PAID). This command
    refuses unsuffixed ids for that reason.
  * The two other $0-listed lanes (prism-ml/Ternary-Bonsai-*:together) book a
    $0.01 placeholder that later REVERSES — $0-in-effect but unreliable.
  * Billing: every request instantly books a $0.01 placeholder; 402 iff
    usedNanoUsd + $0.01 > limitNanoUsd ($0.10/mo included credits). Max ~10
    unsettled requests in flight; true-up lands in ~1-5 min; failed requests
    are never billed. Built-in pacing: 2.2 s between router calls in-process.
  * It's a REASONING model: small max_tokens -> `content` empty and the text
    lands in `reasoning_content` (both surfaced below).

Usage:
  hfx infer chat "PROMPT" [--model M] [--free] [--max-tokens N] [--system S] [--json]
  hfx infer models [--free-only] [--pattern P] [--json]
  hfx infer budget [--json]
  hfx infer embed --text "..." [--model M] [--json]
"""
from __future__ import annotations

import math
import sys
import time

import hfx

# Lane history: a true $0/$0 lane (Ling-3.0-flash-Fin:novita) existed and
# settled $0.00 for 24 lifetime calls (verified 2026-09-23..26) but the promo
# RETIRED ~2026-09-28: a live call then settled $0.01815 for 97 tokens. The
# default is now the cheapest pinned lane. Re-check for new $0 promos monthly:
#   hfx infer models --free-only
DEFAULT_CHAT = "Qwen/Qwen3-4B-Instruct-2507:nscale"   # $0.01/$0.03 per 1M -> ~5M tok per $0.10
DEFAULT_CHAT_IN_CEILING = 0.05          # $/1M input ceiling for doctor's drift sentinel
RETIRED_FREE_LANE = "inclusionAI/Ling-3.0-flash-Fin:novita"  # now ~$0.075/$0.22 (novita)
TRAP_MATCH = "ternary-bonsai"          # together $0.01-placeholder trap
PLACEHOLDER_NANOUSD = 10_000_000       # $0.01 booked per request until true-up
DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"   # hf-inference passthrough
# Embed pricing REPRICED (drift #2, 2026-09-28): settled 48,443 nU/call on 2
# identical warm calls (was 242-601 nU Sep 23-26 — hf-inference passthrough
# got ~100x pricier). ~2,065 calls per $0.10 at the current rate.
EMBED_COST_NANOUSD = (48_443, 60_000)    # (typical, load-ceiling estimate)
PACING_S = 2.2                         # between router calls in one process

# ------------------------------------------------------------------ pacing

_last_router_ts = [0.0]


def _pace():
    """Sleep so consecutive router calls in ONE process are >= 2.2 s apart
    (placeholder-burst protection: >10 unsettled requests -> 402)."""
    if _last_router_ts[0]:
        wait = PACING_S - (time.time() - _last_router_ts[0])
        if wait > 0:
            time.sleep(wait)


def _mark():
    _last_router_ts[0] = time.time()


# ------------------------------------------------------------------ router http

def _hdr(headers: dict, name: str) -> str:
    """Case-insensitive header lookup (urllib dicts keep original casing)."""
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return ""


def router_call(method: str, path: str, *, token: str, json_body: dict | None = None,
                auth: bool = True, timeout: int = 90) -> tuple[int, dict, dict | None, bytes]:
    """One paced router call. Returns (status, headers, parsed_json_or_None, raw).
    Never raises on HTTP errors (caller decides); sleeps 2.2 s after the previous
    router call made by this process."""
    _pace()
    hdrs = {"Content-Type": "application/json"}
    if auth and token:
        hdrs["Authorization"] = f"Bearer {token}"
    body = hfx.json.dumps(json_body).encode() if json_body is not None else None
    st, hs, raw = hfx.http(method, hfx.ROUTER + path, token="",
                           headers=hdrs, body=body, timeout=timeout)
    _mark()
    try:
        parsed = hfx.json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        parsed = None
    return st, hs, parsed, raw


def _quota_refusal(st: int, hs: dict, raw: bytes) -> None:
    """402 = placeholder burst / depleted credits -> friendly exit 3."""
    if st == 402:
        msg = _hdr(hs, "x-error-message") or raw[:200].decode(errors="replace")
        print(f"hfx: 402 from router: {msg}\n"
              "     placeholder burst — wait 2-5 min or settle existing calls "
              "(true-up runs every minute; 402s are never billed).",
              file=sys.stderr)
        hfx.die("inference budget refused", hfx.EXIT_QUOTA)


# ------------------------------------------------------------------ catalog

_catalog_cache: dict | None = None


def catalog(token: str) -> list[dict]:
    """GET /v1/models — PUBLIC (no auth sent, no placeholder booked).
    Shape: {'data': [{'id', 'providers': [{'provider', 'pricing': {'input','output'}}]}]}"""
    global _catalog_cache
    if _catalog_cache is None:
        st, _, parsed, raw = router_call("GET", "/v1/models", token="", auth=False)
        if st != 200 or not parsed:
            hfx.die(f"GET /v1/models -> {st}: {raw[:200].decode(errors='replace')}",
                    hfx.EXIT_FAIL)
        _catalog_cache = parsed
    return _catalog_cache.get("data") or []


def lane_price(token: str, model: str) -> tuple[float, float, str] | None:
    """(input_usd_per_1M, output_usd_per_1M, source) for a `org/name:provider`
    (or `:cheapest`) id, from the public catalog. None = not listed."""
    if ":" not in model:
        return None
    base, _, suffix = model.rpartition(":")
    for entry in catalog(token):
        if entry.get("id") != base:
            continue
        provs = [p for p in (entry.get("providers") or []) if p.get("pricing")]
        if suffix == "cheapest":
            if not provs:
                return None
            best = min(provs, key=lambda p: float(p["pricing"].get("input") or 1e9))
            return (float(best["pricing"].get("input") or 0),
                    float(best["pricing"].get("output") or 0),
                    f":cheapest -> {best.get('provider')}")
        for p in provs:
            if p.get("provider") == suffix:
                pr = p["pricing"]
                return (float(pr.get("input") or 0), float(pr.get("output") or 0),
                        f"{base}:{suffix}")
        return None
    return None


def _est_cost(price: tuple[float, float] | None, prompt: str, system: str,
              max_tokens: int) -> float | None:
    if price is None:
        return None
    est_in = math.ceil(len((system or "") + (prompt or "")) / 4)  # ~4 chars/token
    return (est_in * price[0] + max_tokens * price[1]) / 1_000_000


# ------------------------------------------------------------------ subcommands

def _cmd_chat(a, ctx: dict) -> int:
    token = hfx.need_token(ctx["env"])
    if a.free and a.model:
        hfx.die("--free and --model are mutually exclusive (use one)", hfx.EXIT_CONFIG)
    if a.free:
        # search-then-REFUSE: never silently fall through to a paid lane
        found = _find_free_lane("")
        if not found:
            hfx.die("no true $0 lane in today's catalog (the Ling-Fin:novita $0 promo "
                    "retired ~2026-09-28; the Ternary-Bonsai \"$0\" lanes are billing "
                    "traps). Cheapest pinned lane: " + DEFAULT_CHAT +
                    " ($0.01/$0.03 per 1M = ~5M tok per $0.10/mo). "
                    "Re-check monthly: hfx infer models --free-only",
                    hfx.EXIT_QUOTA)
        model = found
    else:
        model = a.model or DEFAULT_CHAT

    # SAFETY: never send unsuffixed chat ids (default routing = :fastest, price-blind)
    if ":" not in model:
        hfx.die(f"refusing unsuffixed chat id '{model}': default routing is :fastest "
                "which IGNORES price (unsuffixed Ling-Fin -> deepinfra $0.06/$0.18). "
                "Pin a provider: '<model>:novita', '<model>:nscale', or ':cheapest'.",
                hfx.EXIT_CONFIG)
    if model.endswith(":fastest"):
        print("hfx: warning: :fastest ignores price — prefer a pinned provider "
              "(e.g. the default " + DEFAULT_CHAT + ").", file=sys.stderr)

    price = lane_price(token, model)
    est = _est_cost(price, a.prompt, a.system or "", a.max_tokens)
    is_free = price is not None and price[0] == 0.0 and price[1] == 0.0
    # preamble goes to STDERR so --json stdout stays parseable (D1 P1 fix)
    if price is not None:
        tag = ("free lane — settles at $0" if is_free
               else f"${price[0]:g}/${price[1]:g} per 1M in·out (catalog)")
        print(f"model  : {model}  ({tag})", file=sys.stderr)
        if TRAP_MATCH in model.lower():
            print("hfx: warning: Ternary-Bonsai:together books a $0.01 placeholder "
                  "that reverses (~30 min) — unreliable, don't build on it.",
                  file=sys.stderr)
    else:
        print(f"model  : {model}  (pricing NOT in catalog — unknown cost; "
              f"check `hfx infer models --pattern {model.split(':')[0]}`)",
              file=sys.stderr)
    if est is not None:
        if est > 0:
            print(f"hfx: this call costs ~${est:.8f} (against $0.10/mo included credits)",
                  file=sys.stderr)
        else:
            print("cost   : ~$0.000000 (free lane — placeholders still consumed)",
                  file=sys.stderr)

    messages = []
    if a.system:
        messages.append({"role": "system", "content": a.system})
    messages.append({"role": "user", "content": a.prompt})
    st, hs, resp, raw = router_call("POST", "/v1/chat/completions", token=token,
                                    json_body={"model": model, "messages": messages,
                                               "max_tokens": a.max_tokens})
    _quota_refusal(st, hs, raw)
    if st != 200 or not resp:
        hfx.die(f"chat/completions -> {st}: {raw[:300].decode(errors='replace')}",
                hfx.EXIT_FAIL)

    msg = ((resp.get("choices") or [{}])[0].get("message") or {})
    content = msg.get("content") or ""
    finish = (resp.get("choices") or [{}])[0].get("finish_reason")
    # auto-retry once on empty content (reasoning model ate the budget) — only
    # on the FREE lane so a retry never costs money (U3 fix)
    if not content and is_free and finish == "length":
        bigger = min(a.max_tokens * 3, 4096)
        print(f"hfx: empty reply (reasoning ate the budget) — auto-retrying "
              f"with max_tokens={bigger}", file=sys.stderr)
        st, hs, resp, raw = router_call("POST", "/v1/chat/completions", token=token,
                                        json_body={"model": model, "messages": messages,
                                                   "max_tokens": bigger})
        _quota_refusal(st, hs, raw)
        if st == 200 and resp:
            msg = ((resp.get("choices") or [{}])[0].get("message") or {})
            content = msg.get("content") or ""
            finish = (resp.get("choices") or [{}])[0].get("finish_reason")
            a.max_tokens = bigger
        # non-200 on retry: fall through with the original response
    reasoning = msg.get("reasoning_content") or ""
    usage = resp.get("usage") or {}
    provider = _hdr(hs, "x-inference-provider") or "?"
    est_cost_reported = usage.get("estimated_cost")
    if ctx["json"]:
        out = {"model": model, "provider": provider, "content": content,
               "reasoning_content": reasoning,
               "finish_reason": finish,
               "usage": usage, "estimated_cost_reported": est_cost_reported,
               "estimated_cost_catalog": est}
        hfx.jprint(out)
        return hfx.EXIT_OK

    print(f"served : {provider} (x-inference-provider)\n")
    if content:
        print(content)
    else:
        print("(empty content — reasoning model ate the token budget; "
              "raise --max-tokens for a full answer)")
    if reasoning:
        shown = reasoning if len(reasoning) <= 600 else reasoning[:600] + " …[truncated]"
        print(f"\n--- reasoning_content ---\n{shown}")
    u_bits = [f"{usage.get('prompt_tokens', '?')} in + "
              f"{usage.get('completion_tokens', '?')} out tokens"]
    if est_cost_reported is not None:
        u_bits.append(f"estimated_cost ${est_cost_reported} (reported by provider)")
    else:
        u_bits.append("estimated_cost: not reported by this provider — "
                      + (f"catalog estimate ~${est:.8f}" if est is not None
                         else "no catalog price"))
    print(f"\nusage  : " + " · ".join(u_bits))
    if is_free:
        print("budget : $0 lane settles at $0 — but each call still books a $0.01 "
              "placeholder (≤10 unsettled in flight; settled truth in ~2-5 min).")
    else:
        print("budget : paid lane — $0.10/mo included credits, calendar-month reset. "
              "Check standing: hfx infer budget")
    return hfx.EXIT_OK


def _find_free_lane(pattern: str = "") -> str | None:
    """True `is_free` (or $0/$0) lane from the public catalog, or None.
    Trap lanes (Ternary-Bonsai:together list $0/$0 but bill flat $0.01 that
    reverses) are excluded — `is_free` in the new catalog schema is the
    authoritative signal."""
    for entry in catalog(""):
        mid = entry.get("id", "")
        if pattern and pattern.lower() not in mid.lower():
            continue
        for p in (entry.get("providers") or []):
            pr = p.get("pricing") or {}
            pin, pout = pr.get("input"), pr.get("output")
            if pin is None or pout is None:
                continue
            zero = float(pin) == 0 and float(pout) == 0
            if (p.get("is_free") or zero) and TRAP_MATCH not in mid.lower():
                return f"{mid}:{p.get('provider')}"
    return None


def _cmd_models(a, ctx: dict) -> int:
    token = ""  # /v1/models is public; no auth, no placeholder booked
    data = catalog(token)
    lanes = []
    for entry in data:
        mid = entry.get("id", "")
        if a.pattern and a.pattern.lower() not in mid.lower():
            continue
        for p in (entry.get("providers") or []):
            pr = p.get("pricing")
            if not pr:
                continue
            pin, pout = float(pr.get("input") or 0), float(pr.get("output") or 0)
            true_free = bool(p.get("is_free")) or (pin == 0 and pout == 0)
            if a.free_only and not true_free:
                continue
            lanes.append({"id": f"{mid}:{p.get('provider')}", "input": pin,
                          "output": pout, "is_free": true_free})
    lanes.sort(key=lambda l: (l["input"], l["output"], l["id"]))

    if ctx["json"]:
        hfx.jprint({"lanes": lanes, "count": len(lanes),
                    "models_in_catalog": len(data)})
        return hfx.EXIT_OK

    print(f"hfx infer models — {len(data)} models / {len(lanes)} matching lanes "
          f"(prices USD per 1M tokens: in / out; public catalog, no auth needed)")
    unpriced = sum(1 for e in data for p in (e.get("providers") or [])
                   if not p.get("pricing"))
    if unpriced:
        print(f"  ({unpriced} unpriced provider lanes omitted — unknown cost; "
              "e.g. featherless-ai lanes are currently unpriced: treat as "
              "pay-per-use and verify with one tiny call + `hfx infer budget`)")
    for lane in lanes:
        flags = ""
        if lane["id"] == DEFAULT_CHAT:
            flags = "  ✓ KIT DEFAULT (cheapest pinned lane)"
        elif lane.get("is_free") and TRAP_MATCH not in lane["id"].lower():
            flags = "  ✓ true $0 lane (verify with 1 tiny call before trusting)"
        if TRAP_MATCH in lane["id"].lower():
            flags = "  ⚠️ TRAP: $0.01 placeholder that reverses; unreliable — do NOT call"
        print(f"  {lane['id']:<58} ${lane['input']:>6.3f} / ${lane['output']:>6.3f}{flags}")
    if a.free_only:
        traps = [l for l in lanes if TRAP_MATCH in l["id"].lower()]
        true_free = [l for l in lanes if l.get("is_free") and TRAP_MATCH not in l["id"].lower()]
        if true_free:
            print(f"\n{len(true_free)} true $0 lane(s) listed. $0 promos appear and "
                  "VANISH — verify with ONE tiny call (max_tokens 8) + `hfx infer "
                  "budget` after 3 min before building on it.")
        else:
            print("\nno true $0 lanes in today's catalog (the Ling-Fin:novita $0 promo "
                  f"retired ~2026-09-28{'; ' + str(len(traps)) + ' trap lane(s) listed above — do NOT call' if traps else ''}). "
                  "Budget lane: " + DEFAULT_CHAT + " ($0.01/$0.03 per 1M ≈ 5M tok "
                  "per $0.10/mo). Re-check monthly — promos return.")
    print("\nNext: hfx infer chat \"hi\" (default " + DEFAULT_CHAT + ") | hfx infer budget")
    return hfx.EXIT_OK


def _cmd_budget(a, ctx: dict) -> int:
    token = hfx.need_token(ctx["env"])
    ev = hfx.sse_first_full_event("/api/settings/billing/usage/live", token=token)
    inf = ev.get("inference") or {}
    used, limit = inf.get("usedNanoUsd") or 0, inf.get("limitNanoUsd") or 0
    included = inf.get("includedNanoUsd") or 0
    remaining = max(0, limit - used)
    burst_slots = int(remaining // PLACEHOLDER_NANOUSD)
    provs = inf.get("providerDetails") or []

    if ctx["json"]:
        hfx.jprint({
            "used_nano_usd": used, "limit_nano_usd": limit,
            "included_nano_usd": included, "remaining_nano_usd": remaining,
            "max_unsettled_requests": burst_slots,
            "num_requests": inf.get("numRequests"),
            "period": {"start": inf.get("periodStart"), "end": inf.get("periodEnd")},
            "provider_details": provs,
        })
        return hfx.EXIT_OK

    print("hfx infer budget — inference credits (user account; orgs get $0)\n" + "=" * 64)
    print(f"  used        {hfx.human_usd(used):>12}   ({used:,} nanoUsd settled+placeholders)")
    print(f"  limit       {hfx.human_usd(limit):>12}   (monthly included credits)")
    print(f"  included    {hfx.human_usd(included):>12}")
    print(f"  remaining   {hfx.human_usd(remaining):>12}   "
          f"(resets calendar-month: {inf.get('periodEnd', '?')[:10]})")
    if provs:
        print("\n  per provider (settled truth lands ~2-5 min after each call):")
        for p in provs:
            print(f"    {p.get('provider', '?'):<16} {p.get('numRequests', '?'):>4} reqs · "
                  f"{hfx.human_usd(p.get('totalCostNanoUsd', 0))} settled")
    print(f"\n  burst rule: every request books a ${PLACEHOLDER_NANOUSD / 1e9:.2f} "
          f"placeholder -> 402 iff used+$0.01 > limit.\n"
          f"  Max unsettled in flight NOW: {burst_slots}. Pace rapid calls "
          f"(kit paces {PACING_S}s between router calls); on 402 wait 2-5 min.")
    return hfx.EXIT_OK


def _cmd_embed(a, ctx: dict) -> int:
    token = hfx.need_token(ctx["env"])
    model = a.model or DEFAULT_EMBED_MODEL
    # NOTE: the router has NO /v1/embeddings (live-probe 404, data/kit-tests/
    # infer-token/probe-embeddings-endpoint.json) — embeddings ride the
    # hf-inference passthrough instead (findings/inference-probe.md §4).
    print(f"model  : {model} (hf-inference passthrough — embeddings are NOT free)")
    print(f"cost   : ~${EMBED_COST_NANOUSD[0] / 1e9:.7f}–${EMBED_COST_NANOUSD[1] / 1e9:.7f} "
          f"per call (measured range, input-length dependent)")

    st, hs, parsed, raw = router_call(
        "POST", f"/hf-inference/models/{model}", token=token,
        json_body={"inputs": a.text, "options": {"wait_for_model": True}})
    _quota_refusal(st, hs, raw)
    if st != 200:
        hfx.die(f"embeddings -> {st}: {raw[:300].decode(errors='replace')}",
                hfx.EXIT_FAIL)
    vec = parsed if isinstance(parsed, list) else (parsed or {}).get("embeddings")
    if not vec or not isinstance(vec, list):
        hfx.die(f"unexpected embedding response: {hfx.json.dumps(parsed)[:200]}",
                hfx.EXIT_FAIL)
    if ctx["json"]:
        hfx.jprint({"model": model, "dim": len(vec), "first3": vec[:3],
                    "measured_cost_range_nano_usd": list(EMBED_COST_NANOUSD)})
        return hfx.EXIT_OK
    print(f"dim    : {len(vec)}")
    print(f"first3 : {[round(v, 6) for v in vec[:3]]}")
    print("settled: lands at ~242-601 nanoUsd in billing within ~2-5 min "
          "(hf-inference reports no estimated_cost) — verify: hfx infer budget")
    print("budget : embeddings spend real credits ($0.10/mo) — ~166k-413k calls/mo.")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ entry

def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="hfx infer",
        description="LLM calls via the HF router — cheapest pinned lane by default "
                    "(≈5M tok per $0.10/mo), burst-safe, cost-aware. "
                    "Docs: kit/docs/sections/infer.md")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("chat", help="one chat completion (DEFAULT = cheapest pinned "
                                     f"lane {DEFAULT_CHAT}; --free searches for a true "
                                     "$0 lane and REFUSES if none exists)")
    pc.add_argument("prompt", help="user prompt text")
    pc.add_argument("--model", help=f"model id WITH :provider suffix (default: {DEFAULT_CHAT})")
    pc.add_argument("--free", action="store_true",
                    help="use a true $0 lane if one exists today (exits 3 if none — "
                         "never falls back to a paid lane)")
    pc.add_argument("--max-tokens", type=int, default=1200,
                    help="max completion tokens (default 1200; on empty replies from "
                         "reasoning models the kit auto-retries once at 3x, but only "
                         "on true $0 lanes so a retry never costs money)")
    pc.add_argument("--system", help="optional system prompt")
    pc.add_argument("--json", action="store_true", help="machine-readable output")

    pm = sub.add_parser("models", help="list router catalog lanes + prices (public, free)")
    pm.add_argument("--free-only", action="store_true",
                    help="only true $0 lanes (providers[].is_free or $0/$0 pricing; "
                         "trap lanes flagged, never recommended)")
    pm.add_argument("--pattern", help="case-insensitive substring filter on model id")
    pm.add_argument("--json", action="store_true", help="machine-readable output")

    pb = sub.add_parser("budget", help="inference credits standing + burst headroom "
                                       "(read-only SSE)")
    pb.add_argument("--json", action="store_true", help="machine-readable output")

    pe = sub.add_parser("embed", help=f"embeddings via hf-inference passthrough "
                                      f"(default {DEFAULT_EMBED_MODEL}; NOT free)")
    pe.add_argument("--text", required=True, help="text to embed")
    pe.add_argument("--model", help=f"embedding model (default {DEFAULT_EMBED_MODEL})")
    pe.add_argument("--json", action="store_true", help="machine-readable output")

    a = p.parse_args(argv)
    if a.json:
        ctx["json"] = True

    if a.cmd == "chat":
        return _cmd_chat(a, ctx)
    if a.cmd == "models":
        return _cmd_models(a, ctx)
    if a.cmd == "budget":
        return _cmd_budget(a, ctx)
    if a.cmd == "embed":
        return _cmd_embed(a, ctx)
    p.error(f"unknown subcommand {a.cmd}")


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False, "env": {}}))
