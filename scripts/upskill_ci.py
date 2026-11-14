#!/usr/bin/env python3
"""Run upskill-based smoke evaluations for changed skills and compare them to a base ref."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from upskill.ci import load_test_cases, plan_ci_suite
from upskill.config import Config
from upskill.evaluate import evaluate_skill
from upskill.executors.local_fast_agent import LocalFastAgentExecutor
from upskill.models import Skill, TestResult


JUDGE_SYSTEM_PROMPT = """You are grading whether an assistant response correctly applied a repository skill.

Return strict JSON with this shape:
{"score": 0.0, "summary": "short explanation"}

Rules:
- score must be a float between 0.0 and 1.0
- summary must be short
- use the hard-verifier result as context, but do not simply restate it
- prioritize correctness, relevance, completeness, and staying within the skill boundary
"""

SUMMARY_CASE_LIMIT = 2
SUMMARY_REQUEST_LIMIT = 140
SUMMARY_ISSUE_LIMIT = 220
SUMMARY_OUTPUT_LIMIT = 180


@dataclass(frozen=True)
class JudgeConfig:
    provider: str
    model: str


@dataclass
class AggregateMetrics:
    case_success_rate: float
    hard_score: float
    assertions_passed: int
    assertions_total: int
    avg_tokens: float
    avg_turns: float
    judge_score: float | None
    case_details: list[dict[str, Any]]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run upskill smoke checks for changed skills.")
    parser.add_argument(
        "--manifest",
        default=".upskill/evals.json",
        help="Path to the upskill eval manifest.",
    )
    parser.add_argument(
        "--base-ref",
        required=True,
        help="Git ref or commit to compare against.",
    )
    parser.add_argument(
        "--eval-model",
        default=None,
        help="Model name to pass to upskill evaluation. Defaults to upskill.config.yaml.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of repeated runs per scenario variant.",
    )
    parser.add_argument(
        "--artifacts-dir",
        default=".upskill/artifacts",
        help="Directory for raw evaluation artifacts.",
    )
    parser.add_argument(
        "--output",
        default=".upskill/reports/upskill-ci-report.json",
        help="Path for the machine-readable report.",
    )
    parser.add_argument(
        "--hard-regression-threshold",
        type=float,
        default=0.0,
        help="Allowed hard-score drop before failing.",
    )
    parser.add_argument(
        "--judge-regression-threshold",
        type=float,
        default=0.1,
        help="Allowed judge-score drop before failing when hard score is flat or worse.",
    )
    parser.add_argument(
        "--token-regression-threshold",
        type=float,
        default=0.2,
        help="Allowed avg-token increase ratio before failing when hard score is flat or worse.",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Append the current report to the configured Hugging Face dataset history.",
    )
    parser.add_argument(
        "--history-repo",
        default=os.environ.get("UPSKILL_HISTORY_REPO", "hf-skills/skill-performance-history"),
        help="HF dataset repo used for persisted history.",
    )
    return parser.parse_args()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_git(repo_root: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=text,
    )


def _normalize_base_ref(base_ref: str) -> str:
    if base_ref == "0000000000000000000000000000000000000000":
        return "HEAD~1"
    return base_ref


def _materialize_skill_from_git(repo_root: Path, ref: str, skill_path: str, destination: Path) -> Path:
    listed = _run_git(repo_root, "ls-tree", "-r", "--name-only", ref, "--", skill_path)
    if listed.returncode != 0:
        message = listed.stderr.strip() or listed.stdout.strip() or "git ls-tree failed"
        raise RuntimeError(f"Failed to inspect {skill_path} at {ref}: {message}")

    files = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
    if not files:
        raise FileNotFoundError(f"No files found for {skill_path} at {ref}")

    skill_root = destination / skill_path
    for relative_path in files:
        blob = _run_git(repo_root, "show", f"{ref}:{relative_path}", text=False)
        if blob.returncode != 0:
            message = blob.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Failed to read {relative_path} at {ref}: {message}")
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob.stdout)
    return skill_root


def _assertion_counts(test_result: TestResult) -> tuple[int, int]:
    if test_result.validation_result is not None:
        return (
            test_result.validation_result.assertions_passed,
            test_result.validation_result.assertions_total,
        )
    return (1 if test_result.success else 0, 1)


def _safe_average(total: float, count: int) -> float:
    if count <= 0:
        return 0.0
    return total / count


def _truncate_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        text = "; ".join(str(item) for item in value if item)
    else:
        text = str(value)
    text = " ".join(text.split())
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"Judge did not return JSON: {text}")
    return json.loads(stripped[start : end + 1])


def _http_json(url: str, *, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = _truncate_text(exc.read().decode("utf-8", errors="replace"), SUMMARY_ISSUE_LIMIT)
        message = f"HTTP {exc.code} {exc.reason} for {url}"
        if body:
            message = f"{message}: {body}"
        raise RuntimeError(message) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request to {url} failed: {exc.reason}") from exc


def _judge_config() -> JudgeConfig:
    provider = os.environ.get("UPSKILL_JUDGE_PROVIDER")
    if provider is None:
        if os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.environ.get("OPENAI_API_KEY"):
            provider = "openai"

    if provider == "anthropic":
        return JudgeConfig(
            provider="anthropic",
            model=os.environ.get("UPSKILL_JUDGE_MODEL", "claude-haiku-4-5-20251001"),
        )
    if provider == "openai":
        return JudgeConfig(
            provider="openai",
            model=os.environ.get("UPSKILL_JUDGE_MODEL", "gpt-4.1-mini"),
        )
    raise RuntimeError(
        "No judge provider configured. Set UPSKILL_JUDGE_PROVIDER or provide ANTHROPIC_API_KEY/OPENAI_API_KEY."
    )


def _normalize_anthropic_base_url(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/v1"):
        return trimmed[: -len("/v1")]
    return trimmed


def _call_anthropic(prompt: str, config: JudgeConfig) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required for anthropic judge runs.")
    base = _normalize_anthropic_base_url(
        os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    )
    payload = {
        "model": config.model,
        "max_tokens": 300,
        "temperature": 0,
        "system": JUDGE_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = _http_json(
        f"{base}/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        payload=payload,
    )
    blocks = response.get("content", [])
    return "\n".join(block.get("text", "") for block in blocks if block.get("type") == "text").strip()


def _normalize_openai_base_url(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/v1"):
        return trimmed
    return f"{trimmed}/v1"


def _call_openai(prompt: str, config: JudgeConfig) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for openai judge runs.")
    base = _normalize_openai_base_url(os.environ.get("OPENAI_API_BASE", "https://api.openai.com"))
    payload = {
        "model": config.model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    response = _http_json(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        payload=payload,
    )
    choices = response.get("choices", [])
    if not choices:
        raise RuntimeError("OpenAI judge returned no choices.")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        parts = [item.get("text", "") for item in content if isinstance(item, dict)]
        return "\n".join(parts).strip()
    return str(content).strip()


def _judge_case(
    *,
    judge: JudgeConfig,
    scenario_id: str,
    skill_path: str,
    criteria: list[str],
    test_result: TestResult,
) -> tuple[float | None, str | None]:
    verifier_status = "passed" if test_result.success else "failed"
    verifier_details = []
    if test_result.validation_result is not None:
        if test_result.validation_result.error_message:
            verifier_details.append(test_result.validation_result.error_message)
        verifier_details.extend(test_result.validation_result.details)

    prompt = "\n".join(
        [
            f"Scenario: {scenario_id}",
            f"Skill path: {skill_path}",
            "Criteria:",
            *[f"- {criterion}" for criterion in criteria],
            "",
            "User request:",
            test_result.test_case.input,
            "",
            "Assistant response:",
            test_result.output or "(no response)",
            "",
            f"Hard verifier status: {verifier_status}",
            f"Verifier details: {verifier_details or ['none']}",
        ]
    )

    try:
        if judge.provider == "anthropic":
            raw = _call_anthropic(prompt, judge)
        else:
            raw = _call_openai(prompt, judge)
        payload = _extract_json_object(raw)
        score = float(payload["score"])
        score = max(0.0, min(1.0, score))
        summary = str(payload.get("summary", "")).strip() or None
        return score, summary
    except (KeyError, TypeError, ValueError, urllib.error.URLError, RuntimeError) as exc:
        return None, f"judge error: {exc}"


def _aggregate_metrics(
    *,
    scenario_id: str,
    skill_path: str,
    criteria: list[str],
    test_results: list[TestResult],
    judge: JudgeConfig | None,
) -> AggregateMetrics:
    total_cases = len(test_results)
    passed_cases = 0
    assertions_passed = 0
    assertions_total = 0
    total_tokens = 0
    total_turns = 0
    judge_scores: list[float] = []
    details: list[dict[str, Any]] = []

    for index, test_result in enumerate(test_results, start=1):
        passed_cases += int(test_result.success)
        case_assertions_passed, case_assertions_total = _assertion_counts(test_result)
        assertions_passed += case_assertions_passed
        assertions_total += case_assertions_total
        total_tokens += test_result.stats.total_tokens or test_result.tokens_used
        total_turns += test_result.stats.turns or test_result.turns

        judge_score = None
        judge_summary = None
        if judge is not None:
            judge_score, judge_summary = _judge_case(
                judge=judge,
                scenario_id=scenario_id,
                skill_path=skill_path,
                criteria=criteria,
                test_result=test_result,
            )
            if judge_score is not None:
                judge_scores.append(judge_score)

        details.append(
            {
                "test_index": index,
                "success": test_result.success,
                "assertions_passed": case_assertions_passed,
                "assertions_total": case_assertions_total,
                "tokens": test_result.stats.total_tokens or test_result.tokens_used,
                "turns": test_result.stats.turns or test_result.turns,
                "input": getattr(test_result.test_case, "input", None),
                "output": test_result.output,
                "error": test_result.error,
                "validation_error": (
                    test_result.validation_result.error_message
                    if test_result.validation_result is not None
                    else None
                ),
                "validation_details": (
                    list(test_result.validation_result.details)
                    if test_result.validation_result is not None
                    else []
                ),
                "judge_score": judge_score,
                "judge_summary": judge_summary,
            }
        )

    return AggregateMetrics(
        case_success_rate=_safe_average(passed_cases, total_cases),
        hard_score=_safe_average(assertions_passed, assertions_total),
        assertions_passed=assertions_passed,
        assertions_total=assertions_total,
        avg_tokens=_safe_average(total_tokens, total_cases),
        avg_turns=_safe_average(total_turns, total_cases),
        judge_score=_safe_average(sum(judge_scores), len(judge_scores)) if judge_scores else None,
        case_details=details,
    )


async def _evaluate_variant(
    *,
    scenario_id: str,
    skill_path: str,
    skill: Skill,
    tests_path: Path,
    cards_path: Path,
    config: Config,
    model: str,
    runs: int,
    artifact_root: Path,
    judge: JudgeConfig | None,
    criteria: list[str],
) -> AggregateMetrics:
    test_cases = load_test_cases(tests_path)
    executor = LocalFastAgentExecutor()
    all_test_results: list[TestResult] = []

    for run_index in range(1, runs + 1):
        eval_results = await evaluate_skill(
            skill,
            test_cases=test_cases,
            executor=executor,
            model=model,
            fastagent_config_path=config.effective_fastagent_config,
            cards_source_dir=cards_path,
            artifact_root=artifact_root / f"run_{run_index}",
            run_baseline=False,
            max_parallel=config.max_parallel,
            operation="eval",
        )
        all_test_results.extend(eval_results.with_skill_results)

    return _aggregate_metrics(
        scenario_id=scenario_id,
        skill_path=skill_path,
        criteria=criteria,
        test_results=all_test_results,
        judge=judge,
    )


def _compare_variants(
    *,
    current: AggregateMetrics,
    baseline: AggregateMetrics,
    hard_regression_threshold: float,
    judge_regression_threshold: float,
    token_regression_threshold: float,
) -> tuple[bool, list[str], dict[str, float]]:
    reasons: list[str] = []
    deltas = {
        "hard_score": current.hard_score - baseline.hard_score,
        "judge_score": (
            current.judge_score - baseline.judge_score
            if current.judge_score is not None and baseline.judge_score is not None
            else 0.0
        ),
        "avg_tokens": current.avg_tokens - baseline.avg_tokens,
    }

    if current.hard_score + hard_regression_threshold < baseline.hard_score:
        reasons.append(
            f"hard score dropped from {baseline.hard_score:.3f} to {current.hard_score:.3f}"
        )

    hard_is_flat_or_worse = current.hard_score <= baseline.hard_score + 1e-9
    if (
        hard_is_flat_or_worse
        and current.judge_score is not None
        and baseline.judge_score is not None
        and current.judge_score + judge_regression_threshold < baseline.judge_score
    ):
        reasons.append(
            f"judge score dropped from {baseline.judge_score:.3f} to {current.judge_score:.3f}"
        )

    if hard_is_flat_or_worse and baseline.avg_tokens > 0:
        token_increase_ratio = (current.avg_tokens - baseline.avg_tokens) / baseline.avg_tokens
        if token_increase_ratio > token_regression_threshold:
            reasons.append(
                "average tokens increased from "
                f"{baseline.avg_tokens:.1f} to {current.avg_tokens:.1f}"
            )

    return (bool(reasons), reasons, deltas)


def _case_issues(case_detail: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    error = _truncate_text(case_detail.get("error"), SUMMARY_ISSUE_LIMIT)
    if error:
        issues.append(f"execution error: {error}")

    validation_error = _truncate_text(case_detail.get("validation_error"), SUMMARY_ISSUE_LIMIT)
    if validation_error:
        issues.append(f"verifier error: {validation_error}")

    validation_details = case_detail.get("validation_details") or []
    detail = _truncate_text(validation_details, SUMMARY_ISSUE_LIMIT)
    if detail:
        issues.append(f"verifier detail: {detail}")

    if not case_detail.get("success"):
        assertions_passed = case_detail.get("assertions_passed", 0)
        assertions_total = case_detail.get("assertions_total", 0)
        issues.append(f"hard assertions: {assertions_passed}/{assertions_total}")

    judge_summary = _truncate_text(case_detail.get("judge_summary"), SUMMARY_ISSUE_LIMIT)
    if judge_summary:
        prefix = "judge issue" if case_detail.get("judge_score") is None else "judge note"
        issues.append(f"{prefix}: {judge_summary}")

    return issues


def _issue_examples(case_details: list[dict[str, Any]]) -> list[str]:
    examples: list[str] = []
    for case_detail in case_details:
        issues = _case_issues(case_detail)
        if not issues:
            continue

        request = _truncate_text(case_detail.get("input"), SUMMARY_REQUEST_LIMIT) or "(no request)"
        line = (
            f"test {case_detail['test_index']}: request `{request}` | "
            f"issues: {'; '.join(issues)}"
        )
        response = _truncate_text(case_detail.get("output"), SUMMARY_OUTPUT_LIMIT)
        if response:
            line = f"{line} | response `{response}`"
        examples.append(line)
        if len(examples) >= SUMMARY_CASE_LIMIT:
            break
    return examples


def _judge_cell(metrics: dict[str, Any]) -> str:
    judge_score = metrics.get("judge_score")
    if judge_score is not None:
        return f"{judge_score:.3f}"
    case_details = metrics.get("case_details") or []
    if any(case.get("judge_summary") for case in case_details):
        return "error"
    return "n/a"


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Upskill Skill Performance",
        "",
        f"- Base ref: `{report['base_ref']}`",
        f"- Eval model: `{report['eval_model']}`",
        f"- Runs per variant: `{report['runs']}`",
    ]
    if report.get("judge") is not None:
        lines.append(
            f"- Judge: `{report['judge']['provider']}` / `{report['judge']['model']}`"
        )
    if report["selected_scenarios"]:
        lines.append(f"- Selected scenarios: `{', '.join(report['selected_scenarios'])}`")
    else:
        lines.extend(["", "No scenarios were selected."])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            "| Scenario | Skill | Current Hard | Main Hard | Judge | Main Judge | Avg Tokens | Main Tokens | Status |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for scenario in report["scenarios"]:
        current = scenario["current"]
        baseline = scenario["baseline"]
        current_judge = _judge_cell(current)
        baseline_hard = "n/a"
        baseline_tokens = "n/a"
        baseline_judge = "n/a"
        if baseline is not None:
            baseline_hard = f"{baseline['hard_score']:.3f}"
            baseline_tokens = f"{baseline['avg_tokens']:.1f}"
            baseline_judge = _judge_cell(baseline)
        status = "FAIL" if scenario["regression"] else ("PASS" if baseline is not None else "NEW")
        lines.append(
            "| "
            f"{scenario['scenario_id']} | "
            f"{scenario['skill_path']} | "
            f"{current['hard_score']:.3f} | "
            f"{baseline_hard} | "
            f"{current_judge} | "
            f"{baseline_judge} | "
            f"{current['avg_tokens']:.1f} | "
            f"{baseline_tokens} | "
            f"{status} |"
        )
        if scenario["notes"]:
            lines.append("")
            lines.append(f"Notes for `{scenario['scenario_id']}`:")
            for note in scenario["notes"]:
                lines.append(f"- {note}")
        if scenario["reasons"]:
            lines.append("")
            lines.append(f"Reasons for `{scenario['scenario_id']}`:")
            for reason in scenario["reasons"]:
                lines.append(f"- {reason}")
        current_examples = _issue_examples(current["case_details"])
        if current_examples:
            lines.append("")
            lines.append(f"Issue examples for `{scenario['scenario_id']}` current run:")
            for example in current_examples:
                lines.append(f"- {example}")
        if baseline is not None:
            baseline_examples = _issue_examples(baseline["case_details"])
            if baseline_examples:
                lines.append("")
                lines.append(f"Issue examples for `{scenario['scenario_id']}` main baseline:")
                for example in baseline_examples:
                    lines.append(f"- {example}")
    return "\n".join(lines)


def _write_step_summary(markdown: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write(markdown)
        handle.write("\n")


def _persist_history(report: dict[str, Any], repo_id: str) -> None:
    from huggingface_hub import HfApi, hf_hub_download
    from huggingface_hub.utils import HfHubHTTPError

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN is required to persist history.")

    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)

    history_path = "data/history.jsonl"
    metadata_path = "data/metadata.json"
    existing_content = ""

    try:
        downloaded = hf_hub_download(
            repo_id=repo_id,
            repo_type="dataset",
            filename=history_path,
            token=token,
        )
    except HfHubHTTPError as exc:
        if "404" not in str(exc):
            raise
    else:
        existing_content = Path(downloaded).read_text(encoding="utf-8")

    history_rows = report["history_rows"]
    appended = "\n".join(json.dumps(row, sort_keys=True) for row in history_rows)
    new_content = existing_content.strip()
    if new_content and appended:
        new_content = f"{new_content}\n{appended}"
    elif appended:
        new_content = appended

    metadata = {
        "updated_at": _now_iso(),
        "total_rows": len([line for line in new_content.splitlines() if line.strip()]),
        "latest_sha": report["commit_sha"],
        "latest_scenarios": report["selected_scenarios"],
    }

    api.upload_file(
        path_or_fileobj=new_content.encode("utf-8"),
        path_in_repo=history_path,
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=f"Update skill performance history for {report['commit_sha'][:8]}",
    )
    api.upload_file(
        path_or_fileobj=json.dumps(metadata, indent=2).encode("utf-8"),
        path_in_repo=metadata_path,
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=f"Update performance metadata for {report['commit_sha'][:8]}",
    )
    api.upload_file(
        path_or_fileobj=json.dumps(report, indent=2).encode("utf-8"),
        path_in_repo=f"reports/{report['commit_sha']}.json",
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=f"Upload detailed performance report for {report['commit_sha'][:8]}",
    )


async def _run_suite(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path.cwd()
    base_ref = _normalize_base_ref(args.base_ref)
    report_plan, selected_scenarios = plan_ci_suite(
        Path(args.manifest),
        scope="changed",
        base_ref=base_ref,
        working_dir=repo_root,
    )

    config = Config.load()
    eval_model = args.eval_model or config.effective_eval_model
    report: dict[str, Any] = {
        "generated_at": _now_iso(),
        "repo_root": str(repo_root),
        "base_ref": base_ref,
        "eval_model": eval_model,
        "runs": args.runs,
        "changed_files": report_plan.changed_files,
        "changed_skills": report_plan.changed_skills,
        "selected_scenarios": report_plan.selected_scenarios,
        "scenarios": [],
        "history_rows": [],
        "commit_sha": os.environ.get("GITHUB_SHA")
        or _run_git(repo_root, "rev-parse", "HEAD").stdout.strip(),
    }

    if not selected_scenarios:
        return report

    artifact_root = Path(args.artifacts_dir)
    artifact_root.mkdir(parents=True, exist_ok=True)

    judge_config = None
    if any((scenario.judge and scenario.judge.enabled) for scenario in selected_scenarios):
        judge_config = _judge_config()
    report["judge"] = (
        {"provider": judge_config.provider, "model": judge_config.model}
        if judge_config is not None
        else None
    )

    cards_resource = resources.files("upskill").joinpath("agent_cards")
    with resources.as_file(cards_resource) as cards_path, tempfile.TemporaryDirectory(
        prefix="upskill-base-"
    ) as temp_dir:
        temp_root = Path(temp_dir)
        for scenario in selected_scenarios:
            if len(scenario.skills) != 1:
                raise RuntimeError(
                    f"Scenario {scenario.id} must reference exactly one skill for this workflow."
                )

            skill_path = scenario.skills[0]
            current_skill_path = repo_root / skill_path
            tests_path = repo_root / scenario.tests
            if not current_skill_path.exists():
                raise FileNotFoundError(f"Current skill path not found: {current_skill_path}")
            if not tests_path.exists():
                raise FileNotFoundError(f"Tests path not found: {tests_path}")

            current_skill = Skill.load(current_skill_path)
            criteria = list((scenario.judge.criteria if scenario.judge else None) or [])
            active_judge = judge_config if scenario.judge and scenario.judge.enabled else None
            notes: list[str] = []

            current_metrics = await _evaluate_variant(
                scenario_id=scenario.id,
                skill_path=skill_path,
                skill=current_skill,
                tests_path=tests_path,
                cards_path=cards_path,
                config=config,
                model=eval_model,
                runs=args.runs,
                artifact_root=artifact_root / scenario.id / "current",
                judge=active_judge,
                criteria=criteria,
            )
            baseline_metrics = None
            regression = False
            reasons: list[str] = []
            deltas: dict[str, float] = {}
            try:
                baseline_skill_path = _materialize_skill_from_git(
                    repo_root,
                    base_ref,
                    skill_path,
                    temp_root,
                )
            except FileNotFoundError:
                notes.append(f"No baseline skill found at `{base_ref}`.")
            else:
                baseline_skill = Skill.load(baseline_skill_path)
                baseline_metrics = await _evaluate_variant(
                    scenario_id=scenario.id,
                    skill_path=skill_path,
                    skill=baseline_skill,
                    tests_path=tests_path,
                    cards_path=cards_path,
                    config=config,
                    model=eval_model,
                    runs=args.runs,
                    artifact_root=artifact_root / scenario.id / "baseline",
                    judge=active_judge,
                    criteria=criteria,
                )
                regression, reasons, deltas = _compare_variants(
                    current=current_metrics,
                    baseline=baseline_metrics,
                    hard_regression_threshold=args.hard_regression_threshold,
                    judge_regression_threshold=args.judge_regression_threshold,
                    token_regression_threshold=args.token_regression_threshold,
                )

            scenario_report = {
                "scenario_id": scenario.id,
                "skill_path": skill_path,
                "tests_path": scenario.tests,
                "criteria": criteria,
                "notes": notes,
                "regression": regression,
                "reasons": reasons,
                "deltas": deltas,
                "current": {
                    "case_success_rate": current_metrics.case_success_rate,
                    "hard_score": current_metrics.hard_score,
                    "assertions_passed": current_metrics.assertions_passed,
                    "assertions_total": current_metrics.assertions_total,
                    "avg_tokens": current_metrics.avg_tokens,
                    "avg_turns": current_metrics.avg_turns,
                    "judge_score": current_metrics.judge_score,
                    "case_details": current_metrics.case_details,
                },
                "baseline": (
                    {
                        "case_success_rate": baseline_metrics.case_success_rate,
                        "hard_score": baseline_metrics.hard_score,
                        "assertions_passed": baseline_metrics.assertions_passed,
                        "assertions_total": baseline_metrics.assertions_total,
                        "avg_tokens": baseline_metrics.avg_tokens,
                        "avg_turns": baseline_metrics.avg_turns,
                        "judge_score": baseline_metrics.judge_score,
                        "case_details": baseline_metrics.case_details,
                    }
                    if baseline_metrics is not None
                    else None
                ),
            }
            report["scenarios"].append(scenario_report)
            report["history_rows"].append(
                {
                    "generated_at": report["generated_at"],
                    "commit_sha": report["commit_sha"],
                    "base_ref": base_ref,
                    "scenario_id": scenario.id,
                    "skill_path": skill_path,
                    "eval_model": eval_model,
                    "runs": args.runs,
                    "hard_score": current_metrics.hard_score,
                    "judge_score": current_metrics.judge_score,
                    "avg_tokens": current_metrics.avg_tokens,
                    "avg_turns": current_metrics.avg_turns,
                    "baseline_hard_score": (
                        baseline_metrics.hard_score if baseline_metrics is not None else None
                    ),
                    "baseline_judge_score": (
                        baseline_metrics.judge_score if baseline_metrics is not None else None
                    ),
                    "baseline_avg_tokens": (
                        baseline_metrics.avg_tokens if baseline_metrics is not None else None
                    ),
                    "regression": regression,
                    "notes": notes,
                    "reasons": reasons,
                }
            )

    return report


def main() -> int:
    args = _parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        report = asyncio.run(_run_suite(args))
    except Exception as exc:
        print(f"upskill CI failed: {exc}", file=sys.stderr)
        return 2

    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown = _render_markdown(report)
    _write_step_summary(markdown)
    print(markdown)

    if args.persist:
        try:
            _persist_history(report, args.history_repo)
        except Exception as exc:
            print(f"failed to persist history: {exc}", file=sys.stderr)
            return 3

    regressions = [scenario for scenario in report["scenarios"] if scenario["regression"]]
    return 1 if regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())
