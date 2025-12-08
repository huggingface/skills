# Backend configuration

This document covers backend runner configuration and implementation for HPO trials.

## Overview

The HPO orchestrator dispatches individual training trials to cloud GPU backends. Three backends are provided out of the box:

| Backend | Best for | Cold start | Cost |
|---------|----------|------------|------|
| HuggingFace Jobs | HF ecosystem integration | ~30s | $$ |
| Modal | Fast iteration, Python-native | ~2-4s | $$ |
| RunPod | Budget-conscious, flexible | ~2s | $ |

## HuggingFace Jobs (default)

Native integration with the HuggingFace ecosystem. Trials run as UV scripts on HF infrastructure.

### Configuration

```python
from scripts.hf_jobs_runner import HFJobsRunner

runner = HFJobsRunner(
    flavour="a10g-large",           # GPU type
    timeout="2h",                    # Per-trial timeout
    secrets={"HF_TOKEN": "$HF_TOKEN"},
    results_repo="username/my-hpo-results",  # Optional: for intermediate values
)
```

### Hardware flavours

| Flavour | GPU | VRAM | Cost/hr | Model size |
|---------|-----|------|---------|------------|
| `t4-small` | T4 | 16GB | ~$0.75 | <1B |
| `t4-medium` | T4 | 16GB | ~$1.50 | 1-3B |
| `l4x1` | L4 | 24GB | ~$2.00 | 1-3B |
| `a10g-small` | A10G | 24GB | ~$3.50 | 3-7B |
| `a10g-large` | A10G | 24GB | ~$5.00 | 3-7B |
| `a10g-largex2` | 2x A10G | 48GB | ~$10.00 | 7-13B |
| `a100-large` | A100 | 80GB | ~$10.00 | 7-13B |
| `h100` | H100 | 80GB | ~$15.00 | 13B+ |

### Requirements

- HuggingFace Pro, Team, or Enterprise account
- `huggingface_hub>=0.34.0`
- Authenticated: `huggingface-cli login`

### Timeout formats

- Minutes: `"30m"`, `"90m"`
- Hours: `"2h"`, `"1.5h"`
- Days: `"1d"`
- Seconds: `3600` (integer)

**Recommendation:** Set timeout to 1.5x expected trial duration.

### Example

```python
from scripts.hpo_orchestrator import HPOStudy
from scripts.hf_jobs_runner import HFJobsRunner

runner = HFJobsRunner(
    flavour="a10g-large",
    timeout="2h",
    secrets={"HF_TOKEN": "$HF_TOKEN"},
    results_repo="username/my-hpo-results",
)

study = HPOStudy(
    name="my-study",
    model="Qwen/Qwen2.5-0.5B",
    dataset="trl-lib/Capybara",
    runner=runner,
    n_trials=10,
)

study.optimise()
```

---

## Modal

Python-native serverless GPU platform with very fast cold starts.

### Setup

1. Install Modal:
   ```bash
   pip install modal
   ```

2. Authenticate:
   ```bash
   modal token new
   ```

3. Create a Modal secret for HuggingFace:
   ```bash
   modal secret create huggingface-secret HF_TOKEN=hf_xxx...
   ```

4. Deploy the training function:
   ```bash
   # Save the template from scripts/modal_runner.py (MODAL_APP_TEMPLATE)
   # to a file called modal_hpo_app.py, then:
   modal deploy modal_hpo_app.py
   ```

### Configuration

```python
from scripts.modal_runner import ModalRunner

runner = ModalRunner(
    app_name="hpo-training",        # Modal app name
    function_name="train_trial",     # Function name
    gpu="A10G",                      # GPU type
    gpu_count=1,                     # Number of GPUs
    timeout_seconds=7200,            # 2 hours
    results_repo="username/my-hpo-results",
)
```

### GPU options

| GPU | VRAM | Cost/hr | Best for |
|-----|------|---------|----------|
| `T4` | 16GB | ~$0.59 | Small models, testing |
| `L4` | 24GB | ~$0.80 | Efficient inference |
| `A10G` | 24GB | ~$1.10 | General training |
| `A100` | 40GB | ~$3.00 | Large models |
| `A100-80GB` | 80GB | ~$4.00 | Very large models |
| `H100` | 80GB | ~$4.50 | Maximum performance |

Multi-GPU: Use `gpu_count=2` or `gpu="A100:2"` format.

### Deploy the training app

Create `modal_hpo_app.py` with the training function:

```python
import modal

app = modal.App("hpo-training")

training_image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "torch",
    "transformers>=4.36.0",
    "trl>=0.12.0",
    "peft>=0.7.0",
    "accelerate>=0.24.0",
    "datasets",
    "huggingface_hub>=0.20.0",
)

@app.function(
    image=training_image,
    gpu="A10G",
    timeout=7200,
    secrets=[modal.Secret.from_name("huggingface-secret")],
)
def train_trial(
    trial_id: int,
    study_name: str,
    model: str,
    dataset: str,
    # ... other parameters
):
    # Training logic here
    # See scripts/modal_runner.py for full template
    ...
```

Deploy:
```bash
modal deploy modal_hpo_app.py
```

### Example

```python
from scripts.hpo_orchestrator import HPOStudy
from scripts.modal_runner import ModalRunner

runner = ModalRunner(
    app_name="hpo-training",
    function_name="train_trial",
    gpu="A10G",
)

study = HPOStudy(
    name="my-study",
    model="Qwen/Qwen2.5-0.5B",
    dataset="trl-lib/Capybara",
    runner=runner,
    n_trials=10,
)

study.optimise()
```

---

## RunPod

Budget-friendly serverless GPUs with flexible configuration.

### Setup

1. Create a RunPod account at [runpod.io](https://runpod.io)

2. Get your API key from Settings → API Keys

3. Set environment variable:
   ```bash
   export RUNPOD_API_KEY="your-api-key"
   ```

4. Create a serverless endpoint:
   - Go to Serverless → Endpoints → New Endpoint
   - Choose a template or create custom handler
   - Note the Endpoint ID

5. Deploy the training handler:
   - Create a Docker image with the handler from `scripts/runpod_runner.py`
   - Or use a template and customise

### Configuration

```python
from scripts.runpod_runner import RunPodRunner

runner = RunPodRunner(
    endpoint_id="your-endpoint-id",  # Required
    gpu_type="a100",                  # GPU type
    timeout_seconds=7200,             # 2 hours
    api_key=None,                     # Uses RUNPOD_API_KEY env var
    results_repo="username/my-hpo-results",
)
```

### GPU options

| GPU | VRAM | Cost/hr | Best for |
|-----|------|---------|----------|
| `a4000` | 16GB | ~$0.20 | Budget training |
| `a5000` | 24GB | ~$0.30 | Small models |
| `a6000` | 48GB | ~$0.50 | Medium models |
| `a40` | 48GB | ~$0.50 | General training |
| `l40` | 48GB | ~$0.70 | Efficient training |
| `a100` | 40GB | ~$1.20 | Large models |
| `a100-80gb` | 80GB | ~$1.70 | Very large models |
| `h100` | 80GB | ~$2.50 | Maximum performance |

### Deploy the training handler

Create a Docker image with the handler:

```dockerfile
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

RUN pip install \
    runpod \
    transformers>=4.36.0 \
    trl>=0.12.0 \
    peft>=0.7.0 \
    accelerate>=0.24.0 \
    datasets \
    huggingface_hub>=0.20.0

COPY handler.py /handler.py

CMD ["python", "/handler.py"]
```

The handler code is available as `RUNPOD_HANDLER_TEMPLATE` in `scripts/runpod_runner.py`.

### Example

```python
from scripts.hpo_orchestrator import HPOStudy
from scripts.runpod_runner import RunPodRunner

runner = RunPodRunner(
    endpoint_id="abc123xyz",
    gpu_type="a100",
    timeout_seconds=7200,
)

study = HPOStudy(
    name="my-study",
    model="Qwen/Qwen2.5-0.5B",
    dataset="trl-lib/Capybara",
    runner=runner,
    n_trials=10,
)

study.optimise()
```

---

## Implementing custom backends

All backends must implement the `TrialRunner` protocol:

```python
from scripts.backend_interface import (
    TrialRunner,
    TrialConfig,
    TrialResult,
    JobStatus,
)

class MyCustomRunner:
    """Custom backend runner."""

    def __init__(self, **config):
        self.config = config

    def submit(self, trial_config: TrialConfig) -> str:
        """
        Submit a trial job.

        Args:
            trial_config: Trial configuration with hyperparameters

        Returns:
            Unique job ID string
        """
        # Generate training script or payload
        # Submit to your backend
        # Return job ID
        ...

    def status(self, job_id: str) -> JobStatus:
        """
        Check job status.

        Returns one of:
        - JobStatus.PENDING
        - JobStatus.RUNNING
        - JobStatus.COMPLETED
        - JobStatus.FAILED
        - JobStatus.CANCELLED
        - JobStatus.PRUNED
        """
        ...

    def results(self, job_id: str) -> TrialResult:
        """
        Get results from a completed job.

        Must return TrialResult with:
        - objective_value: The metric to optimise
        - hyperparameters: Used parameters
        - metrics: Additional metrics
        - cost_usd: Cost of this trial (optional)
        """
        ...

    def cancel(self, job_id: str) -> None:
        """Cancel a running job."""
        ...

    def logs(self, job_id: str) -> str:
        """Get job logs."""
        ...

    def intermediate_values(self, job_id: str) -> dict[int, float]:
        """
        Get intermediate values for pruning.

        Returns dict mapping step -> objective_value.
        Called periodically during training.
        """
        ...
```

### Trial script requirements

For pruning to work, trial scripts must:

1. Report intermediate values during training (e.g., via `on_evaluate` callback)
2. Upload intermediate values to a shared location (Hub dataset, S3, etc.)
3. Return final objective value in results

### Cost tracking

Backends should track costs in `TrialResult.cost_usd`:

```python
def results(self, job_id: str) -> TrialResult:
    duration_hours = self._get_duration(job_id) / 3600
    hourly_rate = self._get_hourly_rate()
    cost = duration_hours * hourly_rate

    return TrialResult(
        ...
        cost_usd=round(cost, 2),
    )
```

---

## Backend selection guide

| Scenario | Recommended backend |
|----------|---------------------|
| HF ecosystem, Hub integration | HuggingFace Jobs |
| Fast iteration, Python-native | Modal |
| Budget-conscious | RunPod |
| Custom infrastructure | Custom runner |
| Multi-cloud redundancy | Mix of backends |

### Switching backends

The `HPOStudy` accepts any `TrialRunner` implementation:

```python
# Start with HF Jobs
runner = HFJobsRunner(flavour="a10g-large")

# Switch to Modal for faster iteration
runner = ModalRunner(gpu="A10G")

# Or RunPod for budget runs
runner = RunPodRunner(endpoint_id="...", gpu_type="a100")

# Use with same study configuration
study = HPOStudy(
    name="my-study",
    runner=runner,  # Any backend works
    ...
)
```

---

## Troubleshooting

### HuggingFace Jobs

**Job fails immediately:**
- Check HF_TOKEN has write permissions
- Verify Pro/Team/Enterprise account
- Check timeout is sufficient

**Cannot fetch intermediate values:**
- Set `results_repo` parameter
- Ensure repo exists and is writable

### Modal

**Function not found:**
- Run `modal deploy modal_hpo_app.py`
- Check app and function names match

**Authentication error:**
- Run `modal token new`
- Check `~/.modal.toml` exists

**GPU not available:**
- Try different GPU type
- Check Modal status page

### RunPod

**Endpoint not responding:**
- Verify endpoint ID is correct
- Check endpoint is active (not paused)
- Verify API key is valid

**Jobs timing out:**
- Increase `timeout_seconds`
- Check endpoint has sufficient workers

**Missing results:**
- Ensure handler returns proper output format
- Check logs for errors

---

## Cost comparison example

Running 20 trials on A10G-equivalent GPU (~2 hours each):

| Backend | Hourly rate | Total cost |
|---------|-------------|------------|
| HuggingFace Jobs | ~$5.00 | ~$200 |
| Modal | ~$1.10 | ~$44 |
| RunPod | ~$0.50 | ~$20 |

*Note: Prices are approximate and may vary. Check provider pricing pages for current rates.*
