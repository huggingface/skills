## token — credentials: identity + the CI-safe disposable JWT

Two credentials, two jobs:

| Credential | What it is | Use |
|---|---|---|
| `HF_TOKEN` | PAT (role `read`/`write`) | everything everyday: hub API, router, store/host writes |
| `HF_JWT` | browser session cookie (name `token`) | web-app surfaces (billing page, uploads attribution) — **and JWT minting below** |

```bash
hfx token info            # whoami-v2: account, token role, orgs (token masked to 8 chars)
hfx token mint-jwt        # mint + decode a 1h inference-only JWT (prints the JWT — that's the point)
hfx token mint-jwt --verify    # + ONE $0-lane probe proving the router accepts it RIGHT NOW
hfx token mint-jwt --ttl-note  # + the mint-per-CI-run TTL strategy note
hfx doctor                # full credential/deps/endpoint check-up
```

### mint-jwt — THE CI-safe disposable credential

`GET /api/settings/jwt-inference-only` (auth: `Cookie: token=$HF_JWT`) mints a
**fresh JWT on every call, no visible cap**. Claims (decoded for you):
`scope: inference.serverless.write`, `sub: router.huggingface.co`,
**exp − iat = 3600 s**. Properties that make it CI-perfect:

- **Router-only**: works as `Authorization: Bearer <jwt>` on
  `https://router.huggingface.co/v1/*`; **hub writes 401** with it — a leaked
  CI JWT can run inference on your credits but cannot touch your repos.
- **1-hour TTL** (claims): expiry is fail-safe; mint a fresh one per run
  instead of storing it. Unlimited mints (verified: back-to-back calls →
  unique `jti`). Observed live (U7): the *practical* acceptance window can
  be much shorter than the claimed 3600 s (401s minutes after mint) — **mint
  fresh per CI step and re-mint on any 401**; `--verify` catches it at mint
  time (prints PASS/FAIL, exit 1 on FAIL; `--json` carries the raw token +
  decoded claims + `verify` result).
- **Format note**: use the FULL `accessToken` value including the `hf_jwt_`
  prefix — a bare JWT (header.payload.signature only) 401s.

```bash
JWT=$(hfx token mint-jwt --json | jq -r .jwt)
curl -s https://router.huggingface.co/v1/chat/completions \
  -H "Authorization: Bearer $JWT" -H 'Content-Type: application/json' \
  -d '{"model":"inclusionAI/Ling-3.0-flash-Fin:novita","messages":[{"role":"user","content":"hi"}],"max_tokens":300}'
```
(max_tokens ≥300 — the free lane is a reasoning model; tiny budgets return
empty `content` with the text in `reasoning_content`.)

Gotchas:
- Missing `HF_JWT` → exit 2 with extraction hint (devtools → Application →
  Cookies → `token`). It's optional — most commands need only `HF_TOKEN`.
- Endpoint **302s to `/security-checkup`** when HF enforces its password
  security-checkup gate → the kit prints the fix: complete
  <https://huggingface.co/security-checkup> once in a browser (existing tokens
  and minting usually keep working meanwhile).
- Per-token rate limits are **account-level** (all tokens share one bucket) —
  extra tokens are for blast-radius segregation, never quota multiplication.
- Never print full credentials in scripts; `hfx token info` masks to 8 chars
  (mint-jwt prints the JWT itself — that's its purpose, and it expires in 1h).

### doctor

`hfx doctor` checks it all and exits 1 on any FAIL: HF_TOKEN (whoami), HF_JWT
valid (mint endpoint — note this proves the MINT works; router acceptance of
minted JWTs: verify with `hfx token mint-jwt --verify`), `huggingface_hub`
version (**WARN if ≥2.0 — PIN `<2.0`, v2 has breaking changes**), boto3,
gradio_client, router reachable (+ free-lane presence), datasets-server
reachable, quota snapshot (usage/live SSE). Fix hints inline; deps one-liner:
`pip install --user "huggingface_hub<2.0" boto3 gradio_client`.

Evidence: findings/tokens-matrix.md (§7 mint, §5 rate limits) ·
findings/infra-probe.md §C · findings/webapp-endpoints.md ·
live test evidence: data/kit-tests/infer-token/
