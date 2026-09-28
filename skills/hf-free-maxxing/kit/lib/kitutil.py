#!/usr/bin/env python3
"""kitutil — small helpers shared by the K7 command modules
(cmd_watch / cmd_social / cmd_monitor / cmd_registry / cmd_oauth).

Not a command module (no cmd_ prefix, invisible to the dispatcher).
"""
from __future__ import annotations

import base64
import json
import socket
import time
import urllib.request

import hfx

REPO_TYPES = ("space", "model", "dataset")  # bucket handled separately


class SSEError(Exception):
    pass


# ------------------------------------------------------------------ SSE

def stream_sse(url: str, *, headers: dict | None = None, duration_s: float = 30.0):
    """Yield (event, data_str) tuples from an SSE endpoint for `duration_s`
    seconds (then stop cleanly).  `: ping` comments are skipped.  Raises
    SSEError only if the initial connection fails; per-read timeouts just end
    the stream (server sent nothing).

    NOTE: we deliberately do NOT shrink the socket timeout mid-stream — a
    timeout poisons urllib's socket-file wrapper ("cannot read from timed out
    object"), so reads block until data or the overall deadline instead."""
    hdrs = {"User-Agent": hfx.UA, "Accept": "text/event-stream"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, headers=hdrs)
    deadline = time.monotonic() + max(0.5, duration_s)
    try:
        resp = urllib.request.urlopen(req, timeout=max(5.0, duration_s + 10.0))
    except Exception as e:  # noqa: BLE001 — report, don't crash
        raise SSEError(f"{e}") from e
    event, data_lines = "message", []
    try:
        with resp:
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                try:  # tighten read timeout to the remaining window (best-effort;
                    # a fired timeout only happens once the window is over anyway)
                    resp.fp.raw._sock.settimeout(remaining + 2.0)  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass
                try:
                    raw = resp.readline()
                except (TimeoutError, socket.timeout, OSError):
                    break  # overall timeout with no data => window over
                if not raw:
                    break
                line = raw.decode(errors="replace").rstrip("\r\n")
                if line == "":
                    if data_lines:  # skip empty/comment-only events
                        yield event, "\n".join(data_lines)
                    event, data_lines = "message", []
                    continue
                if line.startswith(":"):
                    continue  # ping comment
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())
    except Exception:  # noqa: BLE001 — stream cut
        pass
    if data_lines:  # trailing partial event (if it has data)
        yield event, "\n".join(data_lines)


def parse_sse_json(data: str):
    try:
        return json.loads(data)
    except (ValueError, TypeError):
        return None


# ------------------------------------------------------------------ repo typing

def detect_repo_type(token: str, repo: str, *, explicit: str = "") -> str:
    """Resolve a 'ns/name' reference to its hub type: space|model|dataset|bucket.
    explicit='' autodetects with up to 3 GETs (spaces → datasets → models)."""
    t = (explicit or "").strip().lower()
    if t:
        if t not in REPO_TYPES + ("bucket",):
            hfx.die(f"unknown repo type '{t}' (space|model|dataset|bucket)", hfx.EXIT_CONFIG)
        return t
    for rt in ("space", "dataset", "model"):  # spaces first (most common for kit tests)
        st, _, _ = hfx.http("GET", f"{hfx.HF}/api/{rt}s/{repo}", token=token)
        if st == 200:
            return rt
    # buckets: /api/buckets/{ns}/{name} (repo form ns/name works)
    st, _, _ = hfx.http("GET", f"{hfx.HF}/api/buckets/{repo}", token=token)
    if st == 200:
        return "bucket"
    hfx.die(f"could not detect type of '{repo}' (not a space/dataset/model/bucket, "
            f"or no access). Pass --type explicitly.", hfx.EXIT_FAIL)


def type_api_path(repo_type: str) -> str:
    """/api path segment for a repo type: spaces|models|datasets|buckets."""
    return f"{repo_type}s"


# ------------------------------------------------------------------ JWT

def jwt_decode(token_str: str) -> dict:
    """Decode a JWT payload WITHOUT verification (display only)."""
    try:
        part = token_str.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except Exception:  # noqa: BLE001
        return {"_note": "not a decodable JWT"}


def b64url_nopad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")
