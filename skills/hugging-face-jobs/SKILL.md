---
name: hugging-face-jobs
description: Use this skill when users want to run workloads on Hugging Face Jobs infrastructure. Covers UV scripts, Docker jobs, hardware selection, timeouts, environment variables, secrets, namespaces, popular images, monitoring, debugging, and saving results back to the Hub.
license: Complete terms in LICENSE.txt
---

# Running Workloads on Hugging Face Jobs

## When to Use This Skill

Use this skill when users want to:
- Run Python, data, or ML workloads on Hugging Face infrastructure
- Use cloud CPUs or GPUs without local setup
- Launch batch jobs, experiments, training, or inference
- Push results back to the Hugging Face Hub

## Core Guidance

When helping with Hugging Face Jobs:

1. Default to the `hf jobs` CLI.
2. Use `hf jobs uv run` for most Python workloads.
3. Use `hf jobs run` for non-Python workloads or custom Docker images.
4. Always set a timeout for real workloads. The default is 30 minutes.
5. Jobs are ephemeral. If outputs are not uploaded elsewhere, they are lost.
6. If the job needs Hub access, pass `--secrets HF_TOKEN`.
7. If the user wants org billing or org-owned jobs, add `--namespace <org>`.

Keep answers short and practical. Prefer a concrete command the user can run.

## Overview

Hugging Face Jobs runs compute on managed infrastructure with a UV-like or Docker-like interface.

- UV mode: `hf jobs uv run ...`
- Docker mode: `hf jobs run ...`
- Monitoring: `hf jobs ps`, `hf jobs logs`, `hf jobs stats`, `hf jobs inspect`
- Popular images: `--image vllm/vllm-openai`, `--image huggingface/trl`

Jobs are a good fit for:
- Data processing
- Batch inference
- Fine-tuning and experiments
- Synthetic data generation
- Evaluation runs

## Prerequisites

Jobs require Hugging Face authentication.

Install the CLI:

```bash
curl -LsSf https://hf.co/cli/install.sh | bash
```

Or:

```bash
brew install hf
```

```bash
uv tool install hf
```

Authenticate with a token that can start and manage Jobs:

```bash
hf auth login
```

Useful checks:

```bash
hf whoami
hf jobs hardware
```

## Quick Start

Hello world with UV:

```bash
hf jobs uv run python -c 'print("Hello from the cloud!")'
```

Run a local Python script:

```bash
hf jobs uv run script.py
```

Hello world with Docker:

```bash
hf jobs run ubuntu echo 'Hello from the cloud!'
```

The CLI prints a job ID and a browser URL like:

```text
https://huggingface.co/jobs/<namespace>/<job-id>
```

You can stop log streaming locally and the remote job keeps running.

## UV Jobs

Use `hf jobs uv run` for most Python workloads. This is the default recommendation.

### Basic Pattern

```bash
hf jobs uv run \
  --flavor cpu-basic \
  --python 3.12 \
  --timeout 30m \
  script.py
```

### Add Dependencies

Use `--with` for quick dependencies:

```bash
hf jobs uv run \
  --with trl \
  --with datasets \
  train.py
```

Use `--` when you want to clearly separate Jobs or UV flags from the command:

```bash
hf jobs uv run \
  --with trl \
  --flavor a10g-small \
  --secrets HF_TOKEN \
  -- sft.py --model_name_or_path Qwen/Qwen3-0.6B
```

Or make the script self-contained with a PEP 723 header:

```python
# /// script
# dependencies = ["datasets", "trl"]
# ///

from datasets import load_dataset
from trl import SFTTrainer
```

### GPU Training Example

```bash
hf jobs uv run \
  --flavor a100-large \
  --timeout 6h \
  --with trl \
  --secrets HF_TOKEN \
  train.py
```

Use `--secrets HF_TOKEN` when the script pushes a model or dataset, or reads private Hub assets. Ask the user in case you don't have a `HF_TOKEN` with the appropriate read or write access.

### Custom UV Image

The default UV image is `ghcr.io/astral-sh/uv:python3.12-bookworm`. Override it with `--image` when a workload needs a prebuilt runtime:

```bash
hf jobs uv run \
  --image huggingface/trl \
  --flavor a100-large \
  --timeout 6h \
  --secrets HF_TOKEN \
  train.py
```

### When UV Is Best

Choose UV jobs when:
- The workload is Python-first
- Dependencies are simple to declare with `--with` or PEP 723
- You want the shortest path from local script to remote execution

## Docker Jobs

Use `hf jobs run` when you want full control over the container or the workload is not a simple UV script.

### Basic Pattern

```bash
hf jobs run \
  --flavor cpu-basic \
  --timeout 30m \
  python:3.12 \
  python -c "print('Hello from HF Jobs!')"
```

All Jobs options must come before the image. Use `--` if you want to separate them clearly:

```bash
hf jobs run --timeout 30m ubuntu -- echo "Hello from the cloud!"
```

### GPU Example

```bash
hf jobs run \
  --flavor a10g-large \
  --timeout 1h \
  pytorch/pytorch:2.6.0-cuda12.4-cudnn9-devel \
  python -c "import torch; print(torch.cuda.get_device_name())"
```

### When Docker Is Best

Choose Docker jobs when:
- You need a specific image
- The workload is not Python
- You need a prebuilt runtime with system dependencies already installed

## Environment Variables and Secrets

Jobs expose built-in environment variables inside the container:
- `JOB_ID`
- `ACCELERATOR`
- `CPU_CORES`
- `MEMORY`

Example:

```bash
hf jobs run python:3.12 python -c "import os; print(os.environ['JOB_ID'], os.environ['CPU_CORES'])"
```

Pass user-defined environment variables with `-e` or `--env-file`:

```bash
hf jobs uv run -e FOO=foo -e BAR=bar script.py
hf jobs uv run --env-file .env script.py
```

Pass secrets with `-s`, `--secrets-file`, or `--secrets HF_TOKEN`:

```bash
hf jobs uv run -s API_KEY=secret script.py
hf jobs uv run --secrets-file .env.secrets script.py
hf jobs uv run --secrets HF_TOKEN script.py
```

## Hardware and Pricing

Use `hf jobs hardware` to see the current hardware catalog and pricing.

### Common Choices

| Flavor | Typical Use | Price |
| --- | --- | --- |
| `cpu-basic` | small scripts, smoke tests | $0.01/hour |
| `cpu-upgrade` | larger CPU data jobs | $0.03/hour |
| `t4-small` | lightweight GPU inference | $0.40/hour |
| `a10g-small` | single-GPU training or inference | $1.00/hour |
| `l4x1` | medium GPU inference | $0.80/hour |
| `a10g-large` | heavier inference or training | $1.50/hour |
| `a100-large` | large training or high-throughput jobs | $2.50/hour |
| `l40sx1` | larger inference workloads | $1.80/hour |

### Practical Sizing

- Start with `cpu-basic` or `cpu-upgrade` for data processing and validation.
- Use `t4-small` or `l4x1` for small to medium inference workloads.
- Use `a10g-large` or `a100-large` for training or large-model inference.
- Scale up only after a smaller run proves the workload needs it.

## Timeouts and Cost Control

The default timeout is 30 minutes. Set `--timeout` explicitly for anything non-trivial.

Examples:

```bash
hf jobs uv run --timeout 2h script.py
hf jobs run --timeout 3h ubuntu bash -lc "python main.py"
```

Good habits:
- Add a time buffer for dependency install and uploads.
- Cancel irrelevant jobs early with `hf jobs cancel`.
- Test on smaller hardware before scaling up.
- Use your organization namespace when billing should go to the org.

Organization billing example:

```bash
hf jobs run --namespace my-org ubuntu echo "bill this to the org"
```

## Labels

Add labels to jobs with `--label`. This is useful for later filtering in the UI or CLI.

Examples:

```bash
hf jobs uv run \
  --label fine-tuning \
  --label model=Qwen3-0.6B \
  --label dataset=Capybara \
  train.py
```

Notes:
- Use plain labels like `--label fine-tuning` for broad grouping.
- Use key-value labels like `--label model=Qwen3-0.6B` for structured filtering.
- Reusing the same key overwrites the previous value for that key.

## Monitoring and Management

List running jobs:

```bash
hf jobs ps
```

List all jobs:

```bash
hf jobs ps -a
```

Filter jobs:

```bash
hf jobs ps -a --filter status=error
hf jobs ps -a --filter label=fine-tuning
hf jobs ps -a --filter "command=*train.py"
hf jobs ps -a --filter label!=prod
```

Inspect a job:

```bash
hf jobs inspect <job-id>
```

Stream logs:

```bash
hf jobs logs <job-id>
```

View CPU, memory, network, and GPU usage:

```bash
hf jobs stats
hf jobs stats <job-id>
```

Cancel a job:

```bash
hf jobs cancel <job-id>
```

If you are working under an organization, add `--namespace <org-name>` to these commands.

To debug a failed job, inspect it first and then read the logs:

```bash
hf jobs inspect <job-id>
hf jobs logs <job-id>
```

If the remote run is failing for unclear reasons, reproduce it locally with the equivalent local command:
- `hf jobs uv run ...` -> `uv run ...`
- `hf jobs run ...` -> `docker run ...`

## Saving Results

Job filesystems are temporary. Persist important outputs before the job ends.

Good persistence targets:
- Push models or datasets to the Hugging Face Hub
- Upload artifacts to a Hub repo
- Send outputs to external storage such as S3 or GCS

If a script needs authenticated Hub access, pass:

```bash
hf jobs uv run --secrets HF_TOKEN script.py
```

Inside the job, the token is available as `HF_TOKEN`.

Minimal pattern:

```python
import os
from huggingface_hub import HfApi

api = HfApi(token=os.environ["HF_TOKEN"])
```

Use this for:
- `push_to_hub(...)`
- `upload_file(...)`
- reading private repos inside the job

## Examples and Reusable Scripts

Point users to existing Jobs-ready scripts before reinventing the workflow.

Useful sources:
- `https://huggingface.co/uv-scripts` for self-contained UV scripts
- Unsloth Jobs scripts for LLM or VLM fine-tuning
- Transformers example scripts that can run directly on Jobs

Example with a remote script:

```bash
hf jobs uv run \
  --flavor a10g-small \
  --secrets HF_TOKEN \
  https://raw.githubusercontent.com/huggingface/transformers/main/examples/pytorch/image-classification/run_image_classification.py \
  --model_name_or_path google/vit-base-patch16-224-in21k \
  --dataset_name ethz/food101 \
  --output_dir vit-food101 \
  --push_to_hub
```

Prefer these examples when the user asks for a common training, inference, OCR, or data-processing pattern.

## Scheduled Jobs

Use scheduled Jobs for recurring runs. The same options as regular Jobs apply, including `--timeout`, `--label`, env vars, secrets, and hardware.

Examples:

```bash
hf jobs scheduled uv run @hourly script.py
hf jobs scheduled uv run "0 9 * * 1" python -c "print('Every Monday at 9 AM')"
hf jobs scheduled run @daily ubuntu echo "scheduled job"
```

Manage scheduled jobs:

```bash
hf jobs scheduled ps
hf jobs scheduled ps -a
hf jobs scheduled inspect <job-id>
hf jobs scheduled suspend <job-id>
hf jobs scheduled resume <job-id>
hf jobs scheduled delete <job-id>
```

## Webhooks Automation

Use webhooks when a Job should run after Hub events such as repo updates.

Create the webhook from Python with `create_webhook(...)` and point it at a Job. The triggered Job receives the webhook payload in `WEBHOOK_PAYLOAD`.

Minimal pattern:

```python
from huggingface_hub import create_webhook

webhook = create_webhook(
    job_id=job_id,
    watched=[{"type": "user", "name": "your-username"}],
    domains=["repo"],
    secret="your-secret",
)
```

Mention this when the user wants event-driven automation instead of polling or cron scheduling.

## Popular Images

Use `--image` when the workload benefits from an image that already includes the right stack.

For vLLM batch inference:

```bash
hf jobs uv run --image vllm/vllm-openai --flavor l4x4 generate-responses.py
```

For TRL training:

```bash
hf jobs uv run --image huggingface/trl --flavor a100-large --secrets HF_TOKEN train.py
```

## Local Scripts in This Skill

This skill includes example scripts in `scripts/`:

- `scripts/generate-responses.py`
- `scripts/cot-self-instruct.py`
- `scripts/finepdfs-stats.py`

Treat them like any other local script:

```bash
hf jobs uv run --timeout 2h --flavor cpu-upgrade scripts/finepdfs-stats.py
```

If a script writes back to the Hub, add `--secrets HF_TOKEN`.

## Troubleshooting

### Timeout

Symptom: the job stops before finishing.

Fix:
- Increase `--timeout`
- Reduce workload size
- Move to faster hardware

### Out of Memory

Symptom: the job crashes on large batches or model loads.

Fix:
- Reduce batch size
- Process in chunks
- Move to a larger CPU or GPU flavor

### Auth Errors

Symptom: 401, 403, or push failures.

Fix:
- Run `hf auth login` locally
- Pass `--secrets HF_TOKEN`
- Check that the token has the required permissions

### Wrong Namespace

Symptom: the job appears under the wrong account or org commands fail.

Fix:
- Add `--namespace <org-name>`
- Ensure the token can manage Jobs in that namespace

### Missing Packages

Symptom: import errors.

Fix:
- Add dependencies with `--with`
- Or declare them in the script's PEP 723 header

### Lost Outputs

Symptom: results disappear after completion.

Fix:
- Upload outputs before the job exits
- Push to the Hub or another storage backend

### Scheduled Job Issues

Symptom: the recurring run does not fire or no longer runs.

Fix:
- Check `hf jobs scheduled ps -a`
- Inspect the scheduled job configuration
- Resume it if it was suspended

### Webhook Issues

Symptom: repo events happen but the Job is not triggered.

Fix:
- Verify the webhook watches the correct user or org
- Confirm the right event domains are configured
- Check the target Job and any secret or auth requirements

## Official References
- [Examples & Tutorials](https://huggingface.co/docs/hub/jobs-examples)
- [Manage Jobs](https://huggingface.co/docs/hub/jobs-manage)
- [Configuration](https://huggingface.co/docs/hub/jobs-configuration)
- [Schedule Jobs](https://huggingface.co/docs/hub/jobs-schedule)
- [Webhooks Automation](https://huggingface.co/docs/hub/jobs-webhooks)
- [Jobs Reference](https://huggingface.co/docs/hub/jobs-reference)
- [Popular Images](https://huggingface.co/docs/hub/jobs-popular-images)

## Key Takeaways
1. Prefer `hf jobs uv run` for most Python jobs.
2. Use `hf jobs run` for custom containers or non-Python commands.
3. Set `--timeout` explicitly.
4. Pass `--secrets HF_TOKEN` when the job needs Hub access.
5. Use `-e`, `--env-file`, `-s`, and `--secrets-file` for config and secrets.
6. Use official examples or remote scripts when they already match the task.
7. Use scheduled jobs for recurring runs and webhooks for event-driven runs.
8. Persist outputs before the job exits.
9. Use `hf jobs ps`, `logs`, `inspect`, `stats`, and `cancel` to manage jobs.
