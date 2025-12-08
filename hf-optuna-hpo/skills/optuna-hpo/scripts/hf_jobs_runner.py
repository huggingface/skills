#!/usr/bin/env python3
# /// script
# dependencies = ["huggingface_hub>=0.34.0"]
# ///

"""
HuggingFace Jobs backend runner.

Submits training trials to HuggingFace Jobs infrastructure and monitors
their progress for Optuna integration.
"""

import json
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from huggingface_hub import (
    HfApi,
    run_uv_job,
    inspect_job,
    fetch_job_logs,
    cancel_job,
    hf_hub_download,
)
from huggingface_hub.utils import HfHubHTTPError

from backend_interface import (
    HARDWARE_COSTS,
    JobStatus,
    RunnerConfig,
    TrialConfig,
    TrialResult,
    TrialRunner,
)


# Map HF Jobs stages to our JobStatus
HF_STAGE_TO_STATUS = {
    "RUNNING": JobStatus.RUNNING,
    "COMPLETED": JobStatus.COMPLETED,
    "ERROR": JobStatus.FAILED,
    "CANCELED": JobStatus.CANCELLED,
    "DELETED": JobStatus.CANCELLED,
}


@dataclass
class HFJobsRunner:
    """
    Backend runner for HuggingFace Jobs.

    Submits trials as UV scripts to HF Jobs infrastructure and monitors
    their execution for the HPO orchestrator.
    """

    flavour: str = "a10g-large"
    timeout: str = "2h"
    secrets: dict = field(default_factory=lambda: {"HF_TOKEN": "$HF_TOKEN"})
    env: dict = field(default_factory=dict)

    # Output repository for trial results (used to fetch intermediate values)
    results_repo: str | None = None

    # Internal state
    _jobs: dict = field(default_factory=dict, repr=False)
    _api: HfApi = field(default_factory=HfApi, repr=False)

    def __post_init__(self):
        """Validate configuration."""
        if self.flavour not in HARDWARE_COSTS:
            available = ", ".join(sorted(HARDWARE_COSTS.keys()))
            raise ValueError(
                f"Unknown flavour '{self.flavour}'. Available: {available}"
            )

    def _generate_trial_script(self, config: TrialConfig) -> str:
        """Generate the UV script for a trial."""
        hp = config.hyperparameters

        # Extract hyperparameters with defaults
        learning_rate = hp.get("learning_rate", 2e-5)
        batch_size = hp.get("per_device_train_batch_size", 4)
        weight_decay = hp.get("weight_decay", 0.01)
        num_epochs = hp.get("num_train_epochs", config.num_train_epochs)
        lora_r = hp.get("lora_r", 16)
        lora_alpha = hp.get("lora_alpha", 32)
        lora_dropout = hp.get("lora_dropout", 0.05)
        lr_scheduler = hp.get("lr_scheduler_type", "cosine")
        warmup_ratio = hp.get("warmup_ratio", 0.1)
        grad_accum = hp.get("gradient_accumulation_steps", 4)

        output_dir = config.output_dir or f"{config.study_name}-trial-{config.trial_id}"
        hub_model_id = config.hub_model_id or output_dir

        script = f'''# /// script
# dependencies = [
#     "trl>=0.12.0",
#     "peft>=0.7.0",
#     "transformers>=4.36.0",
#     "accelerate>=0.24.0",
#     "datasets",
#     "trackio",
#     "huggingface_hub>=0.20.0",
# ]
# ///

"""
HPO Trial {config.trial_id} for study: {config.study_name}

Auto-generated training script for hyperparameter optimisation.
"""

import json
import os
from pathlib import Path

import trackio
from datasets import load_dataset
from huggingface_hub import HfApi
from peft import LoraConfig
from trl import SFTTrainer, SFTConfig
from transformers import TrainerCallback


class OptunaPruningCallback(TrainerCallback):
    """Report intermediate values for Optuna pruning."""

    def __init__(self, trial_id: int, study_name: str, results_repo: str | None = None):
        self.trial_id = trial_id
        self.study_name = study_name
        self.results_repo = results_repo
        self.intermediate_values = {{}}
        self.api = HfApi() if results_repo else None

    def on_evaluate(self, args, state, control, metrics=None, **kwargs):
        if metrics and "eval_loss" in metrics:
            step = state.global_step
            value = metrics["eval_loss"]
            self.intermediate_values[step] = value

            # Write intermediate values to file
            results_path = Path(args.output_dir) / "optuna_intermediate.json"
            results_path.write_text(json.dumps(self.intermediate_values))

            # Also upload to Hub if configured (for remote monitoring)
            if self.results_repo and self.api:
                try:
                    self.api.upload_file(
                        path_or_fileobj=str(results_path),
                        path_in_repo=f"{{self.study_name}}/trial-{{self.trial_id}}/optuna_intermediate.json",
                        repo_id=self.results_repo,
                        repo_type="dataset",
                        commit_message=f"Update intermediate values for trial {{self.trial_id}} step {{step}}",
                    )
                except Exception as e:
                    print(f"Warning: Could not upload intermediate values: {{e}}")


class OptunaResultsCallback(TrainerCallback):
    """Save final results for Optuna."""

    def __init__(self, trial_id: int, study_name: str, hyperparameters: dict, results_repo: str | None = None):
        self.trial_id = trial_id
        self.study_name = study_name
        self.hyperparameters = hyperparameters
        self.results_repo = results_repo
        self.api = HfApi() if results_repo else None

    def on_train_end(self, args, state, control, **kwargs):
        # Get best metric
        if state.best_metric is not None:
            objective = state.best_metric
        else:
            objective = state.log_history[-1].get("eval_loss") if state.log_history else None

        results = {{
            "trial_id": self.trial_id,
            "study_name": self.study_name,
            "objective_value": objective,
            "hyperparameters": self.hyperparameters,
            "best_step": state.best_model_checkpoint,
            "total_steps": state.global_step,
            "status": "completed",
        }}

        results_path = Path(args.output_dir) / "optuna_results.json"
        results_path.write_text(json.dumps(results, indent=2))
        print(f"Optuna results saved to {{results_path}}")

        # Upload to Hub if configured
        if self.results_repo and self.api:
            try:
                self.api.upload_file(
                    path_or_fileobj=str(results_path),
                    path_in_repo=f"{{self.study_name}}/trial-{{self.trial_id}}/optuna_results.json",
                    repo_id=self.results_repo,
                    repo_type="dataset",
                    commit_message=f"Final results for trial {{self.trial_id}}",
                )
                print(f"Results uploaded to {{self.results_repo}}")
            except Exception as e:
                print(f"Warning: Could not upload results: {{e}}")


# Configuration
TRIAL_ID = {config.trial_id}
STUDY_NAME = "{config.study_name}"
HYPERPARAMETERS = {json.dumps(hp)}
RESULTS_REPO = {json.dumps(self.results_repo)}

print(f"Starting trial {{TRIAL_ID}} for study {{STUDY_NAME}}")
print(f"Hyperparameters: {{HYPERPARAMETERS}}")

# Load dataset
print("Loading dataset...")
dataset = load_dataset("{config.dataset}", split="train")
print(f"Dataset loaded: {{len(dataset)}} examples")

# Create train/eval split
dataset_split = dataset.train_test_split(test_size=0.1, seed=42)
train_dataset = dataset_split["train"]
eval_dataset = dataset_split["test"]
print(f"Train: {{len(train_dataset)}}, Eval: {{len(eval_dataset)}}")

# Training configuration
config = SFTConfig(
    output_dir="{output_dir}",
    push_to_hub={str(config.push_to_hub)},
    hub_model_id="{hub_model_id}",

    # Hyperparameters from Optuna
    learning_rate={learning_rate},
    per_device_train_batch_size={batch_size},
    weight_decay={weight_decay},
    num_train_epochs={num_epochs},
    lr_scheduler_type="{lr_scheduler}",
    warmup_ratio={warmup_ratio},
    gradient_accumulation_steps={grad_accum},

    # Evaluation for pruning
    eval_strategy="steps",
    eval_steps={config.eval_steps},
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,

    # Logging
    logging_steps=10,
    save_strategy="steps",
    save_steps={config.eval_steps},
    save_total_limit=2,

    # Monitoring
    report_to="trackio",
    run_name="{config.study_name}-trial-{config.trial_id}",
)

# LoRA configuration
peft_config = LoraConfig(
    r={lora_r},
    lora_alpha={lora_alpha},
    lora_dropout={lora_dropout},
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=["q_proj", "v_proj"],
)

# Callbacks for Optuna
pruning_callback = OptunaPruningCallback(TRIAL_ID, STUDY_NAME, RESULTS_REPO)
results_callback = OptunaResultsCallback(TRIAL_ID, STUDY_NAME, HYPERPARAMETERS, RESULTS_REPO)

# Initialise and train
print("Initialising trainer...")
trainer = SFTTrainer(
    model="{config.model}",
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    args=config,
    peft_config=peft_config,
    callbacks=[pruning_callback, results_callback],
)

print("Starting training...")
trainer.train()

print("Pushing to Hub...")
trainer.push_to_hub()

print(f"Trial {{TRIAL_ID}} complete!")
'''
        return script

    def submit(self, trial_config: TrialConfig) -> str:
        """Submit a trial to HuggingFace Jobs."""
        script = self._generate_trial_script(trial_config)

        # Create a temporary file for the script
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix=f"hpo_trial_{trial_config.trial_id}_",
            delete=False,
        ) as f:
            f.write(script)
            script_path = f.name

        try:
            # Submit using huggingface_hub's run_uv_job
            job_info = run_uv_job(
                script_path,
                flavor=self.flavour,
                timeout=self.timeout,
                secrets=self.secrets,
                env=self.env,
            )

            job_id = job_info.id

            # Store job info
            self._jobs[job_id] = {
                "trial_config": trial_config,
                "script": script,
                "script_path": script_path,
                "job_info": job_info,
                "submitted_at": time.time(),
                "result": None,
            }

            print(f"Submitted trial {trial_config.trial_id} as job {job_id}")
            print(f"Monitor at: {job_info.url}")

            return job_id

        except Exception as e:
            # Clean up temp file on error
            Path(script_path).unlink(missing_ok=True)
            raise RuntimeError(f"Failed to submit job: {e}") from e

    def status(self, job_id: str) -> JobStatus:
        """Check job status."""
        try:
            job_info = inspect_job(job_id=job_id)
            hf_stage = job_info.status.stage
            return HF_STAGE_TO_STATUS.get(hf_stage, JobStatus.PENDING)
        except HfHubHTTPError as e:
            if "404" in str(e):
                raise ValueError(f"Unknown job: {job_id}") from e
            raise

    def results(self, job_id: str) -> TrialResult:
        """Get trial results."""
        # Check if we have cached results
        if job_id in self._jobs and self._jobs[job_id].get("result"):
            return self._jobs[job_id]["result"]

        # Get job info
        job_info = inspect_job(job_id=job_id)
        hf_stage = job_info.status.stage

        if hf_stage not in ("COMPLETED", "ERROR", "CANCELED", "DELETED"):
            raise ValueError(f"Job {job_id} not yet finished (status: {hf_stage})")

        status = HF_STAGE_TO_STATUS.get(hf_stage, JobStatus.FAILED)

        # Get trial config from our cache or use defaults
        trial_config = None
        submitted_at = None
        if job_id in self._jobs:
            trial_config = self._jobs[job_id].get("trial_config")
            submitted_at = self._jobs[job_id].get("submitted_at")

        # Calculate duration and cost
        duration = time.time() - submitted_at if submitted_at else 0
        hourly_rate = HARDWARE_COSTS.get(self.flavour, 5.0)
        cost = hourly_rate * (duration / 3600)

        # Try to fetch objective value from Hub results
        objective_value = None
        metrics = {}

        if self.results_repo and trial_config:
            try:
                # Download results file from Hub
                results_path = hf_hub_download(
                    repo_id=self.results_repo,
                    filename=f"{trial_config.study_name}/trial-{trial_config.trial_id}/optuna_results.json",
                    repo_type="dataset",
                )
                with open(results_path) as f:
                    results_data = json.load(f)
                    objective_value = results_data.get("objective_value")
                    metrics = results_data
            except Exception:
                # Results not available on Hub, try parsing logs
                pass

        # If no Hub results, try to parse from logs
        if objective_value is None and status == JobStatus.COMPLETED:
            try:
                logs = list(fetch_job_logs(job_id=job_id))
                # Look for objective value in logs
                for line in reversed(logs):
                    if "eval_loss" in line.lower():
                        # Try to extract numeric value
                        import re
                        match = re.search(r"eval_loss['\"]?\s*[:=]\s*([0-9.]+)", line)
                        if match:
                            objective_value = float(match.group(1))
                            break
            except Exception:
                pass

        result = TrialResult(
            trial_id=trial_config.trial_id if trial_config else 0,
            job_id=job_id,
            status=status,
            objective_value=objective_value,
            hyperparameters=trial_config.hyperparameters if trial_config else {},
            metrics=metrics,
            intermediate_values={},
            duration_seconds=duration,
            cost_usd=round(cost, 2),
        )

        # Cache result
        if job_id in self._jobs:
            self._jobs[job_id]["result"] = result

        return result

    def cancel(self, job_id: str) -> None:
        """Cancel a running job."""
        try:
            cancel_job(job_id=job_id)
            print(f"Cancelled job {job_id}")

            # Update local state
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = JobStatus.CANCELLED

        except HfHubHTTPError as e:
            if "404" in str(e):
                raise ValueError(f"Unknown job: {job_id}") from e
            raise

    def logs(self, job_id: str) -> str:
        """Get job logs."""
        try:
            log_lines = list(fetch_job_logs(job_id=job_id))
            return "\n".join(log_lines)
        except HfHubHTTPError as e:
            if "404" in str(e):
                raise ValueError(f"Unknown job: {job_id}") from e
            raise

    def intermediate_values(self, job_id: str) -> dict[int, float]:
        """Get intermediate values for pruning."""
        if job_id not in self._jobs:
            return {}

        trial_config = self._jobs[job_id].get("trial_config")
        if not trial_config or not self.results_repo:
            return {}

        try:
            # Download intermediate values from Hub
            intermediate_path = hf_hub_download(
                repo_id=self.results_repo,
                filename=f"{trial_config.study_name}/trial-{trial_config.trial_id}/optuna_intermediate.json",
                repo_type="dataset",
            )
            with open(intermediate_path) as f:
                data = json.load(f)
                # Convert string keys to int
                return {int(k): float(v) for k, v in data.items()}
        except Exception:
            # File not yet available
            return {}

    def get_submission_command(self, trial_config: TrialConfig) -> str:
        """
        Get the hf_jobs command for manual submission.

        Useful for debugging or when direct API calls are preferred.
        """
        script = self._generate_trial_script(trial_config)

        return f'''from huggingface_hub import run_uv_job
import tempfile

script = """{script}"""

# Write to temporary file and submit
with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
    f.write(script)
    script_path = f.name

job = run_uv_job(
    script_path,
    flavor="{self.flavour}",
    timeout="{self.timeout}",
    secrets={json.dumps(self.secrets)},
)

print(f"Job ID: {{job.id}}")
print(f"Monitor: {{job.url}}")
'''
