# Troubleshooting

Common issues and solutions for HPO studies.

## Trial failures

### Trials failing consistently

**Symptoms:** All or most trials fail with errors.

**Diagnosis:**
```python
study.get_trial_logs(trial_id)
```

**Common causes:**

1. **Dataset format mismatch**
   - Solution: Validate with dataset inspector first
   ```bash
   uv run https://huggingface.co/datasets/mcp-tools/skills/raw/main/dataset_inspector.py \
     --dataset your/dataset --split train
   ```

2. **Out of memory (OOM)**
   - Solution: Reduce batch size range, use smaller hardware tier
   ```python
   search_space = {
       "per_device_train_batch_size": ("categorical", [2, 4]),  # Smaller
       ...
   }
   ```

3. **Missing dependencies**
   - Solution: Check the generated script includes all required packages in PEP 723 header

4. **Authentication errors**
   - Solution: Verify HF_TOKEN in secrets
   ```python
   runner = HFJobsRunner(
       secrets={"HF_TOKEN": "$HF_TOKEN"},  # Must include this
   )
   ```

### Some trials fail, others succeed

**Symptoms:** Intermittent failures.

**Common causes:**

1. **Hardware-specific OOM**
   - Certain hyperparameter combinations exceed memory
   - Solution: Constrain batch size or enable gradient checkpointing

2. **Timeout exceeded**
   - Some trials take longer than timeout
   - Solution: Increase timeout or reduce epoch count

3. **Network issues**
   - Hub push failures
   - Solution: Add retry logic or check connectivity

## Pruning issues

### Pruning too aggressively

**Symptoms:** Good trials terminated early, best value not improving.

**Solutions:**
1. Increase startup trials:
   ```python
   pruner = MedianPruner(n_startup_trials=15)
   ```

2. Increase warmup steps:
   ```python
   pruner = MedianPruner(n_warmup_steps=100)
   ```

3. Switch to less aggressive pruner:
   ```python
   from optuna.pruners import SuccessiveHalvingPruner
   pruner = SuccessiveHalvingPruner(reduction_factor=2)
   ```

4. Disable pruning temporarily:
   ```python
   study = HPOStudy(pruner=None, ...)
   ```

### Pruning not working

**Symptoms:** Bad trials run to completion.

**Common causes:**

1. **Intermediate values not reported**
   - Ensure trial scripts include `OptunaPruningCallback`
   - Check `eval_strategy="steps"` is set

2. **Wrong step alignment**
   - `n_warmup_steps` should match `eval_steps`

3. **Too few startup trials**
   - Pruning only starts after `n_startup_trials` complete

## Persistence issues

### Study not resuming

**Symptoms:** New study created instead of loading existing.

**Solutions:**

1. Ensure same study name:
   ```python
   study = HPOStudy(name="exact-same-name", ...)
   ```

2. For local storage, check path exists:
   ```bash
   ls ./optuna_studies/my-study.db
   ```

3. For Hub storage, verify download:
   ```python
   from huggingface_hub import hf_hub_download
   path = hf_hub_download(repo_id="...", filename="my-study.db", repo_type="dataset")
   ```

### Hub sync fails

**Symptoms:** Error when syncing to Hub.

**Solutions:**

1. Check token permissions:
   ```python
   from huggingface_hub import whoami
   whoami()  # Should show write access
   ```

2. Create repo first:
   ```python
   from huggingface_hub import HfApi
   HfApi().create_repo("username/my-study", repo_type="dataset", exist_ok=True)
   ```

3. Check file isn't locked:
   - Close any SQLite connections before syncing

## Budget issues

### Budget exceeded

**Symptoms:** Spent more than budget limit.

**Why this happens:**
- Trials in progress when budget is hit will complete
- Cost estimates may be inaccurate

**Prevention:**
1. Set lower `warn_at_percent`:
   ```python
   study = HPOStudy(
       budget_usd=100,
       warn_at_percent=60,  # Warn earlier
   )
   ```

2. Use fewer parallel trials:
   ```python
   study = HPOStudy(n_parallel=1, ...)  # Sequential
   ```

### Cost tracking inaccurate

**Symptoms:** Reported costs don't match actual spend.

**Causes:**
- Startup/shutdown time not counted
- Price changes not reflected

**Solution:** Use actual billing data from HF/Modal/RunPod dashboard.

## Dashboard issues

### Dashboard won't load

**Symptoms:** Error when launching Gradio app.

**Solutions:**

1. Install dependencies:
   ```bash
   pip install gradio optuna pandas plotly
   ```

2. Check study exists:
   ```python
   import optuna
   study = optuna.load_study(study_name="...", storage="sqlite:///...")
   print(len(study.trials))  # Should be > 0
   ```

3. Try different port:
   ```bash
   python gradio_dashboard.py --study ./my-study.db --port 7861
   ```

### Plots not showing

**Symptoms:** Empty plots or error messages.

**Common causes:**

1. **Not enough trials**
   - Parameter importance needs 5+ completed trials
   - Solution: Wait for more trials to complete

2. **All trials pruned/failed**
   - Need at least one completed trial
   - Check trial logs for errors

3. **Browser caching**
   - Hard refresh: Ctrl+Shift+R

## Performance issues

### Optimisation slow

**Symptoms:** Not finding good hyperparameters.

**Solutions:**

1. **Check search space size:**
   ```python
   from scripts.search_spaces import estimate_search_space_size
   size = estimate_search_space_size(my_space)
   # If > 1M, consider constraining
   ```

2. **Increase trials:**
   - Rule of thumb: 10-20 trials per important hyperparameter

3. **Use better sampler:**
   - TPE with multivariate=True for correlated params
   ```python
   from optuna.samplers import TPESampler
   sampler = TPESampler(multivariate=True)
   ```

4. **Constrain search space:**
   - Remove parameters that don't matter
   - Narrow ranges based on early results

### Parallel trials slow

**Symptoms:** Trials queuing, not running in parallel.

**Common causes:**

1. **Backend quota limits**
   - HF Jobs has concurrency limits per account
   - Solution: Reduce `n_parallel` or upgrade plan

2. **Sampler blocking**
   - TPE can block waiting for completed trials
   - Solution: Increase `n_startup_trials` for more random exploration

## Getting help

If these solutions don't help:

1. **Check logs:**
   ```python
   print(study.get_trial_logs(trial_id))
   ```

2. **Inspect study:**
   ```python
   for trial in study.trials:
       print(f"Trial {trial.number}: {trial.state}, value={trial.value}")
   ```

3. **Export for debugging:**
   ```python
   df = study.trials_dataframe()
   df.to_csv("study_debug.csv")
   ```

4. **Open issue:**
   - [HuggingFace Skills](https://github.com/huggingface/skills/issues)
   - Include: study config, error messages, trial logs
