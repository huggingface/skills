#!/usr/bin/env python3
"""hfx cdn — instant media hosting via POST /uploads (quota-free, PERMANENT).

Uploads one media file to HuggingFace's /uploads surface (the web editor's
avatar/blog-image lane) and returns a global-CDN URL that sits OUTSIDE both
the storage AND bandwidth quotas: CORS `*`, HTTP Range (video seeking),
content-type preserved, byte-identical. Evidence: findings/uploads-cdn-probe.md

⚠ Uploads are PERMANENT — NO delete endpoint exists. Never upload anything
sensitive. The type allowlist is magic-byte sniffed on BOTH sides (client
first, so a rejection costs you nothing; the server re-sniffs and 415s lies).

Auth: with HF_JWT (web-session cookie) uploads land in your user namespace
/production/uploads/<userId>/; with NO cookie the ANON lane works too
(/production/uploads/noauth/ — abuse-sensitive, human pace). A PAT is NOT
web auth here (ignored → same as anon).

Rate limit: `pages` bucket — 200/5min with cookie, 100/5min anon; each upload
costs ~1-2 units and even server-rejected 415s consume one, which is why this
tool sniffs client-side BEFORE uploading. Single-shot: one file per run.

Usage: hfx cdn put FILE [--check] [--quiet] [--json]
Exit: 0 ok · 2 bad input/not in allowlist · 1 upload failed · 3 rate-limited
"""
from __future__ import annotations

import sys

import hfx

# (label, content-type) — allowlist mirrored from the server's 415 message:
# "Only GIF, JPEG, JPG, MOV, MP3, MP4, MPGA, PNG, QT, WAV, WEBM, WEBP files
# are supported" (findings/uploads-cdn-probe.md §2)


def sniff(data: bytes) -> tuple[str, str] | None:
    """Magic-byte sniff → (content_type, label) or None if not allowed."""
    if len(data) < 12:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", "PNG"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "JPEG/JPG"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", "GIF"
    if data[:4] == b"RIFF":
        if data[8:12] == b"WEBP":
            return "image/webp", "WEBP"
        if data[8:12] == b"WAVE":
            return "audio/wav", "WAV"
        return None
    if data[4:8] == b"ftyp":  # ISO-BMFF: MP4 / MOV / QT
        brand = data[8:12]
        if brand.startswith(b"qt"):
            return "video/quicktime", "QT/MOV"
        return "video/mp4", "MP4"
    if data[:3] == b"ID3":
        return "audio/mpeg", "MP3"
    if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        # MPEG audio frame sync (raw .mpga / .mp3 without ID3): 11 set bits,
        # version != reserved(01), layer != reserved(00)
        if ((data[1] >> 3) & 0x03) != 0x01 and ((data[1] >> 1) & 0x03) != 0x00:
            return "audio/mpeg", "MPGA/MP3"
        return None
    if data[:4] == b"\x1a\x45\xdf\xa3":  # EBML → webm only (matroska NOT allowed)
        if b"webm" in data[:256]:
            return "video/webm", "WEBM"
        return None
    return None


def _hdr(headers: dict, name: str) -> str:
    """Case-insensitive header lookup."""
    for k, v in headers.items():
        if k.lower() == name.lower():
            return str(v)
    return ""


def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="hfx cdn",
        description="instant media hosting: POST /uploads → permanent CDN URL "
                    "(outside storage AND bandwidth quotas; CORS * + Range). "
                    "PERMANENT — no delete exists. Allowlist: "
                    "GIF/JPEG/JPG/MOV/MP3/MP4/MPGA/PNG/QT/WAV/WEBM/WEBP.")
    sub = p.add_subparsers(dest="cmd", required=True)
    put = sub.add_parser("put", help="upload one media file, print CDN URL")
    put.add_argument("file", help="path to the media file")
    put.add_argument("--check", action="store_true",
                     help="dry-run: sniff magic bytes, print type, do NOT upload")
    put.add_argument("--quiet", action="store_true",
                     help="suppress the PERMANENT-upload warning")
    put.add_argument("--json", action="store_true",
                     help="machine-readable output {url, bytes, type}")
    a = p.parse_args(argv)
    if getattr(a, "json", False):
        ctx["json"] = True

    # ---- read + client-side sniff (a rejection here costs no rate unit)
    import os
    if not os.path.isfile(a.file):
        hfx.die(f"file not found: {a.file}", hfx.EXIT_CONFIG)
    with open(a.file, "rb") as fh:
        data = fh.read()
    if not data:
        hfx.die(f"{a.file} is empty — the server 415s empty bodies anyway",
                hfx.EXIT_CONFIG)
    got = sniff(data)
    if got is None:
        hfx.die(
            f"{a.file}: magic bytes not in the /uploads allowlist "
            f"(GIF/JPEG/JPG/MOV/MP3/MP4/MPGA/PNG/QT/WAV/WEBM/WEBP) — "
            "rejected locally, no rate-limit unit spent.\n"
            "For arbitrary files use `hfx store put` (repo storage) instead.",
            hfx.EXIT_CONFIG)
    ctype, label = got
    nbytes = len(data)

    if a.check:
        if ctx["json"]:
            hfx.jprint({"file": a.file, "type": ctype, "label": label,
                        "bytes": nbytes, "allowed": True})
        else:
            print(f"{a.file}: {label} → Content-Type {ctype} "
                  f"({hfx.human_bytes(nbytes)}) — ALLOWED (dry-run, nothing uploaded)")
        return hfx.EXIT_OK

    # ---- warn EVERY time unless --quiet (goes to stderr; stdout stays parseable)
    if not a.quiet:
        print("hfx cdn: ⚠ uploads are PERMANENT — there is no delete endpoint. "
              "This file will be publicly hosted forever.",
              file=sys.stderr)

    # ---- upload: raw body + sniffed Content-Type; cookie optional (anon lane)
    jwt = ctx["env"].get("HF_JWT") or ""
    cookie = f"token={jwt}" if jwt else ""
    if not a.quiet and not cookie:
        print("hfx cdn: no HF_JWT — using the ANON lane "
              "(/production/uploads/noauth/, 100/5min bucket). Set HF_JWT for "
              "user-scoped URLs (200/5min).", file=sys.stderr)
    st, hs, raw = hfx.http("POST", hfx.HF + "/uploads", cookie=cookie,
                           headers={"Content-Type": ctype}, body=data,
                           timeout=180)
    if st != 200:
        snippet = raw[:300].decode(errors="replace").replace("\n", " ")
        hint = _hdr(hs, "x-error-message")
        if st == 415:
            hfx.die(f"server rejected the type ({snippet or hint or '415'}) — "
                    "its sniffer is the source of truth; not billed as storage, "
                    "but a 415 still costs a rate unit", hfx.EXIT_FAIL)
        if st == 429:
            hfx.die(f"rate-limited on the pages bucket ({snippet or hint}); "
                    "retry after the window resets (see ratelimit-policy header)",
                    hfx.EXIT_QUOTA)
        hfx.die(f"POST /uploads -> {st}: {snippet or hint}", hfx.EXIT_FAIL)
    url = raw.decode(errors="replace").strip()
    if not url.startswith("https://"):
        hfx.die(f"unexpected response (not a URL): {raw[:200]!r}", hfx.EXIT_FAIL)

    # ---- rate-bucket telemetry when HF shares it (ratelimit: "pages";r=..;t=..)
    rl = _hdr(hs, "ratelimit")
    note = f" · pages bucket: {rl}" if rl else ""

    if ctx["json"]:
        hfx.jprint({"url": url, "bytes": nbytes, "type": ctype})
    else:
        print(url)
        print(f"\n  {label} · {hfx.human_bytes(nbytes)} · {ctype}{note}")
        print("\nNext steps:")
        print(f"  embed:      ![image]({url})   (blog/markdown — pairs with `hfx md render`)")
        print(f"  hot-link:   <img src=\"{url}\"> from ANY site (CORS *, Range works)")
        print(f"  verify:     curl -sI {url}")
        print("  remember:   PERMANENT, outside all quotas — findings/uploads-cdn-probe.md")
    return hfx.EXIT_OK


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False, "env": {}}))
