#!/usr/bin/env python3
"""hfx gpu — ZeroGPU harness: preflight, run, and the scriptable-free-compute catalog.

Free $0 surfaces used (all verified live, findings/spaces-probe.md,
findings/infra-probe.md §D, findings/mcp-arbitrary-spaces.md,
findings/wan22-measurement.md):
  quota : GET /api/spaces/zero-gpu/quota            (PAT; GPU-s + runs, rolling 24h)
  live  : GET https://api.hf.space/v1/{owner}/{space}/sse   (anon; zero-gpu-count,
          stage, gcTimeout — ADVISORY: partial coverage, can be stale at the
          quota-reset boundary; the quota GET is authoritative)
  list  : GET /api/spaces?filter=mcp-server&expand[]=runtime (the 100+ MCP-enabled
          ZeroGPU Spaces = scriptable free media compute)

Usage:
  hfx gpu preflight [--space owner/name] [--min-runs N] [--min-sec S] [--min-gpus N]
  hfx gpu run SPACE [--fn FN] [--arg J]... [--arg-file PATH] [--out DIR]
                    [--timeout S] [--force] [--json]
  hfx gpu spaces [--pattern P] [--max-pages N] [--json]

Exit codes: 0 OK · 1 failure · 2 missing deps/config · 3 NO-GO / budget refusal.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import shutil
import sys
import time
import urllib.request

import hfx

# ------------------------------------------------------------------ constants

API_HF_SPACE = "https://api.hf.space"
# raw (session-bound) output URLs captured from the gradio_client download hook
RUN_URLS: list[str] = []
# magic-byte sniffs for the media types ZeroGPU Spaces accept as base64 data-URIs
# (mirrors the uploads-CDN allowlist, findings/uploads-cdn-probe.md — superset of
# what a gradio FileData `url` field will happily ingest server-side)
_MAGIC = [
    (b"GIF8", "image/gif"),
    (b"\x89PNG", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x1a\x45\xdf\xa3", "video/webm"),
    (b"ID3", "audio/mpeg"),
]
_EXT_FALLBACK = {
    ".gif": "image/gif", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".webp": "image/webp", ".mp4": "video/mp4",
    ".mov": "video/quicktime", ".qt": "video/quicktime", ".webm": "video/webm",
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".mpga": "audio/mpeg",
}


# ------------------------------------------------------------------ helpers

def _sniff_media(path: str) -> str | None:
    """Return a mime type if the file's magic bytes (or, failing that, its
    extension) look like an allowed media type. None = not media."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return None
    for magic, mime in _MAGIC:
        if head.startswith(magic):
            return mime
    if head[:4] == b"RIFF" and head[8:12] in (b"WEBP", b"WAVE"):
        return "image/webp" if head[8:12] == b"WEBP" else "audio/wav"
    if head[4:8] == b"ftyp":  # MP4 / MOV (brand at offset 8)
        brand = head[8:12]
        return "video/quicktime" if brand.startswith(b"qt") else "video/mp4"
    if head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):  # raw MPEG audio
        return "audio/mpeg"
    return mimetypes.guess_type(path)[0] if mimetypes.guess_type(path)[0] in \
        set(_EXT_FALLBACK.values()) and os.path.splitext(path)[1] in _EXT_FALLBACK \
        else _EXT_FALLBACK.get(os.path.splitext(path)[1].lower())


def _to_filedata(path: str) -> dict:
    """THE base64 input contract (findings/wan22-measurement.md, verified):
    remote URLs in FileData.url fail pre-GPU with a misleading 404; a base64
    data-URI in `url` ALWAYS works (bypasses server-side fetching entirely).
    path MUST be None (a str path would make gradio_client re-upload it)."""
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    mime = _sniff_media(path) or "application/octet-stream"
    return {
        "path": None,  # deliberately None — pass-through contract, never upload
        "url": f"data:{mime};base64,{b64}",
        "orig_name": os.path.basename(path),
        "meta": {"_type": "gradio.FileData"},
    }


def _coerce_arg(raw: str):
    """--arg values: valid JSON decodes to its value; anything else stays a str.
    An existing local media file auto-converts to the base64 FileData contract."""
    if os.path.isfile(raw):
        mime = _sniff_media(raw)
        if mime:
            size = os.path.getsize(raw)
            if size > 5 * 1024 * 1024:
                print(f"hfx: warning: {raw} is {hfx.human_bytes(size)} — base64 "
                      f"inflates ~4/3; >~1MB inputs may hit the Space's "
                      f"max_file_size", file=sys.stderr)
            return _to_filedata(raw)
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _quota_line(q: dict) -> str:
    """quota GET semantics (VERIFIED — findings/mcp-dynamic-spaces.md §5:
    288.79 → 276.27 after 12.53 GPU-s spent; wan22: 300 → 290.65 = 9.35
    charged): `current` = REMAINING GPU-s, `base` = the 300 cap. Used =
    base - current. (NB: scripts/media_budget.sh labels these inverted.)"""
    runs = q.get("runs") or {}
    sec_left = q.get("current") or 0
    used = (q.get("base") or 0) - sec_left
    reset = runs.get("resetsAt") or q.get("resetsAt")
    reset_s = f" · window resets {reset}" if reset else \
        " · window inactive (resetsAt null = full budget available)"
    return (f"{used:.1f} GPU-s used · {sec_left:.1f}/{q.get('base', '?')} left · "
            f"runs {runs.get('remaining', '?')}/{runs.get('limit', '?')} left"
            f"{reset_s}")


def _sse_space_state(space: str, wait_s: float = 6.0) -> dict:
    """Read the public api.hf.space events SSE for one Space. Returns
    {stage, zero_gpu_count, gc_timeout, hardware_flavor, replicas, raw_error}.
    ADVISORY only — some Spaces 404 on this service and values can be stale at
    the quota-reset boundary; the quota GET is authoritative."""
    out = {"stage": None, "zero_gpu_count": None, "gc_timeout": None,
           "hardware_flavor": None, "replicas": None, "raw_error": None}
    url = f"{API_HF_SPACE}/v1/{space}/sse"
    deadline = time.time() + wait_s
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": hfx.UA, "Accept": "text/event-stream"})
        # short socket timeout: these SSE streams tick ~1/s; a readline() that
        # blocks past the deadline should fail fast, not hang wait_s+5
        with urllib.request.urlopen(req, timeout=3) as resp:
            event = ""
            while time.time() < deadline:
                chunk = resp.readline()
                if not chunk:
                    break
                line = chunk.decode(errors="replace").rstrip("\r\n")
                if not event and line.startswith('{"error"'):
                    # api.hf.space answers some Spaces with an in-body error
                    # JSON (e.g. NOT_FOUND) and then holds the stream open
                    try:
                        out["raw_error"] = json.loads(line).get("error", line)
                    except ValueError:
                        out["raw_error"] = line
                    return out
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:") and event:
                    data = line[5:].strip()
                    if event == "stage":
                        out["stage"] = data
                    elif event == "zero-gpu-count":
                        try:
                            out["zero_gpu_count"] = int(data)
                        except ValueError:
                            pass
                    elif event == "space" and data.startswith("{"):
                        try:
                            spec = (json.loads(data).get("compute") or {}) \
                                .get("spec") or {}
                            cur = (json.loads(data).get("compute") or {}) \
                                .get("current") or {}
                            out["gc_timeout"] = spec.get("gcTimeout")
                            out["hardware_flavor"] = spec.get("hardwareFlavor")
                            out["replicas"] = ((cur.get("status") or {})
                                               .get("readyReplicas"))
                        except ValueError:
                            pass
                    event = ""
    except Exception as e:  # noqa: BLE001 — advisory endpoint, never fatal
        if out["stage"] is None and out["zero_gpu_count"] is None \
                and out["gc_timeout"] is None:
            body = getattr(e, "read", lambda: b"")()
            try:
                out["raw_error"] = json.loads(body or b"{}").get("error", str(e))
            except Exception:  # noqa: BLE001
                out["raw_error"] = str(e)
        # else: events were read before the deadline — a final readline() timeout
        # after the data is normal stream-close behavior, NOT an error
    return out


def _walk_outputs(val, out_dir: str, saved: list, urls: list):
    """Recursively collect gradio outputs: downloaded local files (gradio_client
    fetched them IN SESSION — outputs are session-bound) get copied to out_dir;
    remote URLs recorded for the log. Returns nothing (fills saved/urls)."""
    if isinstance(val, (list, tuple)):
        for v in val:
            _walk_outputs(v, out_dir, saved, urls)
    elif isinstance(val, dict):
        url = val.get("url") if isinstance(val.get("url"), str) else None
        path = val.get("path") if isinstance(val.get("path"), str) else None
        if url and url.startswith(("http://", "https://")):
            urls.append(url)
        if path and os.path.isfile(path):
            _copy_file(path, out_dir, saved)
        if url and url.startswith("data:"):
            _save_data_uri(url, out_dir, saved,
                           val.get("orig_name") or "output.bin")
    elif isinstance(val, str):
        if val.startswith(("http://", "https://")):
            urls.append(val)
        elif os.path.isfile(val):
            _copy_file(val, out_dir, saved)


def _copy_file(src: str, out_dir: str, saved: list):
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, os.path.basename(src))
    if os.path.exists(dst):
        dst = os.path.join(out_dir, f"{int(time.time())}_{os.path.basename(src)}")
    shutil.copy2(src, dst)
    saved.append(dst)


def _save_data_uri(uri: str, out_dir: str, saved: list, name: str):
    os.makedirs(out_dir, exist_ok=True)
    try:
        head, b64 = uri.split(",", 1)
        raw = base64.b64decode(b64)
        dst = os.path.join(out_dir, os.path.basename(name) or "output.bin")
        with open(dst, "wb") as fh:
            fh.write(raw)
        saved.append(dst)
    except Exception as e:  # noqa: BLE001
        print(f"hfx: warning: could not decode data-URI output: {e}",
              file=sys.stderr)


# ------------------------------------------------------------------ subcommands

def cmd_preflight(a, ctx: dict) -> int:
    """quota GO/NO-GO (+ optional live per-Space GPU availability)."""
    token = hfx.need_token(ctx["env"])
    q = hfx.zero_gpu_quota(token)
    runs = q.get("runs") or {}
    sec_left = q.get("current") or 0  # current = REMAINING (see _quota_line)
    runs_left = runs.get("remaining", 0)

    sse = _sse_space_state(a.space) if a.space else None
    reasons = []
    if runs_left < a.min_runs:
        reasons.append(f"runs remaining {runs_left} < --min-runs {a.min_runs}")
    if sec_left < a.min_sec:
        reasons.append(f"GPU-s remaining {sec_left:.1f} < --min-sec {a.min_sec}")
    if sse and sse["zero_gpu_count"] is not None and \
            sse["zero_gpu_count"] < a.min_gpus:
        reasons.append(f"live zero-gpu-count {sse['zero_gpu_count']} < "
                       f"--min-gpus {a.min_gpus} (run would QUEUE)")

    if ctx["json"]:
        hfx.jprint({"space": a.space, "quota": q, "sse": sse,
                    "verdict": "NO-GO" if reasons else "GO",
                    "reasons": reasons})
    else:
        print(f"hfx gpu preflight — ZeroGPU account budget"
              f"{' · ' + a.space if a.space else ''}")
        print("=" * 72)
        print(f"  quota (AUTHORITATIVE) : {_quota_line(q)}")
        if a.space:
            if sse["raw_error"]:
                print(f"  live SSE  (advisory)  : unavailable — {sse['raw_error']}")
                print("                         (api.hf.space coverage is partial; "
                      "the quota GET above is authoritative)")
            else:
                gc = (f"{sse['gc_timeout'] / 3600:.0f}h idle GC"
                      if sse["gc_timeout"] else "n/a")
                print(f"  live SSE  (advisory)  : stage {sse['stage']} · "
                      f"zero-gpu-count {sse['zero_gpu_count']} free GPU slot(s) · "
                      f"{sse['hardware_flavor']} · {gc} · "
                      f"{sse['replicas']} replica(s) ready")
                if sse["zero_gpu_count"] == 0:
                    print("                         (0 free slots = your run will "
                          "QUEUE — wall-clock only, NOT extra quota)")
        print("-" * 72)
        if reasons:
            print("VERDICT: NO-GO")
            for r in reasons:
                print(f"  - {r}")
            print("\nWait for the rolling-24h reset (see window resets above), or")
            print("shop another Space (`hfx gpu spaces`). REMINDER: 8 runs / 24h is")
            print("the BINDING limit — account-global across ALL ZeroGPU Spaces.")
        else:
            print("VERDICT: GO")
            print("\nREMINDER: 8 runs / rolling 24h is the BINDING limit (account-")
            print("global, across ALL public ZeroGPU Spaces); 300 GPU-s rarely binds.")
            print("Errored runs still consume a run slot — the runs counter LAGS")
            print("(recheck quota at +30 min after any error).")
        print("\nNext: hfx gpu spaces --pattern image   # shop the catalog")
        print("      hfx gpu run <space> --fn <fn> --arg '<json>' --arg ...")
    return hfx.EXIT_QUOTA if reasons else hfx.EXIT_OK


def cmd_spaces(a, ctx: dict) -> int:
    """Enumerate MCP-enabled Spaces (the scriptable free-compute catalog)."""
    token = hfx.need_token(ctx["env"])
    items, pages, url = [], 0, (
        f"{hfx.HF}/api/spaces?filter=mcp-server&sort=likes&direction=-1"
        f"&limit=100&expand%5B%5D=runtime")
    while url and pages < a.max_pages:
        st, hs, raw = hfx.http("GET", url, token=token, timeout=60)
        if st != 200:
            hfx.die(f"spaces enumeration -> {st}: {raw[:200]!r}", hfx.EXIT_FAIL)
        try:
            items += json.loads(raw)
        except ValueError:
            hfx.die(f"spaces enumeration: unparseable page {pages + 1}",
                    hfx.EXIT_FAIL)
        pages += 1
        nxt = None
        for part in (hs.get("link", "") or hs.get("Link", "")).split(","):
            if 'rel="next"' in part:
                nxt = part.split("<", 1)[1].split(">", 1)[0]
        if nxt and "expand" not in nxt:
            nxt += ("&" if "?" in nxt else "?") + "expand%5B%5D=runtime"
        url = nxt
        if url:
            time.sleep(1.0)  # be polite: 1 page/s against the api bucket

    pattern = (a.pattern or "").lower()
    shown = [s for s in items if pattern in s.get("id", "").lower()]
    zero_gpu = [s for s in items
                if str(((s.get("runtime") or {}).get("hardware") or {})
                       .get("current") or "").startswith("zero-")]
    running = [s for s in zero_gpu
               if (s.get("runtime") or {}).get("stage") == "RUNNING"]

    if ctx["json"]:
        hfx.jprint({"filter": "mcp-server", "total": len(items),
                    "zero_gpu": len(zero_gpu), "zero_gpu_running": len(running),
                    "pattern": pattern or None, "matches": len(shown),
                    "spaces": shown})
        return hfx.EXIT_OK

    print(f"hfx gpu spaces — MCP-enabled Spaces (tag: mcp-server), "
          f"{len(items)} total across {pages} page(s)")
    print(f"  ZeroGPU hardware: {len(zero_gpu)} · RUNNING: {len(running)}"
          + (f" · pattern '{a.pattern}': {len(shown)} match(es)"
             if pattern else ""))
    print("=" * 72)
    print(f"{'SPACE':<52} {'LIKES':>5}  {'HARDWARE':<10} {'STAGE':<8}")
    print("-" * 72)
    for s in shown[:100]:
        rt = s.get("runtime") or {}
        hw = ((rt.get("hardware") or {}).get("current") or "-")[:10]
        stage = (rt.get("stage") or "-")[:8]
        print(f"{s.get('id', '?'):<52} {s.get('likes', 0):>5}  {hw:<10} {stage:<8}")
    if len(shown) > 100:
        print(f"... and {len(shown) - 100} more (use --pattern to narrow, "
              f"--json for the full list)")
    print("-" * 72)
    print("Every MCP-enabled Space is callable via `hfx mcp call dynamic_space`")
    print("(each invoke = 1 ZeroGPU run) or direct Gradio via `hfx gpu run`.")
    print("Budget: 8 runs + 300 GPU-s / rolling 24h — account-GLOBAL across all.")
    print("\nNext: hfx gpu preflight --space <owner/name>   # live GPU slots")
    print("      hfx gpu run <owner/name> --fn <fn> --arg ...")
    return hfx.EXIT_OK


def cmd_run(a, ctx: dict) -> int:
    """Run one function of a public ZeroGPU Space via gradio_client.

    Mirrors the verified input/output contracts:
      * file args auto-convert to base64 data-URI FileData (remote URLs fail
        pre-GPU with a misleading 404 — findings/wan22-measurement.md)
      * outputs are session-bound: gradio_client downloads them IN THIS SESSION
        and we copy them to --out IMMEDIATELY (raw tmp URLs 403 later)
    """
    hfx.require_py([("gradio_client", "gradio_client")])
    from gradio_client import Client  # noqa: import checked above
    from gradio_client.client import Endpoint as _Endpoint

    # capture the raw (session-bound) output URLs before gradio_client swaps
    # FileData dicts for local paths — they go into the run log as evidence
    if not getattr(_Endpoint, "_hfx_patched", False):
        _orig_dl = _Endpoint._download_file

        def _rec_dl(self, x):
            try:
                if isinstance(x, dict):
                    if x.get("url"):
                        RUN_URLS.append(x["url"])
                    elif x.get("path"):
                        RUN_URLS.append(f"file={x['path']}")
            except Exception:  # noqa: BLE001 — never break the download
                pass
            return _orig_dl(self, x)

        _Endpoint._download_file = _rec_dl
        _Endpoint._hfx_patched = True
    RUN_URLS.clear()

    token = hfx.need_token(ctx["env"])

    # budget gate (refuse to spend the last run by accident) — quota is cheap
    q0 = hfx.zero_gpu_quota(token)
    runs0 = (q0.get("runs") or {})
    sec0 = q0.get("current") or 0  # current = REMAINING GPU-s
    if not a.force and (runs0.get("remaining", 0) < 1 or sec0 < 1):
        print(f"hfx: NO-GO — ZeroGPU budget exhausted ({_quota_line(q0)})", )
        print("hfx: refusing to submit (override with --force if you know better)",
              file=sys.stderr)
        return hfx.EXIT_QUOTA

    out_dir = a.out or os.path.join(os.getcwd(), "hfx-gpu-outputs")
    os.makedirs(out_dir, exist_ok=True)
    t_start = time.time()

    if not ctx["json"]:
        print(f"hfx gpu run — {a.space}")
        print(f"  budget before: {_quota_line(q0)}")

    try:
        client = Client(a.space, token=token, verbose=False)
        api = client.view_api(print_info=False, return_format="dict") or {}
    except Exception as e:  # noqa: BLE001 — bad space id, offline, gated…
        print(f"hfx: cannot load Space '{a.space}' ({str(e).splitlines()[-1][:200]})",
              file=sys.stderr)
        print("hfx: check the id with `hfx gpu spaces --pattern …`; anonymous "
              "access to ZeroGPU Spaces requires a valid HF_TOKEN",
              file=sys.stderr)
        return hfx.EXIT_FAIL
    endpoints = api.get("named_endpoints") or {}
    if not a.fn:
        print(f"hfx gpu run — endpoints of {a.space} (pick one with --fn):")
        for name, ep in endpoints.items():
            params = ", ".join(
                f"{p.get('parameter_name')}:{(p.get('python_type') or {})
                 .get('type', '?')}"
                + (f"={json.dumps(p.get('parameter_default'))[:40]}"
                   if p.get("parameter_has_default") else "")
                for p in ep.get("parameters", []))
            # gradio re-exports a re-registered fn as <base>_1, <base>_2… — the
            # signature is identical; prefer the base name (U4 friction #1)
            base, _, suffix = name.lstrip("/").rpartition("_")
            dup = ""
            if suffix.isdigit() and base and f"/{base}" in endpoints:
                dup = "   (duplicate — same fn as /%s re-exported)" % base
            print(f"  {name}({params}){dup}")
        print("\n(viewing endpoints is FREE — metadata costs no quota)")
        return hfx.EXIT_OK

    api_name = "/" + a.fn.lstrip("/")
    if api_name not in endpoints:
        print(f"hfx: fn '{a.fn}' not found. Available:", file=sys.stderr)
        for name in endpoints:
            print(f"  {name}", file=sys.stderr)
        return hfx.EXIT_FAIL

    args = []
    if a.arg_file:
        with open(a.arg_file, encoding="utf-8") as fh:
            items = json.load(fh)
        if not isinstance(items, list):
            hfx.die(f"--arg-file must contain a JSON array (got "
                    f"{type(items).__name__})", hfx.EXIT_CONFIG)
        for it in items:
            args.append(_to_filedata(it) if isinstance(it, str) and
                        os.path.isfile(it) and _sniff_media(it) else it)
    for raw in a.arg or []:
        args.append(_coerce_arg(raw))

    n_params = len(endpoints[api_name].get("parameters", []))
    if len(args) != n_params:
        print(f"hfx: warning: {api_name} declares {n_params} parameter(s) but "
              f"{len(args)} --arg(s) given — gradio may reject the call "
              f"(pre-GPU rejections cost $0 but an in-function arg error costs "
              f"a run slot)", file=sys.stderr)

    if not ctx["json"]:
        safe_args = []
        for x in args:
            if isinstance(x, dict) and str(x.get("url", "")).startswith("data:"):
                safe_args.append(f"<base64 {x.get('orig_name')} "
                                 f"({len(x['url'])} chars)>")
            else:
                safe_args.append(x)
        print(f"  calling {api_name} with {json.dumps(safe_args, default=str)[:400]}")

    err = None
    result = None
    try:
        job = client.submit(*args, api_name=api_name)
        result = job.result(timeout=a.timeout)
    except Exception as e:  # noqa: BLE001 — capture cost even on failure
        err = str(e)[:500]

    wall = time.time() - t_start
    time.sleep(2)  # let the meter settle before reading quota
    q1 = hfx.zero_gpu_quota(token)
    runs1 = (q1.get("runs") or {})
    charged = (q0.get("current") or 0) - (q1.get("current") or 0)
    runs_delta = (runs1.get("used", 0)) - (runs0.get("used", 0))

    saved, urls = [], []
    if result is not None:
        _walk_outputs(result, out_dir, saved, urls)
    urls = RUN_URLS + [u for u in urls if u not in RUN_URLS]

    log = {
        "space": a.space, "fn": api_name, "args": [
            f"<base64 {x.get('orig_name')}>" if isinstance(x, dict) and
            str(x.get("url", "")).startswith("data:") else x for x in args],
        "wall_s": round(wall, 1), "error": err,
        "quota_before": q0, "quota_after": q1,
        "gpu_s_charged": round(charged, 6), "runs_consumed": runs_delta,
        "output_files": saved, "output_urls": urls,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    log_path = os.path.join(out_dir, f"run-{int(time.time())}.json")
    with open(log_path, "w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=2, default=str)

    if ctx["json"]:
        hfx.jprint(log)
    else:
        print("-" * 72)
        if err:
            print(f"  ERROR (in {wall:.1f}s): {err}")
        else:
            print(f"  done in {wall:.1f}s wall")
        for f in saved:
            print(f"  output file : {f} ({hfx.human_bytes(os.path.getsize(f))}) "
                  f"[FETCHED IN SESSION — copy saved, this is the durable copy]")
        for u in urls:
            print(f"  output url  : {u} (session-bound — dies with the replica, "
                  f"do NOT rely on it)")
        print(f"  charged     : {charged:.2f} GPU-s · runs consumed: "
              f"{runs_delta} (now {runs1.get('used', '?')}/{runs1.get('limit', '?')}"
              f" — {runs1.get('remaining', '?')} run(s) left · "
              f"{q1.get('current', 0):.1f} GPU-s left)")
        if err:
            print("  NOTE: errored runs still consume a run slot and the runs")
            print("  counter LAGS — recheck with `hfx gpu preflight` at +30 min.")
        print(f"  run log     : {log_path}")
        print("\nNext: hfx gpu preflight   # verify remaining budget")
        print("      re-host the output durably: hfx cdn put <file> "
              "(permanent, quota-free)")

    return hfx.EXIT_FAIL if err else hfx.EXIT_OK


# ------------------------------------------------------------------ entry

def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="hfx gpu",
        description="ZeroGPU harness — preflight the free GPU budget, run "
                    "functions on public ZeroGPU Spaces, shop the MCP-enabled "
                    "catalog. Budget: 8 runs + 300 GPU-s per rolling 24h "
                    "(account-global). Evidence: findings/wan22-measurement.md")
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("preflight", help="quota GO/NO-GO (+ live per-Space "
                                          "GPU slots if --space)")
    pf.add_argument("--space", help="owner/name — also read live "
                                    "zero-gpu-count/stage from api.hf.space SSE")
    pf.add_argument("--min-runs", type=int, default=1,
                    help="refuse below N remaining runs (default 1)")
    pf.add_argument("--min-sec", type=float, default=1.0,
                    help="refuse below N remaining GPU-s (default 1)")
    pf.add_argument("--min-gpus", type=int, default=0,
                    help="refuse when live zero-gpu-count < N (default 0: "
                         "advisory only; 0 slots = queue, not failure)")
    pf.set_defaults(func=cmd_preflight)

    rn = sub.add_parser("run", help="call one function of a public ZeroGPU "
                                    "Space (gradio_client; 1 run per call)")
    rn.add_argument("space", help="owner/name of a public ZeroGPU Space")
    rn.add_argument("--fn", help="function/api name (omit to LIST endpoints, "
                                 "free — costs no quota)")
    rn.add_argument("--arg", action="append", default=[],
                    help="one positional arg, JSON-decoded when valid JSON; an "
                         "existing local media FILE auto-converts to the base64 "
                         "data-URI input contract (repeatable)")
    rn.add_argument("--arg-file", help="JSON array file with all args (strings "
                                       "that are local media files also "
                                       "auto-convert)")
    rn.add_argument("--out", help="output dir for artifacts + run log "
                                  "(default ./hfx-gpu-outputs)")
    rn.add_argument("--timeout", type=int, default=600,
                    help="seconds to wait for the call (default 600)")
    rn.add_argument("--force", action="store_true",
                    help="submit even when the budget gate says NO-GO")
    rn.set_defaults(func=cmd_run)

    sp = sub.add_parser("spaces", help="list MCP-enabled Spaces — the "
                                       "scriptable free-compute catalog")
    sp.add_argument("--pattern", help="case-insensitive substring filter on "
                                      "owner/name")
    sp.add_argument("--max-pages", type=int, default=20,
                    help="pagination cap, 100 spaces/page (default 20)")
    sp.set_defaults(func=cmd_spaces)

    a = p.parse_args(argv)
    return a.func(a, ctx)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False, "env": {}}))
