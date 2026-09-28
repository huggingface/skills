#!/usr/bin/env python3
"""hfx registry — the free Docker pull-library at registry.hf.space.

Every PUBLIC Docker-SDK Space's built image is pullable by any logged-in user
(read-only mirror of Space builds).  No pushes; static/Gradio spaces have no
images.  Evidence: findings/containers-registry.md.

  login-cmd   mint a 600s registry token (Basic-auth token endpoint) and print
              the ready-to-run `docker login` + sample `docker pull` commands.
              The token is never stored.
  manifest    fetch an image manifest (tags, digest, config + layers size).

Usage: hfx registry <subcommand> [--json]
"""
from __future__ import annotations

import json
import os
import sys

# allow direct execution (python3 kit/lib/cmd_registry.py …)
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hfx  # noqa: E402

REGISTRY = "https://registry.hf.space"
ACCEPT_MANIFESTS = ("application/vnd.oci.image.manifest.v1+json, "
                    "application/vnd.oci.image.index.v1+json, "
                    "application/vnd.docker.distribution.manifest.v2+json")
SAMPLE_SPACE = "enzostvs/deepsite"  # public Docker-SDK space, verified pullable


def _image_name(space_ref: str) -> str:
    """'owner/space' → 'owner-space' (registry image names are hyphenated)."""
    ref = space_ref.strip().strip("/")
    if ref.startswith("spaces/"):
        ref = ref[len("spaces/"):]
    return ref.replace("/", "-")


def _mint_token(token: str) -> dict:
    """GET /api/registry/token?service=registry.hf.space — ⚠️ Basic auth ONLY
    (Bearer → 401, cookie → anonymous token).  Returns {token, expires_in}."""
    import base64
    import urllib.parse
    basic = base64.b64encode(f":{token}".encode()).decode()
    url = (f"{hfx.HF}/api/registry/token?"
           + urllib.parse.urlencode({"service": "registry.hf.space"}))
    st, _, raw = hfx.http("GET", url, headers={"Authorization": f"Basic {basic}"})
    if st != 200:
        hfx.die(f"registry token mint -> {st}: {raw[:200].decode(errors='replace')} "
                "(the endpoint accepts ONLY Basic auth, never Bearer)", hfx.EXIT_FAIL)
    out = json.loads(raw)
    if not out.get("token"):
        hfx.die("registry token mint returned no token", hfx.EXIT_FAIL)
    return out


def _registry_get(path: str, jwt: str, accept: str = "application/json"):
    st, hs, raw = hfx.http("GET", REGISTRY + path, token="", headers={
        "Authorization": f"Bearer {jwt}", "Accept": accept})
    return st, hs, raw


# ------------------------------------------------------------------ subcommands

def _login_cmd(a, ctx) -> int:
    token = hfx.need_token(ctx["env"])
    _, who, _ = hfx.api("GET", "/api/whoami-v2", token=token)
    user = (who or {}).get("name", "")
    mint = _mint_token(token)
    jwt = mint["token"]

    # verify the minted token actually authenticates at the registry (1 cheap call)
    st, _, _ = _registry_get("/v2/", jwt)
    verified = st == 200

    if ctx["json"]:
        hfx.jprint({"user": user, "registry": "registry.hf.space",
                    "token": jwt, "expires_in": mint.get("expires_in", 600),
                    "verified_against_v2": verified,
                    "login_cmd": f"docker login registry.hf.space -u {user} -p {jwt}",
                    "pull_cmd": f"docker pull registry.hf.space/{_image_name(SAMPLE_SPACE)}"})
        return hfx.EXIT_OK

    print(f"registry.hf.space login — 600s token minted (Basic-auth token endpoint)\n"
          + "=" * 72)
    print(f"  user    : {user}")
    print(f"  token   : {jwt}")
    print(f"  expires : in {mint.get('expires_in', 600)}s (EdDSA JWT, aud=registry.hf.space) "
          "— NEVER stored by hfx")
    print(f"  verified: {'token authenticates at GET /v2/ ✓' if verified else '⚠️ GET /v2/ -> ' + str(st)}"
          )
    print(f"""
Ready-to-run docker commands (paste into your shell):

  docker login registry.hf.space -u {user} -p <TOKEN_ABOVE>

  # sample pull (any PUBLIC Docker-SDK Space image; get a tag via
  # `hfx registry manifest enzostvs/deepsite`):
  docker pull registry.hf.space/{_image_name(SAMPLE_SPACE)}:<tag>

Notes:
  ⚠️ `-p <token>` lands in your shell history — prefer password-stdin:
     docker login registry.hf.space -u {user} --password-stdin <<< <TOKEN_ABOVE>
  • your PAT also works as the password (realm echoes it back; no 600s limit)
  • registry is READ-ONLY (no pushes). Static/Gradio spaces have NO images —
    pre-flight with: GET {hfx.HF}/api/spaces/<id>/registry-auth-check
  • image names are hyphenated: enzostvs/deepsite -> enzostvs-deepsite
  • blob pulls 307 to 20-min presigned S3 URLs — don't cache them""")
    return hfx.EXIT_OK


def _manifest(a, ctx) -> int:
    token = hfx.need_token(ctx["env"])
    img = _image_name(a.space)
    jwt = _mint_token(token)["token"]  # fresh 600s token (per findings recipe)

    st, _, raw = _registry_get(f"/v2/{img}/tags/list", jwt)
    if st == 404:
        hfx.die(f"no image '{img}' — static/Gradio spaces are never dockerized "
                f"(and secret-bearing images need author rights).\n"
                f"recovery: find dockerized spaces — `hfx registry manifest <space>` "
                f"works on spaces with sdk=docker (e.g. enzostvs/deepsite works), "
                f"or check the /api/spaces/{a.space} .sdk field "
                f"(docker ⇒ image exists, gradio/static ⇒ none). "
                f"Evidence: findings/containers-registry.md §2c", hfx.EXIT_FAIL)
    if st != 200:
        hfx.die(f"tags/list -> {st}: {raw[:200].decode(errors='replace')}", hfx.EXIT_FAIL)
    tags = json.loads(raw).get("tags") or []

    ref = a.ref or (tags[0] if tags else "latest")
    st, hs, raw = _registry_get(f"/v2/{img}/manifests/{ref}", jwt,
                                accept=ACCEPT_MANIFESTS)
    if st == 404:
        hint = f"available tags: {', '.join(tags[:5])}…" if tags else "repo has no tags"
        hfx.die(f"manifest for ref '{ref}' not found ({hint}); pass --ref", hfx.EXIT_FAIL)
    if st != 200:
        hfx.die(f"manifest -> {st}: {raw[:200].decode(errors='replace')} "
                "(secret-bearing Space images 401 for non-authors)", hfx.EXIT_FAIL)
    m = json.loads(raw)
    digest = hs.get("docker-content-digest", hs.get("Docker-Content-Digest", ""))
    layers = m.get("layers") or []
    total = sum(l.get("size", 0) for l in layers)
    cfg = m.get("config") or {}

    if ctx["json"]:
        hfx.jprint({"name": img, "ref": ref, "digest": digest,
                    "media_type": m.get("mediaType"), "tags": tags,
                    "config": cfg, "layers": layers, "layers_total_bytes": total,
                    "pull_cmd": f"docker pull registry.hf.space/{img}:{ref}"})
    else:
        print(f"registry.hf.space/{img} — image manifest\n" + "=" * 72)
        print(f"  tags     : {len(tags)} available (using first/most-recent; pass --ref to choose)")
        print(f"  ref      : {ref}")
        print(f"  digest   : {digest}")
        print(f"  mediaType: {m.get('mediaType')}")
        print(f"  config   : {hfx.human_bytes(cfg.get('size', 0))} "
              f"({(cfg.get('digest') or '')[:31]}…)")
        print(f"  layers   : {len(layers)} · {hfx.human_bytes(total)} compressed")
        print(f"\n  pull     : docker pull registry.hf.space/{img}:{ref}")
        print("  (docker login first — see `hfx registry login-cmd`; anon pulls 401)")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ dispatch

def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="hfx registry",
        description="registry.hf.space — free READ-ONLY Docker pull-library of "
                    "every public Docker-SDK Space's build. No pushes; images "
                    "ephemeral per Jobs docs. Evidence: findings/containers-registry.md")
    pj = argparse.ArgumentParser(add_help=False)
    pj.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("login-cmd", parents=[pj],
                        help="mint a 600s registry token and print ready-to-run "
                             "docker login + pull commands (token never stored)")
    pl.set_defaults(fn=_login_cmd)

    pm = sub.add_parser("manifest", parents=[pj],
                        help="fetch an image manifest: tags, digest, config + "
                             "layer sizes")
    pm.add_argument("space", help="Space as 'owner/name' (image = owner-name) "
                                  "or already-hyphenated")
    pm.add_argument("--ref", help="tag/digest (default: first tag from tags/list)")
    pm.set_defaults(fn=_manifest)

    a = p.parse_args(argv)
    ctx["json"] = ctx.get("json") or a.json
    return a.fn(a, ctx)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False,
                                "env": {k: os.environ.get(k, "") for k in hfx.ENV_KEYS}}))
