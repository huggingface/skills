#!/usr/bin/env python3
"""hfx oauth — HuggingFace as a FREE OIDC identity provider (PAT not required).

Recipes verified live (findings/oauth-idp.md):
  register       RFC 7591 anonymous dynamic client registration.  ⚠️ PERMANENT:
                 registered clients can NEVER be deleted (no DELETE endpoint,
                 invisible in settings UI).  Register ONE per project.
  authorize-url  PKCE (S256) auth-code URL + the code_verifier you must keep.
  token          /oauth/token exchange (auth-code or refresh grant) + claims.
  device         RFC 8628 device flow: user_code + verification URL + poll cmd.
  discovery      /.well-known/openid-configuration endpoints & scopes.

Usage: hfx oauth <subcommand> [--json]
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import urllib.parse

# allow direct execution (python3 kit/lib/cmd_oauth.py …)
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hfx  # noqa: E402
import kitutil  # noqa: E402

# 21 live-verified scopes (R3 re-check 2026-09-26; discovery doc carries no
# scopes_supported field) — findings/oauth-idp.md §1
KNOWN_SCOPES = [
    "openid", "profile", "email", "manage-repos", "write-repos", "read-repos",
    "gated-repos", "contribute-repos", "write-discussions", "read-billing",
    "read-memberships", "inference-api", "read-endpoints", "write-endpoints",
    "jobs", "webhooks", "read-mcp", "read-collections", "write-collections",
    "read-network-security", "write-network-security",
]

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


def _formpost(url: str, form: dict, expect: tuple[int, ...] = (200, 201)):
    body = urllib.parse.urlencode(form).encode()
    st, _, raw = hfx.http("POST", url, body=body,
                          headers={"Content-Type": "application/x-www-form-urlencoded",
                                   "Accept": "application/json"})
    if st not in expect:
        hfx.die(f"POST {url} -> {st}: {raw[:300].decode(errors='replace')}", hfx.EXIT_FAIL)
    try:
        return json.loads(raw)
    except ValueError:
        hfx.die(f"POST {url} -> {st}: non-JSON response", hfx.EXIT_FAIL)


# ------------------------------------------------------------------ subcommands

def _register(a, ctx) -> int:
    # the kit's ONLY irreversible action — the warning must fire BEFORE the
    # POST (U5 friction #3), on stderr so --json stdout stays pure
    print(
        "⚠️  BIG WARNING: RFC 7591 clients are UN-DELETABLE.\n"
        "    There is NO delete endpoint (DELETE /oauth/register/<id> → 404)\n"
        "    and they are INVISIBLE in your /settings/applications UI — no edit,\n"
        "    no revoke. They are inert until a user consents, but the client_id\n"
        "    exists forever. Register ONE per project, not per test run.",
        file=sys.stderr)
    body = {
        "client_name": a.name,
        "redirect_uris": [a.redirect_uri],
        "token_endpoint_auth_method": "none",  # public client -> PKCE/device
        "grant_types": ["authorization_code", DEVICE_GRANT],
        "response_types": ["code"],
        "scope": a.scope,
    }
    st, _, raw = hfx.http("POST", f"{hfx.HF}/oauth/register", body=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json",
                                   "Accept": "application/json"})
    if st != 201:
        hfx.die(f"oauth register -> {st}: {raw[:300].decode(errors='replace')}", hfx.EXIT_FAIL)
    client = json.loads(raw)

    if ctx["json"]:
        hfx.jprint(client)
    else:
        print("RFC 7591 dynamic client registered (anonymous, no dashboard needed)\n" + "=" * 72)
        print(f"  client_id     : {client.get('client_id')}")
        print(f"  client_name   : {client.get('client_name')}")
        print(f"  redirect_uris : {', '.join(client.get('redirect_uris') or [])}")
        print(f"  grant_types   : {', '.join(client.get('grant_types') or [])}"
              "   (server force-adds device_code + refresh_token)")
        print(f"  scope         : {client.get('scope')}")
        print(f"  auth method   : {client.get('token_endpoint_auth_method')} (public — no secret)")
        print("  ⚠️ un-deletable client — see the warning above (printed BEFORE the "
              "registration was sent).")
        if a.out:
            with open(a.out, "w", encoding="utf-8") as fh:
                json.dump(client, fh, indent=2)
            os.chmod(a.out, 0o600)
            print(f"  credentials saved (chmod 600): {a.out}")
        else:
            print("\n  Tip: re-run with --out FILE to save these credentials as JSON.")
    print("\nNext: hfx oauth authorize-url --client-id "
          f"{client.get('client_id', '<id>')} --redirect-uri {a.redirect_uri}")
    return hfx.EXIT_OK


def _authorize_url(a, ctx) -> int:
    verifier = kitutil.b64url_nopad(secrets.token_bytes(48))  # 64-char verifier
    challenge = kitutil.b64url_nopad(hashlib.sha256(verifier.encode()).digest())
    state = a.state or secrets.token_hex(8)
    q = urllib.parse.urlencode({
        "client_id": a.client_id,
        "redirect_uri": a.redirect_uri,
        "scope": a.scope,
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    })
    url = f"{hfx.HF}/oauth/authorize?{q}"
    if ctx["json"]:
        hfx.jprint({"url": url, "code_verifier": verifier, "state": state,
                    "code_challenge": challenge})
    else:
        print("PKCE (S256) authorize URL — open in a browser where the user is "
              "logged in to HF:\n" + "=" * 72)
        print(url)
        print(f"""
code_verifier (KEEP — needed for the token exchange):
  {verifier}
state (verify it round-trips): {state}

After consent HF 303s to your redirect_uri with ?code=…&state=…, then:
  hfx oauth token --client-id {a.client_id} --code <CODE> \\
      --verifier {verifier} --redirect-uri {a.redirect_uri}
First consent is a one-time click; later authorizations auto-approve for the
same (user, app, scope-set).""")
    return hfx.EXIT_OK


def _token(a, ctx) -> int:
    form = {"grant_type": "authorization_code", "code": a.code,
            "redirect_uri": a.redirect_uri, "client_id": a.client_id,
            "code_verifier": a.verifier}
    if a.refresh_token:
        form = {"grant_type": "refresh_token", "refresh_token": a.refresh_token,
                "client_id": a.client_id}
    if a.secret:
        form["client_secret"] = a.secret  # confidential clients (client_secret_post)
    tok = _formpost(f"{hfx.HF}/oauth/token", form)

    access = tok.get("access_token", "")
    claims = kitutil.jwt_decode(access) if access else {}
    id_claims = kitutil.jwt_decode(tok["id_token"]) if tok.get("id_token") else {}

    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(tok, fh, indent=2)
        os.chmod(a.out, 0o600)

    if ctx["json"]:
        out = {"response": tok, "access_token_claims": claims,
               "id_token_claims": id_claims}
        if a.out:
            out["saved_to"] = a.out
        hfx.jprint(out)
    else:
        print("token exchange OK\n" + "=" * 72)
        print(f"  token_type : {tok.get('token_type')}")
        print(f"  expires_in : {tok.get('expires_in')}s (~8h; id_token lives only 1h)")
        print(f"  scope      : {tok.get('scope')}")
        print(f"  access_token   : {access}")
        if tok.get("refresh_token"):
            print(f"  refresh_token  : {tok['refresh_token']}")
        if claims:
            print(f"  access claims  : {json.dumps(claims, sort_keys=True)}")
        if id_claims:
            print(f"  id_token claims: {json.dumps(id_claims, sort_keys=True)}")
        if a.out:
            print(f"  saved (chmod 600): {a.out}")
        print("""
⚠️  Secrets above are shown in full by design — mind your terminal history /
scrollback when sharing logs.  Refresh: hfx oauth token --client-id <ID> \\
    --refresh-token <REFRESH> (rotates; same sessionId).  There is NO
revocation endpoint — treat a leaked refresh token as compromised until exp.
Works as 'Authorization: Bearer' on the hub API + router (findings/oauth-idp.md §4).""")
    return hfx.EXIT_OK


def _device(a, ctx) -> int:
    dev = _formpost(f"{hfx.HF}/oauth/device",
                    {"client_id": a.client_id, "scope": a.scope})
    if ctx["json"]:
        hfx.jprint(dev)
    else:
        print("RFC 8628 device authorization issued\n" + "=" * 72)
        print(f"  user_code        : {dev.get('user_code')}")
        print(f"  verification_uri : {dev.get('verification_uri') or 'https://hf.co/oauth/device'}")
        print(f"  device_code      : {dev.get('device_code')}")
        print(f"  expires_in      : {dev.get('expires_in', 300)}s "
              "(user must approve within TTL; consent re-prompts EVERY device grant)")
        print(f"""
User step: open {dev.get('verification_uri') or 'https://hf.co/oauth/device'}, log in to
HF, enter {dev.get('user_code')}, click Authorize.

Poll for the token (no interval in the response — poll every ≥5s):
  curl -s -X POST {hfx.HF}/oauth/token \\
    -d grant_type={DEVICE_GRANT} \\
    -d device_code={dev.get('device_code')} \\
    -d client_id={a.client_id}
→ {{access_token, id_token, refresh_token}} (same shape as `hfx oauth token`).""")
    return hfx.EXIT_OK


def _discovery(a, ctx) -> int:
    st, _, raw = hfx.http("GET", f"{hfx.HF}/.well-known/openid-configuration")
    if st != 200:
        hfx.die(f"discovery -> {st}: {raw[:200].decode(errors='replace')}", hfx.EXIT_FAIL)
    doc = json.loads(raw)
    if ctx["json"]:
        hfx.jprint(doc)
    else:
        print("OIDC discovery — issuer " + doc.get("issuer", "?") + "\n" + "=" * 72)
        for k, v in sorted(doc.items()):
            print(f"  {k:<42} {v}")
        print(f"\n  kit-verified scope list ({len(KNOWN_SCOPES)} — server discovery has "
              f"no scopes_supported field):\n    {' '.join(KNOWN_SCOPES)}")
        print("\nAny OIDC client lib (authlib, openid-client, passport, next-auth…) "
              "consumes this with issuer=https://huggingface.co.")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ dispatch

def run(argv: list[str], ctx: dict) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="hfx oauth",
        description="HuggingFace as a free OIDC identity provider (PKCE + device "
                    "flow + RFC 7591 dynamic registration). No MAU cap; every "
                    "end-user needs an HF account. Evidence: findings/oauth-idp.md")
    pj = argparse.ArgumentParser(add_help=False)
    pj.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("register", parents=[pj], help="RFC 7591 anonymous dynamic client "
                         "registration (⚠️ UN-DELETABLE — register ONE per project)")
    pr.add_argument("--name", required=True, help="client_name shown on consent screens")
    pr.add_argument("--redirect-uri", default="http://localhost:3000/callback",
                    help="redirect URI (default: %(default)s; plain-http localhost accepted)")
    pr.add_argument("--scope", default="openid profile email",
                    help="requested scope string (default: %(default)s)")
    pr.add_argument("--out", help="save credentials JSON here (chmod 600)")
    pr.set_defaults(fn=_register)

    pa = sub.add_parser("authorize-url", parents=[pj], help="build PKCE (S256) authorize URL + code_verifier")
    pa.add_argument("--client-id", required=True)
    pa.add_argument("--redirect-uri", required=True, help="must match a registered redirect URI")
    pa.add_argument("--scope", default="openid profile email",
                    help="requested scope string (default: %(default)s — SAME as "
                         "register; includes email so userinfo returns it)")
    pa.add_argument("--state", help="override the random state token")
    pa.set_defaults(fn=_authorize_url)

    pt = sub.add_parser("token", parents=[pj], help="exchange code (or refresh) for tokens + decoded claims")
    pt.add_argument("--client-id", required=True)
    pt.add_argument("--secret", help="client secret (confidential clients only; "
                                     "public/PKCE clients omit)")
    pt.add_argument("--code", help="authorization code from the redirect")
    pt.add_argument("--verifier", help="PKCE code_verifier (from authorize-url)")
    pt.add_argument("--redirect-uri")
    pt.add_argument("--refresh-token", help="use the refresh_token grant instead")
    pt.add_argument("--out", help="save the full token response JSON here "
                                   "(chmod 600, like register)")
    pt.set_defaults(fn=_token)

    pd = sub.add_parser("device", parents=[pj], help="start RFC 8628 device flow (issue user_code)")
    pd.add_argument("--client-id", required=True)
    pd.add_argument("--scope", default="openid profile email",
                    help="requested scope string (default: %(default)s — SAME as "
                         "register; includes email so userinfo returns it)")
    pd.set_defaults(fn=_device)

    pc = sub.add_parser("discovery", parents=[pj], help="print /.well-known/openid-configuration")
    pc.set_defaults(fn=_discovery)

    a = p.parse_args(argv)
    ctx["json"] = ctx.get("json") or getattr(a, "json", False)
    if a.fn in (_token,) and not (a.refresh_token or (a.code and a.verifier and a.redirect_uri)):
        hfx.die("token: need either --code + --verifier + --redirect-uri, or "
                "--refresh-token", hfx.EXIT_CONFIG)
    return a.fn(a, ctx)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False,
                                "env": {k: os.environ.get(k, "") for k in hfx.ENV_KEYS}}))
