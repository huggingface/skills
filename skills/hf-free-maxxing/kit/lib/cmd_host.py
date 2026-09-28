#!/usr/bin/env python3
"""hfx host — free static-site hosting on HuggingFace Spaces (sdk: static).

Static Spaces are real always-on CDN-backed web hosts: unlimited count, no
cold start, free within the 20 TB/mo bandwidth quota, CORS `*` on every
response. NOT a Netlify clone: no clean URLs, no SPA fallback, no custom 404,
no gzip, no custom domains (PRO-only). Recipe: playbooks/static-hosting.md.

deploy DIR -n NAME
  * creates a PUBLIC static Space <ns>/<name> if absent
    (POST /api/repos/create {"type":"space","sdk":"static","private":false})
  * uploads every non-dotfile under DIR, recursively, via huggingface_hub
    upload_file (README.md is skipped unless it carries `sdk:` front-matter —
    the auto-generated one is what keeps the Space alive)
  * prints the live URL  https://<ns>-<name>.static.hf.space
  * --entity NS deploys into an org namespace (orgs multiply hosting)

ls      list your spaces (GET /api/spaces?author=<ns>)
rm NAME delete a Space — refuses names without "test"/"kit" (exit 3);
        --dry-run shows what WOULD be deleted; --yes skips the y/N prompt

Usage: hfx host {deploy,ls,rm} ...   (each has --help)
"""
from __future__ import annotations

import re
import sys

import hfx

NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def _static_url(ns: str, name: str) -> str:
    return f"https://{ns}-{name}.static.hf.space"


def _norm_name(raw: str) -> str:
    name = raw.strip().lower()
    if not NAME_RE.match(name):
        hfx.die(f"invalid Space name '{raw}': use lowercase letters, digits, "
                "hyphens (must start/end alphanumeric)", hfx.EXIT_CONFIG)
    return name


def _space_info(token: str, ns: str, name: str) -> dict | None:
    """GET /api/spaces/{ns}/{name} → dict or None if 404."""
    st, parsed, _ = hfx.api("GET", f"/api/spaces/{ns}/{name}", token=token,
                            expect=(200, 404))
    return parsed if st == 200 else None


def _whoami_ns(token: str, entity: str | None) -> tuple[str, list[str]]:
    ents = hfx.entities(token)
    names = [e["name"] for e in ents]
    if entity:
        if entity not in names:
            hfx.die(f"--entity {entity}: not one of your entities "
                    f"({', '.join(names)})", hfx.EXIT_CONFIG)
        return entity, names
    return names[0], names  # user namespace first


# ------------------------------------------------------------------ deploy

def _cmd_deploy(a, ctx: dict, token: str) -> int:
    import os
    hfx.require_py([("huggingface_hub", '"huggingface_hub<2.0"')])
    from huggingface_hub import HfApi

    ns, _ = _whoami_ns(token, a.entity)
    name = _norm_name(a.name)
    repo_id = f"{ns}/{name}"
    url = _static_url(ns, name)

    if not os.path.isdir(a.dir):
        hfx.die(f"not a directory: {a.dir}", hfx.EXIT_CONFIG)

    # collect files: recursive, dotfiles/dotdirs skipped (they'd be public!)
    files: list[tuple[str, str]] = []  # (abs_path, path_in_repo)
    for root, dirs, names in os.walk(a.dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for n in sorted(names):
            if n.startswith("."):
                continue
            abs_p = os.path.join(root, n)
            rel = os.path.relpath(abs_p, a.dir).replace(os.sep, "/")
            files.append((abs_p, rel))
    if not files:
        hfx.die(f"no files to deploy under {a.dir} (dotfiles are skipped)",
                hfx.EXIT_CONFIG)

    skipped = []
    uploads = []
    for abs_p, rel in files:
        # README.md rules the Space config — never clobber the sdk front-matter
        if rel == "README.md":
            with open(abs_p, "rb") as fh:
                head = fh.read(400)
            if not (head.startswith(b"---") and b"sdk:" in head):
                skipped.append(rel + " (no sdk: front-matter; keeping the "
                                     "auto-generated one)")
                continue
        uploads.append((abs_p, rel))

    # create if absent, verify sdk if present
    info = _space_info(token, ns, name)
    created = False
    if info is None:
        hfx.api("POST", "/api/repos/create", token=token, json_body={
            "type": "space", "name": name, "organization": ns,
            "sdk": "static", "private": False})
        created = True
        print(f"created static Space {repo_id} (public — private Spaces "
              "are not web-servable)")
    else:
        sdk = (info.get("sdk") or "").lower()
        if sdk != "static":
            hfx.die(f"{repo_id} exists with sdk={sdk or '?'} — this command "
                    "manages STATIC spaces only", hfx.EXIT_FAIL)
        print(f"updating existing static Space {repo_id}")

    hub = HfApi(token=token)
    for abs_p, rel in uploads:
        print(f"  ↑ {rel} ({hfx.human_bytes(os.path.getsize(abs_p))})")
        hub.upload_file(path_or_fileobj=abs_p, path_in_repo=rel,
                        repo_id=repo_id, repo_type="space",
                        commit_message=f"hfx host deploy: {rel}")
        hfx.time.sleep(1.2)  # be a good citizen on the commit API

    # verify it serves (root 302→/index.html when index.html exists)
    live_st, live_hs, _ = hfx.http("GET", url, timeout=30)
    commit = ""
    for k, v in (live_hs or {}).items():
        if k.lower() == "x-repo-commit":
            commit = f" · deployed commit {str(v)[:12]}"
    serve = ("live" if live_st in (200, 302) else f"NOT live yet (HTTP {live_st})")

    if ctx["json"]:
        hfx.jprint({"repo_id": repo_id, "url": url, "created": created,
                    "files": [rel for _, rel in uploads],
                    "skipped": skipped, "http": live_st})
        return hfx.EXIT_OK

    print(f"\nLIVE: {url}  ({serve}{commit})")
    print(f"hub:  https://huggingface.co/spaces/{repo_id}")
    for s in skipped:
        print(f"note: skipped {s}")
    print("\nCaveats (playbooks/static-hosting.md):")
    print("  * no clean URLs / no SPA fallback — link FULL paths (/about/index.html)")
    print("  * use a HASH router for SPAs (/#/about); trailing-slash links escape to HF")
    print("  * no gzip, no Cache-Control — version assets (app.js?v=2); CORS is open *")
    print(f"\nNext: curl -sI {url} | hfx host ls | hfx host rm {name} --dry-run")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ ls

def _cmd_ls(a, ctx: dict, token: str) -> int:
    ns, _ = _whoami_ns(token, a.entity)
    # never GET /api/spaces bare — without ?author= it lists FEATURED spaces
    _, items, _ = hfx.api("GET", f"/api/spaces?author={ns}", token=token)
    if not isinstance(items, list):
        items = []
    if ctx["json"]:
        hfx.jprint({"author": ns, "spaces": items})
        return hfx.EXIT_OK
    print(f"hfx host ls — spaces authored by {ns} ({len(items)} found)\n" + "=" * 72)
    for it in items:
        rid = it.get("id") or it.get("name", "?")
        name = rid.split("/")[-1]
        sdk = it.get("sdk", "?")
        vis = "private" if it.get("private") else "public"
        live = _static_url(ns, name) if sdk == "static" else \
            f"https://huggingface.co/spaces/{rid}"
        print(f"  {rid:<48} sdk={sdk:<8} {vis:<7} {it.get('lastModified', '')}")
        print(f"    → {live}")
    if not items:
        print("  (none)")
    print("\nNext: hfx host deploy ./site -n my-site | hfx host rm <name> --dry-run")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ rm

def _cmd_rm(a, ctx: dict, token: str) -> int:
    ns, _ = _whoami_ns(token, a.entity)
    raw = a.name.split("/")[-1]
    name = _norm_name(raw)
    if a.name.count("/") > 1 or (a.name.count("/") == 1
                                 and a.name.split("/")[0] not in (ns,)):
        hfx.die(f"refusing: {a.name} is not under your namespace {ns}",
                hfx.EXIT_CONFIG)

    # safety gate 1: kit/test names only
    if not any(tag in name for tag in ("test", "kit")):
        hfx.die(f"refusing to delete {ns}/{name}: name contains neither "
                "'test' nor 'kit'. This guard keeps `hfx host rm` off real "
                "projects — delete those manually in the web UI.",
                hfx.EXIT_QUOTA)

    info = _space_info(token, ns, name)
    if info is None:
        hfx.die(f"space not found: {ns}/{name}", hfx.EXIT_CONFIG)
    rid = info.get("id") or f"{ns}/{name}"
    nfiles = len(info.get("siblings") or [])
    detail = (f"{rid} · sdk={info.get('sdk', '?')} · "
              f"{'private' if info.get('private') else 'public'} · "
              f"~{nfiles} files · {_static_url(ns, name) if info.get('sdk') == 'static' else 'no static URL'}")

    if a.dry_run:
        print(f"DRY-RUN — would DELETE space {detail}")
        print("(nothing was deleted; rerun without --dry-run, add --yes to skip the prompt)")
        if ctx["json"]:
            hfx.jprint({"would_delete": rid, "dry_run": True, "detail": detail})
        return hfx.EXIT_OK

    # safety gate 2: y/N confirm unless --yes
    if not a.yes:
        if not sys.stdin.isatty():
            hfx.die(f"non-interactive session — pass --yes to delete ({detail})",
                    hfx.EXIT_QUOTA)
        try:
            ans = input(f"DELETE {detail}\n  type 'y' to confirm: ").strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("y", "yes"):
            print("aborted — nothing deleted")
            return hfx.EXIT_QUOTA

    # primary: legacy /api/repos/delete (verified live — DELETE /api/spaces/{ns}/{name}
    # is a 404 "Cannot DELETE" route, probed 2026-09-26); keep it as fallback
    import json as _json
    st, hs, raw_b = hfx.http("DELETE", hfx.HF + "/api/repos/delete",
                             token=token,
                             headers={"Content-Type": "application/json"},
                             body=_json.dumps({"name": name, "organization": ns,
                                               "type": "space"}).encode(),
                             timeout=60)
    how = "DELETE /api/repos/delete"
    if st not in (200, 201, 204):
        st, hs, raw_b = hfx.http("DELETE", f"{hfx.HF}/api/spaces/{ns}/{name}",
                                 token=token, timeout=60)
        how = "DELETE /api/spaces/{ns}/{name}"
    if st not in (200, 201, 204):
        snippet = raw_b[:200].decode(errors="replace").replace("\n", " ")
        hfx.die(f"delete failed ({st}) via {how}: {snippet}", hfx.EXIT_FAIL)

    msg = f"deleted {rid} via {how}"
    if ctx["json"]:
        hfx.jprint({"deleted": rid, "via": how})
    else:
        print(msg)
        print("\nNext: hfx host ls  (verify it's gone)")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ dispatch

def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="hfx host",
        description="free static hosting on HuggingFace Spaces (sdk: static) — "
                    "unlimited always-on sites, CORS *, 20TB/mo quota. "
                    "No clean URLs/SPA fallback: use hash routes.")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("deploy", help="create-or-update a static Space from a DIR")
    d.add_argument("dir", help="local directory with site files")
    d.add_argument("-n", "--name", required=True,
                   help="Space name (lowercase/digits/hyphens) → "
                        "https://<ns>-<name>.static.hf.space")
    d.add_argument("--entity", help="deploy into org namespace NS (default: your user)")
    d.add_argument("--json", action="store_true")

    l = sub.add_parser("ls", help="list spaces you author")
    l.add_argument("--entity", help="list org namespace NS (default: your user)")
    l.add_argument("--json", action="store_true")

    r = sub.add_parser("rm", help="delete a Space (kit/test names only)")
    r.add_argument("name", help="space name (or ns/name)")
    r.add_argument("--entity", help="org namespace NS (default: your user)")
    r.add_argument("--yes", action="store_true", help="skip the y/N confirm")
    r.add_argument("--dry-run", action="store_true",
                   help="show what would be deleted, delete nothing")
    r.add_argument("--json", action="store_true")

    a = p.parse_args(argv)
    if getattr(a, "json", False):
        ctx["json"] = True
    token = hfx.need_token(ctx["env"])
    if a.cmd == "deploy":
        return _cmd_deploy(a, ctx, token)
    if a.cmd == "ls":
        return _cmd_ls(a, ctx, token)
    return _cmd_rm(a, ctx, token)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False, "env": {}}))
