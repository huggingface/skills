# Pruning strategies

Pruning terminates unpromising trials early, saving GPU costs. This document covers Optuna pruner selection and configuration.

## Why prune?

- **Cost savings:** Pruned trials run ~25% of full duration
- **Faster iteration:** More trials in the same time
- **Better exploration:** Resources redirected to promising regions

Typical savings: **30-50%** reduction in total training time.

## MedianPruner (default)

Prunes trials performing below the median of completed trials at the same step.

```python
from optuna.pruners import MedianPruner

pruner = MedianPruner(
    n_startup_trials=5,    # Trials before pruning starts
    n_warmup_steps=50,     # Steps before pruning within a trial
    interval_steps=10,     # Check interval
)
```

**When to use:**
- General-purpose, works well for most cases
- Balanced between aggressive and conservative

**Configuration tips:**
- `n_startup_trials`: Set to 5-10 for reliable baseline
- `n_warmup_steps`: Match your `eval_steps` setting
- `interval_steps`: Lower = more aggressive pruning

## HyperbandPruner

Aggressive pruner based on successive halving. Good for large search spaces.

```python
from optuna.pruners import HyperbandPruner

pruner = HyperbandPruner(
    min_resource=1,        # Minimum epochs/steps
    max_resource=10,       # Maximum epochs/steps
    reduction_factor=3,    # Reduction rate per bracket
)
```

**When to use:**
- Large search spaces (>100,000 configurations)
- Limited budget
- Want aggressive early stopping

**Trade-off:** May prune good trials too early.

## SuccessiveHalvingPruner

Similar to Hyperband but simpler. Keeps top fraction at each step.

```python
from optuna.pruners import SuccessiveHalvingPruner

pruner = SuccessiveHalvingPruner(
    min_resource=1,
    reduction_factor=4,
    min_early_stopping_rate=0,
)
```

**When to use:**
- Known training duration
- Want predictable pruning behaviour

## PercentilePruner

Prunes trials below a percentile threshold.

```python
from optuna.pruners import PercentilePruner

pruner = PercentilePruner(
    percentile=25.0,       # Prune bottom 25%
    n_startup_trials=5,
    n_warmup_steps=50,
)
```

**When to use:**
- Want to keep top N% of trials
- More aggressive than MedianPruner (percentile < 50)
- More conservative than MedianPruner (percentile > 50)

## ThresholdPruner

Prunes trials exceeding a fixed threshold.

```python
from optuna.pruners import ThresholdPruner

pruner = ThresholdPruner(
    upper=2.0,    # Prune if eval_loss > 2.0
    lower=None,   # No lower bound
)
```

**When to use:**
- Known acceptable loss range
- Want to avoid wasting time on clearly bad trials

## No pruning

Disable pruning entirely:

```python
study = HPOStudy(
    pruner=None,  # or optuna.pruners.NopPruner()
    ...
)
```

**When to use:**
- Very short trials (< 5 minutes)
- Need all trials to complete for analysis
- Debugging

## Pruner selection guide

| Scenario | Recommended pruner |
|----------|-------------------|
| General purpose | MedianPruner |
| Large search space | HyperbandPruner |
| Conservative | SuccessiveHalving with low reduction |
| Aggressive | PercentilePruner (percentile=25) |
| Known thresholds | ThresholdPruner |
| Short trials | None |

## Integration with trial reporting

For pruning to work, trials must report intermediate values:

```python
# In the training script
class OptunaPruningCallback(TrainerCallback):
    def on_evaluate(self, args, state, control, metrics=None, **kwargs):
        if metrics and "eval_loss" in metrics:
            step = state.global_step
            value = metrics["eval_loss"]

            # Write to file for orchestrator
            results_path = Path(args.output_dir) / "optuna_intermediate.json"
            # ...
```

The orchestrator polls `intermediate_values()` and calls `trial.should_prune()`.

## Tuning pruner parameters

### Too aggressive (many good trials pruned)

- Increase `n_startup_trials` (e.g., 10 → 20)
- Increase `n_warmup_steps` (e.g., 50 → 100)
- Switch to SuccessiveHalvingPruner
- Increase percentile (for PercentilePruner)

### Too conservative (bad trials run too long)

- Decrease `n_startup_trials` (e.g., 10 → 5)
- Decrease `n_warmup_steps`
- Use HyperbandPruner
- Decrease percentile (for PercentilePruner)

## Monitoring pruning effectiveness

```python
study = load_study(storage_url, study_name)

completed = len([t for t in study.trials
                 if t.state == optuna.trial.TrialState.COMPLETE])
pruned = len([t for t in study.trials
              if t.state == optuna.trial.TrialState.PRUNED])

pruning_rate = pruned / (completed + pruned)
print(f"Pruning rate: {pruning_rate:.1%}")

# Healthy: 20-40% pruning rate
# Too low: Consider more aggressive pruner
# Too high: Consider more conservative pruner
```
