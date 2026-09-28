#!/usr/bin/env python3
"""hfx etl — HF datasets as a FREE queryable data backend (datasets-server).

Push a CSV/JSON/JSONL/parquet to a public dataset repo → HuggingFace
auto-converts it to parquet (refs/convert/parquet, event-driven, ~seconds–min)
and serves a hosted query API over it at https://datasets-server.huggingface.co:

  upload   create/append a dataset repo (huggingface_hub upload_file)
  filter   server-side WHERE + ORDER BY (single key)     GET /filter
  search   full-text token match (100% recall, 5GB cap)  GET /search
  rows     raw pagination, deep offsets, millions of rows GET /rows
  stats    per-column describe() (mean/median/std/hist)   GET /statistics
  parquet  auto-converted parquet URLs + DuckDB one-liner GET /parquet
  splits   configs/splits + processing state + sizes      GET /splits (+/size)
  sql      (experimental) full SQL via local DuckDB over the parquet URLs
  rm       delete a whole dataset repo (teardown)         DELETE /api/repos/delete

Universal limits (live-verified, findings/datasets-etl-final.md):
  page size <= 100 · conversion+index = first 5 GB ("partial" beyond) ·
  cold start on idle datasets: 500 "index is loading" → retry after >= 60s ·
  no rate limit observed (be polite anyway; bulk extracts = parquet lane) ·
  private datasets are NOT queryable on free accounts (501; PRO $9/mo).

Usage: hfx etl <subcommand> --help
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.parse

import hfx

DS = "https://datasets-server.huggingface.co"
DEFAULT_REPO_NAME = "hf-free-maxxing-kit-etl"  # default repo name — NAMESPACE is
# resolved from the token at runtime (D1 P1-1: a hard-coded foreign namespace
# 403s for every consumer who isn't the kit author)
DEFAULT_CONFIG = "default"
DEFAULT_SPLIT = "train"
PAGE_CAP = 100                       # server hard cap on `length` (422 above)
SUPPORTED_EXT = (".csv", ".tsv", ".json", ".jsonl", ".parquet")
WARMING = ("dataset warming (cold start up to ~2-4 min after idle; the search "
           "index can lag longer) — retry in 60s")


# ------------------------------------------------------------------ helpers

def _check_repo(repo: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo or ""):
        hfx.die(f"bad repo id '{repo}' — expected <namespace>/<name> "
                f"(e.g. <you>/{DEFAULT_REPO_NAME})", hfx.EXIT_CONFIG)
    return repo


def _default_repo(token: str) -> str:
    """<your-user>/hf-free-maxxing-kit-etl — namespace resolved dynamically
    via whoami (hfx.entities), never hard-coded."""
    return f"{hfx.entities(token)[0]['name']}/{DEFAULT_REPO_NAME}"


def _check_page(limit: int, offset: int) -> None:
    if not 0 <= limit <= PAGE_CAP:
        hfx.die(f"--limit must be 0..{PAGE_CAP} (server hard cap on page size; "
                "use --offset to paginate)", hfx.EXIT_CONFIG)
    if offset < 0:
        hfx.die("--offset must be >= 0", hfx.EXIT_CONFIG)


def ds_get(path: str, params: dict, *, auth: bool = False, ctx: dict | None = None,
           timeout: int = 90, quiet_404: bool = False, transient_ok: bool = False,
           warming_retry: bool = False, poll: dict | None = None):
    """GET datasets-server. Returns parsed JSON, or None for handled 404s and
    (with transient_ok=True, used by --wait polling) transient 5xx warm-ups.
    Cold-start aware: 500/502 'index is loading' → polite message, exit 1.
    With warming_retry=True (filter/search/rows/stats): on a warming-signature
    5xx, note it on stderr and auto-retry ONCE after 60s (U6 #3); a second
    warming failure still exits 1 with the warming message.
    poll (dict, used by `filter --wait`): when passed, retryable states
    (404-not-processed, warming 5xx) are recorded into it as
    {"status", "state"} instead of just vanishing into None — lets the
    caller's timeout message say WHAT the last observed state was."""
    qs = {k: str(v) for k, v in params.items() if v not in (None, "")}
    url = f"{DS}{path}?{urllib.parse.urlencode(qs)}"
    token = hfx.need_token((ctx or {}).get("env", {})) if auth else ""
    st, _hdrs, raw = hfx.http("GET", url, token=token, timeout=timeout)

    def _err(msg: str, code: int = hfx.EXIT_FAIL):
        hfx.die(msg, code)

    if st == 0:
        if poll is not None:  # polling helper: a network hiccup is retryable
            poll["status"] = 0
            poll["state"] = "network error (will retry until the --wait deadline)"
            return None
        _err(f"network error talking to datasets-server: {raw.decode(errors='replace')[:200]}")
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        body = None

    if st == 200 and isinstance(body, dict):
        return body
    detail = ""
    if isinstance(body, dict):
        detail = str(body.get("error") or body.get("message") or body)[:300]
    if st in (500, 502, 503, 504):
        if transient_ok:
            if poll is not None:
                poll["status"] = st
                poll["state"] = ("warming — index is loading / server busy"
                                 + (f" [{detail[:100]}]" if detail else ""))
            return None  # caller (wait loop) keeps polling
        low = (detail + raw.decode(errors="replace")[:300]).lower()
        warming = ("index is loading" in low or "busier than usual" in low
                   or st == 502 or "not ready" in low)
        if warming and warming_retry:
            print(f"  {path}: datasets-server warming (cold start) — "
                  "auto-retrying once in 60s...", file=sys.stderr, flush=True)
            time.sleep(60)
            return ds_get(path, params, auth=auth, ctx=ctx, timeout=timeout,
                          quiet_404=quiet_404, transient_ok=transient_ok)
        if warming:
            _err(f"{path}: {WARMING}" + (f" [server said: {detail[:120]}]"
                                         if detail else ""))
        _err(f"{path} -> {st}: {detail or raw[:200]!r}")
    if st == 404 and quiet_404:
        if poll is not None:
            poll["status"] = st
            poll["state"] = ("404 — dataset not found or not processed yet "
                             "(a fresh upload turns queryable in ~2-3 min)")
        return None
    if st == 404:
        _err(f"dataset not found (or not processed yet — a fresh upload takes "
             f"~2-3 min to become queryable): {detail}")
    if st == 401:
        _err(f"dataset is private/gated and this call was anonymous — retry with "
             f"--auth (accepted-conditions gated repos) — {detail}")
    if st == 501:
        _err(f"private datasets are only queryable on PRO/Enterprise ($9/mo); "
             f"free querying = PUBLIC datasets only — {detail}")
    if st == 422:
        _err(f"invalid parameter (422): {detail} — where/orderby syntax: "
             f"'\"col\"=value' / '\"col\" LIKE '%x%'' / orderby '\"col\" desc' "
             f"(single column)")
    _err(f"{path} -> {st}: {detail or raw[:200]!r}")


def _duckdb_oneliner(sql: str) -> str:
    """Render the ready-to-paste shell one-liner:
    python3 -c "import duckdb; print(duckdb.sql(\"<sql>\"))" """
    q = chr(92) + '"'  # backslash-quote, as needed inside a shell "..." string
    return 'python3 -c "import duckdb; print(duckdb.sql(' + q + sql + q + '))"'


def _dtype(feat: dict) -> str:
    t = feat.get("type") or {}
    if t.get("dtype"):
        return str(t["dtype"])
    if "names" in t:
        return "class_label"
    return str(t.get("_type", "?")).lower()


def _cell(v, max_w: int = 40) -> str:
    if v is None:
        return "·"
    if isinstance(v, (list, dict)):
        v = json.dumps(v, default=str)
    s = str(v)
    return s if len(s) <= max_w else s[:max_w - 3] + "..."


def _print_table(names: list[str], rows: list[dict], schema: dict | None = None,
                 max_w: int = 40) -> None:
    hdr = names or ["(row)"]
    body = [[_cell(r.get(n), max_w) if names else _cell(r, max_w) for n in hdr]
            for r in rows]
    w = [len(h) for h in hdr]
    for row in body:
        for i, c in enumerate(row):
            w[i] = min(max(w[i], len(c)), max_w + 6)
    print("  ".join(h.ljust(w[i]) for i, h in enumerate(hdr)))
    print("  ".join("-" * x for x in w))
    for row in body:
        print("  ".join(c.ljust(w[i]) for i, c in enumerate(row)))
    if schema:
        print("\nschema: " + ", ".join(f"{n}:{schema[n]}" for n in names))


def _print_page(payload: dict, *, kind: str, offset: int, note: str = "") -> None:
    """Shared renderer for /filter, /search, /rows responses (same shape)."""
    feats = payload.get("features") or []
    names = [f.get("name", "?") for f in feats]
    schema = {f.get("name", "?"): _dtype(f) for f in feats}
    rows = [r.get("row", {}) for r in payload.get("rows") or []]
    _print_table(names, rows, schema if names else None)
    total = payload.get("num_rows_total", "?")
    per = payload.get("num_rows_per_page") or PAGE_CAP
    try:
        pages = math.ceil(int(total) / int(per)) if per else 1
        page = int(offset) // int(per) + 1
        pg = f"page {page}/{pages}"
    except (TypeError, ValueError, ZeroDivisionError):
        pg = "page ?"
    extra = f" · {note}" if note else ""
    n = len(rows)
    print(f"\n{n} row{'s' if n != 1 else ''} [{kind}] · num_rows_total={total} "
          f"({pg}) · partial={payload.get('partial', False)}{extra}")


def _page_json(payload: dict, *, repo: str, kind: str, offset: int) -> None:
    feats = payload.get("features") or []
    hfx.jprint({
        "repo": repo, "kind": kind, "offset": offset,
        "rows": [r.get("row", {}) for r in payload.get("rows") or []],
        "num_rows_total": payload.get("num_rows_total"),
        "num_rows_per_page": payload.get("num_rows_per_page"),
        "partial": payload.get("partial", False),
        "schema": {f.get("name", "?"): _dtype(f) for f in feats},
    })


_SQL_KW = {"and", "or", "not", "like", "in", "is", "null", "true", "false", "between"}


def _norm_where(w: str) -> str:
    """Bare columns → quoted ("id=25" -> '"id"=25'). Pass through untouched if
    the user already used double quotes (server syntax: "col"='v' AND ...)."""
    if '"' in w:
        return w
    out = []
    for seg in re.split(r"('[^']*')", w):
        if seg.startswith("'") and seg.endswith("'") and len(seg) >= 2:
            out.append(seg)
            continue
        out.append(re.sub(r"[A-Za-z_][A-Za-z0-9_]*",
                          lambda m: m.group(0) if m.group(0).lower() in _SQL_KW
                          else f'"{m.group(0)}"', seg))
    return "".join(out)


def _norm_orderby(ob: str) -> str:
    """'score desc' -> '"score" desc' (column must be double-quoted server-side;
    direction optional, default asc, case-insensitive, SINGLE column only)."""
    ob = (ob or "").strip()
    if not ob or ob.startswith('"'):
        return ob
    parts = ob.split(None, 1)
    col = f'"{parts[0]}"'
    return f"{col} {parts[1]}".strip() if len(parts) > 1 else col


# ------------------------------------------------------------------ subcommands

def cmd_upload(a: argparse.Namespace, ctx: dict) -> int:
    hfx.require_py([("huggingface_hub", "huggingface_hub<2.0")])
    path = a.file
    if not os.path.isfile(path):
        hfx.die(f"no such file: {path}", hfx.EXIT_CONFIG)
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXT:
        hfx.die(f"unsupported file type '{ext}' — supported: "
                f"{'/'.join(SUPPORTED_EXT)} (one data file per repo is the "
                "safe pattern; heterogeneous multi-file repos need configs YAML)",
                hfx.EXIT_CONFIG)
    token = hfx.need_token(ctx["env"])
    if not a.repo:  # D1 P1-1: namespace resolved from the token, never baked in
        a.repo = _default_repo(token)
    _check_repo(a.repo)
    from huggingface_hub import HfApi
    api = HfApi(token=token)

    size = os.path.getsize(path)
    try:
        api.create_repo(repo_id=a.repo, repo_type="dataset", private=False,
                        exist_ok=True)
        fname = a.path or os.path.basename(path)
        rev = api.upload_file(path_or_fileobj=path, path_in_repo=fname,
                              repo_id=a.repo, repo_type="dataset",
                              commit_message=a.message or f"hfx etl upload: {fname}")
        info = api.dataset_info(a.repo)
    except Exception as e:  # noqa: BLE001 — no tracebacks (D1 P1-3)
        resp = getattr(e, "response", None)  # HfHubHTTPError carries .response
        status = (getattr(e, "status_code", None)
                  or getattr(resp, "status_code", None))
        if status in (401, 403):
            hfx.die(f"upload to {a.repo} refused ({status}): token lacks write "
                    "permission (role: write) or the repo belongs to another "
                    f"namespace — use --repo <you>/{DEFAULT_REPO_NAME} or your "
                    "own <ns>/<name>", hfx.EXIT_FAIL)
        lines = [l for l in str(e).splitlines()
                 if l.strip() and "Request ID" not in l]
        hfx.die(f"upload failed: {(lines[0] if lines else str(e))[:300]}",
                hfx.EXIT_FAIL)
    rev_str = rev if isinstance(rev, str) else (getattr(rev, "oid", "")
                                                or str(getattr(rev, "commit_url", rev)))
    rev_oid = rev_str.rstrip("/").split("/")[-1] if "/" in rev_str else rev_str
    url = f"{hfx.HF}/datasets/{a.repo}"
    out = {
        "repo": a.repo, "path_in_repo": fname, "bytes": size,
        "revision": rev_oid, "private": bool(getattr(info, "private", False)),
        "url": url, "file_url": f"{url}/blob/main/{fname}",
    }
    if ctx["json"] or a.json:
        hfx.jprint(out)
        return hfx.EXIT_OK
    print(f"uploaded  {fname} ({hfx.human_bytes(size)}) -> {a.repo} "
          f"@ {str(rev_oid)[:8]}")
    print(f"dataset   {url}")
    print(f"file      {out['file_url']}")
    if out["private"]:
        print("\nWARNING: repo is PRIVATE — datasets-server only queries PUBLIC "
              "datasets on free accounts (501 otherwise).")
    print("""
conversion: HF auto-converts to parquet on branch refs/convert/parquet —
event-driven, appears in ~seconds-minutes; filter/search/rows/stats work
~2-3 min after the commit. Same path_in_repo = replace (new revision);
a NEW data file may break single-config conversion (keep one file per repo
unless you add a configs: YAML).

next:
  hfx etl splits %s --wait 180        # poll until queryable
  hfx etl filter %s --where "score>0.5" --orderby "score desc"
  hfx etl parquet %s                  # parquet URL + DuckDB one-liner
""" % (a.repo, a.repo, a.repo))
    return hfx.EXIT_OK


FILTER_POLL_INTERVAL = 20  # seconds between --wait polls (findings: warming
# lasts minutes and recovers on retry >=60s; 20s is polite + responsive —
# datasets-server has no observed rate limit, and each 5xx fails fast ~20s)


def cmd_filter(a: argparse.Namespace, ctx: dict) -> int:
    _check_repo(a.repo)
    _check_page(a.limit, a.offset)
    if not a.where and not a.orderby:
        hfx.die("give --where and/or --orderby (plain pagination = `hfx etl rows`)",
                hfx.EXIT_CONFIG)
    params = {"dataset": a.repo, "config": a.config, "split": a.split,
              "offset": a.offset, "length": a.limit}
    if a.where:
        params["where"] = _norm_where(a.where)
    if a.orderby:
        params["orderby"] = _norm_orderby(a.orderby)

    # `--wait SECONDS`: /filter is ASYNC-under-the-hood from the consumer's
    # view — a fresh upload 404s until processed, and the filter index warms
    # lazily (500 "index is loading") on first touch / after idle eviction.
    # Poll until the result is queryable (HTTP 200), then print it.
    wait_info = None
    if a.wait:
        if a.wait < 1:
            hfx.die("--wait must be >= 1 second", hfx.EXIT_CONFIG)
        deadline = time.time() + a.wait
        t0 = time.time()
        attempt, d, last = 0, None, {}
        print(f"  polling /filter until queryable (max {a.wait}s, first check "
              "now, then every " + f"{FILTER_POLL_INTERVAL}s)...", file=sys.stderr,
              flush=True)
        while True:
            attempt += 1
            last = {}
            params["_"] = int(time.time() * 1000)  # cache-buster (CDN caches 120s)
            d = ds_get("/filter", params, auth=a.auth, ctx=ctx, timeout=30,
                       transient_ok=True, quiet_404=True, poll=last)
            if d is not None:
                break
            if time.time() >= deadline:
                hfx.die(f"filter still not queryable after {a.wait}s — last "
                        f"state: {last.get('state', 'no response')}. The filter "
                        "index warms lazily (minutes on first-ever touch / idle "
                        "datasets). Try: a longer window (hfx etl filter ... "
                        f"--wait 300), check conversion (hfx etl splits {a.repo} "
                        f"--wait 180), or use /rows which warms separately "
                        f"(hfx etl rows {a.repo})", hfx.EXIT_FAIL)
            left = int(deadline - time.time())
            print(f"  ... {last.get('state', '?')} — {left}s left",
                  file=sys.stderr, flush=True)
            time.sleep(min(FILTER_POLL_INTERVAL, max(1, left)))
        wait_info = {"waited_s": round(time.time() - t0, 1), "attempts": attempt,
                     "queryable": True}
        print(f"  filter queryable — attempt {attempt}, "
              f"{wait_info['waited_s']:.0f}s", file=sys.stderr, flush=True)
    else:
        d = ds_get("/filter", params, auth=a.auth, ctx=ctx, warming_retry=True)
    note = ("num_rows_total = MATCH count (where present)" if a.where
            else "num_rows_total = full count")
    if a.orderby:
        note += f" · orderby={params['orderby']}"
    if ctx["json"] or a.json:
        out = {"repo": a.repo, "kind": "filter", "offset": a.offset,
               "rows": [r.get("row", {}) for r in d.get("rows") or []],
               "num_rows_total": d.get("num_rows_total"),
               "num_rows_per_page": d.get("num_rows_per_page"),
               "partial": d.get("partial", False),
               "schema": {f.get("name", "?"): _dtype(f)
                          for f in d.get("features") or []}}
        if wait_info is not None:
            out["wait"] = wait_info
        hfx.jprint(out)
    else:
        _print_page(d, kind="filter", offset=a.offset, note=note)
    return hfx.EXIT_OK


def cmd_search(a: argparse.Namespace, ctx: dict) -> int:
    _check_repo(a.repo)
    _check_page(a.limit, a.offset)
    if not a.query:
        hfx.die("--query is required (token match, 100% recall, first 5GB indexed)",
                hfx.EXIT_CONFIG)
    d = ds_get("/search", {"dataset": a.repo, "config": a.config,
                           "split": a.split, "query": a.query,
                           "offset": a.offset, "length": a.limit},
               auth=a.auth, ctx=ctx, warming_retry=True)
    if ctx["json"] or a.json:
        _page_json(d, repo=a.repo, kind="search", offset=a.offset)
    else:
        _print_page(d, kind="search", offset=a.offset,
                    note=f"query='{a.query}' token-match")
    return hfx.EXIT_OK


def cmd_rows(a: argparse.Namespace, ctx: dict) -> int:
    _check_repo(a.repo)
    _check_page(a.limit, a.offset)
    d = ds_get("/rows", {"dataset": a.repo, "config": a.config,
                         "split": a.split, "offset": a.offset,
                         "length": a.limit},
               auth=a.auth, ctx=ctx, warming_retry=True)
    if ctx["json"] or a.json:
        _page_json(d, repo=a.repo, kind="rows", offset=a.offset)
    else:
        _print_page(d, kind="rows", offset=a.offset,
                    note="deep offsets OK (verified at 6.4M rows)")
    return hfx.EXIT_OK


def cmd_stats(a: argparse.Namespace, ctx: dict) -> int:
    _check_repo(a.repo)
    d = ds_get("/statistics", {"dataset": a.repo, "config": a.config,
                               "split": a.split}, auth=a.auth, ctx=ctx,
               warming_retry=True)
    if ctx["json"] or a.json:
        hfx.jprint(d)
        return hfx.EXIT_OK
    print(f"{a.repo} [{a.config}/{a.split}]  num_examples="
          f"{d.get('num_examples')}  partial={d.get('partial', False)}")
    for st in d.get("statistics") or []:
        name, ctype, cs = st.get("column_name"), st.get("column_type"), \
            st.get("column_statistics") or {}
        if ctype in ("int", "float", "int64", "float64", "bool"):
            h = cs.get("histogram") or {}
            edges = h.get("bin_edges") or []
            rng = f" over [{edges[0]}, {edges[-1]}]" if edges else ""
            print(f"  {name:<20} {ctype:<7} min={cs.get('min')} max={cs.get('max')} "
                  f"mean={cs.get('mean')} median={cs.get('median')} "
                  f"std={cs.get('std')} nan={cs.get('nan_count')} "
                  f"hist={len(h.get('hist') or [])} bins{rng}")
        elif ctype == "string_label":
            freq = sorted((cs.get("frequencies") or {}).items(),
                          key=lambda kv: -kv[1])
            top = ", ".join(f"{k}x{v}" for k, v in freq[:5])
            more = f" (+{len(freq) - 5} more)" if len(freq) > 5 else ""
            print(f"  {name:<20} label   n_unique={cs.get('n_unique')} "
                  f"nan={cs.get('nan_count')} top: {top}{more}")
        elif ctype == "string_text":
            print(f"  {name:<20} text    len min={cs.get('min')} max={cs.get('max')} "
                  f"mean={round(cs.get('mean') or 0, 2)} "
                  f"median={cs.get('median')} nan={cs.get('nan_count')}")
        else:
            print(f"  {name:<20} {ctype:<7} {json.dumps(cs, default=str)[:160]}")
    return hfx.EXIT_OK


def _parquet_files(repo: str, a: argparse.Namespace, ctx: dict) -> list[dict]:
    d = ds_get("/parquet", {"dataset": repo}, auth=a.auth, ctx=ctx)
    files = d.get("parquet_files") or []
    if not files:
        pend = d.get("pending") or []
        if pend:
            hfx.die(f"parquet conversion still pending: {pend} — "
                    f"{WARMING}", hfx.EXIT_FAIL)
        hfx.die(f"no parquet files (conversion failed?) — failed: "
                f"{d.get('failed')} · check https://huggingface.co/datasets/{repo}"
                " (multi-file heterogeneous repos need a configs: YAML)")
    return files


def cmd_parquet(a: argparse.Namespace, ctx: dict) -> int:
    _check_repo(a.repo)
    files = _parquet_files(a.repo, a, ctx)
    if ctx["json"] or a.json:
        hfx.jprint({"repo": a.repo, "parquet_files": files})
        return hfx.EXIT_OK
    print(f"{a.repo} — auto-converted parquet (branch refs/convert/parquet):")
    for f in files:
        print(f"  {f['config']}/{f['split']}/{f['filename']}  "
              f"{hfx.human_bytes(f.get('size'))}  {f['url']}")
    url = files[0]["url"]
    one = _duckdb_oneliner(f"SELECT * FROM '{url}' LIMIT 10")
    print(f"""
DuckDB one-liner (full SQL over HTTPS — no download step):
  {one}

This is the analytics lane: GROUP BY / JOIN / window functions — everything
/filter can't do. Cross-repo JOINs work too (FROM '<url1>' a JOIN '<url2>' b ...).
Or let the kit run it:  hfx etl sql {a.repo} --query "SELECT count(*) FROM data"
Note: resolver rate bucket for /resolve downloads = 5000/5min authed (3000 anon);
signed CDN URLs behind the 302 expire ~10 min — never cache them, share the
resolve URL instead.""")
    return hfx.EXIT_OK


def cmd_splits(a: argparse.Namespace, ctx: dict) -> int:
    _check_repo(a.repo)
    deadline = time.time() + a.wait if a.wait else 0.0
    if a.wait:
        print(f"  waiting for conversion (first poll in {min(60, a.wait)}s; "
              "typically ~2-3 min)...", flush=True)
        time.sleep(min(60, a.wait))
    while True:
        params = {"dataset": a.repo}
        if a.wait:
            params["_"] = int(time.time() * 1000)  # cache-buster (CDN caches 120s)
        d = ds_get("/splits", params, auth=a.auth, ctx=ctx, timeout=30,
                   quiet_404=bool(a.wait),  # fresh upload = 404 until processed
                   transient_ok=bool(a.wait))  # cold-start 500s -> keep polling
        ready = bool(d and d.get("splits"))
        if ready or not deadline:
            break
        if time.time() >= deadline:
            hfx.die(f"still not queryable after {a.wait}s — conversion usually "
                    f"lands in ~2-3 min; retry later: hfx etl splits {a.repo}")
        left = int(deadline - time.time())
        state = "warming/processing" if d is None else \
            f"pending={len(d.get('pending') or [])}"
        print(f"  ... {state} — {left}s left", flush=True)
        time.sleep(min(25, max(2, left)))

    # U6 #2: READY (parquet converted) ≠ queryable (indexes warm) — after a
    # --wait READY, one bounded /rows?length=1 probe tells the truth.
    probe = None
    if a.wait and ready:
        sp0 = ((d or {}).get("splits") or [{}])[0]
        qs = urllib.parse.urlencode(
            {"dataset": a.repo, "config": sp0.get("config", DEFAULT_CONFIG),
             "split": sp0.get("split", DEFAULT_SPLIT), "offset": 0, "length": 1})
        tok = hfx.need_token((ctx or {}).get("env", {})) if a.auth else ""
        st_p, _h, _b = hfx.http("GET", f"{DS}/rows?{qs}", token=tok, timeout=90)
        probe = "ok" if st_p == 200 else f"warming (HTTP {st_p})"

    size_map, s = {}, None
    if a.size:
        s = ds_get("/size", {"dataset": a.repo}, auth=a.auth, ctx=ctx)
        for sp in (s.get("size") or {}).get("splits") or []:
            size_map[(sp.get("config"), sp.get("split"))] = sp
    if ctx["json"] or a.json:
        hfx.jprint({"repo": a.repo, "splits": (d or {}).get("splits"),
                    "pending": (d or {}).get("pending"),
                    "failed": (d or {}).get("failed"),
                    "size": (s.get("size") if s else None),
                    "rows_probe": probe})
        return hfx.EXIT_OK
    print(f"{a.repo}")
    for sp in (d or {}).get("splits") or []:
        key = (sp.get("config"), sp.get("split"))
        sz = size_map.get(key) or {}
        extra = (f"rows={sz.get('num_rows', '?')} "
                 f"orig={hfx.human_bytes(sz.get('num_bytes_original_files'))} "
                 f"parquet={hfx.human_bytes(sz.get('num_bytes_parquet_files'))}"
                 ) if sz else "rows/bytes: size not ready yet"
        print(f"  {sp['config']}/{sp['split']:<14} READY  {extra}")
    for sp in (d or {}).get("pending") or []:
        print(f"  {sp.get('config', '?')}/{sp.get('split', '?'):<14} PENDING")
    for sp in (d or {}).get("failed") or []:
        print(f"  {sp.get('config', '?')}/{sp.get('split', '?'):<14} FAILED")
    if not ((d or {}).get("splits") or (d or {}).get("pending")
            or (d or {}).get("failed")):
        print("  (no splits yet — fresh upload? conversion takes ~2-3 min)")
    if (d or {}).get("pending"):
        print(f"\n{WARMING}")
    if probe == "ok":
        print("  queryable  yes — /rows probe OK (filter/search/stats good to go)")
    elif probe is not None:
        print("  READY but still warming — /rows probe failed; query endpoints "
              "may 500 for ~1-2 more min (filter/search/rows/stats auto-retry "
              "once after 60s)")
        return hfx.EXIT_QUOTA  # distinct exit: converted but not yet queryable
    return hfx.EXIT_OK


def cmd_rm(a: argparse.Namespace, ctx: dict) -> int:
    """Teardown: delete a whole dataset REPO (U6 #1) via the verified
    DELETE /api/repos/delete route (same one huggingface_hub.delete_repo and
    hfx host rm use; body {name, organization, type:'dataset'})."""
    repo = _check_repo(a.repo)
    token = hfx.need_token(ctx["env"])
    ns, name = repo.split("/", 1)

    # what will be deleted (authed existence + visibility read)
    st, info, _ = hfx.api("GET", f"/api/datasets/{repo}", token=token,
                          expect=(200, 404))
    if st == 404:
        hfx.die(f"dataset {repo} not found (already deleted?) — check what "
                f"exists: hfx store ls", hfx.EXIT_FAIL)
    time.sleep(1)  # API pacing
    private = bool((info or {}).get("private"))

    if not a.yes:  # safety: show what goes, refuse to act
        out = {"op": "rm", "repo": repo, "private": private,
               "would_delete": True, "confirm_cmd": f"hfx etl rm {repo} --yes"}
        if ctx["json"] or a.json:
            hfx.jprint(out)
            return hfx.EXIT_QUOTA
        print(f"hfx etl rm — WOULD DELETE dataset {repo} "
              f"({'private' if private else 'public'}): every file, its git "
              "history and the datasets-server views (quota reclaims ~1-2 min)")
        print(f"  confirm    hfx etl rm {repo} --yes")
        return hfx.EXIT_QUOTA  # safety refusal (same convention as hfx host rm)

    st, _, raw = hfx.api("DELETE", "/api/repos/delete", token=token,
                         json_body={"name": name, "organization": ns,
                                    "type": "dataset"})
    time.sleep(1)  # settle before the verification read
    st2, _, _ = hfx.api("GET", f"/api/datasets/{repo}", token=token,
                        expect=(200, 404))
    gone = st2 == 404
    out = {"op": "rm", "repo": repo, "deleted": True, "private": private,
           "verified_404": gone,
           "note": "quota reclaims within ~1-2 min; datasets-server views lapse "
                   "on their next refresh (verify: hfx status)"}
    if ctx["json"] or a.json:
        hfx.jprint(out)
        return hfx.EXIT_OK
    print(f"hfx etl rm — dataset {repo} deleted (DELETE /api/repos/delete)")
    print(f"  verified   {'yes — authed GET -> 404' if gone else 'pending — still 200 right after the delete; re-check in ~1 min'}")
    print("  quota      reclaims within ~1-2 min (verify: hfx status)")
    return hfx.EXIT_OK


def cmd_sql(a: argparse.Namespace, ctx: dict) -> int:
    """EXPERIMENTAL: full SQL (GROUP BY/JOIN/window fns) via local DuckDB over
    the dataset's auto-converted parquet URLs. The query runs against view
    `data` (= chosen config/split)."""
    _check_repo(a.repo)
    files = _parquet_files(a.repo, a, ctx)
    # pick config/split: requested, else default/train, else first available
    want = [(a.config, a.split)] if (a.config and a.split) else []
    want += [(DEFAULT_CONFIG, DEFAULT_SPLIT), (files[0]["config"], files[0]["split"])]
    chosen = next(((c, s) for c, s in want
                   if any(f["config"] == c and f["split"] == s for f in files)),
                  None)
    if not chosen:
        hfx.die(f"config/split not found — available: "
                f"{sorted({(f['config'], f['split']) for f in files})}",
                hfx.EXIT_CONFIG)
    urls = [f["url"] for f in files
            if (f["config"], f["split"]) == chosen]
    files_sql = "[" + ", ".join(f"'{u}'" for u in urls) + "]"

    try:
        import duckdb  # noqa: PLC0415 — optional dep
    except ImportError:
        one = _duckdb_oneliner(f"SELECT count(*) FROM '{urls[0]}'")
        hfx.die("duckdb not installed (optional dep) — manual one-liner:\n"
                f"  {one}\n"
                "install with:  pip install --user duckdb", hfx.EXIT_CONFIG)

    t0 = time.time()
    con = duckdb.connect()
    for stmt in ("INSTALL httpfs", "LOAD httpfs"):
        try:
            con.execute(stmt)
        except Exception:  # noqa: BLE001 — extension may be autoloaded already
            pass
    alias = re.sub(r"[^a-zA-Z0-9_]", "_", a.repo)
    con.execute(f"CREATE VIEW data AS SELECT * FROM read_parquet({files_sql})")
    con.execute(f"CREATE VIEW {alias} AS SELECT * FROM data")
    cur = con.execute(a.query)
    cols = [d[0] for d in cur.description] if cur.description else []
    fetched = cur.fetchall()
    rows = [dict(zip(cols, r)) for r in fetched]
    elapsed = time.time() - t0
    if ctx["json"] or a.json:
        hfx.jprint({"repo": a.repo, "config": chosen[0], "split": chosen[1],
                    "parquet_urls": urls, "columns": cols, "rows": rows,
                    "elapsed_s": round(elapsed, 2)})
        return hfx.EXIT_OK
    if cols:
        _print_table(cols, rows)
    else:
        print("(no result set)")
    print(f"\n{len(rows)} rows · SQL over {chosen[0]}/{chosen[1]} "
          f"({len(urls)} parquet file(s) over HTTPS) · view: data (= {alias}) "
          f"· {elapsed:.2f}s · EXPERIMENTAL")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ entry

def run(argv: list[str], ctx: dict) -> int:
    p = argparse.ArgumentParser(
        prog="hfx etl",
        description="HF datasets as a free queryable data backend: upload → "
                    "auto-parquet → filter/search/rows/stats; DuckDB for full "
                    "SQL. Evidence: findings/datasets-etl-final.md",
        epilog="limits: page<=100 · first 5GB indexed/converted · cold start: "
               "idle datasets 500 'index is loading' → retry in 60s · public "
               "datasets only (private = PRO). No datasets-server rate limit "
               "observed — be polite anyway.")
    p.add_argument("--json", dest="top_json", action="store_true",
                   help="machine-readable output")
    sub = p.add_subparsers(dest="sub", required=True, metavar="subcommand")

    up = sub.add_parser("upload", help="create/append a dataset repo (default "
                        f"<your-user>/{DEFAULT_REPO_NAME} — namespace resolved "
                        "from your token) with FILE.csv/.json/.jsonl/.parquet")
    up.add_argument("file", help="local data file to upload")
    up.add_argument("--repo", default=None,
                    help=f"target dataset repo <ns>/<name> (default: "
                         f"<your-user>/{DEFAULT_REPO_NAME}, resolved from your "
                         "token at runtime)")
    up.add_argument("--path", help="path_in_repo (default: file basename; same "
                    "path = replace via new commit)")
    up.add_argument("--message", help="commit message")
    up.add_argument("--json", action="store_true")
    up.set_defaults(fn=cmd_upload)

    rm_p = sub.add_parser("rm", help="delete a whole dataset repo (teardown) — "
                          "shows what would go; requires --yes")
    rm_p.add_argument("repo", help="dataset repo <ns>/<name> to delete")
    rm_p.add_argument("--yes", action="store_true",
                      help="actually delete (without it: dry-run + confirm hint)")
    rm_p.add_argument("--json", action="store_true")
    rm_p.set_defaults(fn=cmd_rm)

    for name, help_, fn in (
        ("filter", "server-side WHERE + ORDER BY: --where '\"col\">5 AND "
         "\"name\" LIKE \'%%x%%\'\" --orderby '\"col\" desc' (single column)", cmd_filter),
        ("search", "full-text token match (100%% recall, first 5GB indexed)", cmd_search),
        ("rows", "raw paginated rows (deep offsets OK, millions of rows)", cmd_rows),
        ("stats", "per-column describe(): mean/median/std/histograms", cmd_stats),
        ("parquet", "auto-converted parquet URLs + DuckDB one-liner", cmd_parquet),
        ("splits", "configs/splits + processing state (+ --size for bytes/rows)", cmd_splits),
        ("sql", "EXPERIMENTAL: full SQL via local DuckDB over the parquet URLs",
         cmd_sql),
    ):
        s = sub.add_parser(name, help=help_)
        s.add_argument("repo", help="dataset repo <ns>/<name>")
        if name in ("filter", "search", "rows"):
            s.add_argument("--limit", type=int, default=10,
                           help=f"rows per page 0..{PAGE_CAP} (server hard cap; default 10)")
            s.add_argument("--offset", type=int, default=0,
                           help="row offset (pages the sorted window for --orderby)")
        if name in ("filter", "search", "rows", "stats", "parquet", "splits", "sql"):
            s.add_argument("--auth", action="store_true",
                           help="send HF_TOKEN (gated datasets you've accepted; "
                                "anonymous is default = CDN-cache friendly)")
        if name in ("filter", "search", "rows", "stats", "sql"):
            s.add_argument("--config", default=DEFAULT_CONFIG,
                           help=f"dataset config (default: {DEFAULT_CONFIG})")
            s.add_argument("--split", default=DEFAULT_SPLIT,
                           help=f"dataset split (default: {DEFAULT_SPLIT})")
        if name == "filter":
            s.add_argument("--where", help='server-side WHERE: "col"=25 / '
                         '"name" LIKE \'%%x%%\' / ops = <> > >= <, AND/OR + parens '
                         "(bare column names are auto-quoted)")
            s.add_argument("--orderby", help='sort: "col" [asc|desc] — default '
                         "asc, SINGLE column (multi-key -> 422); e.g. 'score desc'")
            s.add_argument("--wait", type=int, default=0, metavar="SECONDS",
                           help="poll until the filter result is QUERYABLE, then "
                                "print it — fresh uploads 404 until processed "
                                "(~2-3 min) and the filter index warms lazily "
                                "(500 'index is loading', minutes on first-ever "
                                "touch); polls every 20s up to SECONDS, exit 1 "
                                "with the last observed state on timeout")
        if name == "search":
            s.add_argument("--query", help="token(s) to match (no ranking/highlights)")
        if name == "splits":
            s.add_argument("--wait", type=int, default=0, metavar="SECONDS",
                           help="poll until queryable (max seconds; e.g. --wait 180)")
            s.add_argument("--size", action="store_true", default=True,
                           help="also fetch /size for numBytes/numRows (default on)")
            s.add_argument("--no-size", dest="size", action="store_false",
                           help="skip the /size call")
        if name == "sql":
            s.add_argument("--query", required=True,
                           help='SQL against view "data", e.g. "SELECT count(*) '
                           'FROM data" / "SELECT name, avg(score) v FROM data '
                           'GROUP BY name ORDER BY v DESC"')
        if name != "upload":
            s.add_argument("--json", action="store_true")
        s.set_defaults(fn=fn)

    a = p.parse_args(argv)
    if ctx.get("json") or getattr(a, "top_json", False):
        ctx = dict(ctx, json=True)
    try:
        return a.fn(a, ctx)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — consumer CLI: no tracebacks
        hfx.die(f"{getattr(a, 'sub', '?')}: {type(e).__name__}: "
                f"{str(e).splitlines()[0][:300] if str(e) else ''}",
                hfx.EXIT_FAIL)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False, "env": {}}))
