## etl — datasets as a free queryable data backend

> **You have data, no database.** Push a CSV to a public dataset repo and
> HuggingFace gives you — for $0 — a hosted REST API over it: SQL-ish WHERE +
> ORDER BY, full-text search, paginated rows, per-column statistics, and
> auto-converted parquet that DuckDB can query directly over HTTPS (yes,
> including cross-repo JOINs). Writes are git commits; reads are CDN-cached.
> Live-verified end-to-end: `data/kit-tests/etl/` (10/10 ground-truth checks).

**The flow: upload → (wait ~2–3 min) → query.**

```bash
# 1. Push data (csv/tsv/json/jsonl/parquet; creates the repo if needed)
hfx etl upload ./leads.csv                  # default repo: <you>/hf-free-maxxing-kit-etl
                                             # (namespace resolved from your token)
hfx etl upload ./leads.csv --repo myuser/leads --path data.csv

# 2. Wait for auto-parquet conversion (event-driven, ~2-3 min)
hfx etl splits myuser/leads --wait 180      # polls until READY, then probes /rows:
                                             # reports "READY but still warming" if the
                                             # query indexes aren't up yet (~+1-2 min)

# 3. Query it — server-side, no download
hfx etl filter myuser/leads --where "score>0.5 AND name LIKE '%acme%'" \
                          --orderby "score desc" --limit 100
hfx etl search myuser/leads --query "acme"          # token match, 100% recall
hfx etl rows   myuser/leads --offset 5000 --limit 100   # deep offsets OK (6.4M rows verified)
hfx etl stats  myuser/leads                          # free describe(): mean/median/std/histograms

# 4. Full SQL (GROUP BY, JOIN, window functions) — local DuckDB over the parquet URL
hfx etl parquet myuser/leads                        # prints the URLs + a copy-paste one-liner
hfx etl sql myuser/leads --query "SELECT name, count(*) n, avg(score) s \
                                  FROM data GROUP BY name ORDER BY s DESC"   # EXPERIMENTAL

# 5. Teardown — delete the whole repo (files + history + server views)
hfx etl rm myuser/leads                     # dry-run: shows what would go (exit 3)
hfx etl rm myuser/leads --yes               # DELETE /api/repos/delete + authed 404 verify
```

Works from browsers too — datasets-server CORS is `*`, so a static site can
`fetch()` your data with zero backend (pair with `hfx host`).

### Capability matrix (endpoint / syntax / limits)

| Command | Endpoint | Syntax | Limits & notes |
|---|---|---|---|
| `filter` | `/filter` | `--where "\"col\"=25"` · `"col">5` · `"col" LIKE '%x%'` · `AND`/`OR` + parens · `--orderby "\"col\" desc"` (single column, default asc) | page ≤ 100 · index = **first 5 GB** · `num_rows_total` = match count when `where` present · bare column names are auto-quoted by the kit |
| `search` | `/search` | `--query "token"` | token match, 100% recall (7/7 verified) · first 5 GB · index builds LAZILY — can 500 for minutes on fresh/idle datasets |
| `rows` | `/rows` | `--offset N --limit ≤100` | offset-past-end → 200 + empty; length clamps at end; deep offsets fine (6.5s @ 6.4M rows) |
| `stats` | `/statistics` | — | min/max/mean/median/std/histograms per column; std is **sample** (ddof=1); text cols → length stats; labels → frequencies |
| `parquet` | `/parquet` | — | lists `refs/convert/parquet` URLs; conversion = first 5 GB (`partial:true` beyond) |
| `splits` | `/splits` (+`/size`) | `--wait SECONDS` polls until READY, then probes `/rows?length=1` | READY ≠ queryable: the probe reports "READY but still warming" while the query indexes catch up (~+1-2 min) · `/size` (rows/numBytes) lags conversion by minutes |
| `sql` | local DuckDB | `--query "SELECT ... FROM data"` | EXPERIMENTAL · full ANSI SQL incl. cross-repo JOINs · your CPU + the resolver rate bucket |
| `rm` | `DELETE /api/repos/delete` | `hfx etl rm <ns>/<repo> --yes` | teardown: whole repo + history + server views go; without `--yes` = dry-run + exit 3 · quota reclaims ~1-2 min |

DuckDB one-liner (the pattern `hfx etl parquet` prints):

```bash
python3 -c "import duckdb; print(duckdb.sql(\"SELECT * FROM 'https://huggingface.co/datasets/<you>/<repo>/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet' LIMIT 10\"))"
```

The two lanes compose: **/filter+/rows for quick lookups and app previews,
parquet+DuckDB for analytics** (GROUP BY/JOIN verified: 37-row cross-repo
JOIN in 1.29s, 420MB shard columnar-read at ~6.4MB/s).

### Limits & gotchas (all live-verified)

1. **Public data only.** Private datasets → 501 on free accounts (PRO $9/mo).
   Never upload anything sensitive — public means public.
2. **Cold start.** Idle/fresh datasets 500 with "index is loading" or "busier
   than usual" — `filter`/`search`/`rows`/`stats` now note it on stderr and
   **auto-retry once after 60s**; a second failure exits 1 with the warming
   message. Budget ~2–3 min for conversion after upload, ~5 min for the filter
   index on first-ever touch.
   Writes are eventually-consistent (no transactions, no instant read-after-write).
3. **Page size hard cap 100** on every endpoint (client-side enforced too).
4. **5 GB first-chunk cap** for conversion + filter/search/statistics indexes
   (`partial:true` beyond; splits named `partial-*`).
5. **One data file per repo** unless you add a `configs:` YAML — heterogeneous
   multi-file repos can FAIL conversion. Same `--path` = replace (new commit).
6. **Filename → split name**: `k6_test_data.csv` became split **test** (the
   `_test` suffix convention). Use `data.csv` (or any keyword-free name) for
   the default `train` split. Same trap for `_train`/`_validation`.
7. **No rate limit observed** on datasets-server (12-call burst, flat latency)
   — but be polite; bulk extraction = parquet download lane (resolver bucket:
   5000/5min authed, 3000 anon). Anonymous reads get the shared 120s CDN cache;
   authed reads bypass it.
8. `/filter` can't do multi-key ORDER BY (422), aggregates, JOINs, or
   projections — that's the DuckDB lane.
9. Response cache is 120s (`x-revision` header detects staleness); signed CDN
   URLs behind the parquet 302 expire ~10 min — share resolve URLs, not signed ones.

### Teardown (delete the whole dataset repo)

Test/experiment datasets are disposable — clean them up so the 100GB private /
8.7TB public pools stay honest (public repos count against the public pool):

```bash
hfx etl rm myuser/leads            # dry-run: prints what would be deleted, exit 3
hfx etl rm myuser/leads --yes      # deletes repo + history + datasets-server views,
                                   # verifies with an authed GET -> 404
hfx store ls                       # confirm your namespace is clean
```

Quota reclaims within ~1-2 min. Programmatic (non-CLI) scripts must load the
token via the kit (`import hfx; hfx.load_env()`) — ambient `HF_TOKEN` is empty
in a fresh shell.

**Evidence:** `findings/datasets-etl-final.md` (the full verified matrix) ·
`data/kit-tests/etl/` (this kit's live test: 25 calls, 10/10 ground-truth
checks, conversion latencies, 4 new gotchas in `calls.log`).
