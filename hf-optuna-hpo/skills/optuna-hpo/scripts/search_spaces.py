#!/usr/bin/env python3
# /// script
# dependencies = ["optuna>=3.0.0"]
# ///

"""
Search space definitions and utilities for HPO.

Provides pre-defined templates and functions to convert search space
specifications into Optuna trial suggestions.
"""

from typing import Any

import optuna


# =============================================================================
# Search space templates
# =============================================================================

SEARCH_SPACE_STANDARD = {
    "learning_rate": ("float_log", 1e-6, 1e-4),
    "per_device_train_batch_size": ("categorical", [4, 8, 16, 32]),
    "weight_decay": ("float", 0.0, 0.3),
    "num_train_epochs": ("categorical", [1, 2, 3]),
}

SEARCH_SPACE_LORA = {
    **SEARCH_SPACE_STANDARD,
    "lora_r": ("categorical", [8, 16, 32, 64]),
    "lora_alpha": ("categorical", [16, 32, 64]),
    "lora_dropout": ("float", 0.0, 0.1),
}

SEARCH_SPACE_COMPREHENSIVE = {
    **SEARCH_SPACE_LORA,
    "lr_scheduler_type": ("categorical", ["linear", "cosine", "cosine_with_restarts"]),
    "warmup_ratio": ("float", 0.0, 0.2),
    "gradient_accumulation_steps": ("categorical", [1, 2, 4, 8]),
}

# Template aliases
TEMPLATES = {
    "standard": SEARCH_SPACE_STANDARD,
    "a": SEARCH_SPACE_STANDARD,
    "lora": SEARCH_SPACE_LORA,
    "b": SEARCH_SPACE_LORA,
    "comprehensive": SEARCH_SPACE_COMPREHENSIVE,
    "c": SEARCH_SPACE_COMPREHENSIVE,
    "default": SEARCH_SPACE_COMPREHENSIVE,
}


# =============================================================================
# DPO-specific search spaces
# =============================================================================

SEARCH_SPACE_DPO = {
    **SEARCH_SPACE_LORA,
    "beta": ("float", 0.01, 0.5),  # KL penalty coefficient
    "loss_type": ("categorical", ["sigmoid", "hinge", "ipo"]),
}


# =============================================================================
# Utility functions
# =============================================================================

def get_search_space(name_or_dict: str | dict) -> dict:
    """
    Get a search space by name or return the provided dict.

    Args:
        name_or_dict: Template name ("standard", "lora", "comprehensive")
                      or a custom search space dict

    Returns:
        Search space dictionary
    """
    if isinstance(name_or_dict, dict):
        return name_or_dict

    name = name_or_dict.lower()
    if name not in TEMPLATES:
        available = ", ".join(sorted(set(TEMPLATES.keys())))
        raise ValueError(f"Unknown template '{name}'. Available: {available}")

    return TEMPLATES[name]


def suggest_hyperparameters(
    trial: optuna.Trial,
    search_space: dict,
) -> dict:
    """
    Suggest hyperparameters for a trial based on search space.

    Args:
        trial: Optuna trial object
        search_space: Search space specification

    Returns:
        Dictionary of suggested hyperparameters
    """
    hyperparameters = {}

    for name, spec in search_space.items():
        if isinstance(spec, tuple):
            param_type, *args = spec
        else:
            raise ValueError(f"Invalid spec for {name}: {spec}")

        if param_type == "float":
            low, high = args
            hyperparameters[name] = trial.suggest_float(name, low, high)

        elif param_type == "float_log":
            low, high = args
            hyperparameters[name] = trial.suggest_float(name, low, high, log=True)

        elif param_type == "int":
            low, high = args
            hyperparameters[name] = trial.suggest_int(name, low, high)

        elif param_type == "int_log":
            low, high = args
            hyperparameters[name] = trial.suggest_int(name, low, high, log=True)

        elif param_type == "categorical":
            choices = args[0]
            hyperparameters[name] = trial.suggest_categorical(name, choices)

        else:
            raise ValueError(f"Unknown param type '{param_type}' for {name}")

    return hyperparameters


def validate_search_space(search_space: dict) -> list[str]:
    """
    Validate a search space specification.

    Args:
        search_space: Search space to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    for name, spec in search_space.items():
        if not isinstance(spec, tuple):
            errors.append(f"{name}: spec must be a tuple, got {type(spec).__name__}")
            continue

        if len(spec) < 2:
            errors.append(f"{name}: spec must have at least 2 elements")
            continue

        param_type = spec[0]
        valid_types = ("float", "float_log", "int", "int_log", "categorical")

        if param_type not in valid_types:
            errors.append(f"{name}: unknown type '{param_type}', must be one of {valid_types}")
            continue

        if param_type in ("float", "float_log", "int", "int_log"):
            if len(spec) != 3:
                errors.append(f"{name}: {param_type} requires (type, low, high)")
            else:
                low, high = spec[1], spec[2]
                if low >= high:
                    errors.append(f"{name}: low ({low}) must be < high ({high})")

        elif param_type == "categorical":
            if len(spec) != 2:
                errors.append(f"{name}: categorical requires (type, choices)")
            elif not isinstance(spec[1], (list, tuple)):
                errors.append(f"{name}: choices must be a list")
            elif len(spec[1]) < 2:
                errors.append(f"{name}: categorical needs at least 2 choices")

    return errors


def format_search_space(search_space: dict) -> str:
    """
    Format a search space for display.

    Args:
        search_space: Search space dict

    Returns:
        Human-readable string
    """
    lines = []

    for name, spec in search_space.items():
        param_type = spec[0]

        if param_type in ("float", "float_log"):
            low, high = spec[1], spec[2]
            scale = " (log)" if param_type == "float_log" else ""
            lines.append(f"  - {name}: {low} to {high}{scale}")

        elif param_type in ("int", "int_log"):
            low, high = spec[1], spec[2]
            scale = " (log)" if param_type == "int_log" else ""
            lines.append(f"  - {name}: {low} to {high}{scale}")

        elif param_type == "categorical":
            choices = spec[1]
            lines.append(f"  - {name}: {choices}")

    return "\n".join(lines)


def estimate_search_space_size(search_space: dict) -> int:
    """
    Estimate the number of unique configurations in a search space.

    For continuous parameters, estimates based on practical resolution.

    Args:
        search_space: Search space dict

    Returns:
        Estimated number of configurations
    """
    size = 1

    for name, spec in search_space.items():
        param_type = spec[0]

        if param_type in ("float", "float_log"):
            # Assume ~20 meaningful values for continuous params
            size *= 20

        elif param_type in ("int", "int_log"):
            low, high = spec[1], spec[2]
            size *= (high - low + 1)

        elif param_type == "categorical":
            size *= len(spec[1])

    return size
