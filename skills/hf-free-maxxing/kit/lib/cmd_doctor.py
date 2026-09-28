#!/usr/bin/env python3
"""hfx doctor — environment check: credentials, deps, endpoints, quotas.

Checks (PASS / WARN / FAIL — exit 1 on any FAIL):
  1. HF_TOKEN valid      — whoami-v2
  2. HF_JWT present/valid— optional cookie; probed via the jwt-inference-only mint
                           (302 -> security-checkup gate = WARN with browser hint).
                           NOTE: this proves the MINT works, not that the router
                           accepts the minted JWT — `hfx token mint-jwt --verify`
                           does that (one $0-lane probe).
  3. huggingface_hub     — WARN if >=2.0.0 ("PIN <2.0" — v2 httpx2 rewrite breaks
                           the kit; tested against 1.9.x), FAIL if missing
  4. boto3               — S3 storage-bucket paths (hfx store)
  5. gradio_client       — ZeroGPU space calls (hfx gpu)
  6. router reachable    — GET /v1/models (+ free-lane presence check)
  7. datasets-server     — GET /splits on a stable demo dataset (no auth, no limit)
  8. quota snapshot      — usage/live SSE must yield storage + inference numbers

Usage: hfx doctor [--json]
"""
from __future__ import annotations

import json
import sys
import time

import hfx

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
DEMO_DATASET = "lhoestq/demo1"       # HF's own tiny demo dataset (stable, public)
# Drift sentinel: the kit's default chat lane + a price ceiling. The $0
# Ling-Fin promo retired ~2026-09-28; the default is now the cheapest pinned
# lane. If it disappears or its price rises above the ceiling, WARN with an
# actionable hint (catalog lanes DO drift — that is the check's purpose).
DEFAULT_CHAT = "Qwen/Qwen3-4B-Instruct-2507:nscale"
DEFAULT_CHAT_IN_CEILING = 0.05          # USD per 1M input tokens
HUB_PIN = "huggingface_hub<2.0"
DEP_LINE = f"pip install --user \"{HUB_PIN}\" boto3 gradio_client"


def _hdr(headers: dict, name: str) -> str:
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return ""


def _sse_snapshot(token: str) -> tuple[bool, dict | str]:
    """Tolerant read of usage/live SSE (never dies): (ok, event_or_error).
    Retries once — the stream can stall right after connect (observed live)."""
    last_err = "no complete event"
    for _attempt in (1, 2):
        req = hfx.urllib.request.Request(
            hfx.HF + "/api/settings/billing/usage/live",
            headers={"User-Agent": hfx.UA, "Authorization": f"Bearer {token}",
                     "Accept": "text/event-stream"})
        best, deadline = {}, time.time() + 10
        try:
            with hfx.urllib.request.urlopen(req, timeout=25) as resp:
                buf = b""
                while time.time() < deadline:
                    chunk = resp.readline()
                    if not chunk:
                        break
                    buf += chunk
                    if buf.endswith((b"\n\n", b"\r\n\r\n")):
                        for line in buf.decode(errors="replace").splitlines():
                            if line.startswith("data:"):
                                try:
                                    obj = json.loads(line[5:].strip())
                                except ValueError:
                                    continue
                                if isinstance(obj, dict) and "storage" in obj:
                                    best = obj
                        buf = b""
        except Exception as e:  # noqa: BLE001 — report, don't crash
            last_err = str(e)
        if best:
            return True, best
        time.sleep(2)
    return False, last_err


def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="hfx doctor",
        description="check credentials, python deps, endpoints and quota access "
                    "— prints a PASS/FAIL table with fix hints.")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    a = p.parse_args(argv)
    if a.json:
        ctx["json"] = True

    env = ctx["env"]
    results: list[tuple[str, str, str]] = []  # (check, verdict, detail)

    def add(check, verdict, detail):
        results.append((check, verdict, detail))

    # 1 — HF_TOKEN
    token = env.get("HF_TOKEN") or hfx.os.environ.get("HF_TOKEN", "")
    if not token:
        add("HF_TOKEN set", FAIL,
            "export HF_TOKEN=… — create one at https://huggingface.co/settings/tokens "
            "(role: read for GETs, write for store/host)")
        who = None
    else:
        st, _, raw = hfx.http("GET", hfx.HF + "/api/whoami-v2", token=token)
        if st == 200:
            who = json.loads(raw)
            role = ((who.get("auth") or {}).get("accessToken") or {}).get("role", "?")
            add("HF_TOKEN valid (whoami)", PASS,
                f"{who.get('name', '?')} (token role: {role})")
        else:
            who = None
            add("HF_TOKEN valid (whoami)", FAIL,
                f"whoami-v2 -> {st} — token invalid/expired; recreate at "
                "https://huggingface.co/settings/tokens")

    # 2 — HF_JWT (optional)
    jwt_cookie = env.get("HF_JWT") or hfx.os.environ.get("HF_JWT", "")
    if not jwt_cookie:
        add("HF_JWT (optional cookie)", WARN,
            "not set — fine for most commands; needed for `hfx token mint-jwt` and "
            "the billing page. Extract the `token` cookie from a logged-in browser "
            "session, export HF_JWT=…")
    else:
        st, hs, _ = hfx.http("GET", hfx.HF + "/api/settings/jwt-inference-only",
                             cookie=f"token={jwt_cookie}", allow_redirects=False)
        if st == 200:
            add("HF_JWT valid (mint endpoint)", PASS,
                "session cookie works (mint endpoint 200); router acceptance of "
                "minted JWTs: verify with `hfx token mint-jwt --verify`")
        elif st in (301, 302, 303, 307, 308) and \
                "security-checkup" in _hdr(hs, "location"):
            add("HF_JWT valid (mint endpoint)", WARN,
                "security-checkup gate active on credential pages — complete it once "
                f"in a browser: https://huggingface.co/security-checkup "
                "(existing tokens + mint usually keep working)")
        else:
            add("HF_JWT valid (mint endpoint)", FAIL,
                f"mint endpoint -> {st} — cookie stale/invalid; re-extract the "
                "`token` cookie from a fresh browser session")

    # 3-5 — python deps
    try:
        import huggingface_hub
        ver = huggingface_hub.__version__
        if tuple(int(x) for x in ver.split(".")[:2]) >= (2, 0):
            add("huggingface_hub version", WARN,
                f"{ver} installed — PIN <2.0 (v2 breaking: httpx2 rewrite; kit tested "
                f"on 1.9.x). Fix: pip install --user \"{HUB_PIN}\"")
        else:
            add("huggingface_hub version", PASS, f"{ver} (<2.0 as required)")
    except ImportError:
        add("huggingface_hub version", FAIL, f"missing — install: {DEP_LINE}")
    except (ValueError, AttributeError):
        add("huggingface_hub version", WARN, "installed, version unparsable")
    for imp in ("boto3", "gradio_client"):
        try:
            __import__(imp)
            add(imp, PASS, "importable")
        except ImportError:
            add(imp, FAIL, f"missing — install: {DEP_LINE}")

    # 6 — router reachable (+ default-lane drift sentinel). NOTE: `or 1` would
    # treat a REAL $0 price as missing (falsy-zero trap) — compare against None
    # explicitly.
    st, _, raw = hfx.http("GET", hfx.ROUTER + "/v1/models", timeout=20)
    if st == 200:
        try:
            data = json.loads(raw).get("data") or []
        except ValueError:
            data = []
        base, _, suffix = DEFAULT_CHAT.rpartition(":")
        dflt_price = None
        for entry in data:
            if entry.get("id") != base:
                continue
            for prov in (entry.get("providers") or []):
                if prov.get("provider") == suffix:
                    pr = prov.get("pricing") or {}
                    pin = pr.get("input")
                    dflt_price = None if pin is None else float(pin)
        if dflt_price is not None and dflt_price <= DEFAULT_CHAT_IN_CEILING:
            detail = (f"/v1/models 200 ({len(data)} models; default lane "
                      f"{DEFAULT_CHAT} @ ${dflt_price:g}/1M in — OK)")
            add("router reachable", PASS, detail)
        elif dflt_price is not None:
            add("router reachable", WARN,
                f"/v1/models 200 ({len(data)} models) — default lane {DEFAULT_CHAT} "
                f"now ${dflt_price:g}/1M in (> ${DEFAULT_CHAT_IN_CEILING:g} ceiling): "
                "catalog drifted; pick a new pin: hfx infer models --pattern " + base)
        else:
            add("router reachable", WARN,
                f"/v1/models 200 ({len(data)} models) — default lane {DEFAULT_CHAT} "
                "NOT in catalog (retired/renamed); pick a new pin: "
                "hfx infer models --pattern " + base)
    else:
        add("router reachable", FAIL,
            f"GET /v1/models -> {st} — check network / https://status.huggingface.co")

    # 7 — datasets-server reachable
    st, _, _ = hfx.http("GET", "https://datasets-server.huggingface.co/splits?dataset="
                       + DEMO_DATASET.replace("/", "%2F"), timeout=20)
    if st == 200:
        add("datasets-server reachable", PASS,
            f"/splits on {DEMO_DATASET} -> 200 (no auth, no observed rate limit)")
    else:
        add("datasets-server reachable", FAIL,
            f"/splits on {DEMO_DATASET} -> {st} — hfx etl will fail; check "
            "network / status page")

    # 8 — quota snapshot
    if token and who:
        ok, ev = _sse_snapshot(token)
        if ok:
            inf = ev.get("inference") or {}
            add("quota snapshot (usage/live SSE)", PASS,
                f"storage {hfx.human_bytes((ev.get('storage') or {}).get('used', 0))} used · "
                f"inference credits {hfx.human_usd(inf.get('usedNanoUsd', 0))}/"
                f"{hfx.human_usd(inf.get('limitNanoUsd', 0))} used")
        else:
            add("quota snapshot (usage/live SSE)", FAIL,
                f"no complete SSE event in 2 tries — hfx status may fail: {ev}")
    else:
        add("quota snapshot (usage/live SSE)", FAIL,
            "skipped — needs a valid HF_TOKEN (failed above)")

    # ---- report
    fails = [r for r in results if r[1] == FAIL]
    warns = [r for r in results if r[1] == WARN]
    if ctx["json"]:
        hfx.jprint({"checks": [{"check": c, "result": v, "detail": d}
                               for c, v, d in results],
                    "pass": len(results) - len(fails) - len(warns),
                    "warn": len(warns), "fail": len(fails),
                    "exit_code": hfx.EXIT_FAIL if fails else hfx.EXIT_OK})
        return hfx.EXIT_FAIL if fails else hfx.EXIT_OK

    print("hfx doctor — environment check\n" + "=" * 72)
    for check, verdict, detail in results:
        mark = {"PASS": "✓ PASS", "WARN": "! WARN", "FAIL": "✗ FAIL"}[verdict]
        print(f"  {mark}  {check:<28} {detail}")
    print("-" * 72)
    if fails:
        print(f"  {len(fails)} FAIL, {len(warns)} WARN — fix the FAIL hints above, "
              "then rerun `hfx doctor`.")
        print(f"  Deps one-liner: {DEP_LINE}")
        return hfx.EXIT_FAIL
    if warns:
        print(f"  All checks PASS ({len(warns)} warn — optional/read the hints).")
    else:
        print("  All checks PASS — you're fully set up. Start: hfx status")
    return hfx.EXIT_OK


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False, "env": {}}))
