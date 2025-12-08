---
name: optuna-hpo
description: Hyperparameter optimisation for LLM fine-tuning using Optuna. Orchestrates distributed trials across cloud backends (Huggingface Jobs, Modal, etc.) with intelligent sampling, early stopping, and cost tracking. Use when users want to find optimal hyperparameters for training transformer models.
---

# Hyperparameter optimisation with Optuna

## Overview

This skill orchestrates hyperparameter optimisation (HPO) for transformer-based LLM fine-tuning using Optuna. It dispatches individual training trials to cloud backends (Huggingface Jobs for now), tracks results, and provides visualisation through a Gradio dashboard.

**Key capabilities:**
- **Distributed trials** - Run trials in parallel across cloud GPUs
- **Intelligent sampling** - TPE (Tree-structured Parzen Estimator) for efficient search
- **Early stopping** - MedianPruner to terminate unpromising trials early
- **Cost tracking** - Monitor spend per trial and total budget
- **Persistence** - Local SQLite or Hub sync for resume/sharing
- **Visualisation** - Gradio dashboard similar to Trackio

## When to use this skill

Use this skill when users want to:
- Find optimal hyperparameters for LLM fine-tuning
- Run systematic HPO sweeps on cloud infrastructure
- Compare training configurations efficiently
- Optimise learning rate, LoRA parameters, batch size, etc.
- Track and visualise optimisation progress

## Key directives

When assisting with HPO:

1. **ALWAYS clarify before launching** - Use `AskUserQuestion` to confirm model, dataset, training method, search space, and budget before dispatching any trials. GPU time costs money.

2. **Validate datasets first** - Use the dataset inspector from model-trainer to verify format compatibility before starting an HPO study.

3. **Estimate costs upfront** - Calculate approximate costs based on hardware, trial count, and expected duration. Get user approval.

4. **Use sensible defaults** - Template C (Core + LoRA + Scheduler) is the default search space. TPE + MedianPruner is the default sampler/pruner.

5. **Track everything** - Ensure all trials report metrics for pruning decisions and final analysis.

## Prerequisites checklist

Before starting any HPO study, verify:

### Account and authentication
- [ ] HuggingFace account with Pro/Team/Enterprise plan (for HF Jobs)
- [ ] Authenticated: check with `hf_whoami()`
- [ ] HF_TOKEN with write permissions for Hub sync

### Dataset requirements
- [ ] Dataset exists on Hub or is loadable via `datasets.load_dataset()`
- [ ] Format validated with dataset inspector
- [ ] Size appropriate for trial budget

### Study configuration
- [ ] Model selected and compatible with hardware
- [ ] Search space defined (or using default template)
- [ ] Trial count and parallelism set
- [ ] Budget approved by user

## User clarification flow

**CRITICAL: Always clarify before launching trials.**

When a user requests HPO, gather information using `AskUserQuestion`:

### Step 1: Core configuration

```
Question: "Which training method?"
Options:
- SFT (supervised fine-tuning)
- DPO (preference alignment) [v2]
- Other
```

```
Question: "Which search space scope?"
Options:
- Standard (learning_rate, batch_size, weight_decay)
- With LoRA params (+ lora_r, lora_alpha, lora_dropout)
- Comprehensive (+ scheduler, warmup) [recommended]
- Custom (I'll specify)
```

```
Question: "Trial budget?"
Options:
- Quick exploration (5 trials, ~$15)
- Moderate sweep (15 trials, ~$45)
- Thorough optimisation (30 trials, ~$90)
- Custom
```

### Step 2: Confirm configuration

After gathering inputs, display a summary for approval:

```
HPO study configuration
━━━━━━━━━━━━━━━━━━━━━━━━━
Model:      Qwen/Qwen2.5-0.5B
Dataset:    username/my-data
Method:     SFT
Backend:    HF Jobs (a10g-large)

Search space:
  - learning_rate: 1e-6 to 1e-4 (log)
  - batch_size: [4, 8, 16, 32]
  - lora_r: [8, 16, 32, 64]
  - weight_decay: 0.0 to 0.3
  - warmup_ratio: 0.0 to 0.2
  ...

Trials:     15 (3 parallel)
Est. cost:  $40-50
Est. time:  ~2 hours

Proceed? [Yes / Modify / Cancel]
```

### Step 3: Handle issues during execution

If trials consistently fail, pause and ask:
```
Question: "3 trials have failed. How to proceed?"
Options:
- Show error logs and debug
- Adjust configuration
- Cancel study
```

If approaching budget limit:
```
Question: "Budget 80% consumed ($40/$50). Continue?"
Options:
- Continue (may exceed budget)
- Stop after current trials
- Cancel remaining trials
```

## Quick start

### Minimal example

```python
# /// script
# dependencies = ["optuna>=3.0.0", "huggingface_hub"]
# ///

from scripts.hpo_orchestrator import HPOStudy
from scripts.hf_jobs_runner import HFJobsRunner

study = HPOStudy(
    name="qwen-sft-hpo",
    model="Qwen/Qwen2.5-0.5B",
    dataset="trl-lib/Capybara",
    method="sft",
    runner=HFJobsRunner(flavour="a10g-large"),
    n_trials=10,
)

best = study.optimise()
print(f"Best trial: {best.hyperparameters}")
print(f"Best objective: {best.objective_value}")
```

### With Huggingface Hub persistence and dashboard

```python
study = HPOStudy(
    name="qwen-sft-hpo",
    model="Qwen/Qwen2.5-0.5B",
    dataset="trl-lib/Capybara",
    method="sft",

    # Custom search space
    search_space={
        "learning_rate": ("float_log", 1e-6, 1e-4),
        "lora_r": ("categorical", [8, 16, 32]),
        "per_device_train_batch_size": ("categorical", [4, 8]),
    },

    # Execution
    runner=HFJobsRunner(flavour="a10g-large"),
    n_trials=20,
    n_parallel=3,

    # Persistence
    storage="hub://username/my-hpo-study",

    # Budget
    budget_usd=100,
)

best = study.optimise()

# Launch dashboard
study.launch_dashboard()
```

## Search space configuration

### Default templates

**Template A: Standard** (fast, minimal)
```python
SEARCH_SPACE_STANDARD = {
    "learning_rate": ("float_log", 1e-6, 1e-4),
    "per_device_train_batch_size": ("categorical", [4, 8, 16, 32]),
    "weight_decay": ("float", 0.0, 0.3),
    "num_train_epochs": ("categorical", [1, 2, 3]),
}
```

**Template B: With LoRA** (recommended for PEFT)
```python
SEARCH_SPACE_LORA = {
    **SEARCH_SPACE_STANDARD,
    "lora_r": ("categorical", [8, 16, 32, 64]),
    "lora_alpha": ("categorical", [16, 32, 64]),
    "lora_dropout": ("float", 0.0, 0.1),
}
```

**Template C: Comprehensive** (default)
```python
SEARCH_SPACE_COMPREHENSIVE = {
    **SEARCH_SPACE_LORA,
    "lr_scheduler_type": ("categorical", ["linear", "cosine", "cosine_with_restarts"]),
    "warmup_ratio": ("float", 0.0, 0.2),
    "gradient_accumulation_steps": ("categorical", [1, 2, 4, 8]),
}
```

### Custom search space

Define arbitrary hyperparameters:

```python
search_space = {
    # Float with log scale
    "learning_rate": ("float_log", 1e-6, 1e-4),

    # Float with linear scale
    "weight_decay": ("float", 0.0, 0.3),

    # Categorical choices
    "lora_r": ("categorical", [8, 16, 32]),

    # Integer range
    "num_train_epochs": ("int", 1, 5),
}
```

See `references/search_spaces.md` for complete documentation.

## Backend configuration

### HuggingFace Jobs (default)

```python
from scripts.hf_jobs_runner import HFJobsRunner

runner = HFJobsRunner(
    flavour="a10g-large",      # GPU type
    timeout="2h",               # Per-trial timeout
    secrets={"HF_TOKEN": "$HF_TOKEN"},
)
```

**Available flavours:** `t4-small`, `t4-medium`, `l4x1`, `a10g-small`, `a10g-large`, `a100-large`

### Custom backends

Implement the `TrialRunner` protocol:

```python
from scripts.backend_interface import TrialRunner, JobStatus, TrialResult

class MyCustomRunner(TrialRunner):
    def submit(self, script: str, config: dict) -> str:
        # Submit job, return job_id
        ...

    def status(self, job_id: str) -> JobStatus:
        # Return current status
        ...

    def results(self, job_id: str) -> TrialResult:
        # Return trial results
        ...

    def cancel(self, job_id: str) -> None:
        # Cancel running job
        ...
```

See `references/backends.md` for adding Modal, RunPod, etc.

## Persistence and visualisation

### Local storage (default)

```python
study = HPOStudy(
    name="my-study",
    storage="local",  # SQLite in ./optuna_studies/
    ...
)
```

### Hub sync

```python
# Store directly on Hub
study = HPOStudy(
    name="my-study",
    storage="hub://username/my-hpo-study",
    ...
)

# Or sync after completion
study = HPOStudy(name="my-study", storage="local", ...)
study.optimise()
study.sync_to_hub("username/my-hpo-study")
```

### Gradio dashboard

Launch the visualisation dashboard:

```python
study.launch_dashboard()
# Opens browser at http://localhost:7860
```

Or from command line:

```bash
python scripts/gradio_dashboard.py --study ./optuna_studies/my-study.db
python scripts/gradio_dashboard.py --hub username/my-hpo-study
```

Dashboard features:
- Optimisation history plot
- Parameter importance analysis
- Trial table with filtering
- Best trial details
- Cost summary

## Sampler and pruner configuration

### Default: TPE + MedianPruner

```python
study = HPOStudy(
    sampler="tpe",           # Tree-structured Parzen Estimator
    pruner="median",         # Prune below-median trials
    ...
)
```

### Advanced configuration

```python
import optuna

study = HPOStudy(
    sampler=optuna.samplers.TPESampler(
        n_startup_trials=5,
        multivariate=True,
    ),
    pruner=optuna.pruners.HyperbandPruner(
        min_resource=1,
        max_resource=10,
        reduction_factor=3,
    ),
    ...
)
```

See `references/pruning_strategies.md` for guidance on when to use each strategy.

## Parallelism and budget

### Fixed parallelism (default)

```python
study = HPOStudy(
    n_trials=20,
    n_parallel=3,  # Run up to 3 trials simultaneously
    ...
)
```

### Budget-aware mode

```python
study = HPOStudy(
    n_trials=50,
    n_parallel=5,
    budget_usd=100,        # Hard budget limit
    warn_at_percent=80,    # Warn when 80% consumed
    ...
)
```

When budget is nearly exhausted, the skill will pause and ask the user how to proceed.

## Training method support

### Currently supported
- **SFT** (Supervised Fine-Tuning) - Full support

### Roadmap
- **DPO** (Direct Preference Optimisation) - v2
- **GRPO** (Group Relative Policy Optimisation) - v3
- **Reward Modelling** - v3

The architecture is extensible. See `references/adding_methods.md` to add new training methods.

## Example scripts

- `scripts/hpo_orchestrator.py` - Main orchestrator class
- `scripts/hf_jobs_runner.py` - HuggingFace Jobs backend
- `scripts/backend_interface.py` - Backend protocol definition
- `scripts/trial_script_template.py` - Trial execution template
- `scripts/gradio_dashboard.py` - Visualisation app
- `scripts/hub_sync.py` - Hub persistence utilities
- `scripts/search_spaces.py` - Search space templates

## Troubleshooting

### Trials failing consistently

1. Check error logs: `study.get_trial_logs(trial_id)`
2. Verify dataset format with inspector
3. Check hardware is sufficient for model size
4. Ensure HF_TOKEN has correct permissions

### Pruning too aggressively

- Increase `n_startup_trials` (default 10) to gather more data before pruning
- Switch to `SuccessiveHalvingPruner` for more conservative pruning
- Disable pruning: `pruner=None`

### Study not resuming

- Ensure same `name` is used
- For Hub storage, verify repo exists and is accessible
- Check SQLite file exists for local storage

### Budget exceeded

- Trials in progress when budget is hit will complete
- Set `warn_at_percent` lower for earlier warnings
- Use `budget_usd` as a hard limit

See `references/troubleshooting.md` for complete troubleshooting guide.

## References

### In this skill
- `references/search_spaces.md` - Search space templates and customisation
- `references/backends.md` - Backend configuration and custom runners
- `references/pruning_strategies.md` - Optuna pruner selection guide
- `references/troubleshooting.md` - Common issues and solutions

### External links
- [Optuna documentation](https://optuna.readthedocs.io/)
- [TRL documentation](https://huggingface.co/docs/trl)
- [HF Jobs guide](https://huggingface.co/docs/huggingface_hub/guides/jobs)
- [model-trainer skill](../../../hf-llm-trainer/skills/model-trainer/SKILL.md)

## Key takeaways

1. **Always clarify before launching** - Use `AskUserQuestion` to confirm configuration
2. **Validate datasets first** - Prevent wasted GPU spend on format errors
3. **Estimate costs upfront** - Get user approval before expensive sweeps
4. **Use MedianPruner** - Saves 30-50% on trial costs via early stopping
5. **Sync to Hub** - Enable resume and sharing across sessions
6. **Launch dashboard** - Visualise progress with the Gradio app
