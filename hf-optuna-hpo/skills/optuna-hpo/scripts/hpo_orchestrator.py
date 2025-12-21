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
from huggingface_hub import HfApi, whoami
from huggingface_hub.utils import HfHubHTTPError

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


def verify_hf_auth(require_write: bool = True) -> dict:
    """
    Verify HuggingFace Hub authentication.

    Args:
        require_write: If True, verify the token has write permissions

    Returns:
        User info dict with 'name', 'orgs', 'auth' keys

    Raises:
        RuntimeError: If authentication fails or token lacks required permissions
    """
    try:
        user_info = whoami()
    except HfHubHTTPError as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            raise RuntimeError(
                "HuggingFace Hub authentication failed.\n"
                "Please run: huggingface-cli login\n"
                "Or set the HF_TOKEN environment variable."
            ) from e
        raise RuntimeError(f"HuggingFace Hub error: {e}") from e
    except Exception as e:
        raise RuntimeError(
            f"Could not verify HuggingFace authentication: {e}\n"
            "Please run: huggingface-cli login"
        ) from e

    # Check token type
    auth_info = user_info.get("auth", {})
    token_type = auth_info.get("type", "unknown")

    if require_write:
        # Check for write access
        access_token = auth_info.get("accessToken", {})
        role = access_token.get("role", "")

        # Fine-grained tokens have explicit permissions
        if token_type == "fine-grained":
            # For fine-grained tokens, check if write permission exists
            # The role field might be 'write' or similar
            if role not in ("write", "admin"):
                raise RuntimeError(
                    f"HuggingFace token lacks write permissions (role: {role}).\n"
                    "HPO requires write access to push models and sync studies.\n"
                    "Please create a token with write permissions at:\n"
                    "https://huggingface.co/settings/tokens"
                )

    return {
        "name": user_info.get("name", "unknown"),
        "username": user_info.get("name", "unknown"),
        "orgs": [org.get("name") for org in user_info.get("orgs", [])],
        "auth": auth_info,
        "token_type": token_type,
    }


def check_hf_auth() -> tuple[bool, str, dict | None]:
    """
    Check HuggingFace authentication status without raising.

    Returns:
        Tuple of (is_valid, message, user_info)
    """
    try:
        user_info = verify_hf_auth(require_write=True)
        return True, f"Authenticated as: {user_info['username']}", user_info
    except RuntimeError as e:
        return False, str(e), None


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
    trial_timeout_minutes: int = 180  # 3 hour default per trial
    poll_interval_seconds: int = 30
    report_interval_seconds: int = 300  # Report progress every 5 minutes

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
    results_dataset: str | None = None  # Hub dataset for results table (e.g., "username/hpo-results")
    scripts_dataset: str | None = None  # Hub dataset for trial scripts (e.g., "username/hpo-scripts")

    # Authentication
    skip_auth_check: bool = False  # Set to True for testing without Hub

    # Callbacks
    progress_callback: Callable[[dict], None] | None = None

    # Internal state
    _study: optuna.Study | None = field(default=None, repr=False)
    _active_jobs: dict = field(default_factory=dict, repr=False)
    _total_cost: float = field(default=0.0, repr=False)
    _storage_path: Path | None = field(default=None, repr=False)
    _last_report_time: float = field(default=0.0, repr=False)
    _trials_started: int = field(default=0, repr=False)
    _user_info: dict | None = field(default=None, repr=False)

    def __post_init__(self):
        """Initialise the study."""
        # Verify HuggingFace authentication
        if not self.skip_auth_check:
            require_write = self.push_to_hub or self.storage.startswith("hub://")
            try:
                self._user_info = verify_hf_auth(require_write=require_write)
                print(f"✓ Authenticated as: {self._user_info['username']}")
            except RuntimeError as e:
                raise RuntimeError(
                    f"Authentication required for HPO study.\n{e}"
                ) from e
        else:
            self._user_info = None

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

    def _report_progress(self, force: bool = False) -> None:
        """Report progress to callback if enough time has passed."""
        now = time.time()
        if not force and (now - self._last_report_time) < self.report_interval_seconds:
            return

        self._last_report_time = now

        # Build progress report
        study = self._create_or_load_study()
        completed = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
        pruned = len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])
        failed = len([t for t in study.trials if t.state == optuna.trial.TrialState.FAIL])

        progress = {
            "timestamp": now,
            "trials_completed": completed,
            "trials_pruned": pruned,
            "trials_failed": failed,
            "trials_active": len(self._active_jobs),
            "trials_remaining": max(0, self.n_trials - completed),
            "total_cost_usd": round(self._total_cost, 2),
            "budget_usd": self.budget_usd,
            "budget_percent_used": (
                round(100 * self._total_cost / self.budget_usd, 1)
                if self.budget_usd else None
            ),
            "best_value": study.best_value if completed > 0 else None,
            "active_jobs": {
                trial_id: {
                    "job_id": info["job_id"],
                    "elapsed_minutes": round((now - info["start_time"]) / 60, 1),
                }
                for trial_id, info in self._active_jobs.items()
            },
        }

        # Print progress summary
        print(f"\n{'=' * 50}")
        print(f"HPO PROGRESS REPORT - {self.name}")
        print(f"{'=' * 50}")
        print(f"Completed: {completed}/{self.n_trials} | Pruned: {pruned} | Failed: {failed}")
        print(f"Active trials: {len(self._active_jobs)}")
        if completed > 0:
            print(f"Best objective so far: {progress['best_value']:.6f}")
        print(f"Total cost: ${self._total_cost:.2f}", end="")
        if self.budget_usd:
            print(f" / ${self.budget_usd} ({progress['budget_percent_used']}%)")
        else:
            print()
        for trial_id, info in progress["active_jobs"].items():
            print(f"  - Trial {trial_id}: running for {info['elapsed_minutes']:.1f} min")
        print(f"{'=' * 50}\n")

        # Call user callback if provided
        if self.progress_callback:
            self.progress_callback(progress)

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
        start_time = time.time()
        self._active_jobs[trial.number] = {
            "job_id": job_id,
            "config": trial_config,
            "start_time": start_time,
        }
        self._trials_started += 1

        timeout_seconds = self.trial_timeout_minutes * 60

        # Poll for completion with pruning checks and timeout
        while True:
            status = self.runner.status(job_id)
            elapsed = time.time() - start_time

            if status == JobStatus.COMPLETED:
                result = self.runner.results(job_id)
                self._total_cost += result.cost_usd or 0
                del self._active_jobs[trial.number]
                self._report_progress()

                if result.objective_value is None:
                    raise optuna.TrialPruned("No objective value returned")

                return result.objective_value

            elif status == JobStatus.FAILED:
                result = self.runner.results(job_id)
                self._total_cost += result.cost_usd or 0
                del self._active_jobs[trial.number]
                self._report_progress()
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
                        self._report_progress()
                        raise optuna.TrialPruned()

            # Check timeout
            if elapsed > timeout_seconds:
                print(f"Trial {trial.number} timed out after {self.trial_timeout_minutes} minutes")
                self.runner.cancel(job_id)
                del self._active_jobs[trial.number]
                self._report_progress()
                raise optuna.TrialPruned(f"Trial timed out after {self.trial_timeout_minutes} minutes")

            # Check budget
            if self.budget_usd and self._total_cost >= self.budget_usd:
                self.runner.cancel(job_id)
                del self._active_jobs[trial.number]
                self._report_progress()
                raise optuna.TrialPruned("Budget exhausted")

            # Report progress periodically
            self._report_progress()

            time.sleep(self.poll_interval_seconds)

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

    def sync_results_table(self, repo_id: str | None = None) -> str:
        """
        Sync trial results as a structured table to HuggingFace Hub.

        Creates a dataset with a results table containing:
        - study_name, trial_id, job_id
        - All hyperparameters as columns
        - objective_value, status, duration, cost

        Args:
            repo_id: Hub repository ID (default: from results_dataset setting)

        Returns:
            URL to the uploaded dataset
        """
        import io
        import csv

        if repo_id is None:
            repo_id = self.results_dataset
        if repo_id is None:
            raise ValueError(
                "No results_dataset configured. Set results_dataset parameter "
                "or pass repo_id explicitly."
            )

        study = self._create_or_load_study()
        api = HfApi()

        # Ensure repo exists
        api.create_repo(repo_id, repo_type="dataset", exist_ok=True)

        # Collect all hyperparameter keys across trials
        all_hp_keys = set()
        for trial in study.trials:
            all_hp_keys.update(trial.params.keys())
        hp_keys = sorted(all_hp_keys)

        # Build CSV data
        csv_buffer = io.StringIO()
        fieldnames = [
            "study_name",
            "trial_id",
            "job_id",
            "status",
            "objective_value",
            "duration_minutes",
            "cost_usd",
        ] + hp_keys

        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()

        for trial in study.trials:
            row = {
                "study_name": self.name,
                "trial_id": trial.number,
                "job_id": f"{self.name}-trial-{trial.number}",
                "status": trial.state.name,
                "objective_value": trial.value,
                "duration_minutes": (
                    round(trial.duration.total_seconds() / 60, 2)
                    if trial.duration else None
                ),
                "cost_usd": trial.user_attrs.get("cost_usd"),
            }
            # Add hyperparameters
            for key in hp_keys:
                row[key] = trial.params.get(key)

            writer.writerow(row)

        # Upload CSV
        csv_content = csv_buffer.getvalue().encode("utf-8")
        url = api.upload_file(
            path_or_fileobj=csv_content,
            path_in_repo=f"{self.name}_results.csv",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"Update results for {self.name}",
        )

        # Also create/update README
        self._create_results_readme(repo_id, study, hp_keys)

        print(f"Synced results table to: {url}")
        return url

    def _create_results_readme(
        self,
        repo_id: str,
        study: optuna.Study,
        hp_keys: list[str],
    ) -> None:
        """Create README for results dataset."""
        api = HfApi()

        completed = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])

        readme = f"""---
license: apache-2.0
tags:
- optuna
- hpo
- hyperparameter-optimization
- results
---

# HPO Results: {self.name}

Hyperparameter optimisation results for `{self.model}` on `{self.dataset}`.

## Summary

| Metric | Value |
|--------|-------|
| Study | {self.name} |
| Model | {self.model} |
| Dataset | {self.dataset} |
| Method | {self.method} |
| Completed trials | {completed} |
"""

        if completed > 0:
            readme += f"""| Best objective | {study.best_value:.6f} |

## Best hyperparameters

| Parameter | Value |
|-----------|-------|
"""
            for key, value in sorted(study.best_params.items()):
                if isinstance(value, float):
                    readme += f"| {key} | {value:.6g} |\n"
                else:
                    readme += f"| {key} | {value} |\n"

        readme += f"""

## Results table

The file `{self.name}_results.csv` contains all trial results with columns:
- `study_name`: Name of the HPO study
- `trial_id`: Optuna trial number
- `job_id`: HuggingFace Jobs identifier
- `status`: Trial status (COMPLETE, PRUNED, FAIL)
- `objective_value`: Final eval_loss
- `duration_minutes`: Trial duration
- `cost_usd`: Estimated cost
- Hyperparameters: {", ".join(f"`{k}`" for k in hp_keys)}

## Usage

```python
import pandas as pd
from huggingface_hub import hf_hub_download

# Download results
path = hf_hub_download(
    repo_id="{repo_id}",
    filename="{self.name}_results.csv",
    repo_type="dataset",
)

# Load and analyse
df = pd.read_csv(path)
print(df.sort_values("objective_value").head())
```
"""

        api.upload_file(
            path_or_fileobj=readme.encode("utf-8"),
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"Update README for {self.name}",
        )

    def sync_scripts(self, repo_id: str | None = None) -> str:
        """
        Sync trial scripts to a HuggingFace Hub dataset.

        Stores the generated training scripts for each trial for
        reproducibility and debugging.

        Args:
            repo_id: Hub repository ID (default: from scripts_dataset setting)

        Returns:
            URL to the uploaded dataset
        """
        if repo_id is None:
            repo_id = self.scripts_dataset
        if repo_id is None:
            raise ValueError(
                "No scripts_dataset configured. Set scripts_dataset parameter "
                "or pass repo_id explicitly."
            )

        api = HfApi()

        # Ensure repo exists
        api.create_repo(repo_id, repo_type="dataset", exist_ok=True)

        # Upload scripts from active/completed jobs
        uploaded = []
        for trial_id, job_info in self._active_jobs.items():
            if "config" in job_info:
                script = self.runner._generate_trial_script(job_info["config"])
                url = api.upload_file(
                    path_or_fileobj=script.encode("utf-8"),
                    path_in_repo=f"{self.name}/trial_{trial_id}.py",
                    repo_id=repo_id,
                    repo_type="dataset",
                    commit_message=f"Trial {trial_id} script for {self.name}",
                )
                uploaded.append(url)

        if uploaded:
            print(f"Synced {len(uploaded)} scripts to: {repo_id}")
            return uploaded[-1]
        else:
            print("No scripts to sync")
            return ""

    def sync_all(self) -> dict[str, str]:
        """
        Sync study database, results table, and scripts to Hub.

        Returns:
            Dict with URLs for 'study', 'results', 'scripts'
        """
        urls = {}

        # Sync study database
        if self.storage.startswith("hub://") or hasattr(self, "_hub_repo"):
            urls["study"] = self.sync_to_hub()

        # Sync results table
        if self.results_dataset:
            urls["results"] = self.sync_results_table()

        # Sync scripts
        if self.scripts_dataset:
            urls["scripts"] = self.sync_scripts()

        return urls

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

        results_info = self.results_dataset or "Not configured"
        scripts_info = self.scripts_dataset or "Not configured"

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
Timeout:    {self.trial_timeout_minutes} min per trial
Progress:   Reports every {self.report_interval_seconds // 60} min

Storage:
  Study DB: {self.storage}
  Results:  {results_info}
  Scripts:  {scripts_info}

Dashboard:  python scripts/gradio_dashboard.py --study ./optuna_studies/{self.name}.db --name {self.name}
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
