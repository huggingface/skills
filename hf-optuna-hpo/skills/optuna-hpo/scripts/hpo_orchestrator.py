#!/usr/bin/env python3
# /// script
# dependencies = [
#     "optuna>=3.0.0",
#     "huggingface_hub>=0.20.0",
# ]
# ///

"""
HPO orchestrator for distributed hyperparameter optimisation.

Manages Optuna studies, dispatches trials to cloud backends, and coordinates
results collection for transformer fine-tuning optimisation.
"""

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import optuna
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler

from backend_interface import (
    JobStatus,
    RunnerConfig,
    TrialConfig,
    TrialResult,
    TrialRunner,
    estimate_study_cost,
)
from search_spaces import (
    get_search_space,
    suggest_hyperparameters,
    validate_search_space,
    format_search_space,
)


@dataclass
class HPOStudy:
    """
    Hyperparameter optimisation study orchestrator.

    Manages an Optuna study that dispatches trials to cloud backends,
    tracks progress and provides visualisation.
    """

    # Required parameters
    name: str
    model: str
    dataset: str
    runner: TrialRunner

    # Training configuration
    method: str = "sft"
    eval_steps: int = 50
    num_train_epochs: int = 1

    # Search space
    search_space: str | dict = "default"

    # Execution
    n_trials: int = 20
    n_parallel: int = 3
    direction: str = "minimize"  # minimize eval_loss

    # Budget
    budget_usd: float | None = None
    warn_at_percent: float = 80.0

    # Persistence
    storage: str = "local"  # "local" or "hub://username/repo"

    # Optuna configuration
    sampler: str | optuna.samplers.BaseSampler = "tpe"
    pruner: str | optuna.pruners.BasePruner | None = "median"
    n_startup_trials: int = 5

    # Hub configuration
    push_to_hub: bool = True
    hub_model_prefix: str | None = None

    # Internal state
    _study: optuna.Study | None = field(default=None, repr=False)
    _active_jobs: dict = field(default_factory=dict, repr=False)
    _total_cost: float = field(default=0.0, repr=False)
    _storage_path: Path | None = field(default=None, repr=False)

    def __post_init__(self):
        """Initialise the study."""
        # Validate and resolve search space
        self._search_space = get_search_space(self.search_space)
        errors = validate_search_space(self._search_space)
        if errors:
            raise ValueError(f"Invalid search space:\n" + "\n".join(errors))

        # Set up storage
        self._setup_storage()

        # Set up sampler
        if isinstance(self.sampler, str):
            if self.sampler.lower() == "tpe":
                self._sampler = TPESampler(n_startup_trials=self.n_startup_trials)
            elif self.sampler.lower() == "random":
                self._sampler = optuna.samplers.RandomSampler()
            else:
                raise ValueError(f"Unknown sampler: {self.sampler}")
        else:
            self._sampler = self.sampler

        # Set up pruner
        if self.pruner is None:
            self._pruner = optuna.pruners.NopPruner()
        elif isinstance(self.pruner, str):
            if self.pruner.lower() == "median":
                self._pruner = MedianPruner(
                    n_startup_trials=self.n_startup_trials,
                    n_warmup_steps=self.eval_steps,
                )
            elif self.pruner.lower() == "hyperband":
                self._pruner = optuna.pruners.HyperbandPruner()
            else:
                raise ValueError(f"Unknown pruner: {self.pruner}")
        else:
            self._pruner = self.pruner

        # Hub model prefix
        if self.hub_model_prefix is None:
            self.hub_model_prefix = self.name

    def _setup_storage(self):
        """Set up study storage."""
        if self.storage == "local":
            # Local SQLite storage
            storage_dir = Path("./optuna_studies")
            storage_dir.mkdir(exist_ok=True)
            self._storage_path = storage_dir / f"{self.name}.db"
            self._storage_url = f"sqlite:///{self._storage_path}"

        elif self.storage.startswith("hub://"):
            # Hub storage - download DB if exists, or create new
            repo_id = self.storage.replace("hub://", "")
            self._hub_repo = repo_id

            # Try to download existing study
            try:
                from huggingface_hub import hf_hub_download
                local_path = hf_hub_download(
                    repo_id=repo_id,
                    filename=f"{self.name}.db",
                    repo_type="dataset",
                )
                self._storage_path = Path(local_path)
            except Exception:
                # Create new local DB that will be synced
                storage_dir = Path("./optuna_studies")
                storage_dir.mkdir(exist_ok=True)
                self._storage_path = storage_dir / f"{self.name}.db"

            self._storage_url = f"sqlite:///{self._storage_path}"

        else:
            # Assume it's a direct SQLite path or URL
            self._storage_url = self.storage
            if self.storage.startswith("sqlite:///"):
                self._storage_path = Path(self.storage.replace("sqlite:///", ""))

    def _create_or_load_study(self) -> optuna.Study:
        """Create or load the Optuna study."""
        if self._study is not None:
            return self._study

        self._study = optuna.create_study(
            study_name=self.name,
            storage=self._storage_url,
            sampler=self._sampler,
            pruner=self._pruner,
            direction=self.direction,
            load_if_exists=True,
        )

        return self._study

    def _objective(self, trial: optuna.Trial) -> float:
        """Objective function for Optuna optimisation."""
        # Suggest hyperparameters
        hyperparameters = suggest_hyperparameters(trial, self._search_space)

        # Create trial config
        trial_config = TrialConfig(
            trial_id=trial.number,
            study_name=self.name,
            hyperparameters=hyperparameters,
            model=self.model,
            dataset=self.dataset,
            method=self.method,
            eval_steps=self.eval_steps,
            num_train_epochs=self.num_train_epochs,
            push_to_hub=self.push_to_hub,
            hub_model_id=f"{self.hub_model_prefix}-trial-{trial.number}",
        )

        # Submit job
        job_id = self.runner.submit(trial_config)
        self._active_jobs[trial.number] = {
            "job_id": job_id,
            "config": trial_config,
            "start_time": time.time(),
        }

        # Poll for completion with pruning checks
        while True:
            status = self.runner.status(job_id)

            if status == JobStatus.COMPLETED:
                result = self.runner.results(job_id)
                self._total_cost += result.cost_usd or 0
                del self._active_jobs[trial.number]

                if result.objective_value is None:
                    raise optuna.TrialPruned("No objective value returned")

                return result.objective_value

            elif status == JobStatus.FAILED:
                result = self.runner.results(job_id)
                self._total_cost += result.cost_usd or 0
                del self._active_jobs[trial.number]
                raise optuna.TrialPruned(f"Job failed: {result.error_message}")

            elif status == JobStatus.RUNNING:
                # Check intermediate values for pruning
                intermediate = self.runner.intermediate_values(job_id)
                for step, value in intermediate.items():
                    trial.report(value, step)

                    if trial.should_prune():
                        self.runner.cancel(job_id)
                        result = self.runner.results(job_id)
                        self._total_cost += result.cost_usd or 0
                        del self._active_jobs[trial.number]
                        raise optuna.TrialPruned()

            # Check budget
            if self.budget_usd and self._total_cost >= self.budget_usd:
                self.runner.cancel(job_id)
                raise optuna.TrialPruned("Out of cash.")

            time.sleep(30)  # Poll every 30 seconds

    def optimise(
        self,
        callbacks: list[Callable] | None = None,
        show_progress: bool = True,
    ) -> TrialResult:
        """
        Run the optimisation study.

        Args:
            callbacks: Optional list of Optuna callbacks
            show_progress: Whether to show progress bar

        Returns:
            Best trial result
        """
        study = self._create_or_load_study()

        # Calculate remaining trials
        completed = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
        remaining = max(0, self.n_trials - completed)

        if remaining == 0:
            print(f"Study already has {completed} completed trials")
        else:
            print(f"Running {remaining} trials ({completed} already completed)")

            study.optimize(
                self._objective,
                n_trials=remaining,
                n_jobs=self.n_parallel,
                callbacks=callbacks,
                show_progress_bar=show_progress,
            )

        # Get best trial
        best = study.best_trial

        return TrialResult(
            trial_id=best.number,
            job_id=f"{self.name}-trial-{best.number}",
            status=JobStatus.COMPLETED,
            objective_value=best.value,
            hyperparameters=best.params,
            metrics=best.user_attrs,
            duration_seconds=best.duration.total_seconds() if best.duration else 0,
            cost_usd=None,
        )

    def sync_to_hub(self, repo_id: str | None = None) -> str:
        """
        Sync study database to HuggingFace Hub.

        Args:
            repo_id: Hub repository ID (default: from storage setting)

        Returns:
            URL to the uploaded file
        """
        from huggingface_hub import HfApi

        if repo_id is None:
            if hasattr(self, "_hub_repo"):
                repo_id = self._hub_repo
            else:
                raise ValueError("No repo_id specified and storage is not Hub-based")

        if self._storage_path is None:
            raise ValueError("No local storage path to sync")

        api = HfApi()

        # Ensure repo exists
        api.create_repo(repo_id, repo_type="dataset", exist_ok=True)

        # Upload DB file
        url = api.upload_file(
            path_or_fileobj=str(self._storage_path),
            path_in_repo=f"{self.name}.db",
            repo_id=repo_id,
            repo_type="dataset",
        )

        print(f"Synced study to: {url}")
        return url

    def launch_dashboard(self, port: int = 7860) -> None:
        """
        Launch the Gradio visualisation dashboard.

        Args:
            port: Port to run the dashboard on
        """
        from gradio_dashboard import create_dashboard

        app = create_dashboard(self._storage_url, self.name)
        app.launch(server_port=port)

    def get_summary(self) -> dict:
        """Get a summary of the study."""
        study = self._create_or_load_study()

        completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
        pruned = [t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED]
        failed = [t for t in study.trials if t.state == optuna.trial.TrialState.FAIL]

        summary = {
            "name": self.name,
            "model": self.model,
            "dataset": self.dataset,
            "method": self.method,
            "n_trials_target": self.n_trials,
            "n_completed": len(completed),
            "n_pruned": len(pruned),
            "n_failed": len(failed),
            "n_remaining": max(0, self.n_trials - len(completed)),
            "total_cost_usd": round(self._total_cost, 2),
            "budget_usd": self.budget_usd,
        }

        if completed:
            summary["best_value"] = study.best_value
            summary["best_params"] = study.best_params

        return summary

    def get_trial_logs(self, trial_id: int) -> str:
        """Get logs for a specific trial."""
        if trial_id in self._active_jobs:
            job_id = self._active_jobs[trial_id]["job_id"]
            return self.runner.logs(job_id)
        else:
            return f"Trial {trial_id} not in active jobs"

    def format_config_summary(self) -> str:
        """Format a human-readable configuration summary."""
        min_cost, max_cost = estimate_study_cost(
            getattr(self.runner, "flavour", "a10g-large"),
            self.n_trials,
            avg_trial_minutes=30,
        )

        return f"""HPO study configuration
{'=' * 40}
Model:      {self.model}
Dataset:    {self.dataset}
Method:     {self.method}
Backend:    {type(self.runner).__name__}

Search space:
{format_search_space(self._search_space)}

Trials:     {self.n_trials} ({self.n_parallel} parallel)
Est. cost:  ${min_cost} - ${max_cost}
Budget:     {"$" + str(self.budget_usd) if self.budget_usd else "No limit"}
Storage:    {self.storage}
"""


def load_study(
    name: str,
    storage: str = "local",
) -> HPOStudy:
    """
    Load an existing study from storage.

    Args:
        name: Study name
        storage: Storage location ("local" or "hub://...")

    Returns:
        HPOStudy instance
    """
    # This is a simplified loader - real implementation would
    # need to restore all configuration from metadata
    raise NotImplementedError("Use HPOStudy constructor with load_if_exists=True")
