#!/usr/bin/env python3
"""hfx social — content/social thin wrappers (discussions, collections, likes).

PAT Bearer, no CSRF needed for discussions + collections (verified live,
findings/review-identity-infra-cluster.md §C1-C3).  Likes are COOKIE-only
(PAT → 401) — graceful exit 2 with a hint if HF_JWT is missing.

  discuss REPO           list discussions (or --create / --rm)
  collect ls|create|add|rm   collections CRUD (public curation/read-lists)
  like|unlike REPO       needs the web-session cookie (HF_JWT)

Usage: hfx social <subcommand> [--json]
"""
from __future__ import annotations

import os
import sys

# allow direct execution (python3 kit/lib/cmd_social.py …)
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hfx  # noqa: E402
import kitutil  # noqa: E402


def _need_cookie(ctx: dict) -> str:
    jwt = ctx["env"].get("HF_JWT") or os.environ.get("HF_JWT", "")
    if not jwt or jwt.startswith("[REDACTED"):
        hfx.die("this call needs the web-session cookie (PAT gets 401). Extract "
                "the cookie named 'token' from an authenticated browser session "
                "and export HF_JWT=… (see kit/AGENTS.md prerequisites §3).",
                hfx.EXIT_CONFIG)
    return f"token={jwt}"


def _web_headers() -> dict:
    """Likes/posts on web surfaces need Origin+Referer or 403 'same site'."""
    return {"Origin": hfx.HF, "Referer": hfx.HF + "/"}


# ------------------------------------------------------------------ discussions

def _discuss(a, ctx) -> int:
    token = hfx.need_token(ctx["env"])
    rt = kitutil.detect_repo_type(token, a.repo, explicit=a.type)
    base = f"/api/{kitutil.type_api_path(rt)}/{a.repo}/discussions"

    if a.rm:
        hfx.api("DELETE", f"{base}/{a.rm}", token=token, expect=(200, 204))
        print(f"discussion #{a.rm} on {a.repo} deleted ✓ "
              "(verify: hfx social discuss " + a.repo + ")")
        return hfx.EXIT_OK

    if a.create:
        if not a.title or len(a.title) < 3:
            hfx.die("--title is required for --create (3-200 chars)", hfx.EXIT_CONFIG)
        _, raw, _ = hfx.api("POST", base, token=token, json_body={
            "title": a.title, "description": a.body or ""})
        d = raw or {}
        url = hfx.HF + (d.get("url") or "")
        if ctx["json"]:
            hfx.jprint(d)
        else:
            print("discussion created\n" + "=" * 72)
            print(f"  #{d.get('num')}  {a.title}")
            print(f"  url: {url}")
            print(f"\n  comment: POST {base}/{d.get('num')}/comment {{\"comment\":…}}")
            print(f"  reactions (12): 🔥 🚀 👀 ❤️ 🤗 😎 ➕ 🧠 👍 🤝 😔 🤯 "
                  f"(POST …/comment/{{id}}/reaction)")
            print(f"  delete  : hfx social discuss {a.repo} --rm {d.get('num')}")
        return hfx.EXIT_OK

    _, raw, _ = hfx.api("GET", base, token=token)
    disc = (raw or {}).get("discussions") or []
    if ctx["json"]:
        hfx.jprint(raw)
        return hfx.EXIT_OK
    print(f"discussions on {a.repo} — {len(disc)} open-ish "
          f"(count {(raw or {}).get('count', '?')}, closed "
          f"{(raw or {}).get('numClosedDiscussions', '?')})\n" + "=" * 72)
    if not disc:
        print("  (none — create one with --create --title … --body …)")
    for d in disc:
        author = (d.get("author") or {}).get("name", "?")
        print(f"  #{d.get('num', '?'):<4} [{d.get('status', '?'):<6}] "
              f"{(d.get('title') or '?')[:56]}  — {author}")
    print("\nFull free CRUD layer: title/description edits, comments, 12 reactions, "
          "merge/pin/status — findings/review-identity-infra-cluster.md §C1.")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ collections

def _collect(a, ctx) -> int:
    token = hfx.need_token(ctx["env"])

    if a.ccmd == "ls":
        owner = a.owner
        if not owner:
            _, who, _ = hfx.api("GET", "/api/whoami-v2", token=token)
            owner = (who or {}).get("name", "")
        _, raw, _ = hfx.api("GET", f"/api/collections?owner={owner}", token=token)
        cols = raw if isinstance(raw, list) else (raw or {}).get("collections") or []
        if ctx["json"]:
            hfx.jprint(cols)
            return hfx.EXIT_OK
        print(f"collections owned by {owner} — {len(cols)}\n" + "=" * 72)
        if not cols:
            print("  (none — create one: hfx social collect create --title …)")
        for c in cols:
            print(f"  [{c.get('private') and 'PRIVATE' or 'public':<7}] "
                  f"{(c.get('title') or '?')[:44]}")
            print(f"          {c.get('slug', '?')} · "
                  f"{len(c.get('items') or [])} items · "
                  f"{c.get('upvotes', 0)} upvotes")
        return hfx.EXIT_OK

    if a.ccmd == "create":
        if not a.title:
            hfx.die("collect create needs --title", hfx.EXIT_CONFIG)
        namespace = a.namespace
        if not namespace:
            _, who, _ = hfx.api("GET", "/api/whoami-v2", token=token)
            namespace = (who or {}).get("name", "")
        body = {"title": a.title, "namespace": namespace}
        if a.description:
            body["description"] = a.description
        if a.item:
            rt = kitutil.detect_repo_type(token, a.item, explicit=a.type)
            body["item"] = {"type": rt, "id": a.item}
        _, raw, _ = hfx.api("POST", "/api/collections", token=token, json_body=body)
        c = raw or {}
        slug = c.get("slug", "?")
        if ctx["json"]:
            hfx.jprint(c)
        else:
            print("collection created (slug gets a -<id> suffix)\n" + "=" * 72)
            print(f"  title : {c.get('title', a.title)}")
            print(f"  slug  : {slug}")
            print(f"  url   : {hfx.HF}/collections/{slug}")
        print(f"\n  add item: hfx social collect add --slug '{slug}' --item <owner/repo>")
        print(f"  delete : hfx social collect rm --slug '{slug}'")
        return hfx.EXIT_OK

    if a.ccmd == "add":
        if not a.slug or not a.item:
            hfx.die("collect add needs --slug and --item", hfx.EXIT_CONFIG)
        rt = kitutil.detect_repo_type(token, a.item, explicit=a.type)
        body = {"item": {"type": rt, "id": a.item}}
        if a.note:
            body["note"] = a.note
        _, raw, _ = hfx.api("POST", f"/api/collections/{a.slug}/items",
                            token=token, json_body=body)
        if ctx["json"]:
            hfx.jprint(raw)
        else:
            n = len((raw or {}).get("items") or [])
            print(f"added {rt} '{a.item}' to {a.slug} ✓ ({n} items now)")
            print(f"  view: {hfx.HF}/collections/{a.slug}")
        return hfx.EXIT_OK

    if a.ccmd == "rm":
        if not a.slug:
            hfx.die("collect rm needs --slug", hfx.EXIT_CONFIG)
        hfx.api("DELETE", f"/api/collections/{a.slug}", token=token)
        print(f"collection {a.slug} deleted ✓")
        return hfx.EXIT_OK

    hfx.die("collect needs a subcommand: ls|create|add|rm", hfx.EXIT_CONFIG)
    return hfx.EXIT_CONFIG


# ------------------------------------------------------------------ likes

def _fetch_csrf(cookie: str) -> str:
    """Extract authLight.csrfToken from the homepage (needed by the like POST —
    live-verified 2026-09-26: cookie+Origin alone now 403 'CSRF token not
    provided'; DELETE needs no csrf)."""
    import re
    st, _, raw = hfx.http("GET", hfx.HF + "/", cookie=cookie,
                          headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                                                 "hf-free-maxxing-kit"})
    if st != 200:
        hfx.die(f"homepage fetch for csrf -> {st}", hfx.EXIT_FAIL)
    html = raw.decode(errors="replace")
    m = (re.search(r'"csrfToken":"([^"]+)"', html)          # raw JSON variant
         or re.search(r'csrfToken&quot;:&quot;([^&]+)&quot;', html))  # data-props variant
    if not m:
        hfx.die("could not extract csrfToken from the homepage (page layout "
                "drift?)", hfx.EXIT_FAIL)
    return m.group(1)


def _like(a, ctx) -> int:
    cookie = _need_cookie(ctx)
    token = ctx["env"].get("HF_TOKEN") or os.environ.get("HF_TOKEN", "")
    if not token and not a.type:
        hfx.die("like/unlike needs HF_TOKEN for repo-type detection (plus the "
                "HF_JWT cookie for the call itself)", hfx.EXIT_CONFIG)
    rt = kitutil.detect_repo_type(token, a.repo, explicit=a.type) if token \
        else a.type
    method = "POST" if a.lcmd == "like" else "DELETE"
    hdrs = _web_headers()
    body = None
    if method == "POST":
        import json as _json
        body = _json.dumps({"csrf": _fetch_csrf(cookie)}).encode()
        hdrs["Content-Type"] = "application/json"  # or the csrf body is not parsed
    st, _, raw = hfx.http(method, f"{hfx.HF}/api/{kitutil.type_api_path(rt)}/{a.repo}/like",
                          cookie=cookie, headers=hdrs, body=body)
    if st not in (200, 201):
        if st in (401, 403):
            hfx.die(f"like -> {st}: cookie rejected/insufficient "
                    f"({raw[:150].decode(errors='replace')}). Re-extract the "
                    "'token' cookie from a fresh browser session.",
                    hfx.EXIT_CONFIG)
        hfx.die(f"like -> {st}: {raw[:200].decode(errors='replace')}", hfx.EXIT_FAIL)
    import json as _json
    try:
        out = _json.loads(raw)
    except ValueError:
        out = {"raw": raw.decode(errors="replace")}
    if ctx["json"]:
        hfx.jprint(out)
    else:
        liked = out.get("isLikedByUser", "?")
        print(f"{a.lcmd}d {a.repo} ✓ — likes: {out.get('likes', '?')} · "
              f"isLikedByUser: {liked}")
        if a.lcmd == "like":
            print(f"  undo: hfx social unlike {a.repo}")
        print("  409 = already liked · likers: GET /api/"
              f"{kitutil.type_api_path(rt)}/{a.repo}/likers (anon OK)")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ dispatch

def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="hfx social",
        description="Discussions, collections, likes — the free content/social "
                    "API layer. PAT for discussions+collections; cookie for "
                    "likes. Evidence: findings/review-identity-infra-cluster.md §C")
    pj = argparse.ArgumentParser(add_help=False)
    pj.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    pd = sub.add_parser("discuss", parents=[pj],
                        help="list/create/delete discussions on any repo you can see")
    pd.add_argument("repo", help="owner/repo (type autodetected)")
    pd.add_argument("--create", action="store_true", help="create a discussion")
    pd.add_argument("--title", help="discussion title (3-200 chars)")
    pd.add_argument("--body", help="description/markdown body (≤64k)")
    pd.add_argument("--rm", metavar="NUM", help="delete discussion #NUM")
    pd.add_argument("--type", default="", help="force space|model|dataset|bucket")
    pd.set_defaults(fn=_discuss)

    pc = sub.add_parser("collect", parents=[pj], help="collections CRUD")
    csub = pc.add_subparsers(dest="ccmd", required=True)

    cls = csub.add_parser("ls", parents=[pj], help="list collections (default: yours)")
    cls.add_argument("--owner", help="namespace to list (default: your user)")
    cls.set_defaults(fn=_collect)

    ccr = csub.add_parser("create", parents=[pj], help="create a collection")
    ccr.add_argument("--title", required=True)
    ccr.add_argument("--namespace", help="owner namespace (default: your user)")
    ccr.add_argument("--description", default="", help="optional description")
    ccr.add_argument("--item", help="optional first item owner/repo")
    ccr.add_argument("--type", default="", help="force item type space|model|dataset")
    ccr.set_defaults(fn=_collect)

    cad = csub.add_parser("add", parents=[pj], help="add an item to a collection")
    cad.add_argument("--slug", required=True, help="full slug ns/name-<id>")
    cad.add_argument("--item", required=True, help="owner/repo to add")
    cad.add_argument("--note", default="", help="per-item note (≤500 chars)")
    cad.add_argument("--type", default="", help="force item type")
    cad.set_defaults(fn=_collect)

    crm = csub.add_parser("rm", parents=[pj], help="delete a collection by slug")
    crm.add_argument("--slug", required=True)
    crm.set_defaults(fn=_collect)

    for name, help_txt in (("like", "like a repo (cookie required)"),
                           ("unlike", "remove your like (cookie required)")):
        pl = sub.add_parser(name, parents=[pj], help=help_txt)
        pl.add_argument("repo", help="owner/repo")
        pl.add_argument("--type", default="", help="force space|model|dataset")
        pl.set_defaults(fn=_like, lcmd=name)
    a = p.parse_args(argv)
    ctx["json"] = ctx.get("json") or a.json
    return a.fn(a, ctx)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False,
                                "env": {k: os.environ.get(k, "") for k in hfx.ENV_KEYS}}))
