# Trackio Storage Schema and Direct SQL

Use this reference when you need to inspect Trackio data directly instead of going through higher-level `trackio list` or `trackio get` commands.

## Where Data Is Stored

- Local project databases live in `TRACKIO_DIR`, which defaults to `~/.cache/huggingface/trackio`.
- Each project is stored in its own SQLite file: `{project}.db`.
- Media files live under `TRACKIO_DIR/media/`.
- Parquet files are derived exports written from SQLite for syncing and static Spaces.

## SQLite Tables

Trackio defines its live schema in `trackio/sqlite_storage.py` inside `SQLiteStorage.init_db()`.

### `metrics`

- `id`: integer primary key
- `timestamp`: ISO timestamp
- `run_name`: run identifier
- `step`: integer step
- `metrics`: JSON text payload
- `log_id`: optional deduplication key
- `space_id`: optional pending-sync marker

Indexes:

- `(run_name, step)`
- `(run_name, timestamp)`
- unique partial index on `log_id`
- partial index on `space_id`

### `configs`

- `id`: integer primary key
- `run_name`: run identifier
- `config`: JSON text payload
- `created_at`: ISO timestamp

Constraints:

- unique `run_name`
- index on `run_name`

### `system_metrics`

- `id`: integer primary key
- `timestamp`: ISO timestamp
- `run_name`: run identifier
- `metrics`: JSON text payload
- `log_id`: optional deduplication key
- `space_id`: optional pending-sync marker

Indexes:

- `(run_name, timestamp)`
- unique partial index on `log_id`
- partial index on `space_id`

### `project_metadata`

- `key`: primary key
- `value`: metadata value

### `pending_uploads`

- `id`
- `space_id`
- `run_name`
- `step`
- `file_path`
- `relative_path`
- `created_at`

### `alerts`

- `id`
- `timestamp`
- `run_name`
- `title`
- `text`
- `level`
- `step`
- `alert_id`

Indexes:

- `run_name`
- `timestamp`
- unique partial index on `alert_id`

### `traces`

- `id` (primary key, `run_id:log_id:key[:index]`)
- `run_id`
- `run_name`
- `timestamp`
- `step`
- `key` — the key used in the `trackio.log()` payload
- `trace_index` — position when traces were logged as a list, else NULL
- `messages` — JSON, OpenAI-style messages
- `metadata` — JSON, trace-level metadata
- `spans` — JSON array of execution spans, defaults to `[]`
- `search_text` — flattened text backing `--search`
- `log_id`, `space_id`

Indexes:

- `(run_id, step)`
- `(run_id, timestamp)`
- `search_text`

`spans` is a JSON array, so use `json_each` to analyze it. Each span may carry
`id`, `parent_id`, `name`, `kind` (`span`/`generation`/`tool`), `start_time`,
`end_time`, `duration_ms`, `status`, `error`, `input`, `output`, `model`,
`usage.input_tokens`, `usage.output_tokens`, `cost_usd`, and `metadata`:

```bash
trackio query project --project <name> --sql "
SELECT json_extract(s.value,'\$.name') AS operation, COUNT(*) AS calls
FROM traces, json_each(traces.spans) AS s
GROUP BY operation ORDER BY calls DESC"
```

Prefer the dedicated commands (`trackio get trace-summary`, `trackio list
traces`) over hand-written SQL where they cover the question — see
[traces.md](traces.md).

## Parquet Layout

Trackio flattens JSON blobs when exporting parquet:

- `{project}.parquet` comes from `metrics`
- `{project}_system.parquet` comes from `system_metrics`
- `{project}_configs.parquet` comes from `configs`

Static export layout:

- `metrics.parquet`
- `aux/system_metrics.parquet`
- `aux/configs.parquet`
- `runs.json`
- `settings.json`

The flattened parquet files keep structural columns such as `timestamp`, `run_name`, and `step`, then add one column per JSON key found in the source payload.

## Direct SQL With The CLI

Use `trackio query` for read-only SQL:

```bash
trackio query project --project my-project --sql "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name" --json
trackio query project --project my-project --sql "PRAGMA table_info(metrics)"
trackio query project --project my-project --sql "SELECT run_name, MAX(step) AS last_step FROM metrics GROUP BY run_name ORDER BY last_step DESC"
```

Remote query works too:

```bash
trackio query project --project my-project --sql "SELECT COUNT(*) AS num_alerts FROM alerts" --space username/my-space --json
```

`trackio query` accepts read-only `SELECT`, `WITH`, and safe schema `PRAGMA` queries.

## Common Query Patterns

Recent alerts:

```bash
trackio query project --project my-project --sql "SELECT timestamp, run_name, level, title, step FROM alerts ORDER BY timestamp DESC LIMIT 20"
```

Latest step per run:

```bash
trackio query project --project my-project --sql "SELECT run_name, MAX(step) AS last_step FROM metrics GROUP BY run_name ORDER BY last_step DESC"
```

Recent configs:

```bash
trackio query project --project my-project --sql "SELECT run_name, created_at, config FROM configs ORDER BY created_at DESC"
```

Schema inspection:

```bash
trackio query project --project my-project --sql "PRAGMA index_list(metrics)"
```

## Agent Guidance

- Start with `trackio list projects --json` if you do not know the project name yet.
- Use `trackio get` for common summaries and metric retrieval.
- Fall back to `trackio query` when you need one-off aggregates, joins, or schema introspection.
- Prefer `--json` when another agent or script needs to consume the result.
