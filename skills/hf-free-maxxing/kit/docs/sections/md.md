## md — free markdown→HTML renderer

`hfx md render FILE_OR_TEXT` renders markdown through the community-blog
preview API (`POST /api/blog/preview {"content": ...}` → `{"html": ...}`) —
the same renderer the HF blog editor uses. Costs nothing (`api` bucket,
1000/5min).

```bash
hfx md render "**bold** and a list"
# → <p><strong>bold</strong> and a list</p>

hfx md render README.md            # file input
hfx md render - < notes.md         # stdin
hfx --json md render "# hi"        # {"html": "<h1 ...>...</h1>\n"}
```

| Limit | Detail |
|---|---|
| Auth | **web-session cookie only** (`HF_JWT`) — PATs get 401, anonymous gets 401; Origin/Referer headers required (the kit sends them) |
| Math | **no KaTeX** — `$E=mc^2$` passes through unrendered |
| Output | headings with anchor links, bold, inline `code`, fenced blocks (`<pre><code class="language-x">`), links (rel=nofollow), images, lists, blockquotes — wrapped in HF blog Tailwind classes |

Pairs with `hfx cdn put` (upload image → embed the returned URL) and
`hfx host deploy` (ship rendered HTML to a static Space).

Evidence: findings/blog-publish-probe.md §4 · live test: data/kit-tests/cdn-host-md/
