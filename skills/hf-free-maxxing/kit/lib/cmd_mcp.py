#!/usr/bin/env python3
"""hfx mcp — hosted MCP client for https://huggingface.co/mcp.

Plain JSON-RPC 2.0 over HTTP POST (protocol 2025-03-26), PAT Bearer.
Server: huggingface.co/mcp (canonical: the evalstate/hf-mcp-server Space);
11 tools on this account with every built-in enabled (verified live,
findings/mcp-probe.md, findings/review-compute-cluster.md R2).

Usage:
  hfx mcp tools                                   # initialize + tools/list
  hfx mcp call TOOL [--args-json '{...}'] [--out DIR]
  hfx mcp resources [--uri skill://hf-cli/SKILL.md]

Gotchas baked in (findings/mcp-probe.md / mcp-dynamic-spaces.md):
  * responses are plain JSON (not SSE-framed) — but keep the dual Accept header
  * mcp-session-id response header is REQUIRED after initialize
  * dynamic_space: `invoke` takes `parameters` as a JSON-encoded STRING
  * every dynamic_space invoke = 1 ZeroGPU run (8/24h account-global budget)
  * hf_sandbox/hf_jobs create → 402 on free accounts (prepaid credits only)

Exit codes: 0 OK · 1 failure/tool-error · 2 missing config · 3 budget refusal.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time

import hfx

MCP_URL = "https://huggingface.co/mcp"
PROTO = "2025-03-26"
CLIENT_INFO = {"name": "hfx-kit", "version": "0.1"}

# per-tool footnotes shown in `hfx mcp tools` (verified behaviors)
_NOTES = {
    "dynamic_space": "discover/view_parameters are FREE; every invoke = 1 "
                     "ZeroGPU run (8/24h account-global — the binding limit)",
    "hf_sandbox": "create needs PREPAID credits — 402 on free accounts",
    "hf_jobs": "run/scheduled need PREPAID credits — 402 on free accounts",
    "hf_sandbox_exec": "needs a live (paid) sandbox",
    "hf_fs_write": "writes to repos/buckets (PAT write role)",
}


# ------------------------------------------------------------------ transport

def _rpc(token: str, method: str, params: dict | None = None,
         id_: int | None = None, sid: str | None = None,
         timeout: int = 180) -> tuple[dict | None, str | None]:
    """One JSON-RPC call. Returns (parsed_body, session_id)."""
    body: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    if id_ is not None:
        body["id"] = id_
    headers = {"Accept": "application/json, text/event-stream",
               "Content-Type": "application/json"}
    if sid:
        headers["mcp-session-id"] = sid
    st, hs, raw = hfx.http("POST", MCP_URL, token=token, headers=headers,
                           body=json.dumps(body).encode(), timeout=timeout)
    if st not in (200, 202):
        hfx.die(f"MCP {method} -> HTTP {st}: "
                f"{raw[:300].decode(errors='replace')}", hfx.EXIT_FAIL)
    parsed = None
    if raw:
        try:
            parsed = json.loads(raw)
        except ValueError:
            hfx.die(f"MCP {method}: unparseable response ({len(raw)} bytes)",
                    hfx.EXIT_FAIL)
    new_sid = (hs.get("mcp-session-id") or hs.get("Mcp-Session-Id")
               or hs.get("MCP-Session-Id") or sid)
    return parsed, new_sid


def _session(token: str) -> tuple[dict, str]:
    """initialize + notifications/initialized. Returns (init_result, sid)."""
    init, sid = _rpc(
        token, "initialize",
        {"protocolVersion": PROTO, "capabilities": {}, "clientInfo": CLIENT_INFO},
        id_=1)
    if not sid:
        hfx.die("MCP initialize: no mcp-session-id header — cannot continue",
                hfx.EXIT_FAIL)
    _rpc(token, "notifications/initialized", sid=sid)  # HTTP 202, no body
    return (init or {}).get("result") or {}, sid


def _check_rpc_error(body: dict | None, method: str) -> dict:
    if isinstance(body, dict) and body.get("error"):
        hfx.die(f"MCP {method} error: {json.dumps(body['error'])[:400]}",
                hfx.EXIT_FAIL)
    return (body or {}).get("result") or {}


# ------------------------------------------------------------------ subcommands

def cmd_tools(a, ctx: dict) -> int:
    """MCP initialize + tools/list → the account's tool surface."""
    token = hfx.need_token(ctx["env"])
    init, sid = _session(token)
    body, _ = _rpc(token, "tools/list", {"params": {}}, id_=2, sid=sid)
    result = _check_rpc_error(body, "tools/list")
    tools = result.get("tools") or []
    server = init.get("serverInfo") or {}

    if ctx["json"]:
        hfx.jprint({"server": server, "count": len(tools), "tools": tools})
        return hfx.EXIT_OK

    print(f"hfx mcp tools — {server.get('name', MCP_URL)} "
          f"v{server.get('version', '?')} · {len(tools)} tool(s) enabled")
    print("(tool set is per-account: toggle built-ins at "
          "https://huggingface.co/settings/mcp)")
    print("=" * 72)
    for t in tools:
        desc = (t.get("description") or "").strip().splitlines()
        one = desc[0][:88] if desc else ""
        print(f"  {t['name']}")
        if one:
            print(f"      {one}")
        if t["name"] in _NOTES:
            print(f"      >> {_NOTES[t['name']]}")
    print("-" * 72)
    print("\nNext: hfx mcp call hf_whoami                  # auth context (free)")
    print("      hfx mcp call dynamic_space --args-json "
          "'{\"operation\":\"discover\"}'")
    print("      hfx mcp resources                       # 155 skill:// docs")
    print("      (invoke on a ZeroGPU Space = 1 of your 8 runs/24h!)")
    return hfx.EXIT_OK


def cmd_call(a, ctx: dict) -> int:
    """tools/call — invoke one MCP tool, print text content."""
    token = hfx.need_token(ctx["env"])
    try:
        args = json.loads(a.args_json) if a.args_json else {}
    except ValueError as e:
        hfx.die(f"--args-json is not valid JSON: {e}", hfx.EXIT_CONFIG)
    if not isinstance(args, dict):
        hfx.die("--args-json must be a JSON object", hfx.EXIT_CONFIG)

    _hint = (a.tool == "dynamic_space" and args.get("operation") == "invoke"
             and not isinstance(args.get("parameters"), (str, type(None))))
    if _hint:
        print("hfx: note: dynamic_space `invoke` wants `parameters` as a "
              "JSON-encoded STRING, not a nested object (findings/"
              "mcp-dynamic-spaces.md gotcha #1) — sending as-is anyway",
              file=sys.stderr)

    _, sid = _session(token)
    body, _ = _rpc(token, "tools/call",
                   {"name": a.tool, "arguments": args}, id_=3, sid=sid,
                   timeout=a.timeout)
    result = _check_rpc_error(body, "tools/call")
    log = {"tool": a.tool, "arguments": args, "result": result,
           "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    if ctx["json"]:
        hfx.jprint(log)
        return hfx.EXIT_FAIL if result.get("isError") else hfx.EXIT_OK

    saved = []
    for c in result.get("content") or []:
        ctype = c.get("type")
        if ctype == "text":
            print(c.get("text", ""))
        elif ctype in ("image", "audio"):
            data, mime = c.get("data", ""), c.get("mimeType", "application/octet-stream")
            ext = {"image/webp": ".webp", "image/png": ".png", "image/jpeg": ".jpg",
                   "audio/wav": ".wav"}.get(mime, ".bin")
            print(f"[{ctype} content block: {mime}, {len(data)} base64 chars]")
            if a.out:
                os.makedirs(a.out, exist_ok=True)
                dst = os.path.join(a.out, f"{a.tool}-{int(time.time())}{ext}")
                with open(dst, "wb") as fh:
                    fh.write(base64.b64decode(data))
                saved.append(dst)
            else:
                print("  (pass --out DIR to save binary content blocks)")
        elif ctype == "resource":
            res = c.get("resource") or {}
            print(f"[resource block: {res.get('uri')}]")
            if res.get("text"):
                print(res["text"])
        else:
            print(f"[{ctype or '?'} content block omitted]")
    for f in saved:
        print(f"  saved: {f}")
    if result.get("isError"):
        print("\nhfx: tool returned isError — see content above", file=sys.stderr)
        return hfx.EXIT_FAIL
    print("\nNext: hfx gpu preflight   # if you invoked a ZeroGPU Space: 1 run "
          "consumed (8/24h binding)")
    return hfx.EXIT_OK


def cmd_resources(a, ctx: dict) -> int:
    """resources/list (155 skill:// Agent-Skills docs) [+ resources/read]."""
    token = hfx.need_token(ctx["env"])
    _, sid = _session(token)

    if a.uri:
        body, _ = _rpc(token, "resources/read", {"uri": a.uri}, id_=4, sid=sid)
        result = _check_rpc_error(body, "resources/read")
        if ctx["json"]:
            hfx.jprint(result)
            return hfx.EXIT_OK
        for c in result.get("contents") or []:
            print(f"--- {c.get('uri')} ({c.get('mimeType', '?')}) ---")
            if c.get("text") is not None:
                print(c["text"])
            elif c.get("blob"):
                print(f"[{len(c['blob'])} base64 chars of blob data]")
            else:
                print("(empty)")
        return hfx.EXIT_OK

    body, _ = _rpc(token, "resources/list", {"params": {}}, id_=4, sid=sid)
    result = _check_rpc_error(body, "resources/list")
    resources = result.get("resources") or []
    if ctx["json"]:
        hfx.jprint({"count": len(resources), "resources": resources})
        return hfx.EXIT_OK

    print(f"hfx mcp resources — {len(resources)} resource(s) "
          "(skill:// = Agent-Skills docs: hf-cli, zerogpu, training, ...)")
    print("=" * 72)
    for r in resources[:60]:
        name = (r.get("name") or "").replace("\n", " ")[:56]
        print(f"  {r.get('uri', '?'):<70} {name}")
    if len(resources) > 60:
        print(f"... and {len(resources) - 60} more (--json for the full list)")
    print("-" * 72)
    print("\nNext: hfx mcp resources --uri skill://hf-cli/SKILL.md   # read one")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ entry

def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="hfx mcp",
        description="hosted MCP client (huggingface.co/mcp) — tools, calls, "
                    "skill:// resources. JSON-RPC over POST with PAT Bearer. "
                    "Every dynamic_space invoke = 1 ZeroGPU run (8/24h "
                    "account-global). Evidence: findings/mcp-probe.md")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("tools", help="initialize + tools/list → tool table")
    t.set_defaults(func=cmd_tools)

    c = sub.add_parser("call", help="tools/call — invoke one tool, print text "
                                    "content")
    c.add_argument("tool", help="tool name (see `hfx mcp tools`)")
    c.add_argument("--args-json", default="{}",
                   help='JSON object of arguments, e.g. '
                        '\'{"operation":"discover"}\' — NOTE dynamic_space '
                        "invoke wants `parameters` as a JSON-encoded STRING")
    c.add_argument("--out", help="dir to save image/audio content blocks into")
    c.add_argument("--timeout", type=int, default=300,
                   help="seconds to wait for the tool (default 300)")
    c.set_defaults(func=cmd_call)

    r = sub.add_parser("resources", help="resources/list (+ resources/read "
                                         "with --uri)")
    r.add_argument("--uri", help="read one resource, e.g. "
                                 "skill://hf-cli/SKILL.md")
    r.set_defaults(func=cmd_resources)

    a = p.parse_args(argv)
    return a.func(a, ctx)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False, "env": {}}))
