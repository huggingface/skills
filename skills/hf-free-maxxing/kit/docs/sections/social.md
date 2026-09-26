## social — discussions, collections, likes (free content layer)

Thin wrappers over the community APIs — free "comments + curation + applause"
for any project living on HF repos. Discussions and collections take a PAT
(no CSRF); **likes need the web-session cookie** (`HF_JWT`).

```bash
hfx social discuss <you>/my-space            # list discussions
hfx social discuss <you>/my-space --create \
    --title "Feedback" --body "Say hi"              # → prints the URL; --rm N
hfx social collect ls                               # your collections
hfx social collect create --title "My reading list" # → slug ns/name-<id>
hfx social collect add --slug <slug> --item owner/repo --note "why"
hfx social collect rm --slug <slug>
hfx social like owner/repo        # cookie required; unlike to undo
```

### Discussions = a free comment/feedback/kanban layer

Full CRUD on any repo you can see (public, or your private ones): create,
comment, **12 reactions** (🔥 🚀 👀 ❤️ 🤗 😎 ➕ 🧠 👍 🤝 😔 🤯), plus
merge/pin/status/ignore/hide per the openapi. Bot threads (parquet-converter)
show up in notifications — a repo discussion thread is the closest thing HF
has to free hosted comments; embed it under your demo Space. Deleting via
`--rm N` works for your own discussions (verified on the kit test repo).

### Collections = free public curation/read-lists

`POST /api/collections {title, namespace, item?}` — the slug gets a
`-<id>` suffix (keep it: every follow-up call wants the FULL slug). Items:
`space|model|dataset|bucket|paper|collection` + optional ≤500-char note.
Public page at `https://huggingface.co/collections/<slug>` with upvotes —
use as a shareable reading list, changelog, or "awesome-list" for your
project. (No `/like` route on collections — 404, upvote is web-only.)

### Likes (cookie-only) — the 2026-09 drift

`POST/DELETE /api/{type}s/{repo}/like`. PAT → 401, always cookie. The POST
now additionally needs a **`{"csrf": …}` JSON body** (token scraped from the
homepage `authLight.csrfToken` — the kit does this for you) — cookie+Origin
alone 403s `CSRF token not provided`; DELETE needs no csrf. →
`{likes, isLikedByUser}`; 409 = already liked. Don't mass-like: ToS-wise
keep `blockedPastWeek=0`.

Evidence: findings/review-identity-infra-cluster.md §C1-C3 (discussions,
collections, likes/follow) · live tests: data/kit-tests/k7/
(discussion create→list→delete ✓, collection create→add→ls→delete ✓,
like→unlike with the csrf recipe ✓).
