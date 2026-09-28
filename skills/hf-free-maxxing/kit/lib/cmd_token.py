#!/usr/bin/env python3
"""hfx token — credentials: who you are, and the disposable CI JWT.

Two surfaces:
  * HF_TOKEN (PAT)  — the everyday credential (whoami / repos / router).
  * HF_JWT          — the browser session cookie (named `token`), needed ONLY
    for web-app surfaces. Its superpower: GET /api/settings/jwt-inference-only
    mints a fresh 1-hour INFERENCE-ONLY JWT per call, no visible cap — hub
    writes 401 with it, so it's THE CI-safe disposable credential
    (findings/tokens-matrix.md §7, findings/infra-probe.md §C).

Usage:
  hfx token mint-jwt [--ttl-note] [--verify] [--json]
  hfx token info [--json]
  hfx doctor                  (alias — full environment check)
"""
from __future__ import annotations

import base64
import json
import sys
import time

import hfx

MINT_PATH = "/api/settings/jwt-inference-only"
SECURITY_CHECKUP_URL = "https://huggingface.co/security-checkup"
# probe lane for --verify: cheapest pinned lane (the $0 Ling-Fin promo retired
# ~2026-09-28 — same history as cmd_infer). max_tokens 5 ≈ $0.0000005/call.
PROBE_LANE = "Qwen/Qwen3-4B-Instruct-2507:nscale"


def mask(tok: str) -> str:
    """Never print full credentials — first 8 chars only."""
    return (tok[:8] + "…") if len(tok) > 8 else tok


# ------------------------------------------------------------------ jwt helpers

def jwt_payload(jwt_str: str) -> dict:
    """Decode the middle base64url segment (no signature verification)."""
    try:
        part = jwt_str.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except (IndexError, ValueError, TypeError) as e:
        return {"_decode_error": str(e)}


def _fmt_ts(epoch) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime(int(epoch)))
    except (TypeError, ValueError):
        return "?"


def _router_probe(jwt: str) -> dict:
    """ONE cheap-lane chat probe (max_tokens 5, ≈$0.0000005) proving the minted
    JWT is accepted by the router RIGHT NOW. Rationale (U7 F1/F2): minted JWTs
    claim a 1h TTL but have been observed 401ing minutes after mint — this
    probe catches the failure at mint time instead of mid-CI-run."""
    payload = json.dumps({"model": PROBE_LANE,
                          "messages": [{"role": "user", "content": "Say READY"}],
                          "max_tokens": 5}).encode()
    st, _, raw = hfx.http("POST", hfx.ROUTER + "/v1/chat/completions",
                          token=jwt, body=payload, timeout=30,
                          headers={"Content-Type": "application/json"})
    out: dict = {"http_status": st, "pass": st == 200, "model": PROBE_LANE}
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            msg = ((obj.get("choices") or [{}])[0].get("message")) or {}
            reply = msg.get("content") or msg.get("reasoning_content") or ""
            if reply:
                out["reply"] = reply[:80]  # free lane is a reasoning model —
                # text may land in reasoning_content; a 200 with either field
                # proves the JWT was accepted
            if obj.get("error"):
                err = obj["error"]
                out["error"] = err.get("message") if isinstance(err, dict) else str(err)
    except ValueError:
        out["body"] = raw[:120].decode(errors="replace")
    return out


# ------------------------------------------------------------------ subcommands

def _cmd_mint_jwt(a, ctx: dict) -> int:
    env = ctx["env"]
    jwt_cookie = env.get("HF_JWT") or hfx.os.environ.get("HF_JWT", "")
    if not jwt_cookie or jwt_cookie.startswith("[REDACTED"):
        hfx.die(
            "HF_JWT is not set. It's the browser session cookie (name: `token`) — "
            "extract it from an authenticated huggingface.co session "
            "(devtools → Application → Cookies → token), then export HF_JWT=… "
            "or put it in .env next to the kit. "
            "(Optional credential — most commands only need HF_TOKEN.)",
            hfx.EXIT_CONFIG)

    st, hs, raw = hfx.http("GET", hfx.HF + MINT_PATH, cookie=f"token={jwt_cookie}",
                           allow_redirects=False)
    if st in (301, 302, 303, 307, 308):
        loc = ""
        for k, v in hs.items():
            if k.lower() == "location":
                loc = v
        if "security-checkup" in loc:
            print("hfx: HF is enforcing its password security-checkup gate on "
                  "credential-management pages.\n"
                  f"Fix once in a browser: visit {SECURITY_CHECKUP_URL} and complete "
                  "the checkup.\n(existing tokens and this mint endpoint usually keep "
                  "working — retry after the browser step).", file=sys.stderr)
            hfx.die("mint blocked by security-checkup gate", hfx.EXIT_FAIL)
        hfx.die(f"unexpected redirect {st} -> {loc}", hfx.EXIT_FAIL)
    if st == 401 or st == 403:
        hfx.die(f"cookie rejected ({st}) — HF_JWT is stale/invalid; re-extract the "
                "`token` cookie from a fresh browser session.", hfx.EXIT_CONFIG)
    if st != 200:
        hfx.die(f"GET {MINT_PATH} -> {st}: {raw[:200].decode(errors='replace')}",
                hfx.EXIT_FAIL)
    try:
        body = json.loads(raw)
        access = body["accessToken"]
    except (ValueError, KeyError):
        hfx.die(f"unexpected response shape: {raw[:200].decode(errors='replace')}",
                hfx.EXIT_FAIL)

    claims = jwt_payload(access)
    now = int(time.time())
    ttl = int(claims.get("exp", 0)) - now
    perms = claims.get("permissions")
    scope = perms if isinstance(perms, str) else json.dumps(perms)

    verify = _router_probe(access) if a.verify else None

    if ctx["json"]:
        hfx.jprint({"jwt": access, "claims": claims, "ttl_seconds": ttl,
                    "server_exp": body.get("exp"), "verify": verify,
                    "usage": "router-only; hub writes 401; 1h TTL"})
        if verify and not verify.get("pass"):
            return hfx.EXIT_FAIL
        return hfx.EXIT_OK

    print(f"# minted {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now))} "
          f"(unlimited mints — fresh JWT every call)\n")
    print(access)
    print(f"\nclaims (decoded):")
    print(f"  sub          {claims.get('sub', '?')}  (on behalf of: "
          f"{claims.get('onBehalfOf', '?')})")
    print(f"  scope        {scope or '?'}")
    print(f"  issued       {_fmt_ts(claims.get('iat'))} (iat)")
    print(f"  expires      {_fmt_ts(claims.get('exp'))} (exp) — TTL {max(ttl, 0)}s ≈ "
          f"{max(ttl, 0) // 60} min")
    print(f"  jti          {claims.get('jti', '?')}")
    print("\nformat note: use the FULL accessToken value including the "
          "hf_jwt_ prefix — a bare JWT (header.payload.signature only) 401s")
    if verify is not None:
        if verify.get("pass"):
            print(f"verify: PASS — router accepted this JWT right now "
                  f"(cheap-lane probe ≈$0.0000005, http {verify['http_status']}"
                  + (f", reply: {verify['reply']!r}" if verify.get("reply") else "")
                  + ")")
        else:
            print(f"verify: FAIL — router probe -> http {verify.get('http_status')}: "
                  f"{verify.get('error') or verify.get('body') or 'no content'}")
            print("         minted JWTs can 401 minutes after mint (observed "
                  "live, U7): mint fresh per CI step, re-mint on 401")
    print("\nusage note: THIS JWT is inference-ROUTER-ONLY "
          "(Authorization: Bearer <jwt> on https://router.huggingface.co/v1/*) — "
          "hub writes 401 with it, so it cannot leak your account. 1-hour TTL; "
          "THE CI-safe disposable credential.")
    if a.ttl_note:
        print("ttl note: exp-iat = 3600s every mint; no visible mint cap — mint a "
              "FRESH one per CI run instead of storing it; expiry is fail-safe "
              "(worst case: the job 401s after 1h, never a leaked long-lived key).")
    print("\ntry it: curl -s https://router.huggingface.co/v1/chat/completions "
          "-H 'Authorization: Bearer <jwt>' -H 'Content-Type: application/json' "
          "-d '{\"model\":\"Qwen/Qwen3-4B-Instruct-2507:nscale\","
          "\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":64}' "
          "(cheapest pinned lane — ~5M tok per $0.10/mo; PIN THE :provider SUFFIX "
          "always: unsuffixed ids route price-blind)")
    if verify is not None and not verify.get("pass"):
        return hfx.EXIT_FAIL
    return hfx.EXIT_OK


def _cmd_info(a, ctx: dict) -> int:
    token = hfx.need_token(ctx["env"])
    st, _, raw = hfx.http("GET", hfx.HF + "/api/whoami-v2", token=token)
    if st != 200:
        hfx.die(f"whoami-v2 -> {st}: HF_TOKEN invalid or expired. Create one at "
                "https://huggingface.co/settings/tokens and export HF_TOKEN.",
                hfx.EXIT_CONFIG)
    who = json.loads(raw)
    auth = who.get("auth") or {}
    acc = auth.get("accessToken") or {}

    if ctx["json"]:
        hfx.jprint({
            "name": who.get("name"), "fullname": who.get("fullname"),
            "type": who.get("type"), "token_role": acc.get("role"),
            "token_display_name": acc.get("displayName"),
            "auth_type": auth.get("type"), "is_pro": who.get("isPro"),
            "orgs": [o.get("name") for o in (who.get("orgs") or [])],
            "token_used": mask(token),
        })
        return hfx.EXIT_OK

    print(f"hfx token info — whoami-v2 (credential shown masked, first 8 chars only)\n"
          + "=" * 64)
    print(f"  account      {who.get('name', '?')}  ({who.get('fullname', '')}, "
          f"type={who.get('type', '?')}, pro={who.get('isPro', False)})")
    print(f"  credential   {mask(token)}  ({auth.get('type', '?')}, "
          f"role={acc.get('role', '?')}, name='{acc.get('displayName', '?')}', "
          f"created {str(acc.get('createdAt', '?'))[:10]})")
    orgs = who.get("orgs") or []
    if orgs:
        print(f"  orgs         {', '.join(o.get('name', '?') for o in orgs)} "
              f"(each org = its own storage/bandwidth pools — hfx status)")
    else:
        print("  orgs         none")
    print("\nnext: hfx status (quotas) | hfx token mint-jwt (CI-safe 1h JWT)")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ entry

def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="hfx token",
        description="credential utilities — identity + the disposable CI JWT. "
                    "Docs: kit/docs/sections/token.md")
    sub = p.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("mint-jwt", help="mint a 1h inference-only JWT from the "
                                         "HF_JWT browser cookie (CI-safe)")
    pm.add_argument("--ttl-note", action="store_true",
                    help="print the TTL/mint-capacity note (fresh JWT per run)")
    pm.add_argument("--verify", action="store_true",
                    help="after minting, ONE cheap-lane chat probe (max_tokens 5, "
                         "≈$0.0000005) proving the token works on the router "
                         "RIGHT NOW; prints PASS/FAIL (exit 1 on FAIL)")
    pm.add_argument("--json", action="store_true", help="machine-readable output")

    pi = sub.add_parser("info", help="whoami-v2: account + token role + orgs "
                                     "(safe fields, token masked)")
    pi.add_argument("--json", action="store_true", help="machine-readable output")

    pd = sub.add_parser("doctor", help="alias for `hfx doctor` — full "
                                       "environment check")
    pd.add_argument("rest", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)

    a = p.parse_args(argv)
    if getattr(a, "json", False):
        ctx["json"] = True

    if a.cmd == "mint-jwt":
        return _cmd_mint_jwt(a, ctx)
    if a.cmd == "info":
        return _cmd_info(a, ctx)
    if a.cmd == "doctor":
        sys.path.insert(0, hfx.LIB_ROOT)
        import cmd_doctor
        return cmd_doctor.run(a.rest, ctx)
    p.error(f"unknown subcommand {a.cmd}")


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False, "env": {}}))
