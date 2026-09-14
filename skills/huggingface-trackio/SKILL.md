---
name: huggingface-trackio
description: Track and visualize ML training experiments and agent traces with Trackio. Use when logging metrics during training, firing alerts for training, or retrieving/analyzing logged data.
metadata:
  source: https://github.com/gradio-app/trackio/tree/main/.agents/skills/trackio
---

# Trackio - Experiment Tracking for ML Training

Trackio is an experiment tracking library for logging and visualizing ML training metrics. It can be used locally or optionally syncs to Hugging Face Spaces for real-time monitoring dashboards.

## Tasks

| Task | Interface | Reference |
|------|-----------|-----------|
| **Logging metrics** during training | Python API | [logging_metrics.md](references/logging_metrics.md) |
| **Firing alerts** for training diagnostics | Python API | [alerts.md](references/alerts.md) |
| **Retrieving metrics & alerts** after/during training | CLI | [retrieving_metrics.md](references/retrieving_metrics.md) |
| **Analyzing agent traces** (latency, cost, tool failures) | CLI | [traces.md](references/traces.md) |
| **Inspecting storage schema and running direct SQL** | CLI | [storage_schema.md](references/storage_schema.md) |
| **Sharing an experiment campaign as a logbook** | CLI | [logbook.md](references/logbook.md) |

## When to Use Each

### Python API → Logging

Use `import trackio` in your training scripts to log metrics:

- Initialize tracking with `trackio.init()`
- Log metrics with `trackio.log()` or use TRL's `report_to="trackio"`
- Finalize with `trackio.finish()`

**Key concept**: For remote/cloud training, pass `space_id` — metrics sync to a Space dashboard so they persist after the instance terminates. Auto-created Spaces are **public by default** — pass `private=True` if the metrics should not be public.

→ See [logging_metrics.md](references/logging_metrics.md) for setup, TRL integration, and configuration options.

**When a logbook exists**: run ML scripts through `trackio logbook run -- ...` instead of invoking `python ...` directly. Keep `trackio.init()` / `trackio.log()` / `trackio.finish()` inside the script, but launch it like:

```bash
trackio logbook page "Baseline"
trackio logbook run -- python train.py --lr 1e-4
```

This tees output live and records the exact command, detected script/config files, exit code, duration, and captured output in the logbook. `trackio.init()` inside the script immediately adds a live embedded dashboard cell to the logbook page for that project, so anyone watching the logbook preview sees training metrics in real time.

### Python API → Alerts

Insert `trackio.alert()` calls in training code to flag important events — like inserting print statements for debugging, but structured and queryable:

- `trackio.alert(title="...", level=trackio.AlertLevel.WARN)` — fire an alert
- Three severity levels: `INFO`, `WARN`, `ERROR`
- Alerts are printed to terminal, stored in the database, shown in the dashboard, and optionally sent to webhooks (Slack/Discord)

**Key concept for LLM agents**: Alerts are the primary mechanism for autonomous experiment iteration. An agent should insert alerts into training code for diagnostic conditions (loss spikes, NaN gradients, low accuracy, training stalls). Since alerts are printed to the terminal, an agent that is watching the training script's output will see them automatically. For background or detached runs, the agent can poll via CLI instead.

→ See [alerts.md](references/alerts.md) for the full alerts API, webhook setup, and autonomous agent workflows.

### CLI → Retrieving

Use the `trackio` command to query logged metrics and alerts:

- `trackio list projects/runs/metrics` — discover what's available
- `trackio get project/run/metric` — retrieve summaries and values
- `trackio query project --project <name> --sql "SELECT ..."` — run catch-all read-only SQL
- `trackio list alerts --project <name> --json` — retrieve alerts
- `trackio list traces` / `get trace` / `get trace-summary` — inspect agent traces and spans
- `trackio show` — launch the dashboard
- `trackio sync` — sync to HF Space

**Key concept**: Add `--json` for programmatic output suitable for automation and LLM agents.

**Remote Spaces**: Add `--space <space_id_or_url>` to any `list`/`get`/`query` command to query a remote HF Space instead of local data. Use `--hf-token` for private Spaces.

→ See [retrieving_metrics.md](references/retrieving_metrics.md) for all commands, workflows, and JSON output formats.

### CLI → Analyzing agent traces

Traces are agent/LLM sessions: messages plus execution spans (model generations,
tool calls) carrying latency, status, token usage, and cost. Use these to answer
questions about **agent behaviour** rather than training progress:
*"look at the traces and tell me what we can improve"*, *"why is the agent slow
or expensive"*, *"what's failing"*.

- `trackio get trace-summary --project <name>` — per-operation rollup (calls, errors, latency, tokens, cost)
- `trackio list traces --project <name> [--search <text>]` — the trace index
- `trackio get trace --project <name> --trace-id <id>` — one session's full span tree
- `trackio query project --sql "... json_each(traces.spans) ..."` — arbitrary span analysis

Often you might need to run multiple commands to answer a question that a user has about the traces.

## Minimal Logging Setup

```python
import trackio

# Spaces are PUBLIC by default (good for shareable dashboards);
# pass private=True if the metrics should not be public
trackio.init(project="my-project", space_id="username/trackio", private=True)
trackio.log({"loss": 0.1, "accuracy": 0.9})
trackio.log({"loss": 0.09, "accuracy": 0.91})
trackio.finish()
```

### Minimal Retrieval

```bash
trackio list projects --json
trackio get metric --project my-project --run my-run --metric loss --json
trackio query project --project my-project --sql "SELECT name FROM sqlite_master WHERE type = 'table'" --json

# Query a remote Space
trackio list projects --space username/my-space --json
```

## Autonomous ML Experiment Workflow

When running experiments autonomously as an LLM agent, the recommended workflow is:

1. **Set up training with alerts** — insert `trackio.alert()` calls for diagnostic conditions
2. **Launch training** — if a logbook exists, use `trackio logbook run -- ...`; otherwise run the script normally
3. **Poll for alerts** — use `trackio list alerts --project <name> --json --since <timestamp>` to check for new alerts
4. **Read metrics** — use `trackio get metric ...` to inspect specific values
5. **Iterate** — based on alerts and metrics, stop the run, adjust hyperparameters, and launch a new run

```python
import trackio

trackio.init(project="my-project", config={"lr": 1e-4})

for step in range(num_steps):
    loss = train_step()
    trackio.log({"loss": loss, "step": step})

    if step > 100 and loss > 5.0:
        trackio.alert(
            title="Loss divergence",
            text=f"Loss {loss:.4f} still high after {step} steps",
            level=trackio.AlertLevel.ERROR,
        )
    if step > 0 and abs(loss) < 1e-8:
        trackio.alert(
            title="Vanishing loss",
            text="Loss near zero — possible gradient collapse",
            level=trackio.AlertLevel.WARN,
        )

trackio.finish()
```

Then poll from a separate terminal/process:

```bash
trackio list alerts --project my-project --json --since "2025-01-01T00:00:00"
```
