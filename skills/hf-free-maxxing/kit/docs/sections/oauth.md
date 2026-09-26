## oauth — HuggingFace as a FREE OIDC identity provider

"Sign in with HF" for your side project, $0, no MAU cap (every end-user needs
an HF account). Full OIDC: discovery doc, PKCE S256 auth-code, RFC 8628 device
flow, refresh tokens, RFC 7591 **anonymous dynamic client registration** (no
dashboard!). Killer feature vs Auth0/Firebase free tiers: users can grant your
app `inference-api` — **GPU spend lands on THEIR credits, not yours**.

```bash
hfx oauth discovery          # endpoints + the 21-scope kit-verified list
hfx oauth register --name myapp --redirect-uri http://localhost:3000/callback \
    --out myapp-client.json  # RFC 7591 dynamic client (⚠️ read the warning)
hfx oauth authorize-url --client-id ID --redirect-uri http://localhost:3000/callback
    # default --scope "openid profile email" — SAME as register (email
    # included, so userinfo returns it; pass --scope to narrow)
hfx oauth token --client-id ID --code CODE --verifier VERIFIER \
    --redirect-uri http://localhost:3000/callback --out tokens.json
    # (+ --refresh-token R to refresh; --out saves chmod 600 like register)
hfx oauth device --client-id ID    # TV/CLI login: user_code + poll command
```

### PKCE auth-code flow, step by step (all kit-automated except the consent click)

1. **Register once** (`register`) → `client_id` (public client, no secret).
   ⚠️ **RFC 7591 clients are UN-DELETABLE** — no DELETE endpoint (404),
   invisible in `/settings/applications`. One per project, never per test run.
   The server force-adds `device_code` + `refresh_token` grants to every
   dynreg client.
2. **`authorize-url`** prints the S256 authorize URL **and the
   `code_verifier`** — keep it; it's needed for the exchange.
3. User opens the URL in a browser where they're logged in to HF → first time
   a one-time consent click → HF 303s to your redirect_uri with
   `?code=…&state=…` (verify state round-trips). Later grants **auto-approve**
   for the same (user, app, scope-set).
4. **`token`** exchanges code+verifier → `access_token` (`hf_oauth_…` EdDSA,
   8 h), `id_token` (RS256, **only 1 h** — don't cache past that),
   `refresh_token` (grant rotates, same sessionId). Works as Bearer on the hub
   API **and** the router.

### Device flow (CLIs, TVs, headless)

`hfx oauth device` → `user_code XXXX-XXXX` + `https://hf.co/oauth/device`
(TTL 300 s). User logs in to HF, enters the code, clicks Authorize (consent
**re-prompts every device grant**, unlike auth-code). Poll
`POST /oauth/token` with `grant_type=urn:ietf:params:oauth:grant-type:device_code`
every ≥5 s (no `interval` in the response).

### What app tokens can do (live-verified scope matrix)

`whoami-v2` (any) · `userinfo` incl. verified email (`openid profile email`) ·
`read-billing` (usage-v2 + live SSE) · `jobs` · `inference-api` (router calls,
**billed to the user**). 21 scopes total — `hfx oauth discovery` prints the
kit-verified scope list (server discovery has no `scopes_supported` field,
so the list is kit-maintained and can lag server reality).

### App integration (web-app wiring beyond the CLI)

**(a) The raw token exchange** — `POST /oauth/token` is **form-encoded**
(any language, no kit needed):

```bash
curl -s -X POST https://huggingface.co/oauth/token \
  -d grant_type=authorization_code -d client_id=$CLIENT_ID \
  -d code=$CODE -d redirect_uri=http://localhost:3000/callback \
  -d code_verifier=$VERIFIER
# → {"access_token":"hf_oauth_…","id_token":"eyJ…","refresh_token":"…",
#     "token_type":"bearer","expires_in":28800,"scope":"openid profile email"}
```

**(b) Callback-handler sketch** (Flask; extract `code`+`state`, exchange via
the kit, keep the rotated refresh token):

```python
@app.get("/callback")
def callback():
    if request.args.get("state") != session["state"]:
        return "state mismatch — reject", 401            # CSRF guard
    subprocess.run(["hfx", "oauth", "token", "--client-id", CLIENT_ID,
                    "--code", request.args["code"], "--verifier", session["verifier"],
                    "--redirect-uri", REDIRECT_URI, "--out", "tokens.json"],
                   check=True)                            # chmod-600 JSON
    tok = json.load(open("tokens.json"))
    session["refresh_token"] = tok["refresh_token"]      # ROTATES — see (e)
    return "logged in"
```

**(c) Verify the id_token (RS256) before trusting its claims** — the kit only
*decodes* claims for display, it does **not** verify signatures. In your app:
issuer must be `https://huggingface.co`; fetch the discovery doc's `jwks_uri`
(`https://huggingface.co/oauth/jwks`), match the token's `kid` header to a JWK,
and verify RS256 with any JWT lib (e.g. PyJWT:
`jwt.decode(id_token, jwt.PyJWK.from_dict(jwk), algorithms=["RS256"],
audience=CLIENT_ID)`).

**(d) Sample `GET /oauth/userinfo` fields** (Bearer access_token; build your
User model from these): `sub`, `name`, `preferred_username`, `profile`,
`picture`, `isPro`, `orgs[]` — plus `email`, `email_verified` (and `canPay`,
`billingMode`) when the `email` scope was granted.

**(e) Refresh tokens ROTATE**: every `refresh_token` grant returns a NEW
refresh_token (the old one dies; same `sessionId` continues). Persist the new
value on EVERY exchange — lose it and the user's session cannot be refreshed
(there is no revocation endpoint either, so treat refresh tokens as secrets).

**(f) When the user DENIES consent** (redirect shapes live-verified 2026-09-26
on the kit's own K7 client — deny is a normal, recoverable path, not an error
to fear):
- **Auth-code flow**: the consent page's Deny button 303s back to YOUR
  redirect_uri with
  `?error=access_denied&error_description=The+user+denied+the+request&state=<your state>`
  — `state` still round-trips, so verify it, then render a "login cancelled"
  page. There is no `code` to exchange; do not call /oauth/token.
- **Device flow**: the user lands on a "denied" page; your token poll gets
  `400 {"error":"access_denied","error_description":"Device code denied"}` —
  stop polling (RFC 8628 terminal error).
- **Retry is free**: a deny is NOT cached — send the user through
  `hfx oauth authorize-url` (or a fresh device grant) and the consent form
  shows again. Auto-approve only exists AFTER a grant, per (user, app,
  scope-set) — so a denied user simply re-runs the same login link.

**(g) Logout & disconnect** — no `/oauth/revoke` exists, so:
- Your app's logout = drop the LOCAL session + refresh token (access tokens
  live ≤ 8 h; refresh TTL undisclosed — treat both as secrets either way).
- HF-side logout is the user's browser business (`POST /logout`, the
  account-menu button; anonymous `GET /logout` is a 404). Whether it kills
  already-issued app tokens is unverified — your app's session is the
  source of truth for who is logged in.
- Full disconnect: the user revokes your app at
  <https://huggingface.co/settings/connected-applications> (per-app Revoke).
- Denied because they were in the WRONG HF account? Have them log out of HF
  in the browser, then retry the authorize URL — fresh consent under the
  right account.

Gotchas:
- **No token revocation endpoint** — a leaked refresh token is compromised
  until it expires; treat it like a password.
- Any OIDC client lib (authlib, next-auth, passport…) works with
  `issuer=https://huggingface.co`.
- Rate-limit hops count in the `pages` bucket (200/5 min) — fine for normal
  login flows, don't loop authorize pages.
- `hfx oauth register/token` print full secrets BY DESIGN (that's their job) —
  mind scrollback/logs.

Evidence: findings/oauth-idp.md (PKCE e2e, device flow, RFC 7591, scope
matrix, Auth0/Firebase comparison) · live tests: data/kit-tests/k7/
(one dynamically-registered research client: un-deletable, kept as evidence).
