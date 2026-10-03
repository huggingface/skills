# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pandas>=2.0.0",
#     "scikit-learn>=1.3.0",
#     "numpy>=1.24.0",
#     "huggingface_hub>=0.20.0",
#     "pyyaml>=6.0",
# ]
# ///
"""ML Benchmark Manager — prepare, grade, validate, and publish benchmarks on HF Hub."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import textwrap
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


class InvalidSubmissionError(ValueError):
    """Raised when a submission fails validation checks."""


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

METRICS = {
    "rmse": ("lower", "Root Mean Squared Error"),
    "mse": ("lower", "Mean Squared Error"),
    "mae": ("lower", "Mean Absolute Error"),
    "r2": ("higher", "R-squared"),
    "accuracy": ("higher", "Accuracy"),
    "f1-binary": ("higher", "F1 Score (Binary)"),
    "f1-macro": ("higher", "F1 Score (Macro)"),
    "f1-micro": ("higher", "F1 Score (Micro)"),
    "roc-auc": ("higher", "ROC AUC"),
    "log-loss": ("lower", "Log Loss"),
}


def compute_metric(y_true: np.ndarray, y_pred: np.ndarray, metric: str) -> float:
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        log_loss,
        mean_absolute_error,
        mean_squared_error,
        r2_score,
        roc_auc_score,
    )

    dispatch = {
        "rmse": lambda yt, yp: float(np.sqrt(mean_squared_error(yt, yp))),
        "mse": lambda yt, yp: float(mean_squared_error(yt, yp)),
        "mae": lambda yt, yp: float(mean_absolute_error(yt, yp)),
        "r2": lambda yt, yp: float(r2_score(yt, yp)),
        "accuracy": lambda yt, yp: float(accuracy_score(yt, yp)),
        "f1-binary": lambda yt, yp: float(f1_score(yt, yp, average="binary")),
        "f1-macro": lambda yt, yp: float(f1_score(yt, yp, average="macro")),
        "f1-micro": lambda yt, yp: float(f1_score(yt, yp, average="micro")),
        "roc-auc": lambda yt, yp: float(roc_auc_score(yt, yp)),
        "log-loss": lambda yt, yp: float(log_loss(yt, yp)),
    }
    if metric not in dispatch:
        raise ValueError(f"Unknown metric '{metric}'. Choose from: {list(dispatch)}")
    return dispatch[metric](y_true, y_pred)


# ---------------------------------------------------------------------------
# Prepare
# ---------------------------------------------------------------------------


def cmd_prepare(args: argparse.Namespace) -> None:
    raw_path = Path(args.raw_data)
    output_dir = Path(args.output_dir)
    public = output_dir / "public"
    private = output_dir / "private"
    public.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=True)

    # Handle zip extraction if raw_data is a directory
    if raw_path.is_dir():
        for zf in raw_path.rglob("*.zip"):
            try:
                with zipfile.ZipFile(zf, "r") as z:
                    z.extractall(raw_path)
            except Exception:
                pass
        candidates = sorted(raw_path.rglob("train.csv"))
        if not candidates:
            raise FileNotFoundError(f"No train.csv found in {raw_path}")
        raw_path = candidates[0]

    df = pd.read_csv(raw_path)
    id_col = args.id_column
    target_col = args.target_column
    test_size = args.test_size

    if id_col not in df.columns:
        raise ValueError(f"ID column '{id_col}' not found. Columns: {list(df.columns)}")
    if target_col not in df.columns:
        raise ValueError(f"Target column '{target_col}' not found. Columns: {list(df.columns)}")
    if len(df) < 100:
        raise ValueError(f"Dataset has {len(df)} rows — minimum 100 required for benchmarking.")

    min_test = 30
    if int(len(df) * test_size) < min_test:
        test_size = min(0.3, min_test / len(df))
        print(f"Adjusted test_size to {test_size:.2f} to ensure >= {min_test} test rows.")

    # Split strategy
    if args.time_column:
        df = df.sort_values(args.time_column)
        split_idx = int(len(df) * (1 - test_size))
        train_df = df.iloc[:split_idx]
        test_df = df.iloc[split_idx:]
        print(f"Temporal split on '{args.time_column}': {len(train_df)} train, {len(test_df)} test")
    elif args.group_column:
        from sklearn.model_selection import GroupShuffleSplit

        gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=0)
        groups = df[args.group_column]
        train_idx, test_idx = next(gss.split(df, groups=groups))
        train_df = df.iloc[train_idx]
        test_df = df.iloc[test_idx]
        print(f"Grouped split on '{args.group_column}': {len(train_df)} train, {len(test_df)} test")
    elif args.task_type == "classification":
        from sklearn.model_selection import train_test_split

        train_df, test_df = train_test_split(
            df, test_size=test_size, random_state=0, stratify=df[target_col]
        )
        print(f"Stratified split: {len(train_df)} train, {len(test_df)} test")
    else:
        from sklearn.model_selection import train_test_split

        train_df, test_df = train_test_split(df, test_size=test_size, random_state=0)
        print(f"Random split: {len(train_df)} train, {len(test_df)} test")

    assert len(test_df) >= min_test, f"Test set has {len(test_df)} rows, need >= {min_test}"

    train_ids = set(train_df[id_col])
    test_ids = set(test_df[id_col])
    assert train_ids.isdisjoint(test_ids), "Train and test IDs overlap!"

    train_df.to_csv(public / "train.csv", index=False)
    test_df.drop(columns=[target_col]).to_csv(public / "test.csv", index=False)

    private_df = test_df[[id_col, target_col]].copy()
    private_df.columns = ["ans_id", "ans_target"]
    private_df.to_csv(private / "test.csv", index=False)

    sample_sub = test_df[[id_col]].copy()
    if args.task_type == "regression":
        sample_sub[target_col] = 0.0
    else:
        sample_sub[target_col] = df[target_col].mode()[0]
    sample_sub.to_csv(public / "sample_submission.csv", index=False)

    print(f"\nPrepared benchmark in {output_dir}:")
    print(f"  public/train.csv          — {len(train_df)} rows")
    print(f"  public/test.csv           — {len(test_df)} rows")
    print(f"  public/sample_submission.csv — {len(test_df)} rows")
    print(f"  private/test.csv          — {len(test_df)} rows")


# ---------------------------------------------------------------------------
# Grade
# ---------------------------------------------------------------------------


def _validate_and_merge(
    submission: pd.DataFrame,
    answers: pd.DataFrame,
    id_col: str,
    pred_col: str,
    metric: str,
) -> tuple[pd.Series, pd.Series]:
    """Validate submission and return aligned (y_true, y_pred)."""
    ans_id, ans_target = "ans_id", "ans_target"

    if id_col not in submission.columns or pred_col not in submission.columns:
        raise InvalidSubmissionError(
            f"Submission must have columns '{id_col}' and '{pred_col}'. "
            f"Found: {list(submission.columns)}"
        )

    if submission[pred_col].isnull().any():
        n = submission[pred_col].isnull().sum()
        raise InvalidSubmissionError(f"Predictions contain {n} NaN values")

    is_numeric_metric = metric in ("rmse", "mse", "mae", "r2", "roc-auc", "log-loss")
    if is_numeric_metric:
        preds = pd.to_numeric(submission[pred_col], errors="coerce")
        if preds.isnull().any():
            raise InvalidSubmissionError("Predictions contain non-numeric values")
        if np.isinf(preds).any():
            raise InvalidSubmissionError(
                f"Predictions contain {np.isinf(preds).sum()} infinite values"
            )
        if metric in ("roc-auc", "log-loss"):
            if (preds < 0).any() or (preds > 1).any():
                raise InvalidSubmissionError("Probabilities must be in [0, 1]")

    sub = submission[[id_col, pred_col]].copy()
    ans = answers[[ans_id, ans_target]].copy()

    sub[id_col] = sub[id_col].astype(str)
    ans[ans_id] = ans[ans_id].astype(str)

    sub = sub.drop_duplicates(subset=[id_col], keep="first")
    merged = sub.merge(ans, left_on=id_col, right_on=ans_id, how="inner")

    missing = set(ans[ans_id]) - set(merged[ans_id])
    if missing:
        sample = sorted(missing)[:5]
        raise InvalidSubmissionError(
            f"Missing predictions for {len(missing)} IDs. Sample: {sample}"
        )

    y_true = merged[ans_target].astype(float) if is_numeric_metric else merged[ans_target]
    y_pred = merged[pred_col].astype(float) if is_numeric_metric else merged[pred_col]
    return y_true, y_pred


def cmd_grade(args: argparse.Namespace) -> None:
    submission = pd.read_csv(args.submission)
    answers = pd.read_csv(args.answers)

    y_true, y_pred = _validate_and_merge(
        submission, answers, args.id_column, args.prediction_column, args.metric
    )
    score = compute_metric(y_true.values, y_pred.values, args.metric)

    direction = METRICS[args.metric][0]
    print(f"Metric: {METRICS[args.metric][1]}")
    print(f"Score:  {score:.6f} ({direction} is better)")


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------


def cmd_validate(args: argparse.Namespace) -> None:
    answers = pd.read_csv(args.answers)
    sample = pd.read_csv(args.sample_submission)
    id_col = args.id_column
    pred_col = args.prediction_column
    metric = args.metric

    results: list[tuple[str, str, str]] = []

    def _run(name: str, sub: pd.DataFrame) -> None:
        try:
            yt, yp = _validate_and_merge(sub, answers, id_col, pred_col, metric)
            score = compute_metric(yt.values, yp.values, metric)
            results.append((name, "PASS", f"score={score:.6f}"))
        except (InvalidSubmissionError, Exception) as e:
            results.append((name, "PASS (rejected)", str(e)[:80]))

    def _run_expect_error(name: str, sub: pd.DataFrame) -> None:
        try:
            yt, yp = _validate_and_merge(sub, answers, id_col, pred_col, metric)
            compute_metric(yt.values, yp.values, metric)
            results.append((name, "FAIL (should reject)", "No error raised"))
        except (InvalidSubmissionError, Exception):
            results.append((name, "PASS", "Correctly rejected"))

    # Valid submission
    _run("Valid submission (sample)", sample)

    # Missing IDs
    missing = sample.head(len(sample) // 2)
    _run_expect_error("Missing IDs (half removed)", missing)

    # Duplicate IDs
    dup = pd.concat([sample, sample.head(5)])
    _run("Duplicate IDs", dup)

    # NaN predictions
    nan_sub = sample.copy()
    nan_sub.loc[nan_sub.index[0], pred_col] = np.nan
    _run_expect_error("NaN in predictions", nan_sub)

    is_numeric = metric in ("rmse", "mse", "mae", "r2", "roc-auc", "log-loss")
    if is_numeric:
        # Inf predictions
        inf_sub = sample.copy()
        inf_sub.loc[inf_sub.index[0], pred_col] = np.inf
        _run_expect_error("Inf in predictions", inf_sub)

    # Wrong columns
    wrong = sample.rename(columns={pred_col: "wrong_col"})
    _run_expect_error("Wrong column names", wrong)

    # Empty submission
    _run_expect_error("Empty submission", pd.DataFrame())

    print("\nValidation Results")
    print("=" * 70)
    for name, status, detail in results:
        icon = "✓" if "PASS" in status and "FAIL" not in status else "✗"
        print(f"  {icon} {name:35s} {status:20s} {detail}")

    failures = [r for r in results if "FAIL" in r[1]]
    print(f"\n{len(results) - len(failures)}/{len(results)} tests passed")
    if failures:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


def cmd_publish(args: argparse.Namespace) -> None:
    from huggingface_hub import HfApi

    prepared = Path(args.prepared_dir)
    if not (prepared / "public" / "train.csv").exists():
        raise FileNotFoundError(f"No prepared data at {prepared}. Run 'prepare' first.")

    api = HfApi()
    repo_id = args.repo_id

    api.create_repo(repo_id, repo_type="dataset", private=args.private, exist_ok=True)

    readme = _generate_dataset_card(args)
    readme_path = prepared / "README.md"
    readme_path.write_text(readme, encoding="utf-8")

    api.upload_file(
        path_or_fileobj=str(prepared / "public" / "train.csv"),
        path_in_repo="data/train.csv",
        repo_id=repo_id,
        repo_type="dataset",
    )
    api.upload_file(
        path_or_fileobj=str(prepared / "public" / "test.csv"),
        path_in_repo="data/test.csv",
        repo_id=repo_id,
        repo_type="dataset",
    )
    api.upload_file(
        path_or_fileobj=str(prepared / "public" / "sample_submission.csv"),
        path_in_repo="data/sample_submission.csv",
        repo_id=repo_id,
        repo_type="dataset",
    )
    api.upload_file(
        path_or_fileobj=str(prepared / "private" / "test.csv"),
        path_in_repo="answers/test.csv",
        repo_id=repo_id,
        repo_type="dataset",
    )
    api.upload_file(
        path_or_fileobj=str(readme_path),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
    )

    url = f"https://huggingface.co/datasets/{repo_id}"
    print(f"Published benchmark to {url}")


def _generate_dataset_card(args: argparse.Namespace) -> str:
    direction, metric_label = METRICS.get(args.metric, ("unknown", args.metric))
    tags_str = ""
    if args.tags:
        tags_str = "\n".join(f"- {t.strip()}" for t in args.tags.split(","))

    return textwrap.dedent(f"""\
        ---
        license: apache-2.0
        task_categories:
        - tabular-{args.task_type}
        tags:
        - benchmark
        - ml-benchmark
        {tags_str}
        ---

        # {args.benchmark_name}

        {args.description or "An ML benchmark dataset."}

        ## Evaluation

        - **Metric**: {metric_label}
        - **Direction**: {direction} is better
        - **ID column**: {args.id_column or "id"}
        - **Prediction column**: {args.target_column or "target"}

        ## Dataset Structure

        - `data/train.csv` — Training data with features and target
        - `data/test.csv` — Test features (no target)
        - `data/sample_submission.csv` — Submission template
        - `answers/test.csv` — Ground truth (ans_id, ans_target)

        ## How to Participate

        1. Download `data/train.csv` and `data/test.csv`
        2. Train your model on the training data
        3. Generate predictions for the test set
        4. Format as CSV with columns matching `sample_submission.csv`
        5. Grade locally or submit for evaluation
    """)


# ---------------------------------------------------------------------------
# Checksums
# ---------------------------------------------------------------------------


def cmd_checksums(args: argparse.Namespace) -> None:
    prepared = Path(args.prepared_dir)
    output = Path(args.output)
    checksums: dict[str, str] = {}

    for f in sorted(prepared.rglob("*")):
        if f.is_file():
            rel = f.relative_to(prepared).as_posix()
            md5 = hashlib.md5(f.read_bytes()).hexdigest()
            checksums[rel] = md5

    output.write_text(yaml.dump(checksums, default_flow_style=False), encoding="utf-8")
    print(f"Wrote {len(checksums)} checksums to {output}")
    for rel, md5 in checksums.items():
        print(f"  {rel}: {md5}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchmark_manager",
        description="Create, grade, validate, and publish ML benchmarks on Hugging Face Hub.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # prepare
    p = sub.add_parser("prepare", help="Prepare benchmark train/test splits from raw data")
    p.add_argument("--raw-data", required=True, help="Path to raw CSV or directory containing data")
    p.add_argument("--output-dir", required=True, help="Output directory for prepared splits")
    p.add_argument("--id-column", required=True, help="Name of the ID column")
    p.add_argument("--target-column", required=True, help="Name of the target column")
    p.add_argument("--task-type", required=True, choices=["regression", "classification"])
    p.add_argument("--test-size", type=float, default=0.1, help="Fraction for test split (default: 0.1)")
    p.add_argument("--group-column", help="Column for grouped splitting (prevents leakage)")
    p.add_argument("--time-column", help="Column for temporal splitting")

    # grade
    g = sub.add_parser("grade", help="Grade a submission against ground truth")
    g.add_argument("--submission", required=True, help="Path to submission CSV")
    g.add_argument("--answers", required=True, help="Path to answers CSV (private/test.csv)")
    g.add_argument("--metric", required=True, choices=list(METRICS), help="Evaluation metric")
    g.add_argument("--id-column", required=True, help="ID column in submission")
    g.add_argument("--prediction-column", required=True, help="Prediction column in submission")

    # validate
    v = sub.add_parser("validate", help="Validate grading robustness with edge cases")
    v.add_argument("--answers", required=True, help="Path to answers CSV")
    v.add_argument("--sample-submission", required=True, help="Path to sample submission CSV")
    v.add_argument("--metric", required=True, choices=list(METRICS))
    v.add_argument("--id-column", required=True)
    v.add_argument("--prediction-column", required=True)

    # publish
    pub = sub.add_parser("publish", help="Publish benchmark to Hugging Face Hub")
    pub.add_argument("--prepared-dir", required=True, help="Path to prepared/ directory")
    pub.add_argument("--repo-id", required=True, help="HF repo ID (user/name)")
    pub.add_argument("--benchmark-name", required=True, help="Human-readable benchmark name")
    pub.add_argument("--metric", required=True, choices=list(METRICS))
    pub.add_argument("--task-type", required=True, choices=["regression", "classification"])
    pub.add_argument("--description", default="", help="Benchmark description")
    pub.add_argument("--id-column", default="id")
    pub.add_argument("--target-column", default="target")
    pub.add_argument("--tags", default="", help="Comma-separated tags")
    pub.add_argument("--private", action="store_true", help="Create private dataset")

    # checksums
    c = sub.add_parser("checksums", help="Generate MD5 checksums for prepared files")
    c.add_argument("--prepared-dir", required=True)
    c.add_argument("--output", default="checksums.yaml")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "prepare": cmd_prepare,
        "grade": cmd_grade,
        "validate": cmd_validate,
        "publish": cmd_publish,
        "checksums": cmd_checksums,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
