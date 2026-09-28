#!/usr/bin/env python3
"""hfx watch — events: webhooks, bucket change-feed SSE, notifications.

  webhooks ls        GET  /api/settings/webhooks (PAT) — your webhook inventory
  webhooks add       POST /api/settings/webhooks {watched, url, domains}
                     (PAT, no CSRF; 1000 triggers/24h per webhook)
  webhooks rm        DELETE /api/settings/webhooks/{id}
  bucket NS/NAME     stream the bucket change-feed SSE (GET /api/buckets/{ns}/
                     {name}/events) — ready/changes/reset/reconnect events
  notifications      GET /api/notifications (PAT; cookie fallback) + optional
                     --mark-all-read

Usage: hfx watch <subcommand> [--json]
"""
from __future__ import annotations

import os
import sys

# allow direct execution (python3 kit/lib/cmd_watch.py …)
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hfx  # noqa: E402
import kitutil  # noqa: E402


def _wh_list_payload(raw) -> list[dict]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and isinstance(raw.get("webhooks"), list):
        return raw["webhooks"]
    return []


# ------------------------------------------------------------------ webhooks

def _webhooks_ls(a, ctx) -> int:
    token = hfx.need_token(ctx["env"])
    _, raw, _ = hfx.api("GET", "/api/settings/webhooks", token=token)
    hooks = _wh_list_payload(raw)
    if ctx["json"]:
        hfx.jprint(hooks)
        return hfx.EXIT_OK
    print(f"webhooks — {len(hooks)} configured\n" + "=" * 72)
    if not hooks:
        print("  (none)")
    for wh in hooks:
        watched = ", ".join(f"{w.get('type', '?')}:{w.get('name', '?')}"
                            for w in wh.get("watched") or []) or "(account-wide)"
        domains = ",".join(wh.get("domains") or [])
        print(f"  [{wh.get('id', '?')[:24]}] {wh.get('url', '?')}")
        print(f"      watched: {watched} · domains: {domains} · "
              f"{'DISABLED' if wh.get('disabled') else 'active'} · "
              f"lastTrigger: {wh.get('lastTriggerAt') or 'never'}")
    if hooks:
        print("\n  rm: hfx watch webhooks rm --id <id> · replay/logs are HTML-only "
              "(findings/infra-probe.md §B)")
    print("\n  add: hfx watch webhooks add --url https://ntfy.sh/<topic> "
          "--watch <owner/repo>")
    return hfx.EXIT_OK


def _webhooks_add(a, ctx) -> int:
    token = hfx.need_token(ctx["env"])
    watched = []
    for repo in a.watch:
        rt = kitutil.detect_repo_type(token, repo, explicit=a.type)
        watched.append({"type": rt, "name": repo})
    body = {"watched": watched, "url": a.url,
            "domains": [d.strip() for d in a.domains.split(",") if d.strip()]}
    _, raw, _ = hfx.api("POST", "/api/settings/webhooks", token=token,
                        json_body=body, expect=(200, 201))
    wh = (raw or {}).get("webhook") or raw or {}
    wh_id = wh.get("id", "?")
    if ctx["json"]:
        hfx.jprint(wh)
    else:
        wtxt = ", ".join(f"{w['type']}:{w['name']}" for w in watched) or "(account-wide)"
        print("webhook created\n" + "=" * 72)
        print(f"  id      : {wh_id}")
        print(f"  url     : {wh.get('url', a.url)}")
        print(f"  watched : {wtxt}")
        print(f"  domains : {', '.join(body['domains'])}")
        print("""
Notes (findings/infra-probe.md §B):
  • receiver gotcha: HF delivery workers CANNOT resolve webhook.site (DNS
    blocked) — ntfy.sh verified working; 1000 triggers/24h per webhook.
  • payload v3: {event:{action,scope}, repo:{...}, webhook:{id,version:3},
    updatedRefs:[{ref,oldSha,newSha}]} (+ updatedFiles for bucket domains).
  • trigger by committing: POST /api/spaces/{repo}/commit/main (NDJSON).""")
    print(f"\nVerify: hfx watch webhooks ls   ·   cleanup: hfx watch webhooks rm --id {wh_id}")
    return hfx.EXIT_OK


def _webhooks_rm(a, ctx) -> int:
    token = hfx.need_token(ctx["env"])
    hfx.api("DELETE", f"/api/settings/webhooks/{a.id}", token=token, expect=(200, 204))
    print(f"webhook {a.id} deleted ✓")
    print("Verify: hfx watch webhooks ls")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ bucket SSE

def _bucket(a, ctx) -> int:
    token = hfx.need_token(ctx["env"])
    ns, _, name = a.bucket.partition("/")
    if not ns or not name:
        hfx.die("bucket must be NS/NAME (e.g. myuser/my-bucket)",
                hfx.EXIT_CONFIG)
    path = f"/api/buckets/{ns}/{name}/events"
    if a.cursor:
        path += f"?cursor={a.cursor}"
    url = hfx.HF + path
    if ctx["json"]:
        events = []
        try:
            for ev, data in kitutil.stream_sse(
                    url, headers={"Authorization": f"Bearer {token}"},
                    duration_s=a.duration):
                obj = kitutil.parse_sse_json(data)
                events.append({"event": ev, "data": obj if obj is not None else data})
                if ev == "reconnect":
                    break
        except kitutil.SSEError as e:
            hfx.die(f"bucket events: {e} (does the bucket exist? `hfx store ls` "
                    "or GET /api/buckets/{ns})", hfx.EXIT_FAIL)
        hfx.jprint({"bucket": a.bucket, "duration_s": a.duration, "events": events})
        return hfx.EXIT_OK

    print(f"bucket change-feed — {ns}/{name} ({a.duration}s window)\n" + "=" * 72)
    n_changes = 0
    try:
        for ev, data in kitutil.stream_sse(
                url, headers={"Authorization": f"Bearer {token}"},
                duration_s=a.duration):
            obj = kitutil.parse_sse_json(data)
            if ev == "ready":
                print(f"  [ready]   replay done, live changes follow "
                      f"(cursor={obj.get('cursor') if obj else '?'})")
            elif ev == "changes":
                for ch in (obj or {}).get("changes", []):
                    n_changes += 1
                    size = f" {hfx.human_bytes(ch['size'])}" if ch.get("size") else ""
                    print(f"  [change]  {ch.get('op', '?'):<6} {ch.get('path', '?')}{size}")
            elif ev in ("reset", "reconnect"):
                print(f"  [{ev}]     {data} — reconnect with that cursor")
                break
            else:
                print(f"  [{ev}]     {data}")
    except kitutil.SSEError as e:
        hfx.die(f"bucket events: {e} (does the bucket exist?)", hfx.EXIT_FAIL)
    print("=" * 72)
    print(f"{n_changes} change(s) in {a.duration}s.  Trigger one: upload an object "
          "via S3 (s3.hf.co/<ns>) or POST /api/buckets/{ns}/{name}/batch.")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ notifications

def _notifications(a, ctx) -> int:
    token = ctx["env"].get("HF_TOKEN") or os.environ.get("HF_TOKEN", "")
    cookie = ctx["env"].get("HF_JWT") or os.environ.get("HF_JWT", "")
    hdrs = {"Origin": hfx.HF, "Referer": hfx.HF + "/"}

    if a.mark_all_read:
        if not token and not cookie:
            hfx.die("notifications needs HF_TOKEN (or HF_JWT cookie). Export "
                    "HF_TOKEN — see kit/AGENTS.md prerequisites.", hfx.EXIT_CONFIG)
        auth = {"token": token} if token else {"cookie": f"token={cookie}"}
        hfx.api("POST", "/api/notifications/mark-as-read", headers=hdrs,
                json_body={}, expect=(200, 201), **auth)
        print("all notifications marked read ✓")
        return hfx.EXIT_OK

    raw, used = None, ""
    if token:
        _, raw, _ = hfx.api("GET", "/api/notifications", token=token)
        used = "PAT"
    elif cookie:
        _, raw, _ = hfx.api("GET", "/api/notifications", cookie=f"token={cookie}")
        used = "cookie"
    else:
        hfx.die("notifications needs HF_TOKEN (PAT works) or the HF_JWT web-session "
                "cookie. Create a PAT at https://huggingface.co/settings/tokens, "
                "export HF_TOKEN=… — see kit/AGENTS.md prerequisites.",
                hfx.EXIT_CONFIG)
    notes = (raw or {}).get("notifications") or []
    counts = (raw or {}).get("count") or {}
    if ctx["json"]:
        hfx.jprint(raw)
        return hfx.EXIT_OK
    print(f"notifications (auth: {used}) — {len(notes)} shown · "
          f"unread {counts.get('unread', '?')} / all {counts.get('all', '?')}\n" + "=" * 72)
    if not notes:
        print("  (none)")
    for n in notes:
        repo = (n.get("repo") or {}).get("name", "?")
        disc = n.get("discussion") or {}
        title = disc.get("title") or n.get("type", "?")
        state = "read" if n.get("read") else "UNREAD"
        print(f"  [{state:<6}] {n.get('type', '?'):<18} {repo}")
        if title:
            print(f"          discussion #{disc.get('num', '?')}: {title[:70]}")
    print("\nMark everything read: hfx watch notifications --mark-all-read")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ dispatch

def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="hfx watch",
        description="Events: webhook CRUD (PAT), bucket change-feed SSE, "
                    "notifications. Evidence: findings/infra-probe.md, "
                    "findings/storage-probe.md §4a")
    pj = argparse.ArgumentParser(add_help=False)
    pj.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    pw = sub.add_parser("webhooks", parents=[pj], help="webhook CRUD")
    wsub = pw.add_subparsers(dest="wcmd", required=True)

    pls = wsub.add_parser("ls", parents=[pj], help="list webhooks")
    pls.set_defaults(fn=_webhooks_ls)

    pad = wsub.add_parser("add", parents=[pj],
                          help="create a webhook (PAT, no CSRF needed)")
    pad.add_argument("--url", required=True,
                     help="receiver URL (ntfy.sh verified; webhook.site is DNS-blocked "
                          "from HF's workers)")
    pad.add_argument("--watch", action="append", default=[],
                     help="repo to watch, e.g. owner/space (repeatable; default: none)")
    pad.add_argument("--type", default="",
                     help="force repo type space|model|dataset|bucket (default: autodetect)")
    pad.add_argument("--domains", default="repo,discussion",
                     help="event domains (default: %(default)s)")
    pad.set_defaults(fn=_webhooks_add)

    prm = wsub.add_parser("rm", parents=[pj], help="delete a webhook by id")
    prm.add_argument("--id", required=True)
    prm.set_defaults(fn=_webhooks_rm)

    pb = sub.add_parser("bucket", parents=[pj],
                        help="stream a bucket's change-feed SSE")
    pb.add_argument("bucket", help="bucket as NS/NAME")
    pb.add_argument("--duration", type=float, default=30.0,
                    help="seconds to stream (default: %(default)s)")
    pb.add_argument("--cursor", help="resume from a change-feed cursor "
                                     "(server buffers ~15 min)")
    pb.set_defaults(fn=_bucket)

    pn = sub.add_parser("notifications", parents=[pj],
                        help="list notifications (PAT or cookie)")
    pn.add_argument("--mark-all-read", action="store_true",
                    help="mark every notification read")
    pn.set_defaults(fn=_notifications)

    a = p.parse_args(argv)
    ctx["json"] = ctx.get("json") or a.json
    return a.fn(a, ctx)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False,
                                "env": {k: os.environ.get(k, "") for k in hfx.ENV_KEYS}}))
