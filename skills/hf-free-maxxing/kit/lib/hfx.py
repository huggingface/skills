#!/usr/bin/env python3
"""hfx — HuggingFace free-maxxing kit CLI.

One entry point for every verified-free HuggingFace capability:
status / store / cdn / host / infer / gpu / mcp / etl / oauth / registry /
token / watch / social / md / monitor.  See kit/AGENTS.md for the full guide.

Conventions (all command modules must follow):
  * self-locating: no dependency on cwd; KIT_ROOT/lib resolved from __file__
  * config: real env vars win; then kit/.env; then repo-root .env
  * --json everywhere machine output matters; humans get tables by default
  * on missing python deps print the EXACT pip line, exit 2
  * on quota/budget refusal exit 3; on operational failure exit 1
  * on success print actionable next steps (URLs, follow-up commands)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

KIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(KIT_ROOT)

HF = "https://huggingface.co"
ROUTER = "https://router.huggingface.co"
S3_ENDPOINT = "https://s3.hf.co"
UA = "hf-free-maxxing-kit/0.1"

EXIT_OK, EXIT_FAIL, EXIT_CONFIG, EXIT_QUOTA = 0, 1, 2, 3

ENV_KEYS = ("HF_TOKEN", "HF_JWT", "HF_S3_ACCESS_KEY_ID", "HF_S3_SECRET_ACCESS_KEY",
            "HFX_ENTITIES")


# ------------------------------------------------------------------ config

def load_env() -> dict:
    """Env vars win; then kit/.env; then repo-root .env (git-is-disk pattern)."""
    for path in (os.path.join(KIT_ROOT, ".env"), os.path.join(REPO_ROOT, ".env")):
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            os.environ.setdefault(k.strip(), v.strip())
            except OSError:
                pass
    return {k: os.environ.get(k, "") for k in ENV_KEYS}


def need(env: dict, key: str, hint: str) -> str:
    val = env.get(key) or os.environ.get(key, "")
    if not val or val.startswith("[REDACTED"):
        die(f"{key} is not set. {hint}", EXIT_CONFIG)
    return val


def need_token(env: dict) -> str:
    return need(env, "HF_TOKEN",
                "Create one at https://huggingface.co/settings/tokens (role: read "
                "is enough for GETs; write for store/host). Then export HF_TOKEN=... "
                "or put it in .env next to the kit.")


# ------------------------------------------------------------------ output

def die(msg: str, code: int = EXIT_FAIL):
    print(f"hfx: {msg}", file=sys.stderr)
    sys.exit(code)


def jprint(obj):
    print(json.dumps(obj, indent=2, default=str, sort_keys=False))


def human_bytes(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "n/a"
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024 or unit == "PB":
            return f"{n:.2f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024.0
    return f"{n:.2f} PB"


def human_usd(nanousd) -> str:
    try:
        return f"${float(nanousd) / 1e9:.6f}"
    except (TypeError, ValueError):
        return "n/a"


# ------------------------------------------------------------------ http

def http(method: str, url: str, *, token: str = "", cookie: str = "",
         headers: dict | None = None, body: bytes | None = None,
         timeout: int = 60, allow_redirects: bool = True) -> tuple[int, dict, bytes]:
    """Tiny urllib wrapper. Returns (status, headers, body). Raises nothing;
    network errors return (0, {}, b'')."""
    hdrs = {"User-Agent": UA}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    if cookie:
        hdrs["Cookie"] = cookie
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, method=method, headers=hdrs)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener() if allow_redirects else \
        urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:  # noqa: BLE001 — deliberate: report, don't crash
        return 0, {}, str(e).encode()


def api(method: str, path: str, *, token: str, cookie: str = "",
        json_body: dict | None = None, headers: dict | None = None,
        timeout: int = 60, expect: tuple[int, ...] = (200, 201, 204),
        base: str = HF) -> tuple[int, dict, bytes]:
    """huggingface.co (or router) API call. json_body auto-serializes.
    Returns (status, parsed_json_or_none, raw_body)."""
    hdrs = dict(headers or {})
    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    st, hs, raw = http(method, base + path, token=token, cookie=cookie,
                       headers=hdrs, body=body, timeout=timeout)
    parsed = None
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        pass
    if st not in expect:
        snippet = raw[:300].decode(errors="replace").replace("\n", " ")
        die(f"API {method} {path} -> {st} (expected {expect}): {snippet}", EXIT_FAIL)
    return st, parsed, raw


def sse_first_full_event(path: str, *, token: str, base: str = HF,
                         wait_s: float = 8.0) -> dict:
    """GET an SSE endpoint, return the LAST complete JSON `data:` event seen in
    the window. First events can be partial snapshots — usage/live gotcha.
    The socket timeout is bounded to the window (+1s) so a blocked read can't
    overshoot the deadline — the usage/live stream stays open server-side and
    sends events sparsely (observed: 2 in 25s), so an unbounded per-read
    timeout made every call spend window+timeout wall time (status was 13s/
    entity for an 8s window before this fix, 2026-09-26)."""
    url = base + path
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Authorization": f"Bearer {token}", "Accept": "text/event-stream"})
    best, deadline = {}, time.time() + wait_s
    try:
        with urllib.request.urlopen(req, timeout=max(1.0, wait_s + 1.0)) as resp:
            buf = b""
            while time.time() < deadline:
                chunk = resp.readline()
                if not chunk:
                    break
                buf += chunk
                if buf.endswith(b"\n\n") or buf.endswith(b"\r\n\r\n"):
                    for line in buf.decode(errors="replace").splitlines():
                        if line.startswith("data:"):
                            try:
                                obj = json.loads(line[5:].strip())
                            except ValueError:
                                continue
                            if isinstance(obj, dict) and "storage" in obj:
                                best = obj  # keep last complete
                    buf = b""
    except Exception as e:  # noqa: BLE001
        if not best:
            die(f"SSE {path} failed: {e}", EXIT_FAIL)
    if not best:
        die(f"SSE {path}: no complete event within {wait_s}s", EXIT_FAIL)
    return best


# ------------------------------------------------------------------ shared facts

def entities(token: str) -> list[dict]:
    """[{kind:'user'|'org', name}] — user first, then orgs from whoami-v2."""
    _, who, _ = api("GET", "/api/whoami-v2", token=token)
    if not who or "name" not in who:
        die("whoami-v2 failed — is HF_TOKEN valid?", EXIT_CONFIG)
    out = [{"kind": "user", "name": who["name"]}]
    for org in who.get("orgs", []) or []:
        out.append({"kind": "org", "name": org.get("name", "")})
    return out


def entity_usage_path(ent: dict) -> str:
    return ("/api/settings/billing/usage/live" if ent["kind"] == "user"
            else f"/api/organizations/{ent['name']}/billing/usage/live")


def zero_gpu_quota(token: str) -> dict:
    _, q, _ = api("GET", "/api/spaces/zero-gpu/quota", token=token)
    return q or {}


# ------------------------------------------------------------------ deps

def require_py(modules: list[tuple[str, str]]):
    """modules = [(import_name, pip_name)]. Exit 2 with exact pip line on miss."""
    missing = []
    for imp, pip in modules:
        try:
            __import__(imp)
        except ImportError:
            missing.append(pip)
    if missing:
        quoted = " ".join(f"'{m}'" if any(c in m for c in "<>=!") else m
                          for m in missing)
        die("missing python deps; install with:\n"
            f"  pip install --user {quoted}", EXIT_CONFIG)


# ------------------------------------------------------------------ dispatcher

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hfx",
        description="HuggingFace free-maxxing kit — every verified-free capability, "
                    "one CLI. Docs: kit/AGENTS.md",
        epilog="Each command has its own --help. Run `hfx` with no args to list commands.")
    p.add_argument("--json", action="store_true",
                   help="machine-readable output where supported")
    p.add_argument("command", nargs="?", default="",
                   help="command to run (see available list below)")
    p.add_argument("args", nargs=argparse.REMAINDER,
                   help="arguments passed to the command")
    return p


def _available() -> list[str]:
    return sorted(f[4:-3].replace("_", "-")
                  for f in os.listdir(LIB_ROOT)
                  if f.startswith("cmd_") and f.endswith(".py"))


def main(argv: list[str] | None = None) -> int:
    load_env()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        print("hfx — HuggingFace free-maxxing kit\n\navailable commands:")
        for name in _available():
            print(f"  hfx {name} --help")
        print("\nDocs: kit/AGENTS.md (start there — prerequisites + quick wins).")
        return EXIT_OK

    sys.path.insert(0, LIB_ROOT)
    ctx = {
        "json": args.json,
        "env": {k: os.environ.get(k, "") for k in ENV_KEYS},
        "HF": HF, "ROUTER": ROUTER, "S3_ENDPOINT": S3_ENDPOINT,
    }

    # allow trailing --json anywhere (commands may not define it themselves)
    if "--json" in args.args:
        args.args = [a for a in args.args if a != "--json"]
        ctx["json"] = True

    # import the command module named cmd_<command>.py
    mod_name = f"cmd_{args.command.replace('-', '_')}"
    try:
        mod = __import__(mod_name)
    except ImportError:
        print(f"hfx: unknown command '{args.command}'", file=sys.stderr)
        print("available: " + " ".join(_available()), file=sys.stderr)
        return EXIT_CONFIG

    # allow --json anywhere (commands that define their own --json update ctx too)
    rc = mod.run(args.args, ctx)  # type: ignore[attr-defined]
    return rc if isinstance(rc, int) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
