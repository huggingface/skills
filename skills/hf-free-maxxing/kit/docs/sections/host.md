## host — free static-site hosting (Spaces, sdk: static)

`hfx host deploy DIR -n NAME` creates (if absent) a **public static Space**
and uploads every non-dotfile in `DIR` recursively via `huggingface_hub`.
Always-on from birth, no cold start, free within the 20 TB/mo bandwidth quota,
unlimited site count, and **CORS `*` on every response** (any site can fetch
your assets — a free JSON/asset CDN in its own right).

```bash
hfx host deploy ./mysite -n my-site
# → LIVE: https://<you>-my-site.static.hf.space

hfx host deploy ./site -n my-site --entity my-org    # org namespace (orgs multiply hosting)
hfx host ls                                           # your spaces
hfx host ls --entity my-org
hfx host rm my-site --dry-run                         # show what WOULD be deleted
hfx host rm my-site --yes                             # actually delete (kit/test names only)
```

What deploy does: `POST /api/repos/create {"type":"space","sdk":"static",
"private":false}` → `upload_file` per file. Your `README.md` is **skipped
unless it carries `sdk:` front-matter** (the auto-generated one is what keeps
the Space a static Space — clobbering it breaks the site). Dotfiles are never
uploaded.

| Limit / gotcha | Detail |
|---|---|
| Routing | **exact file paths only** — no clean URLs, no dir index, no SPA fallback, no custom 404 (`404.html` is decorative). Bare `GET /` works (302 → `/index.html`); for multi-page sites either link FULL file paths (`/about.html`) or use a hash router (`/#/about`); trailing-slash links bounce visitors to huggingface.co |
| Caching | ETag/304 on assets, **no `Cache-Control`**, no gzip → version assets (`app.js?v=2`) and pre-minify |
| Privacy | everything in a public Space is world-readable (it's a public git repo); `.md` files serve as RENDERED HTML |
| Variables | injected into served HTML as `window.huggingface.variables` → **public by design**; secrets exist but are write-only and useless (no backend) |
| Not free/absent | custom domains = PRO $9/mo; `app_build_command` builds are credits-gated (build in CI, upload `dist/`); private Spaces are not web-servable as a site |
| Safety | `hfx host rm` refuses names without "test"/"kit" (exit 3) and asks y/N unless `--yes` |

`rm` uses `DELETE /api/repos/delete` (verified; the plausible-looking
`DELETE /api/spaces/{ns}/{name}` is a 404 route).

Evidence: playbooks/static-hosting.md · live test: data/kit-tests/cdn-host-md/
