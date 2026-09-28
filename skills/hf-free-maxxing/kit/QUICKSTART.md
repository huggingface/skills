# QUICKSTART — the 15-minute end-to-end run

For: a fresh agent or human with a HuggingFace account + PAT, no prior kit exposure.

**What you build:** one composed mini-project — a live static site whose text is
LLM-generated and whose image is permanently CDN-hosted — touching storage,
inference, CDN, hosting, GPU preflight and the data engine along the way.
**Total spend if you run everything: ≤ $0.001** (one budget-lane LLM call ≈
$0.000001 + optionally 1 ZeroGPU run ≈ 3 GPU-s at $0 credits). Every step lists
its **done-when oracle** — a fixed string you can grep — so a tester or CI can
assert success mechanically.

## 0. Prerequisites `[GATED: browser, once]`

- A HF account + PAT (role **write**) from <https://huggingface.co/settings/tokens>.
- Python deps: `pip install --user "huggingface_hub<2.0" boto3 gradio_client`
  (⚠️ PIN hub `<2.0` — v2 has breaking changes).
- A token in the environment: either `export HF_TOKEN=hf_...` **or** a `.env`
  file at the repo root next to `kit/` (the kit auto-loads `kit/.env` then the
  parent dir's `.env` — if you run `echo $HF_TOKEN` and it's empty but the
  `.env` exists, that's fine: the kit reads the file itself).
- Optional: `export HF_JWT=<browser cookie "token">` unlocks JWT minting (skip for now).
- Set the alias every shell will need (adjust the path to where you put the kit):
  ```bash
  alias hfx='bash /path/to/kit/bin/hfx'   # all commands below assume this
  ```

**Done-when:** `hfx doctor` in step 1 runs and reaches the credential check
(if it says `HF_TOKEN is not set`, fix the env/.env first).

## 1. Doctor — full setup check `$0`

```bash
hfx doctor
```

**Done-when:** a line starting `All checks PASS` (grep for `All checks PASS` —
the suffix varies: with `HF_JWT` set it reads "— you're fully set up", without
it "(1 warn …)" which is expected and fine; exit code 0). FAIL lines carry
their own fix hints.

## 2. Status — your free capacity `$0`

```bash
hfx status --storage-only
```

**Done-when:** your username row appears showing the private-pool limit
(≈93.13 GiB = 100 GB per entity; a brand-new account shows `0 B/93.13 GB`).
Full `hfx status` (~30 s) adds credits + ZeroGPU + every org pool.

## 3. Storage round-trip (repo path) `$0 · ~KB`

```bash
printf 'hfx-e2e %s\n' "$(date -u +%FT%TZ)" > /tmp/qs.txt
hfx store put /tmp/qs.txt --repo hfx-qs-test
hfx store get hfx-qs-test qs.txt --out /tmp/qs.back
cmp /tmp/qs.txt /tmp/qs.back && echo ROUND-TRIP-OK
hfx store rm qs.txt --repo hfx-qs-test --purge-lfs
```

**Done-when:** `ROUND-TRIP-OK` prints (byte-identical) and `hfx store ls
--repo hfx-qs-test` is empty again (`--purge-lfs` frees quota in ~25-80 s).
The empty dataset-repo shell remains (harmless, 0 bytes) — remove it too with
`hfx etl rm hfx-qs-test` if you want a spotless account.
(S3-bucket variant `[GATED: S3 creds minted from a write token]`:
`hfx store put f --bucket my-b` — same pool, deletable.)

## 4. The PIN-rule guard — negative oracle `$0 (refused before any request)`

```bash
hfx infer chat "hi" --model inclusionAI/Ling-3.0-flash-Fin
```

**Done-when:** exit code **2** and the refusal `refusing unsuffixed chat id` —
this proves the price-blind-routing guard (the single most important safety
property; unsuffixed ids route `:fastest` and IGNORE price).

## 5. Budget LLM call — the site's text `~$0.000001`

```bash
hfx infer chat "Write a 2-line haiku about free GPUs. Reply with ONLY the haiku." \
  --max-tokens 64
```

**Done-when:** non-empty content, and the stderr line `this call costs ~$` shows
≤ $0.00001. (Default model = cheapest pinned lane `Qwen/Qwen3-4B-Instruct-2507:nscale`,
≈5M tokens per $0.10/mo. Note: each router call books a **$0.01 placeholder**
against the cap for ~1-2 min — if you watch `hfx status` right after, credits
look $0.01 higher; that's the placeholder, not real spend. Settled truth:
`hfx infer budget` after 3 min.) Save the haiku with the same budget:
`hfx infer chat "...same prompt..." --max-tokens 64 --json | jq -r .content > /tmp/haiku.txt`.

## 6. CDN upload — the site's image (PERMANENT!) `$0 · outside all quotas`

```bash
# a real 1×1 PNG (70 B, no deps needed — 12+ bytes so the magic-byte sniffer reads it)
printf 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==' \
  | base64 -d > /tmp/pixel-head.png
hfx cdn put /tmp/pixel-head.png --check            # dry-run: sniff only, NO upload
```

**Done-when (`--check`):** prints `PNG → Content-Type image/png … ALLOWED
(dry-run, nothing uploaded)` and exits 0. **Real upload is PERMANENT (no
delete endpoint exists)** — when you have a real image, drop `--check` and
**Done-when:** a `https://cdn-uploads.huggingface.co/production/uploads/...`
URL that returns HTTP 200 with `Content-Type: image/...`. Never upload
anything sensitive.

## 7. Host the site `$0`

```bash
mkdir -p /tmp/qs-site
{ echo "<h1>hfx QUICKSTART</h1><p>$(cat /tmp/haiku.txt)</p>"; \
  echo '<img src="https://cdn-uploads.huggingface.co/production/uploads/YOUR-URL" alt="cdn">'; } \
  > /tmp/qs-site/index.html
hfx host deploy /tmp/qs-site -n hfx-qs-test
```

**Done-when:** the `LIVE: https://<you>-hfx-qs-test.static.hf.space` line, then
`curl -sL <url>/` returns 200 (follow the redirect — the bare root 302s to
`/index.html`; there are no clean URLs) and contains your haiku text;
`curl -sI <url>/index.html` shows `x-repo-commit:`. (Link explicit
`/dir/index.html` paths; hash routes for SPAs.)

## 8. GPU preflight (no invoke) + data query `$0`

```bash
hfx gpu preflight
hfx etl rows lhoestq/demo1 --limit 5
```

**Done-when:** `VERDICT: GO` (8 runs + 300 GPU-s budget OK; add `--space
mrfakename/Z-Image-Turbo` for live slot counts) and 5 data rows print (the free
query engine works — no rate limit, no auth for public data). Real GPU run is
optional `[GATED: 1 run + ~3-6 GPU-s (measured 2.7-5.3)]`: `hfx gpu run
mrfakename/Z-Image-Turbo --fn generate_image --arg '"a cat astronaut"' --arg
1024 --arg 1024 --arg 4 --arg 42 --arg false --out ./out` → **done-when:**
`out/image.png` + `out/run-*.json` sidecar exist (the sidecar IS the
measurement record).

## 9. Teardown + where next

```bash
hfx host rm hfx-qs-test --yes
hfx etl rm hfx-qs-test --yes    # removes the step-3 repo shell (dry-run without --yes)
hfx host ls                     # done-when: no hfx-qs-test rows
```

| Want next | Go to |
|---|---|
| Every command in depth | `kit/AGENTS.md` (the reference) |
| The gotcha rules (read once, save hours) | AGENTS.md → "The rules that keep it free" |
| Why a call 402'd at $0.01 spend | AGENTS.md → "Burst mechanics" |
| Raw curl equivalents (no Python) | AGENTS.md → "Raw API quick reference" |
| More entities (orgs ×2-3 pools) | AGENTS.md → "Entity (org) lifecycle" |
| Your own GPU Spaces (day-30 unlock) | AGENTS.md → "The 30-day age-gate unlock" |
| Full research provenance | `RESOURCE-MAP.md` + `findings/` in the parent repo |

**The final oracle:** your site URL served your LLM-written text and CDN-hosted
image; total spend ≤$0.001; teardown clean. You have now exercised: status,
doctor, store, infer (+ its safety guard), cdn, host, gpu, etl — the full
free-tier surface in 15 minutes.
