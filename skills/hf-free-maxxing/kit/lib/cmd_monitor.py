#!/usr/bin/env python3
"""hfx monitor — live usage metrics + per-Space observability (poor-man's probe).

  live            GET /api/settings/metrics/live (SSE, PAT) — storage +
                  inference per-provider spend, jobs, rate-limit counters,
                  blockedPastWeek.  Your account's live dashboard stream.
  space SPACE     api.hf.space events SSE (anonymous) for any public Space:
                  runtime stage, zero-gpu-count (ZeroGPU availability!),
                  hardware spec + service domains.  --metrics switches to the
                  per-second live-metrics stream (cpu/mem/net).

Usage: hfx monitor <subcommand> [--json]
"""
from __future__ import annotations

import os
import sys

# allow direct execution (python3 kit/lib/cmd_monitor.py …)
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hfx  # noqa: E402
import kitutil  # noqa: E402

API_HF_SPACE = "https://api.hf.space"


def _ts() -> str:
    return hfx.time.strftime("%H:%M:%S")


# ------------------------------------------------------------------ metrics/live

def _usage_line(ev: dict) -> str:
    s = ev.get("storage") or {}
    inf = ev.get("inference") or {}
    providers = inf.get("providerDetails") or []
    jobs = ev.get("jobs") or {}
    rl_all = ev.get("rateLimits") or {}
    rl = rl_all.get("instant") or {}
    zgpu = ev.get("zeroGpu") or {}
    return (f"[{_ts()}] storage {hfx.human_bytes(s.get('used', 0))} "
            f"(priv {hfx.human_bytes(s.get('usedPrivate', 0))}/"
            f"{hfx.human_bytes(s.get('privateStorageLimit', 0))} · pub "
            f"{hfx.human_bytes(s.get('usedPublic', 0))}) · "
            f"inference {hfx.human_usd(inf.get('usedNanoUsd'))} / "
            f"{hfx.human_usd(inf.get('limitNanoUsd'))} "
            f"({inf.get('numRequests', 0)} req, {len(providers)} providers) · "
            f"jobs {hfx.human_usd((jobs.get('usedMicroUsd') or 0) * 1000)} · "
            f"api {rl.get('api', {}).get('used', '?')}/{rl.get('api', {}).get('limit', '?')} · "
            f"blockedPastWeek {rl_all.get('blockedPastWeek', '?')}"
            + (f" · zeroGPU {zgpu.get('current', '?')}s" if zgpu else ""))


def _live(a, ctx) -> int:
    token = hfx.need_token(ctx["env"])
    url = hfx.HF + "/api/settings/metrics/live"
    hdrs = {"Authorization": f"Bearer {token}"}
    try:
        if ctx["json"]:
            events = [{"event": ev, "data": kitutil.parse_sse_json(data) or data}
                      for ev, data in kitutil.stream_sse(url, headers=hdrs,
                                                         duration_s=a.duration)]
            hfx.jprint({"duration_s": a.duration, "events": events})
            return hfx.EXIT_OK
        _print_live_stream(url, hdrs, a.duration)
    except kitutil.SSEError as e:
        hfx.die(f"metrics/live stream failed: {e} (PAT valid? `hfx status` "
                "sanity-checks it)", hfx.EXIT_FAIL)
    return hfx.EXIT_OK


def _print_live_stream(url: str, hdrs: dict, duration: float) -> None:
    """Human output for the metrics/live stream (SSEError propagates up)."""
    print(f"metrics/live — account usage stream (SSE, {duration}s window)\n" + "=" * 72)
    n = 0
    for ev, data in kitutil.stream_sse(url, headers=hdrs, duration_s=duration):
        obj = kitutil.parse_sse_json(data)
        if ev == "usage" and isinstance(obj, dict):
            n += 1
            if n == 1:
                inf = obj.get("inference") or {}
                print("  period   : "
                      f"{(inf.get('periodStart') or '?')[:10]} → "
                      f"{(inf.get('periodEnd') or '?')[:10]} "
                      "(calendar-month credits)")
                print("  top provs: " + (" · ".join(
                    f"{p.get('provider')}: {p.get('numRequests', 0)}req "
                    f"${(p.get('totalCostNanoUsd') or 0) / 1e9:.6f}"
                    for p in sorted(inf.get("providerDetails") or [],
                                    key=lambda x: -(x.get("numRequests") or 0))[:4])
                    or "none"))
                print("  " + "-" * 70)
            print("  " + _usage_line(obj))
        else:
            print(f"  [{_ts()}] {ev}: {data[:100]}")
    print("=" * 72)
    print(f"{n} usage event(s).  Same data, org variant: "
          "/api/organizations/<org>/billing/usage/live.  Static snapshot: hfx status")


# ------------------------------------------------------------------ space probe

def _space_summary(obj: dict) -> str:
    cur = ((obj.get("compute") or {}).get("current") or {})
    spec = cur.get("spec") or (obj.get("compute") or {}).get("spec") or {}
    status = (cur.get("status") or {})
    svc = ((obj.get("service") or {}).get("status") or {})
    domains = ", ".join(d.get("domain", "?") for d in svc.get("domains") or [])
    return (f"sdk {spec.get('sdk', '?')} {spec.get('sdkVersion', '')} · "
            f"hw {spec.get('hardwareFlavor', '?')} · region {spec.get('region', '?')} · "
            f"replicas {status.get('readyReplicas', '?')}/{status.get('targetReplicas', '?')} · "
            f"stage {status.get('stage', obj.get('status', '?'))}"
            + (f" · domains {domains}" if domains else ""))


def _space(a, ctx) -> int:
    owner, _, space = a.space.partition("/")
    if not owner or not space:
        hfx.die("space must be owner/name (e.g. myuser/my-space)",
                hfx.EXIT_CONFIG)
    base = f"{API_HF_SPACE}/v1/{owner}/{space}"
    if a.metrics:
        url = f"{base}/live-metrics/sse"
    else:
        url = f"{base}/sse"
    # api.hf.space is PUBLIC/anonymous — no auth header at all
    try:
        if ctx["json"]:
            collected = [{"event": ev, "data": kitutil.parse_sse_json(data) or data}
                         for ev, data in kitutil.stream_sse(url, duration_s=a.duration)]
            hfx.jprint({"space": a.space,
                        "stream": "live-metrics" if a.metrics else "events",
                        "duration_s": a.duration, "events": collected})
            return hfx.EXIT_OK
        _print_space_stream(url, a)
    except kitutil.SSEError as e:
        hfx.die(f"SSE /v1/{owner}/{space}/{'live-metrics/sse' if a.metrics else 'sse'} "
                f"failed: {e}\n(static Spaces have no compute container — "
                "live-metrics answers 'Space is stale'; use the events stream)",
                hfx.EXIT_FAIL)
    return hfx.EXIT_OK


def _print_space_stream(url: str, a) -> None:
    """Human output for an api.hf.space stream (SSEError propagates up)."""
    kind = "live-metrics (per-second cpu/mem/net)" if a.metrics else "events (stage/zero-gpu/runtime)"
    print(f"api.hf.space — {a.space} · {kind} · {a.duration}s window (anonymous)\n" + "=" * 72)
    n = 0
    last_stage = None
    static_space = False   # static SDK Spaces: CONFIG_ERROR is EXPECTED (U8 #3)
    static_domain = ""
    for ev, data in kitutil.stream_sse(url, duration_s=a.duration):
        n += 1
        obj = kitutil.parse_sse_json(data)
        if a.metrics:
            if isinstance(obj, dict) and "cpu_usage_pct" in obj:
                gpus = obj.get("gpus") or {}
                print(f"  [{_ts()}] cpu {obj.get('cpu_usage_pct', 0):.0f}% "
                      f"({obj.get('cpu_millicores', 0)}m) · mem "
                      f"{hfx.human_bytes(obj.get('memory_used_bytes', 0))}/"
                      f"{hfx.human_bytes(obj.get('memory_total_bytes', 0))} · "
                      f"net rx {hfx.human_bytes(obj.get('rx_bps', 0))}/s tx "
                      f"{hfx.human_bytes(obj.get('tx_bps', 0))}/s · replica "
                      f"{obj.get('replica', '?')}"
                      + (f" · gpus {gpus}" if gpus else ""))
            else:
                print(f"  [{_ts()}] {ev}: {data[:120]}")
        else:
            if ev == "stage":
                if data != last_stage:
                    print(f"  [{_ts()}] stage: {data}")
                    last_stage = data
            elif ev == "zero-gpu-count":
                print(f"  [{_ts()}] ⚡ zero-gpu-count (live available GPUs): {data}")
            elif ev == "space" and isinstance(obj, dict):
                print(f"  [{_ts()}] runtime: {_space_summary(obj)}")
                compute = obj.get("compute") or {}
                msg = ((compute.get("status") or {}).get("message"))
                if msg:
                    print(f"            message: {msg}")
                # static-SDK special case (U8 #3): stage CONFIG_ERROR + "Static
                # SDK is not supported" + no compute spec is HEALTHY here —
                # static serving bypasses the compute runtime entirely
                sdk = ((compute.get("spec") or {}).get("sdk")) or ""
                if sdk == "static" or "Static SDK" in str(msg or "") or \
                        (last_stage == "CONFIG_ERROR" and not compute.get("spec")):
                    static_space = True
                    doms = (((obj.get("service") or {}).get("status") or {})
                            .get("domains") or [])
                    if doms and not static_domain:
                        static_domain = "https://" + (doms[0].get("domain") or "")
            else:
                print(f"  [{_ts()}] {ev}: {data[:120]}")
    if n == 0:
        print("  (no events — static Spaces have no compute container: "
              "live-metrics answers 'Space is stale'; try the events stream)")
    print("=" * 72)
    if static_space:
        print("static Space — no compute runtime is expected; the static domain "
              "itself is the health check (curl the URL). CONFIG_ERROR above "
              "is NOT an outage.")
        if static_domain:
            print(f"  curl -s -o /dev/null -w '%{{http_code}}' {static_domain} "
                  "→ 200/302 = healthy")
    else:
        print("Poor-man's uptime probe: a RUNNING stage + ready replicas = healthy.\n"
              "ZeroGPU pre-flight: watch zero-gpu-count before burning one of your "
              "8 runs/24h (findings/infra-probe.md §D).")


# ------------------------------------------------------------------ dispatch

def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="hfx monitor",
        description="Live monitoring: account metrics/live SSE (PAT) + "
                    "api.hf.space per-Space observability (anonymous). "
                    "Evidence: findings/review-stone-taxonomy.md #①, "
                    "findings/infra-probe.md §D")
    pj = argparse.ArgumentParser(add_help=False)
    pj.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("live", parents=[pj],
                        help="stream /api/settings/metrics/live (storage, "
                             "inference per-provider, rate limits)")
    pl.add_argument("--duration", type=float, default=30.0,
                    help="seconds to stream (default: %(default)s)")
    pl.set_defaults(fn=_live)

    ps = sub.add_parser("space", parents=[pj],
                        help="watch a public Space: runtime stage, zero-gpu-count, "
                             "hardware spec (anonymous api.hf.space SSE)")
    ps.add_argument("space", help="owner/name (e.g. black-forest-labs/FLUX.1-schnell)")
    ps.add_argument("--duration", type=float, default=30.0,
                    help="seconds to stream (default: %(default)s)")
    ps.add_argument("--metrics", action="store_true",
                    help="per-second live-metrics stream instead (cpu/mem/net; "
                         "static Spaces answer 'stale')")
    ps.set_defaults(fn=_space)

    a = p.parse_args(argv)
    ctx["json"] = ctx.get("json") or a.json
    return a.fn(a, ctx)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False,
                                "env": {k: os.environ.get(k, "") for k in hfx.ENV_KEYS}}))
