# Search space reference

This document covers search space configuration for hyperparameter optimisation.

## Pre-defined templates

### Template A: Standard (minimal)

Fast exploration of core training parameters:

```python
SEARCH_SPACE_STANDARD = {
    "learning_rate": ("float_log", 1e-6, 1e-4),
    "per_device_train_batch_size": ("categorical", [4, 8, 16, 32]),
    "weight_decay": ("float", 0.0, 0.3),
    "num_train_epochs": ("categorical", [1, 2, 3]),
}
```

**When to use:** Quick experiments, baseline tuning, limited budget.

### Template B: With LoRA

Adds LoRA/PEFT parameters for efficient fine-tuning:

```python
SEARCH_SPACE_LORA = {
    **SEARCH_SPACE_STANDARD,
    "lora_r": ("categorical", [8, 16, 32, 64]),
    "lora_alpha": ("categorical", [16, 32, 64]),
    "lora_dropout": ("float", 0.0, 0.1),
}
```

**When to use:** PEFT fine-tuning, memory-constrained setups.

### Template C: Comprehensive (default)

Full search including scheduler parameters:

```python
SEARCH_SPACE_COMPREHENSIVE = {
    **SEARCH_SPACE_LORA,
    "lr_scheduler_type": ("categorical", ["linear", "cosine", "cosine_with_restarts"]),
    "warmup_ratio": ("float", 0.0, 0.2),
    "gradient_accumulation_steps": ("categorical", [1, 2, 4, 8]),
}
```

**When to use:** Production tuning, thorough optimisation.

## Custom search spaces

Define arbitrary hyperparameters using a dictionary:

```python
search_space = {
    "param_name": (type, *args),
}
```

### Parameter types

| Type | Args | Description | Example |
|------|------|-------------|---------|
| `float` | low, high | Uniform float | `("float", 0.0, 1.0)` |
| `float_log` | low, high | Log-uniform float | `("float_log", 1e-6, 1e-4)` |
| `int` | low, high | Uniform integer | `("int", 1, 10)` |
| `int_log` | low, high | Log-uniform integer | `("int_log", 1, 1000)` |
| `categorical` | choices | Categorical | `("categorical", [4, 8, 16])` |

### Examples

```python
# Custom SFT search space
search_space = {
    # Core
    "learning_rate": ("float_log", 5e-6, 5e-5),
    "per_device_train_batch_size": ("categorical", [2, 4, 8]),

    # LoRA with narrower range
    "lora_r": ("categorical", [16, 32]),
    "lora_alpha": ("int", 16, 64),

    # Custom parameter
    "max_grad_norm": ("float", 0.5, 2.0),
}

# DPO-specific
search_space = {
    "learning_rate": ("float_log", 1e-7, 1e-5),
    "beta": ("float", 0.05, 0.5),
    "loss_type": ("categorical", ["sigmoid", "hinge", "ipo"]),
}
```

## Parameter guidance

### Learning rate

- **Range:** `1e-6` to `1e-4` (log scale)
- **Default:** `2e-5`
- **Tips:** Lower for larger models, higher for smaller datasets

### Batch size

- **Values:** `[4, 8, 16, 32]`
- **Constraint:** Limited by GPU memory
- **Tips:** Larger batches need more gradient accumulation for stability

### LoRA rank (r)

- **Values:** `[8, 16, 32, 64]`
- **Trade-off:** Higher = more capacity but slower training
- **Tips:** Start with 16, increase if underfitting

### LoRA alpha

- **Values:** `[16, 32, 64]`
- **Relationship:** Usually set to `2 * lora_r` as baseline
- **Tips:** Higher alpha = stronger LoRA effect

### Weight decay

- **Range:** `0.0` to `0.3`
- **Default:** `0.01`
- **Tips:** Higher for larger datasets to prevent overfitting

### Scheduler

- **Options:** `linear`, `cosine`, `cosine_with_restarts`
- **Recommendation:** `cosine` works well for most cases
- **Tips:** `cosine_with_restarts` for longer training

## Validation

Always validate custom search spaces:

```python
from scripts.search_spaces import validate_search_space

errors = validate_search_space(my_search_space)
if errors:
    print("Errors:", errors)
```

## Estimating search space size

```python
from scripts.search_spaces import estimate_search_space_size

size = estimate_search_space_size(my_search_space)
print(f"Approximate configurations: {size}")
```

For a space with ~1,000,000 configurations, 20-30 trials with TPE sampling typically finds near-optimal solutions.
