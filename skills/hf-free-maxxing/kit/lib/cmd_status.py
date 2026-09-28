#!/usr/bin/env python3
"""hfx status — quota picture across EVERY entity (user + orgs).

Free $0 read-only endpoints:
  user: GET /api/settings/billing/usage/live (SSE)
  org:  GET /api/organizations/<org>/billing/usage/live (SSE)
  user: GET /api/spaces/zero-gpu/quota  (GPU-seconds + runs)

Usage: hfx status [--entity NAME]... [--storage-only] [--json]

--storage-only (fast mode): storage/S3/bucket standing only — skips the
ZeroGPU quota call and the credits read, and reads each entity's usage SSE
with a short window (first complete event lands ~instantly; the stream stays
open server-side, so the default 8s window is pure wait time). Same numbers
as full status for every storage row.
"""
from __future__ import annotations

import sys

import hfx

STORAGE_SSE_FAST_S = 3.0  # --storage-only SSE window per entity (vs 8.0);
# if the fast window catches no complete event, one patient retry at 8s


def _usage_event(ent: dict, token: str, fast: bool) -> dict:
    """Read one entity's usage/live SSE. fast=True (--storage-only): short
    window first, patient retry on a miss — the SSE stream stays open, so the
    default window spends ~8s/entity waiting for a second event that rarely
    changes anything."""
    path = hfx.entity_usage_path(ent)
    if fast:
        try:
            return hfx.sse_first_full_event(path, token=token,
                                            wait_s=STORAGE_SSE_FAST_S)
        except SystemExit:  # hfx.die on an empty fast window — retry patient
            return hfx.sse_first_full_event(path, token=token)
    return hfx.sse_first_full_event(path, token=token)


def _storage_rows(ev: dict) -> list[tuple[str, str, str]]:
    """SSE shape (verified 2026-09-26): storage = {used, usedPrivate, usedPublic,
    privateStorageLimit, publicStorageLimit, summary:{<type>:{used,usedPrivate,
    usedPublic,count}}}."""
    s = ev.get("storage") or {}
    rows = [("TOTAL",
             hfx.human_bytes(s.get("used", 0)),
             f"private {hfx.human_bytes(s.get('usedPrivate', 0))}/"
             f"{hfx.human_bytes(s.get('privateStorageLimit', 0))} · "
             f"public {hfx.human_bytes(s.get('usedPublic', 0))}/"
             f"{hfx.human_bytes(s.get('publicStorageLimit', 0))}")]
    for repo_type, nums in sorted((s.get("summary") or {}).items()):
        unit = "buckets" if repo_type == "bucket" else "repos"
        rows.append((repo_type,
                     hfx.human_bytes(nums.get("used", 0)),
                     f"priv {hfx.human_bytes(nums.get('usedPrivate', 0))} · "
                     f"pub {hfx.human_bytes(nums.get('usedPublic', 0))} · "
                     f"{nums.get('count', '?')} {unit}"))
    return rows


def _gpu_rows(q: dict) -> list[tuple[str, str]]:
    runs = q.get("runs") or {}
    base = q.get("base") or 0
    cur = q.get("current")  # = REMAINING GPU-s (K5-proven 2026-09-26)
    used_s = max(base - (cur or 0), 0.0)
    return [
        ("ZeroGPU GPU-seconds", f"{used_s:.1f} used of {base} · {cur} left "
                                f"(rolling 24h from first use)"),
        ("ZeroGPU runs", f"{runs.get('used', '?')} used / {runs.get('limit', '?')} limit "
                         f"({runs.get('remaining', '?')} left)"),
    ]


def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="hfx status",
                                description="quotas across user + every org")
    p.add_argument("--entity", action="append",
                   help="restrict to entity name (repeatable); default: all")
    p.add_argument("--storage-only", action="store_true",
                   help="fast mode: report storage/S3/bucket standing only — "
                        "skips the ZeroGPU quota call and credits read, short "
                        "SSE window (roughly 2-3x faster; same storage numbers)")
    a = p.parse_args(argv)

    token = hfx.need_token(ctx["env"])
    ents = hfx.entities(token)
    if a.entity:
        keep = set(a.entity)
        ents = [e for e in ents if e["name"] in keep] or ents

    report = {"entities": [], "generated": hfx.time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                             hfx.time.gmtime())}
    totals = {"private_used": 0, "public_used": 0}

    for ent in ents:
        ev = _usage_event(ent, token, fast=a.storage_only)
        item = {"name": ent["name"], "kind": ent["kind"],
                "storage": ev.get("storage") or {}}
        if not a.storage_only:  # full mode: credits (+ ZeroGPU for the user)
            inf = (ev.get("inference") or {})
            used_nu = inf.get("usedNanoUsd") or 0
            limit_nu = inf.get("limitNanoUsd") or 0
            included_nu = inf.get("includedNanoUsd") or 0
            item["inference_credits"] = {
                "used": hfx.human_usd(used_nu),
                "limit": hfx.human_usd(limit_nu) if limit_nu else "n/a(org)",
                "included": hfx.human_usd(included_nu) if included_nu else "0 (orgs: none)",
            }
        s = item["storage"]
        totals["private_used"] += s.get("usedPrivate") or 0
        totals["public_used"] += s.get("usedPublic") or 0
        if not a.storage_only and ent["kind"] == "user":
            q = hfx.zero_gpu_quota(token)
            item["zero_gpu"] = q
        report["entities"].append(item)

    # ---- human output
    if not ctx["json"]:
        mode = " (storage-only)" if a.storage_only else ""
        print(f"hfx status{mode} — {len(ents)} entities "
              f"({', '.join(e['name'] for e in ents)})\n" + "=" * 72)
        for item in report["entities"]:
            print(f"\n[{item['kind']}] {item['name']}")
            for rt, used, limit in _storage_rows({"storage": item["storage"]}):
                print(f"  storage/{rt:<10} {used:>12} used / {limit}")
            if not a.storage_only:
                ic = item["inference_credits"]
                print(f"  credits        {ic['used']} used / {ic['limit']} "
                      f"(included {ic['included']}) [incl. UNSETTLED $0.01 placeholders — "
                      "settled truth: hfx infer budget]")
                if "zero_gpu" in item:
                    for label, val in _gpu_rows(item["zero_gpu"]):
                        print(f"  {label:<14} {val}")
        if a.storage_only:
            print("\n(storage-only: skipped ZeroGPU + credits for speed — "
                  "full picture: hfx status)")
        print("\nBOTTOM LINE: each org adds its OWN 100GB private + 8.7TB public "
              "pool + 30TB/mo bandwidth.\n"
              "Next: hfx store --help | hfx gpu preflight --help | kit/AGENTS.md")
    else:
        hfx.jprint(report)
    return hfx.EXIT_OK


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False, "env": {}}))
