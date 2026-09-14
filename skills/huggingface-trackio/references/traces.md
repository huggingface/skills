# Analyzing Agent Traces with Trackio CLI

Traces are agent or LLM sessions: OpenAI-style messages plus **execution spans**
(model generations, tool calls, sub-steps) carrying latency, status, model, token
usage, and cost. Where metrics answer "how is training going", traces answer
"what is my agent actually doing in production, and what should I fix".

Use this reference when asked things like *"look at the traces and tell me what
we can improve"*, *"why is the agent slow/expensive"*, *"what's failing in
production"*, or *"where do the tokens go"*.

## The funnel

No single command answers "what can we improve". Work through four steps, and do
not skip step 3 — it is the difference between a bug report and a prioritized
one.

```
1. Orient      -> is there trace data, and does it carry spans?
2. Rollup      -> one command for the whole shape; read it for anomalies
3. Quantify    -> turn each anomaly into a measured cost or latency impact
4. Verify      -> read one full trace to confirm the story holds
```

### Step 1: Orient

```bash
trackio list projects --json
trackio list traces --project <name> --limit 5
```

Check the `Ops` column. If it is 0 everywhere, the traces carry no spans — only
messages are available, so latency/cost/tool analysis is not possible. Say so
instead of guessing.

Add `--space <space_id_or_url>` to every command below to analyze a deployed
Space rather than local data.

### Step 2: Rollup — one command for the whole shape

```bash
trackio get trace-summary --project <name>
```

```
operation                  | kind       | calls | errors | avg_ms  | max_ms  | input_tokens | output_tokens | cost_usd
provider-request           | generation | 205   | 0      | 3380.8  | 5535.0  | 2915829      | 63020         | 9.6928
run-bash-command           | tool       | 157   | 25     | 818.4   | 1548.0  | 0            | 0             | 0.0
acquire-sandbox            | span       | 48    | 0      | 2438.6  | 10615.0 | 0            | 0             | 0.0
```

Read it for anomalies. Each is a **hypothesis**, not yet a finding:

| Signal | Hypothesis to test |
|---|---|
| `errors` > 0 | A systematic tool/prompt bug, or genuine flakiness — step 3 distinguishes them |
| `input_tokens` >> `output_tokens` | Context re-sent every turn; prompt caching or tool-output truncation is the lever |
| `max_ms` >> `avg_ms` | Bimodal latency (cold starts, retries), not a uniformly slow operation |
| High `cost_usd` on one operation | Where optimization effort actually pays off |
| `calls` >> session count | Repeated work per session; look for retry loops |

### Step 3: Quantify — make each hypothesis a measured impact

The rollup cannot tell you whether 25 errors are one bug or twenty, or whether
they cost anything. Drop to SQL. `spans` is a JSON column, so `json_each` works.

**Which failures, and are they systematic?** A command that fails *every* time it
is attempted is a bug in the prompt or tooling; one that fails sometimes is
flakiness. Very different fixes.

```bash
trackio query project --project <name> --sql "
SELECT json_extract(s.value,'\$.input.command') AS cmd,
       json_extract(s.value,'\$.status') AS status,
       COUNT(*) AS n, COUNT(DISTINCT traces.id) AS sessions
FROM traces, json_each(traces.spans) AS s
WHERE json_extract(s.value,'\$.kind') = 'tool'
GROUP BY cmd, status ORDER BY n DESC"
```

**What does it cost?** Compare sessions that hit the problem against those that
did not. This is the step that turns an observation into a priority:

```bash
trackio query project --project <name> --sql "
WITH per_session AS (
  SELECT traces.id AS tid,
         SUM(COALESCE(json_extract(s.value,'\$.cost_usd'),0)) AS cost,
         SUM(CASE WHEN json_extract(s.value,'\$.name')='provider-request'
                  THEN 1 ELSE 0 END) AS model_calls,
         MAX(CASE WHEN json_extract(s.value,'\$.status')='error'
                  THEN 1 ELSE 0 END) AS hit
  FROM traces, json_each(traces.spans) AS s GROUP BY traces.id
)
SELECT hit, COUNT(*) AS sessions, ROUND(AVG(cost),4) AS avg_cost_usd,
       ROUND(AVG(model_calls),2) AS avg_model_calls
FROM per_session GROUP BY hit"
```

**Is a slow operation bimodal?** Group by whatever metadata marks the two modes
(e.g. a `cold_start` flag), or bucket the durations:

```bash
trackio query project --project <name> --sql "
SELECT json_extract(s.value,'\$.metadata.cold_start') AS cold_start,
       COUNT(*) AS n,
       ROUND(AVG((julianday(json_extract(s.value,'\$.end_time'))
                - julianday(json_extract(s.value,'\$.start_time')))*86400),2) AS avg_s,
       ROUND(MAX((julianday(json_extract(s.value,'\$.end_time'))
                - julianday(json_extract(s.value,'\$.start_time')))*86400),2) AS max_s
FROM traces, json_each(traces.spans) AS s
WHERE json_extract(s.value,'\$.name') = '<operation>'
GROUP BY cold_start"
```

**Is context growing within a session?** Compare per-turn input tokens, and
check whether any caching is happening at all:

```bash
trackio query project --project <name> --sql "
SELECT SUM(COALESCE(json_extract(s.value,'\$.usage.input_tokens'),0)) AS input_tokens,
       SUM(COALESCE(json_extract(s.value,'\$.usage.output_tokens'),0)) AS output_tokens,
       SUM(COALESCE(json_extract(s.value,'\$.metadata.cache_read_input_tokens'),0)) AS cached
FROM traces, json_each(traces.spans) AS s
WHERE json_extract(s.value,'\$.kind') = 'generation'"
```

Also useful: `trackio list traces --project <name> --search "<error text>"`
finds the affected sessions, since search covers span names, models, statuses,
and errors.

### Step 4: Verify — read one trace end to end

```bash
trackio get trace --project <name> --trace-id <id>
```

```
Trace f179746a789348639e1f1963f320bd02
  Totals:   error | 25.0s | $0.33 | 101338 in / 1804 out tokens | 21 operation(s)

Execution:
  answer-research-question [span]  25.0s
    generate-research-response [span]  23.7s
      acquire-sandbox [span]  914ms
      dispatch-model-request [span]  2.18s
        provider-request [generation]  2.18s  my-model  8347->239 tok  $0.03
      ERROR run-bash-command [tool]  168ms
        -> {"exit_code": 2, "stderr": "error: unrecognized arguments: --full"}
      dispatch-model-request [span]  3.40s
        provider-request [generation]  3.40s  my-model  14632->110 tok  $0.05
```

This confirms the aggregate story in one concrete session — here, input tokens
climbing 8347 -> 14632 per turn, with the failing call visible in place. It is
also the most legible artifact to show a human, so quote it when reporting.

`--trace-id` accepts the short id from `list traces` or the full stored id.

## Reporting rules

- **Report findings, not hypotheses.** "25 tool calls failed" is step 2 output.
  "This command failed 21/21 times, costing $0.03 and 0.6 extra model calls per
  affected session" is a finding. Do not present the former as the latter.
- **Attach a number to every recommendation**, drawn from step 3.
- **Distinguish systematic from flaky.** A 100% failure rate points at a prompt
  or tooling bug; a partial rate points at rate limits, timeouts, or retries.
- **Say when spans are missing.** Without `end_time`/`usage`/`cost_usd`, latency
  and cost analysis is not possible; recommend instrumenting those rather than
  inferring.
- **Do not trust a trace's `status` alone.** Operations derived from messages
  have no success signal (OpenAI-style tool results carry none), so their status
  is intentionally unset. Use the `errors` column and `error` fields.

## Cost and payload notes

`get trace-summary` and `query project` aggregate inside SQLite and return only
the result rows. `list traces` and `get trace` return full trace payloads,
including span `input`/`output`, which routinely contain the whole conversation
per generation. On projects with large prompts:

- Start with `trace-summary` and `query project`.
- Use `--limit` on `list traces`.
- Reach for `get trace` only once you know which trace you want.

Span `input`/`output` are deliberately **not** covered by `--search`, precisely
because they duplicate the conversation. Search matches message content, trace
metadata, and each span's `id`, `name`, `kind`, `model`, `status`, and `error`.

## Command reference

| Task | Command |
|---|---|
| List traces (all runs) | `trackio list traces --project <name>` |
| Filter by run / step / text | `trackio list traces --project <name> [--run <r>] [--step <n>] [--search <t>]` |
| Sort and page | `trackio list traces --project <name> --sort step_desc --limit 100 --offset 50` |
| One trace + span tree | `trackio get trace --project <name> --trace-id <id>` |
| Per-operation rollup | `trackio get trace-summary --project <name> [--run <r>]` |
| Arbitrary span analysis | `trackio query project --project <name> --sql "... json_each(traces.spans) ..."` |

`--sort` accepts `request_time_desc` (default), `request_time_asc`, `step_asc`,
`step_desc`. All commands accept `--json` and `--space`. With `--json`,
`list traces` adds a per-trace `summary` (latency, cost, tokens, status, span
count) so you can compute without re-deriving it.

See [storage_schema.md](storage_schema.md) for the full `traces` table schema.
