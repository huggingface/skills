#!/usr/bin/env python3
"""hfx md — free markdown→HTML via the community-blog preview renderer.

POST /api/blog/preview {"content": ...} → {"html": ...} — the same renderer
the HF blog editor uses: headings with anchor links, bold, inline code,
fenced code blocks, links (rel=nofollow), images, lists, blockquotes.
NO math/KaTeX ($E=mc^2$ passes through raw).

Auth: web-session cookie ONLY (HF_JWT — a PAT gets 401, anonymous gets 401).
Costs nothing; sits in the `api` rate bucket (1000/5min).
Evidence: findings/blog-publish-probe.md §4

Usage: hfx md render FILE_OR_TEXT [--json]
  FILE_OR_TEXT = path to a .md file, '-' for stdin, or literal markdown text.
"""
from __future__ import annotations

import sys

import hfx

UA_BROWSER = ("Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 "
              "Firefox/132.0")


def _read_input(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    import os
    if os.path.isfile(arg):
        with open(arg, encoding="utf-8") as fh:
            return fh.read()
    return arg  # literal markdown text


def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="hfx md",
        description="markdown→HTML via the free /api/blog/preview renderer "
                    "(cookie-only, no KaTeX math). No account costs, "
                    "api bucket 1000/5min.")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="render markdown → HTML")
    r.add_argument("text",
                   help="path to a markdown file, '-' (stdin), or literal text")
    r.add_argument("--json", action="store_true",
                   help='machine-readable {"html": ...}')
    a = p.parse_args(argv)
    if a.json:
        ctx["json"] = True

    jwt = hfx.need(ctx["env"], "HF_JWT",
                   "This endpoint is web-session-only (PATs get 401). "
                   "Extract the cookie named `token` from an authenticated "
                   "browser session on huggingface.co and export HF_JWT=...")
    content = _read_input(a.text)
    if not content.strip():
        hfx.die("no markdown input", hfx.EXIT_CONFIG)

    # cookie + browser-ish headers required (Origin/Referer; no CSRF needed)
    st, parsed, raw = hfx.api(
        "POST", "/api/blog/preview", token="", cookie=f"token={jwt}",
        json_body={"content": content},
        headers={"User-Agent": UA_BROWSER, "Accept": "application/json",
                 "Origin": hfx.HF, "Referer": hfx.HF + "/new-blog"},
        expect=(200, 401, 403, 429))
    if st == 401:
        hfx.die("401 — /api/blog/preview is cookie-only: your HF_JWT is "
                "missing/expired (PATs are rejected here)",
                hfx.EXIT_CONFIG)
    if st == 403:
        hfx.die("403 — session rejected; re-extract the `token` cookie from "
                "a fresh browser login", hfx.EXIT_CONFIG)
    if st == 429:
        hfx.die("429 — api bucket exhausted (1000/5min); retry shortly",
                hfx.EXIT_QUOTA)
    html = (parsed or {}).get("html")
    if html is None:
        hfx.die(f"unexpected response shape: {raw[:200]!r}", hfx.EXIT_FAIL)

    if ctx["json"]:
        hfx.jprint({"html": html})
    else:
        print(html)
        print("\n# hfx md: rendered by /api/blog/preview (free, cookie-only; "
              "no KaTeX math)", file=sys.stderr)
        print("# next: pair with `hfx cdn put` for images, or save to a "
              "static Space (`hfx host deploy`)", file=sys.stderr)
    return hfx.EXIT_OK


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False, "env": {}}))
