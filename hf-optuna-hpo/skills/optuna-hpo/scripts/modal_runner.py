#!/usr/bin/env python3
# /// script
# dependencies = ["modal>=0.64.0", "huggingface_hub>=0.20.0"]
# ///

"""
Modal backend runner.

Submits training trials to Modal serverless GPU infrastructure and monitors
their progress for Optuna integration.
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import modal

from backend_interface import (
    JobStatus,
    TrialConfig,
    TrialResult,
    TrialRunner,
)


# Modal GPU pricing (approximate USD/hr, as of 2025)
MODAL_COSTS = {
    "T4": 0.59,
    "L4": 0.80,
    "A10G": 1.10,
    "A100": 3.00,
    "A100-80GB": 4.00,
    "H100": 4.50,
}

# Map friendly names to Modal GPU specs
GPU_MAP = {
    "t4": "T4",
    "l4": "L4",
    "a10g": "A10G",
    "a100": "A100",
    "a100-40gb": "A100",
    "a100-80gb": "A100-80GB",
    "h100": "H100",
}

# Map Modal function call states to our JobStatus
MODAL_STATUS_MAP = {
    "pending": JobStatus.PENDING,
    "running": JobStatus.RUNNING,
    "success": JobStatus.COMPLETED,
    "failure": JobStatus.FAILED,
    "terminated": JobStatus.CANCELLED,
}


@dataclass
class ModalRunner:
    """
    Backend runner for Modal serverless infrastructure.

    Requires a pre-deployed Modal app with a training function.
    See references/backends.md for setup instructions.
    """

    # Modal app and function names
    app_name: str = "hpo-training"
    function_name: str = "train_trial"

    # GPU configuration
    gpu: str = "A10G"
    gpu_count: int = 1

    # Timeout in seconds (default 2 hours)
    timeout_seconds: int = 7200

    # Results repository for intermediate values
    results_repo: str | None = None

    # Internal state
    _jobs: dict = field(default_factory=dict, repr=False)
    _function: modal.Function | None = field(default=None, repr=False)

    def __post_init__(self):
        """Initialise Modal client."""
        # Resolve GPU type
        if self.gpu.lower() in GPU_MAP:
            self._gpu_type = GPU_MAP[self.gpu.lower()]
        else:
            self._gpu_type = self.gpu

        # Look up the deployed function
        try:
            self._function = modal.Function.from_name(self.app_name, self.function_name)
        except modal.exception.NotFoundError:
            # Function not deployed yet - will need to be created
            self._function = None

    def _get_hourly_cost(self) -> float:
        """Get hourly cost for configured GPU type."""
        return MODAL_COSTS.get(self._gpu_type, 1.0) * self.gpu_count

    def _generate_trial_input(self, config: TrialConfig) -> dict:
        """Generate the input payload for a Modal job."""
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
        """Submit a trial to Modal."""
        if self._function is None:
            raise RuntimeError(
                f"Modal function '{self.app_name}/{self.function_name}' not found. "
                "Deploy the training function first. See references/backends.md"
            )

        input_payload = self._generate_trial_input(trial_config)

        # Spawn async function call
        function_call = self._function.spawn(**input_payload)
        job_id = function_call.object_id

        # Store job info
        self._jobs[job_id] = {
            "trial_config": trial_config,
            "function_call": function_call,
            "submitted_at": time.time(),
            "result": None,
        }

        print(f"Submitted trial {trial_config.trial_id} as Modal job {job_id}")
        return job_id

    def status(self, job_id: str) -> JobStatus:
        """Check job status."""
        if job_id not in self._jobs:
            # Try to look up the function call
            try:
                function_call = modal.functions.FunctionCall.from_id(job_id)
            except Exception:
                raise ValueError(f"Unknown job: {job_id}")
        else:
            function_call = self._jobs[job_id]["function_call"]

        # Check if complete
        try:
            # Try to get result with zero timeout
            function_call.get(timeout=0)
            return JobStatus.COMPLETED
        except TimeoutError:
            return JobStatus.RUNNING
        except modal.exception.ExecutionError:
            return JobStatus.FAILED
        except Exception:
            return JobStatus.PENDING

    def results(self, job_id: str) -> TrialResult:
        """Get trial results."""
        # Check cached results
        if job_id in self._jobs and self._jobs[job_id].get("result"):
            return self._jobs[job_id]["result"]

        if job_id not in self._jobs:
            raise ValueError(f"Unknown job: {job_id}")

        job_data = self._jobs[job_id]
        function_call = job_data["function_call"]
        trial_config = job_data["trial_config"]
        submitted_at = job_data["submitted_at"]

        # Get result (blocking)
        try:
            output = function_call.get()
            status = JobStatus.COMPLETED
        except modal.exception.ExecutionError as e:
            output = {"error": str(e)}
            status = JobStatus.FAILED
        except Exception as e:
            output = {"error": str(e)}
            status = JobStatus.FAILED

        # Calculate duration and cost
        duration = time.time() - submitted_at
        hourly_rate = self._get_hourly_cost()
        cost = hourly_rate * (duration / 3600)

        # Extract objective value from output
        objective_value = None
        metrics = {}
        intermediate_values = {}

        if output and isinstance(output, dict):
            objective_value = output.get("objective_value")
            metrics = output.get("metrics", {})
            intermediate_values = output.get("intermediate_values", {})

        result = TrialResult(
            trial_id=trial_config.trial_id,
            job_id=job_id,
            status=status,
            objective_value=objective_value,
            hyperparameters=trial_config.hyperparameters,
            metrics=metrics,
            intermediate_values=intermediate_values,
            duration_seconds=duration,
            cost_usd=round(cost, 2),
        )

        # Cache result
        self._jobs[job_id]["result"] = result
        return result

    def cancel(self, job_id: str) -> None:
        """Cancel a running job."""
        if job_id in self._jobs:
            function_call = self._jobs[job_id]["function_call"]
            try:
                function_call.cancel()
            except Exception as e:
                print(f"Warning: Could not cancel job {job_id}: {e}")
        print(f"Cancelled Modal job {job_id}")

    def logs(self, job_id: str) -> str:
        """Get job logs."""
        # Modal logs are streamed during execution
        # After completion, they're available via the Modal dashboard
        return "[Logs available in Modal dashboard: https://modal.com/apps]"

    def intermediate_values(self, job_id: str) -> dict[int, float]:
        """Get intermediate values for pruning."""
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


# Modal app definition for training trials
MODAL_APP_TEMPLATE = '''
"""
Modal app for HPO training trials.

Deploy with: modal deploy modal_hpo_app.py
"""

import json
import modal
from pathlib import Path

# Define the Modal app
app = modal.App("hpo-training")

# Define the container image
training_image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "torch",
    "transformers>=4.36.0",
    "trl>=0.12.0",
    "peft>=0.7.0",
    "accelerate>=0.24.0",
    "datasets",
    "huggingface_hub>=0.20.0",
    "bitsandbytes",
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
    method: str = "sft",
    hyperparameters: dict = None,
    output_dir: str = None,
    hub_model_id: str = None,
    push_to_hub: bool = True,
    eval_steps: int = 50,
    num_train_epochs: int = 1,
    results_repo: str = None,
    learning_rate: float = 2e-5,
    per_device_train_batch_size: int = 4,
    weight_decay: float = 0.01,
    lora_r: int = 16,
    lora_alpha: int = 32,
    lora_dropout: float = 0.05,
    lr_scheduler_type: str = "cosine",
    warmup_ratio: float = 0.1,
    gradient_accumulation_steps: int = 4,
):
    """Train a single HPO trial."""
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

    print(f"Starting trial {trial_id} for study {study_name}")
    print(f"Model: {model}, Dataset: {dataset}")

    # Load dataset
    ds = load_dataset(dataset, split="train")
    dataset_split = ds.train_test_split(test_size=0.1, seed=42)

    output_dir = output_dir or f"{study_name}-trial-{trial_id}"

    # Training config
    config = SFTConfig(
        output_dir=output_dir,
        push_to_hub=push_to_hub,
        hub_model_id=hub_model_id or output_dir,
        learning_rate=learning_rate,
        per_device_train_batch_size=per_device_train_batch_size,
        weight_decay=weight_decay,
        num_train_epochs=num_train_epochs,
        lr_scheduler_type=lr_scheduler_type,
        warmup_ratio=warmup_ratio,
        gradient_accumulation_steps=gradient_accumulation_steps,
        eval_strategy="steps",
        eval_steps=eval_steps,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        logging_steps=10,
        save_strategy="steps",
        save_steps=eval_steps,
        save_total_limit=2,
    )

    # LoRA config
    peft_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
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
    if push_to_hub:
        trainer.push_to_hub()

    print(f"Trial {trial_id} complete! Objective: {objective}")

    return {
        "trial_id": trial_id,
        "study_name": study_name,
        "objective_value": objective,
        "hyperparameters": hyperparameters or {},
        "intermediate_values": pruning_callback.intermediate_values,
        "status": "completed",
    }
'''
