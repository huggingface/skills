# Trackio Logbooks — sharing open experiments

A **logbook** is a shareable, Hub-native lab notebook for an experiment campaign, stored in `./.trackio/logbook/` (found by walking up from the cwd, like `.git`). It publishes to a static Hugging Face Space with three human views: Logbook, Traces, and Workspace. The Logbook sidebar lists Pages, while `trackio logbook read` provides compact agent views on demand.

The logbook is **just files you edit directly**. There are only a few CLI commands; everything else is a normal file edit.

## The few CLI commands

```bash
trackio logbook open [username/space] --title "..."     # scaffold ./.trackio/logbook/ (run once)
trackio logbook page "..."                              # add/select a page as the default target
trackio logbook cell markdown "..." --page "..."        # log a finding onto a page (creates it if new)
trackio logbook cell code --page "..." --code train.py [--output "..."]  # --output is optional
trackio logbook cell figure --page "..." --html plot.html --raw data.json  # inlined Plotly.js is rewritten to CDN (use --inline-plotlyjs to embed)
trackio logbook cell artifact project/name:vN            # record a Trackio artifact as its own cell
trackio logbook cell dashboard <project> [--space owner/name]  # embed a live Trackio dashboard
trackio logbook cell remove cell_<id> [--page "..."]     # delete a cell from a page
trackio logbook run --page "..." -- python train.py --lr 3e-4  # run + capture command, scripts, output, output files
trackio logbook attach trace <filepath> [--title "..."] # attach this agent session's JSON/JSONL trace
trackio logbook remove trace <session-id>                # remove an attached session
trackio logbook sync                                     # regenerate the site files from the page sources
trackio logbook read                                    # compact agent view of the whole logbook
trackio logbook read <username/space | url>             # read a remote logbook (Space id, Space URL, or serve URL)
trackio logbook read pages                              # list pages
trackio logbook read page "..."                         # markdown bodies + code/figure ids
trackio logbook read cell cell_<id> --full              # read full code cell
trackio logbook read cell cell_<id> --raw               # read figure raw data
trackio logbook read cell cell_<id> --html              # read figure HTML
trackio logbook serve [path]                            # preview locally
trackio logbook publish [username/space]                # manually publish the current state
trackio logbook publish --review-publication            # ask the Traces/Workspace privacy questions again
```

`cell markdown` **appends** a markdown cell — you never clobber findings someone else wrote. Fenced code blocks inside the markdown render with syntax highlighting, so embed short snippets directly in the body. Use `cell code` when the entry is code plus output (`--output` is optional). Use `cell figure` for HTML figures such as Plotly exports plus raw data. Use `cell artifact` to record a Trackio artifact and `cell dashboard` to embed a project's live Trackio dashboard. (`trackio.init()` / `trackio.log_artifact()` are side-effect-free on any logbook in the current directory — they never add cells or pages — so record artifacts and dashboards explicitly with these commands.) Every cell has a stable id and title; pass `--title` when you know the best label, otherwise Trackio derives one. Models, datasets, Spaces, artifacts, papers, jobs, buckets, and repos detected from URLs render as inline links or resource chips; images render inline and Trackio-tagged Spaces embed as live dashboards. Everything else is a direct file edit.

`run` is the preferred way to execute experiments from the terminal: it tees output live, stores the exact command, attaches any script/config argv tokens it can see, records exit code and duration, and captures truncated output in one code cell. It also detects model/data files the command created or modified under the working directory (checkpoints like `.pt`/`.safetensors`/`.ckpt`, datasets like `.parquet`/`.csv`/`.jsonl`) and records each as a **path-reference artifact cell**. Disable with `--no-artifacts`. A path-reference cell does not itself upload the file; it appears locally in Workspace when the run finishes and is mirrored only when Workspace publication is approved.

## Attach the current agent session

Near the beginning of an agent session, locate the JSON or JSONL file where the current agent runtime is recording its session, then attach it:

```bash
trackio logbook attach trace /absolute/path/to/current-session.jsonl
```

The agent runtime, not Trackio, determines this path. Find the current session file from the local runtime's own session/config directories and use the file whose timestamps and session metadata match the active conversation. This flow is intentionally vendor-agnostic: do not install a provider hook or wait for Trackio to identify Codex, Claude, or another runtime automatically.

Attaching records the source path and keeps a private raw copy under `.trackio/`; nothing is published merely by attaching. Sensitive capture state is added to `.trackio/.gitignore`. Active JSONL files may be attached before the session ends. While the local preview is open, Trackio refreshes changed attached sessions and Workspace files every few seconds; it also refreshes when attaching or publishing. A logbook can retain multiple attached sessions; the Traces view renders them chronologically with session anchors.

Attaching also establishes the Workspace baseline. The Workspace view lists the final model/data files with Trackio-supported artifact extensions that were created or changed after attachment. Publishing asks separately whether these files may be mirrored to a public or private HF Bucket; the default is not to publish them.

## The structure

- **Give the logbook a descriptive title.** Pass `--title "Reproducing X (paper)"` when you `open` it, or edit the `# ...` heading of `pages/index.md` afterwards. Without it the title defaults to the directory name (e.g. `cot`), which is a bad title for a published Space.
- **The main page** (`pages/index.md`) is the **table of contents only** — an `## Pages` table with a single `Page` column by default, one row per page, each linking to that page. **Never write findings here.**
- The default table is deliberately unopinionated. Add columns (e.g. `Status`, `Owner`, `Decision`) by editing the markdown directly; the CLI keeps appending rows correctly and fills a `Status` column if one exists.
- **Each experiment has its own page** where findings accumulate.
- **Open every page with a short context cell.** Before the first experiment lands on a page, add a markdown cell saying what the page is trying to show or reproduce (e.g. the paper's claim, in a sentence or two) and how you plan to test it. A reader landing on the page should understand the cells that follow without reading the rest of the logbook.

## Add pages as they become relevant

When you know the next page, add it directly:

```bash
trackio logbook page "Run baselines"
```

This adds a row to the table of contents, creates the page if needed, and makes it the default target for later `cell` and `run` commands. Add pages one at a time as the campaign takes shape; the reader still sees the same clean table of contents without requiring an upfront planning step.

Edit the table directly if you want extra columns (statuses, owners, decisions, …).

## Log onto an experiment

```bash
trackio logbook cell markdown "Zero-shot baseline: 41% valid; need SFT." --page "Baseline"
trackio logbook cell markdown "3e-4 wins; 1e-3 diverges ~300 steps." --page "LR sweep"
```

`--page "Name"` **creates the page + adds its row to the index** the first time, and appends to it thereafter. This keeps the main page a clean TOC automatically.

After a page has been updated once, `cell` and `run` can omit `--page`; they append to the most recently updated page.

## Read efficiently as an agent

Start with outlines, not full page bodies:

```bash
trackio logbook read
trackio logbook read /path/to/workspace
trackio logbook read username/space               # published logbook, no clone needed
trackio logbook read http://localhost:7861        # a locally served logbook
trackio logbook read pages --json
trackio logbook read page "Baseline" --json
trackio logbook read cell cell_ab12cd34ef56 --full --json
trackio logbook read cell cell_figure1234 --raw --json
```

`trackio logbook read` returns a flattened one-shot summary: the index page markdown verbatim, then every page's cells with

- full markdown and artifact cell bodies
- code cells: the command with exit code and duration, attached script names, the first 3 code lines, and the last 3 output lines (configure with `--head N` / `--tail N`; 0 hides)
- figure cells: raw data inlined when small (default ≤ 500 chars; configure with `--raw-limit N`), otherwise payload sizes

`read page` uses the same cell previews for one page. Fetch complete payloads with `read cell <id> [--full|--raw|--html]`. `read --json` returns the same content structured (pages → cells with command/exit_code/code_head/output_tail/raw fields) instead of markdown. Trackio does not write a separate flattened Markdown artifact for this.

## Also editable directly (your normal file tools)

Any page's content, the index table, and the styling (`logbook.css` / `index.html` / `logbook.js`, which live inside the logbook) are plain files — edit them when the CLI verbs aren't enough. `serve` to preview and fix.

- `--title`: an optional short title for the cell; if omitted, Trackio derives one. **Do not repeat the title as a heading at the top of the body** — the viewer already renders the title in the cell header.
- Body: normal Markdown. Use paragraphs, bullets, headings, and tables as appropriate for the material. Bare Hub model ids mentioned in text or output (e.g. `meta-llama/Llama-3.1-8B-Instruct`) are detected and linked automatically.
- Links: write URLs directly in the markdown body (or let them appear in command output). Resource URLs render inline for HF models / datasets / Spaces / **Jobs** (`huggingface.co/jobs/...`) / **Buckets** (`huggingface.co/buckets/...`), arXiv / HF papers, and GitHub. **Trackio dashboards embed live** in the page body — in the local preview too: `serve` hosts the local dashboard so embeds are live during training — and image URLs render inline. There is no `--link` flag.
- Code: embed fenced code blocks directly in the markdown body — they render with syntax highlighting. For code-plus-output entries use `cell code` (its `--code PATH` includes a file); `logbook run` attaches the scripts it executed automatically.
- Artifacts: record one with `trackio logbook cell artifact project/name:vN [--type dataset]` (or `logbook run`, which captures output files automatically). `trackio.log_artifact()` does **not** add a cell to a logbook in the current directory. Artifact cells render inline and are marked local until published. **Log datasets you construct locally as artifacts of type `dataset`** (e.g. a hand-curated eval set) so they are captured and pushed to the Bucket on publish.
- It's just Markdown you can also edit by hand — if something renders wrong, `serve` to preview and fix the file directly.

## Prefer typed cells when the shape is clear

```bash
trackio logbook cell code --page "Eval" --title "Eval output" --code eval.py --output "exact_match: 0.41"
trackio logbook cell figure --page "Samples" --title "Generated grid" --html grid.html --raw grid.json
trackio logbook run --page "Eval" -- python eval.py --checkpoint ckpt.safetensors
```

Typed cells still live in the same Markdown files. Keep the persisted cell types simple: markdown, code, figure, and artifact. If a plot has raw data, use a figure cell so humans see the HTML figure while agents can explicitly request the raw data. `cell figure` rewrites an inlined Plotly.js bundle to a CDN `<script src>` by default so pages stay small (pass `--inline-plotlyjs` to embed the ~3.5 MB library instead); you can still export with `fig.write_html(path, include_plotlyjs="cdn")` yourself.

## Make it reproducible

For each experiment, capture enough that someone could re-run it:

- The **exact code**: run experiments with `trackio logbook run -- ...` so the scripts are captured, or embed configs as fenced blocks in markdown.
- **Where it ran**: include the HF **Job** URL (`https://huggingface.co/jobs/<owner>/<id>`) in the cell body or output so a reader can open its logs/status.
- **What it produced**: dump generated images/plots and their **raw data** to an HF **Bucket**, and link both — the image (unfurls as a preview) and the underlying data file (so results can be re-plotted or checked), plus the Trackio dashboard for live metrics.

## Automatic capture from trackio

If a logbook exists in the working directory, trackio **auto-captures itself** — no manual cell needed for these:

- `trackio.init()` immediately records an **embedded dashboard cell** on a page named after the trackio **project** (one per project per page; live in the local preview, promoted to a Space on publish), so anyone watching the logbook sees training metrics in real time. `finish()` no longer writes a run cell. Note: the hook lives in the trackio the script imports — a separate environment with an older trackio won't fire it.
- `trackio.log_artifact(...)` records the artifact as its own **artifact cell**. On `publish`, artifacts are pushed to an HF Bucket and the cells link to it.
- `trackio logbook run` records model/data files the command created or modified as **path-reference artifact cells** (path, size, and type only). The cell itself does not upload the file. Captured paths appear in Workspace after the run finishes even without a trace; with an attached active trace, supported post-baseline files can appear while work is still in progress. They are uploaded only if Workspace publication is approved. Disable per run with `--no-artifacts`.

Local runs/artifacts are marked as local until you publish (see below). Set `TRACKIO_LOGBOOK_AUTONOTE=0` to disable (e.g. during large sweeps).

## Human views

The published logbook has three top-level views: **Logbook**, **Traces**, and **Workspace**. Logbook is the normal continuous logbook. Traces is the normalized chronological agent session view. Workspace is the downloadable final-state model/data file inventory associated with attached sessions. When those views are published, their headers link to the Agent Traces Dataset and HF Bucket respectively, including private destinations.

## Publishing & privacy

- **Local until `publish`** — edits never auto-sync. Nothing leaves the machine until you explicitly run `trackio logbook publish`. `publish` creates a public static Space by default, but attached Traces and tracked Workspace files each have a separate default-deny prompt.
- **Traces require explicit approval** — choose a public Agent Traces Dataset, a private Agent Traces Dataset, or not published (the default). Review the local Trace view first: raw sessions can contain prompts, tool inputs, command output, paths, screenshots, secrets, private code, and personal data. Supported Codex, Claude Code, Pi, and already-valid STS JSONL is uploaded unchanged; other attached formats are exported as Session Trace Simple Format. The Dataset card sets `viewer_mode: traces` and `format:agent-traces` so these sessions open in the Hub's native trace viewer.
- **Workspace requires explicit approval** — the prompt includes the tracked file count and offers a public HF Bucket, private HF Bucket, or not published (the default). Use `--traces public|private|none` and `--workspace public|private|none` for non-interactive publishing.
- Trackio remembers both publication choices, including “not published,” and reuses them on later manual publishes. It prints the reused choices each time. Run `trackio logbook publish --review-publication` to answer the questions again.
- Choosing “not published” after an earlier upload retracts the dedicated Dataset or Bucket after the replacement Space is published. Failed retractions are saved and retried on the next publish.
- The remote Space is remembered in `./.trackio/metadata.json`, so later `publish` commands need no Space argument.
- Extra Space tags (e.g. required by a challenge board) go in `./.trackio/metadata.json` as `"tags": ["some-tag", ...]` — they are written into the published Space README on every publish.
- **Publishing promotes local resources**: `publish` deploys any local trackio dashboards it captured as Spaces under the logbook's namespace and pushes local artifacts to a Bucket, then rewrites the links. Add `--private` to make the logbook, dashboards, and bucket all private (for team/internal logbooks); default is public.
