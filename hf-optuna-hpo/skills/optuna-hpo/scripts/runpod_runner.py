#!/usr/bin/env python3
# /// script
# dependencies = ["runpod>=1.6.0", "huggingface_hub>=0.20.0"]
# ///

"""
RunPod serverless backend runner.

Submits training trials to RunPod serverless GPU endpoints and monitors
their progress for Optuna integration.
"""

import json
import os
import time
from dataclasses import dataclass, field

import runpod

from backend_interface import (
    HARDWARE_COSTS,
    JobStatus,
    TrialConfig,
    TrialResult,
    TrialRunner,
)


# RunPod GPU pricing (approximate USD/hr, as of 2025)
RUNPOD_COSTS = {
    "NVIDIA RTX A4000": 0.20,
    "NVIDIA RTX A4500": 0.25,
    "NVIDIA RTX A5000": 0.30,
    "NVIDIA RTX A6000": 0.50,
    "NVIDIA A40": 0.50,
    "NVIDIA L40": 0.70,
    "NVIDIA A100 PCIe": 1.20,
    "NVIDIA A100 SXM": 1.50,
    "NVIDIA A100 80GB": 1.70,
    "NVIDIA H100 PCIe": 2.50,
    "NVIDIA H100 SXM": 3.00,
}

# Map friendly names to RunPod GPU types
GPU_TYPE_MAP = {
    "a4000": "NVIDIA RTX A4000",
    "a5000": "NVIDIA RTX A5000",
    "a6000": "NVIDIA RTX A6000",
    "a40": "NVIDIA A40",
    "l40": "NVIDIA L40",
    "a100": "NVIDIA A100 PCIe",
    "a100-80gb": "NVIDIA A100 80GB",
    "h100": "NVIDIA H100 PCIe",
    "h100-sxm": "NVIDIA H100 SXM",
}

# Map RunPod status to our JobStatus
RUNPOD_STATUS_MAP = {
    "IN_QUEUE": JobStatus.PENDING,
    "IN_PROGRESS": JobStatus.RUNNING,
    "COMPLETED": JobStatus.COMPLETED,
    "FAILED": JobStatus.FAILED,
    "TIMED_OUT": JobStatus.FAILED,
    "CANCELLED": JobStatus.CANCELLED,
}


@dataclass
class RunPodRunner:
    """
    Backend runner for RunPod serverless endpoints.

    Requires a pre-deployed RunPod serverless endpoint configured with
    a training handler. See references/backends.md for setup instructions.
    """

    # Required: Your RunPod endpoint ID
    endpoint_id: str

    # GPU type (friendly name or full RunPod name)
    gpu_type: str = "a100"

    # Execution timeout in seconds (default 2 hours)
    timeout_seconds: int = 7200

    # API key (defaults to RUNPOD_API_KEY env var)
    api_key: str | None = None

    # Results repository for intermediate values
    results_repo: str | None = None

    # Internal state
    _jobs: dict = field(default_factory=dict, repr=False)
    _endpoint: runpod.Endpoint | None = field(default=None, repr=False)

    def __post_init__(self):
        """Initialise RunPod client."""
        # Set API key
        if self.api_key:
            runpod.api_key = self.api_key
        elif os.environ.get("RUNPOD_API_KEY"):
            runpod.api_key = os.environ["RUNPOD_API_KEY"]
        else:
            raise ValueError(
                "RunPod API key required. Set RUNPOD_API_KEY env var or pass api_key parameter."
            )

        # Resolve GPU type
        if self.gpu_type.lower() in GPU_TYPE_MAP:
            self._gpu_type_full = GPU_TYPE_MAP[self.gpu_type.lower()]
        else:
            self._gpu_type_full = self.gpu_type

        # Create endpoint client
        self._endpoint = runpod.Endpoint(self.endpoint_id)

    def _get_hourly_cost(self) -> float:
        """Get hourly cost for configured GPU type."""
        return RUNPOD_COSTS.get(self._gpu_type_full, 1.0)

    def _generate_trial_input(self, config: TrialConfig) -> dict:
        """Generate the input payload for a RunPod job."""
        hp = config.hyperparameters

        return {
            "trial_id": config.trial_id,
            "study_name": config.study_name,
            "model": config.model,
            "dataset": config.dataset,
            "method": config.method,
            "hyperparameters": hp,
            "output_dir": config.output_dir or f"{config.study_name}-trial-{config.trial_id}",
            "hub_model_id": config.hub_model_id,
            "push_to_hub": config.push_to_hub,
            "eval_steps": config.eval_steps,
            "num_train_epochs": config.num_train_epochs,
            "results_repo": self.results_repo,
            # Training hyperparameters with defaults
            "learning_rate": hp.get("learning_rate", 2e-5),
            "per_device_train_batch_size": hp.get("per_device_train_batch_size", 4),
            "weight_decay": hp.get("weight_decay", 0.01),
            "lora_r": hp.get("lora_r", 16),
            "lora_alpha": hp.get("lora_alpha", 32),
            "lora_dropout": hp.get("lora_dropout", 0.05),
            "lr_scheduler_type": hp.get("lr_scheduler_type", "cosine"),
            "warmup_ratio": hp.get("warmup_ratio", 0.1),
            "gradient_accumulation_steps": hp.get("gradient_accumulation_steps", 4),
        }

    def submit(self, trial_config: TrialConfig) -> str:
        """Submit a trial to RunPod serverless endpoint."""
        input_payload = self._generate_trial_input(trial_config)

        # Submit async job
        run_request = self._endpoint.run(
            {
                "input": input_payload,
                "executionTimeout": self.timeout_seconds * 1000,  # Convert to ms
            }
        )

        job_id = run_request.job_id

        # Store job info
        self._jobs[job_id] = {
            "trial_config": trial_config,
            "run_request": run_request,
            "submitted_at": time.time(),
            "result": None,
        }

        print(f"Submitted trial {trial_config.trial_id} as RunPod job {job_id}")
        return job_id

    def status(self, job_id: str) -> JobStatus:
        """Check job status."""
        if job_id in self._jobs:
            run_request = self._jobs[job_id]["run_request"]
            runpod_status = run_request.status()
        else:
            # Try to check status directly via API
            import requests
            url = f"https://api.runpod.ai/v2/{self.endpoint_id}/status/{job_id}"
            headers = {"authorization": runpod.api_key}
            response = requests.get(url, headers=headers)
            if response.status_code == 404:
                raise ValueError(f"Unknown job: {job_id}")
            runpod_status = response.json().get("status", "FAILED")

        return RUNPOD_STATUS_MAP.get(runpod_status, JobStatus.PENDING)

    def results(self, job_id: str) -> TrialResult:
        """Get trial results."""
        # Check cached results
        if job_id in self._jobs and self._jobs[job_id].get("result"):
            return self._jobs[job_id]["result"]

        # Get job status and output
        if job_id in self._jobs:
            run_request = self._jobs[job_id]["run_request"]
            trial_config = self._jobs[job_id]["trial_config"]
            submitted_at = self._jobs[job_id]["submitted_at"]

            # Block until complete
            output = run_request.output()
            runpod_status = run_request.status()
        else:
            raise ValueError(f"Unknown job: {job_id}")

        status = RUNPOD_STATUS_MAP.get(runpod_status, JobStatus.FAILED)

        if status not in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            raise ValueError(f"Job {job_id} not yet finished (status: {runpod_status})")

        # Calculate duration and cost
        duration = time.time() - submitted_at
        hourly_rate = self._get_hourly_cost()
        cost = hourly_rate * (duration / 3600)

        # Extract objective value from output
        objective_value = None
        metrics = {}

        if output and isinstance(output, dict):
            objective_value = output.get("objective_value")
            metrics = output.get("metrics", {})

        result = TrialResult(
            trial_id=trial_config.trial_id,
            job_id=job_id,
            status=status,
            objective_value=objective_value,
            hyperparameters=trial_config.hyperparameters,
            metrics=metrics,
            intermediate_values=output.get("intermediate_values", {}) if output else {},
            duration_seconds=duration,
            cost_usd=round(cost, 2),
        )

        # Cache result
        self._jobs[job_id]["result"] = result
        return result

    def cancel(self, job_id: str) -> None:
        """Cancel a running job."""
        if job_id in self._jobs:
            run_request = self._jobs[job_id]["run_request"]
            run_request.cancel()
        else:
            # Cancel via API
            import requests
            url = f"https://api.runpod.ai/v2/{self.endpoint_id}/cancel/{job_id}"
            headers = {"authorization": runpod.api_key}
            requests.post(url, headers=headers)

        print(f"Cancelled RunPod job {job_id}")

    def logs(self, job_id: str) -> str:
        """Get job logs."""
        # RunPod doesn't provide streaming logs via API
        # Logs are available in the output after completion
        if job_id in self._jobs:
            run_request = self._jobs[job_id]["run_request"]
            status = run_request.status()
            if status in ("COMPLETED", "FAILED"):
                output = run_request.output()
                if output and isinstance(output, dict):
                    return output.get("logs", "[No logs available]")
        return "[Logs available after job completion]"

    def intermediate_values(self, job_id: str) -> dict[int, float]:
        """Get intermediate values for pruning."""
        # RunPod serverless doesn't support streaming intermediate values
        # Values are available in final output or via results_repo
        if self.results_repo and job_id in self._jobs:
            trial_config = self._jobs[job_id]["trial_config"]
            try:
                from huggingface_hub import hf_hub_download
                intermediate_path = hf_hub_download(
                    repo_id=self.results_repo,
                    filename=f"{trial_config.study_name}/trial-{trial_config.trial_id}/optuna_intermediate.json",
                    repo_type="dataset",
                )
                with open(intermediate_path) as f:
                    data = json.load(f)
                    return {int(k): float(v) for k, v in data.items()}
            except Exception:
                pass
        return {}


# Example handler code for RunPod serverless endpoint
RUNPOD_HANDLER_TEMPLATE = '''
"""
RunPod serverless handler for HPO trials.

Deploy this as a RunPod serverless endpoint to enable HPO trials.
"""

import json
import runpod
from pathlib import Path

from datasets import load_dataset
from huggingface_hub import HfApi
from peft import LoraConfig
from trl import SFTTrainer, SFTConfig
from transformers import TrainerCallback


class OptunaPruningCallback(TrainerCallback):
    """Report intermediate values for Optuna pruning."""

    def __init__(self, trial_id, study_name, results_repo=None):
        self.trial_id = trial_id
        self.study_name = study_name
        self.results_repo = results_repo
        self.intermediate_values = {}
        self.api = HfApi() if results_repo else None

    def on_evaluate(self, args, state, control, metrics=None, **kwargs):
        if metrics and "eval_loss" in metrics:
            step = state.global_step
            value = metrics["eval_loss"]
            self.intermediate_values[step] = value

            if self.results_repo and self.api:
                try:
                    results_path = Path(args.output_dir) / "optuna_intermediate.json"
                    results_path.write_text(json.dumps(self.intermediate_values))
                    self.api.upload_file(
                        path_or_fileobj=str(results_path),
                        path_in_repo=f"{self.study_name}/trial-{self.trial_id}/optuna_intermediate.json",
                        repo_id=self.results_repo,
                        repo_type="dataset",
                    )
                except Exception as e:
                    print(f"Warning: Could not upload intermediate values: {e}")


def handler(job):
    """Handle HPO trial job."""
    job_input = job["input"]

    trial_id = job_input["trial_id"]
    study_name = job_input["study_name"]
    model = job_input["model"]
    dataset_name = job_input["dataset"]
    results_repo = job_input.get("results_repo")

    print(f"Starting trial {trial_id} for study {study_name}")

    # Load dataset
    dataset = load_dataset(dataset_name, split="train")
    dataset_split = dataset.train_test_split(test_size=0.1, seed=42)

    # Training config
    config = SFTConfig(
        output_dir=job_input.get("output_dir", f"trial-{trial_id}"),
        push_to_hub=job_input.get("push_to_hub", True),
        hub_model_id=job_input.get("hub_model_id"),
        learning_rate=job_input["learning_rate"],
        per_device_train_batch_size=job_input["per_device_train_batch_size"],
        weight_decay=job_input["weight_decay"],
        num_train_epochs=job_input.get("num_train_epochs", 1),
        lr_scheduler_type=job_input["lr_scheduler_type"],
        warmup_ratio=job_input["warmup_ratio"],
        gradient_accumulation_steps=job_input["gradient_accumulation_steps"],
        eval_strategy="steps",
        eval_steps=job_input.get("eval_steps", 50),
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        logging_steps=10,
        save_strategy="steps",
        save_steps=job_input.get("eval_steps", 50),
        save_total_limit=2,
    )

    # LoRA config
    peft_config = LoraConfig(
        r=job_input["lora_r"],
        lora_alpha=job_input["lora_alpha"],
        lora_dropout=job_input["lora_dropout"],
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "v_proj"],
    )

    # Callback
    pruning_callback = OptunaPruningCallback(trial_id, study_name, results_repo)

    # Train
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset_split["train"],
        eval_dataset=dataset_split["test"],
        args=config,
        peft_config=peft_config,
        callbacks=[pruning_callback],
    )

    trainer.train()

    # Get final metric
    if trainer.state.best_metric is not None:
        objective = trainer.state.best_metric
    else:
        objective = trainer.state.log_history[-1].get("eval_loss")

    # Push to Hub
    if job_input.get("push_to_hub", True):
        trainer.push_to_hub()

    return {
        "trial_id": trial_id,
        "study_name": study_name,
        "objective_value": objective,
        "hyperparameters": job_input.get("hyperparameters", {}),
        "intermediate_values": pruning_callback.intermediate_values,
        "status": "completed",
    }


runpod.serverless.start({"handler": handler})
'''
