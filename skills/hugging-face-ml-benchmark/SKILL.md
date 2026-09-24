---
name: hugging-face-ml-benchmark
description: Create, prepare, and grade ML benchmark competitions on Hugging Face Hub. Supports train/test splitting with proper methodology (stratified, grouped, temporal), submission grading with robust validation, and publishing benchmarks as HF datasets. Use when building evaluation benchmarks, Kaggle-style competitions, or leaderboard datasets.
---

# Overview

This skill provides tools to create and manage ML benchmark competitions on Hugging Face Hub. It covers the full lifecycle: splitting raw data into public/private sets, grading submissions against ground truth, validating grading robustness, and publishing benchmarks as HF datasets.

## Integration with HF Ecosystem
- **HF Datasets**: Publish benchmarks as structured datasets with train/test/private splits
- **HF Evaluation**: Complements model evaluation by providing the benchmark datasets to evaluate against
- **HF CLI**: Upload and manage benchmark repositories on the Hub

# Version
1.0.0

# Dependencies
# Scripts use PEP 723 inline dependency management
# Run with: uv run scripts/script_name.py

- uv (Python package manager)
- pandas>=2.0.0
- scikit-learn>=1.3.0
- numpy>=1.24.0
- huggingface_hub>=0.20.0

# Core Capabilities

## 1. Data Preparation (Train/Test Splitting)

Create proper benchmark splits from raw datasets with methodology-aware splitting:

- **Stratified Split**: For classification tasks — preserves class distribution
- **Grouped Split**: For data with grouping keys (user_id, session, etc.) — prevents leakage
- **Temporal Split**: For time-series data — respects chronological order
- **Random Split**: For IID tabular regression/other tasks

### Split Methodology Decision Tree

1. Does the data have a time/date column used for ordering? → **Temporal split**
2. Does the data have a grouping key where the same entity appears in multiple rows? → **Grouped split**
3. Is the task classification with a categorical target? → **Stratified split**
4. Otherwise → **Random split**

### Usage

```bash
# Basic preparation (auto-detects split strategy)
uv run scripts/benchmark_manager.py prepare \
  --raw-data ./raw/train.csv \
  --output-dir ./prepared \
  --id-column "id" \
  --target-column "price" \
  --task-type regression

# Classification with stratified split
uv run scripts/benchmark_manager.py prepare \
  --raw-data ./raw/train.csv \
  --output-dir ./prepared \
  --id-column "id" \
  --target-column "label" \
  --task-type classification

# Grouped split (prevent data leakage)
uv run scripts/benchmark_manager.py prepare \
  --raw-data ./raw/train.csv \
  --output-dir ./prepared \
  --id-column "id" \
  --target-column "rating" \
  --task-type regression \
  --group-column "user_id"

# Temporal split
uv run scripts/benchmark_manager.py prepare \
  --raw-data ./raw/train.csv \
  --output-dir ./prepared \
  --id-column "id" \
  --target-column "sales" \
  --task-type regression \
  --time-column "date"

# Custom split ratio (default is 90/10)
uv run scripts/benchmark_manager.py prepare \
  --raw-data ./raw/train.csv \
  --output-dir ./prepared \
  --id-column "id" \
  --target-column "target" \
  --task-type classification \
  --test-size 0.2
```

### Output Structure

```
prepared/
├── public/
│   ├── train.csv              # Training data with all columns including target
│   ├── test.csv               # Test features only (no target column)
│   └── sample_submission.csv  # IDs + placeholder predictions
└── private/
    └── test.csv               # Ground truth: ans_id, ans_target
```

### Preparation Rules

- Minimum 30 test rows required; adjust split ratio up to 70/30 for small datasets
- Datasets with fewer than 100 rows are rejected
- `random_state=0` is always used for reproducibility
- IDs are validated for no overlap between train and test
- Sample submission IDs exactly match private test IDs

## 2. Submission Grading

Grade submissions against ground truth with robust validation and common ML metrics.

### Supported Metrics

| Metric | Task Type | Direction |
|--------|-----------|-----------|
| RMSE | Regression | Lower is better |
| MSE | Regression | Lower is better |
| MAE | Regression | Lower is better |
| R² | Regression | Higher is better |
| Accuracy | Classification | Higher is better |
| F1 (binary) | Classification | Higher is better |
| F1 (macro) | Classification | Higher is better |
| F1 (micro) | Classification | Higher is better |
| ROC AUC | Classification (probabilities) | Higher is better |
| Log Loss | Classification (probabilities) | Lower is better |

### Usage

```bash
# Grade a submission
uv run scripts/benchmark_manager.py grade \
  --submission ./submission.csv \
  --answers ./prepared/private/test.csv \
  --metric rmse \
  --id-column "id" \
  --prediction-column "price"

# Classification grading
uv run scripts/benchmark_manager.py grade \
  --submission ./submission.csv \
  --answers ./prepared/private/test.csv \
  --metric f1-macro \
  --id-column "id" \
  --prediction-column "label"

# Probability-based grading
uv run scripts/benchmark_manager.py grade \
  --submission ./submission.csv \
  --answers ./prepared/private/test.csv \
  --metric roc-auc \
  --id-column "id" \
  --prediction-column "probability"
```

### Grading Validation

The grader performs these checks before computing the metric:

1. **Column validation**: Required columns must exist in submission
2. **NaN check**: No null values allowed in predictions
3. **Inf check**: No infinite values in numeric predictions
4. **ID coercion**: IDs are cast to string for safe merging
5. **Duplicate handling**: Duplicate IDs keep first occurrence
6. **Coverage check**: Every answer ID must have a corresponding prediction
7. **Range checks**: Probabilities must be in [0, 1]; classifications must be in valid label set

## 3. Grading Validation (Testing the Grader)

Validate that a grading function handles edge cases correctly.

```bash
# Run validation suite against a grade function
uv run scripts/benchmark_manager.py validate \
  --answers ./prepared/private/test.csv \
  --sample-submission ./prepared/public/sample_submission.csv \
  --metric rmse \
  --id-column "id" \
  --prediction-column "price"
```

### Validation Tests

| Test | Description |
|------|-------------|
| Valid submission | Sample submission should return a finite score |
| Missing IDs | Submission with dropped rows should raise error |
| Extra IDs | Submission with extra rows should still grade correctly |
| Duplicate IDs | Submission with duplicated rows should keep first |
| NaN predictions | Submission with NaN values should raise error |
| Inf predictions | Submission with Inf values should raise error |
| Wrong columns | Submission with renamed columns should raise error |
| Empty submission | Empty DataFrame should raise error |

## 4. Publish to Hugging Face Hub

Publish a prepared benchmark as a structured HF dataset.

```bash
# Publish benchmark to Hub
uv run scripts/benchmark_manager.py publish \
  --prepared-dir ./prepared \
  --repo-id "username/my-ml-benchmark" \
  --benchmark-name "My ML Benchmark" \
  --metric rmse \
  --task-type regression \
  --description "House price prediction benchmark" \
  --private

# Publish with full metadata
uv run scripts/benchmark_manager.py publish \
  --prepared-dir ./prepared \
  --repo-id "username/my-ml-benchmark" \
  --benchmark-name "My ML Benchmark" \
  --metric rmse \
  --task-type regression \
  --description "House price prediction benchmark" \
  --id-column "id" \
  --target-column "price" \
  --tags "tabular,regression,housing"
```

### Published Dataset Structure

The published HF dataset includes:
- `train.csv` — Full training data with target
- `test.csv` — Test features without target
- `sample_submission.csv` — Template for submissions
- `answers.csv` — Ground truth (in a gated/private config)
- `README.md` — Auto-generated dataset card with benchmark metadata

## 5. Checksums Generation

Generate reproducibility checksums for prepared data files.

```bash
# Generate checksums for prepared directory
uv run scripts/benchmark_manager.py checksums \
  --prepared-dir ./prepared \
  --output checksums.yaml
```

Output format:
```yaml
public/train.csv: d41d8cd98f00b204e9800998ecf8427e
public/test.csv: a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6
public/sample_submission.csv: 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d
private/test.csv: f1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6
```

# Code Generation Templates

When generating `prepare.py` or `grade.py` for a new benchmark, use the templates below as starting points.

## prepare.py Template

```python
from pathlib import Path
import shutil
import zipfile
import pandas as pd
from sklearn.model_selection import train_test_split


def prepare(raw: Path, public: Path, private: Path):
    public.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=True)

    for zip_file in raw.rglob("*.zip"):
        try:
            with zipfile.ZipFile(zip_file, "r") as zip_ref:
                zip_ref.extractall(raw)
        except Exception:
            pass

    train_path = raw / "train.csv"
    if not train_path.exists():
        candidates = sorted(raw.rglob("train.csv"))
        if candidates:
            train_path = candidates[0]
        else:
            raise FileNotFoundError(f"Expected train.csv in {raw}, not found.")
    df = pd.read_csv(train_path)

    ID_COL = "id"          # ← set to actual ID column
    TARGET_COL = "target"   # ← set to actual target column

    assert ID_COL in df.columns, f"ID column '{ID_COL}' not found"
    assert TARGET_COL in df.columns, f"Target column '{TARGET_COL}' not found"
    assert len(df) >= 100, f"Dataset too small ({len(df)} rows), need >= 100"

    train_df, test_df = train_test_split(df, test_size=0.1, random_state=0)
    # For classification: add stratify=df[TARGET_COL]
    # For grouped data: use GroupShuffleSplit on group column
    # For temporal data: sort by time column and slice

    assert set(train_df[ID_COL]).isdisjoint(set(test_df[ID_COL]))

    train_df.to_csv(public / "train.csv", index=False)
    test_df.drop(columns=[TARGET_COL]).to_csv(public / "test.csv", index=False)

    private_df = test_df[[ID_COL, TARGET_COL]].copy()
    private_df.columns = ["ans_id", "ans_target"]
    private_df.to_csv(private / "test.csv", index=False)

    sample_sub = test_df[[ID_COL]].copy()
    sample_sub[TARGET_COL] = 0.0  # placeholder
    sample_sub.to_csv(public / "sample_submission.csv", index=False)

    for item in raw.iterdir():
        if item.is_file() and item.suffix.lower() not in (".zip", ".csv"):
            shutil.copy2(item, public / item.name)

    assert (public / "train.csv").exists()
    assert (public / "test.csv").exists()
    assert (public / "sample_submission.csv").exists()
    assert (private / "test.csv").exists()
```

## grade.py Template

```python
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error


class InvalidSubmissionError(ValueError):
    pass


def grade(submission: pd.DataFrame, answers: pd.DataFrame) -> float:
    SUB_ID = "id"            # ← set to submission ID column
    SUB_PRED = "target"      # ← set to prediction column
    ANS_ID = "ans_id"
    ANS_TARGET = "ans_target"

    if SUB_ID not in submission.columns or SUB_PRED not in submission.columns:
        raise InvalidSubmissionError(
            f"Submission must have columns '{SUB_ID}' and '{SUB_PRED}'. "
            f"Found: {list(submission.columns)}"
        )

    if submission[SUB_PRED].isnull().any():
        raise InvalidSubmissionError("Predictions contain NaN values")

    preds = pd.to_numeric(submission[SUB_PRED], errors="coerce")
    if np.isinf(preds).any():
        raise InvalidSubmissionError("Predictions contain infinite values")

    sub = submission[[SUB_ID, SUB_PRED]].copy()
    ans = answers[[ANS_ID, ANS_TARGET]].copy()

    sub[SUB_ID] = sub[SUB_ID].astype(str)
    ans[ANS_ID] = ans[ANS_ID].astype(str)

    sub = sub.drop_duplicates(subset=[SUB_ID], keep="first")

    merged = sub.merge(ans, left_on=SUB_ID, right_on=ANS_ID, how="inner")

    missing = set(ans[ANS_ID]) - set(merged[ANS_ID])
    if missing:
        raise InvalidSubmissionError(
            f"Missing predictions for {len(missing)} IDs. "
            f"Sample: {list(missing)[:5]}"
        )

    y_true = merged[ANS_TARGET].astype(float)
    y_pred = merged[SUB_PRED].astype(float)

    # ← Replace with appropriate metric
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))
```

# Commands Reference

```bash
# Prepare benchmark splits
uv run scripts/benchmark_manager.py prepare --raw-data <path> --output-dir <path> \
  --id-column <col> --target-column <col> --task-type <regression|classification> \
  [--test-size 0.1] [--group-column <col>] [--time-column <col>]

# Grade a submission
uv run scripts/benchmark_manager.py grade --submission <path> --answers <path> \
  --metric <metric> --id-column <col> --prediction-column <col>

# Validate grading robustness
uv run scripts/benchmark_manager.py validate --answers <path> \
  --sample-submission <path> --metric <metric> \
  --id-column <col> --prediction-column <col>

# Publish to HF Hub
uv run scripts/benchmark_manager.py publish --prepared-dir <path> \
  --repo-id <user/repo> --benchmark-name <name> --metric <metric> \
  --task-type <type> [--description <text>] [--private] [--tags <csv>]

# Generate checksums
uv run scripts/benchmark_manager.py checksums --prepared-dir <path> \
  --output <path>
```

# Best Practices

1. **Always verify the evaluation metric** against the competition/benchmark documentation before grading
2. **Use grouped splits** when entities repeat across rows to prevent data leakage
3. **Use temporal splits** for time-ordered data to simulate realistic evaluation
4. **Ensure >= 30 test rows** for statistical significance; adjust split ratio for small datasets
5. **Validate grading robustness** with the validate command before publishing
6. **Generate checksums** after preparing data for reproducibility verification
7. **Use `InvalidSubmissionError`** (not generic `ValueError`) for submission validation failures
8. **Coerce IDs to string** before merging to avoid type mismatch issues
9. **Keep first occurrence** when handling duplicate submission IDs
10. **Check for NaN, Inf, and type errors** in predictions before computing metrics

# Error Handling

- **Dataset too small**: Raises error if fewer than 100 rows total or fewer than 30 test rows
- **Missing columns**: Clear error messages listing expected vs found columns
- **Invalid predictions**: NaN, Inf, out-of-range values rejected with descriptive messages
- **ID mismatches**: Reports count and sample of missing IDs
- **File not found**: Explicit messages when raw data or prepared files are missing
