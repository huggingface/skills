#!/usr/bin/env python3
# /// script
# dependencies = []
# ///

"""
Backend interface for HPO trial execution.

This module defines the protocol that all backend runners must implement,
enabling pluggable execution across HuggingFace Jobs, Modal, RunPod, etc.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class JobStatus(Enum):
    """Status of a trial job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PRUNED = "pruned"


@dataclass
class TrialConfig:
    """Configuration for a single trial."""

    trial_id: int
    study_name: str
    hyperparameters: dict
    model: str
    dataset: str
    method: str = "sft"
    eval_steps: int = 50
    max_steps: int | None = None
    num_train_epochs: int = 1
    output_dir: str | None = None
    push_to_hub: bool = True
    hub_model_id: str | None = None
    report_to: str = "none"


@dataclass
class TrialResult:
    """Result of a completed trial."""

    trial_id: int
    job_id: str
    status: JobStatus
    objective_value: float | None = None
    hyperparameters: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    intermediate_values: dict = field(default_factory=dict)  # step -> value
    duration_seconds: float = 0.0
    cost_usd: float | None = None
    error_message: str | None = None
    logs_url: str | None = None
    model_url: str | None = None


@dataclass
class RunnerConfig:
    """Configuration for a backend runner."""

    flavour: str = "a10g-large"
    timeout: str = "2h"
    secrets: dict = field(default_factory=lambda: {"HF_TOKEN": "$HF_TOKEN"})
    env: dict = field(default_factory=dict)


@runtime_checkable
class TrialRunner(Protocol):
    """
    Protocol for backend runners.

    Implementations must provide methods to submit, monitor, and control
    trial jobs on their respective platforms.
    """

    def submit(self, trial_config: TrialConfig) -> str:
        """
        Submit a trial job to the backend.

        Args:
            trial_config: Configuration for this trial

        Returns:
            Job ID string for tracking
        """
        ...

    def status(self, job_id: str) -> JobStatus:
        """
        Check the current status of a job.

        Args:
            job_id: The job identifier returned by submit()

        Returns:
            Current JobStatus
        """
        ...

    def results(self, job_id: str) -> TrialResult:
        """
        Get the results of a completed job.

        Args:
            job_id: The job identifier

        Returns:
            TrialResult with objective value, metrics, etc.

        Raises:
            ValueError: If job is not yet completed
        """
        ...

    def cancel(self, job_id: str) -> None:
        """
        Cancel a running job.

        Args:
            job_id: The job identifier
        """
        ...

    def logs(self, job_id: str) -> str:
        """
        Get logs from a job.

        Args:
            job_id: The job identifier

        Returns:
            Log output as string
        """
        ...

    def intermediate_values(self, job_id: str) -> dict[int, float]:
        """
        Get intermediate objective values for pruning decisions.

        Args:
            job_id: The job identifier

        Returns:
            Dict mapping step number to objective value
        """
        ...


# Cost estimates per hour (USD) for common hardware
HARDWARE_COSTS = {
    "cpu-basic": 0.10,
    "cpu-upgrade": 0.20,
    "t4-small": 0.75,
    "t4-medium": 1.50,
    "l4x1": 2.00,
    "l4x4": 8.00,
    "a10g-small": 3.50,
    "a10g-large": 5.00,
    "a10g-largex2": 10.00,
    "a10g-largex4": 20.00,
    "a100-large": 10.00,
    "h100": 15.00,
    "h100x8": 120.00,
}


def estimate_trial_cost(
    flavour: str,
    duration_minutes: float,
) -> float:
    """
    Estimate the cost of a trial.

    Args:
        flavour: Hardware flavour
        duration_minutes: Expected duration in minutes

    Returns:
        Estimated cost in USD
    """
    hourly_rate = HARDWARE_COSTS.get(flavour, 5.00)
    return hourly_rate * (duration_minutes / 60)


def estimate_study_cost(
    flavour: str,
    n_trials: int,
    avg_trial_minutes: float,
    pruning_rate: float = 0.3,
) -> tuple[float, float]:
    """
    Estimate the cost range for a study.

    Args:
        flavour: Hardware flavour
        n_trials: Number of trials
        avg_trial_minutes: Average trial duration if not pruned
        pruning_rate: Expected fraction of trials to be pruned early

    Returns:
        Tuple of (min_cost, max_cost) in USD
    """
    full_trial_cost = estimate_trial_cost(flavour, avg_trial_minutes)

    # Pruned trials run ~25% of full duration on average
    pruned_trial_cost = full_trial_cost * 0.25

    n_full = int(n_trials * (1 - pruning_rate))
    n_pruned = n_trials - n_full

    min_cost = n_full * full_trial_cost * 0.8 + n_pruned * pruned_trial_cost
    max_cost = n_trials * full_trial_cost

    return (round(min_cost, 2), round(max_cost, 2))
