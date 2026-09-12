#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Search Hugging Face benchmark datasets and fetch leaderboard results.

This script is designed to be pipeline-friendly:
  - search benchmark datasets by free text, alias, task, and modality
  - fetch dataset leaderboards in normalized JSON / NDJSON / table form
  - optionally read dataset ids from stdin for chaining

It uses HF_TOKEN automatically when present.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable


BASE_URL = "https://huggingface.co"
DEFAULT_TIMEOUT = 30

ALIASES: dict[str, list[str]] = {
    "ocr": [
        "ocr",
        "olmocr",
        "pdf",
        "image-to-text",
        "screen",
        "screenspot",
        "markdown",
        "text recognition",
    ],
    "coding": [
        "code",
        "coding",
        "software engineering",
        "programming",
        "swe",
        "terminal",
        "patch",
        "bug",
        "cuda",
    ],
    "math": [
        "math",
        "reasoning",
        "gsm8k",
        "mmlu",
        "gpqa",
        "aime",
        "hmmt",
    ],
    "retrieval": [
        "retrieval",
        "search",
        "mteb",
        "arguana",
        "bright",
    ],
    "agents": [
        "agent",
        "agents",
        "terminal",
        "screen",
        "computer use",
        "tool use",
    ],
    "asr": [
        "asr",
        "speech",
        "audio",
        "transcribe",
        "transcription",
    ],
}


class HfApiError(RuntimeError):
    pass


class FullHelpArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._search_parser: argparse.ArgumentParser | None = None
        self._leaderboard_parser: argparse.ArgumentParser | None = None
        self._model_results_parser: argparse.ArgumentParser | None = None

    def format_help(self) -> str:
        text = super().format_help()
        extra_sections: list[str] = []

        if self._search_parser is not None:
            extra_sections.append(
                "\nsearch command options:\n"
                + textwrap.indent(self._search_parser.format_help().strip(), "  ")
            )

        if self._leaderboard_parser is not None:
            extra_sections.append(
                "\nleaderboard command options:\n"
                + textwrap.indent(self._leaderboard_parser.format_help().strip(), "  ")
            )

        if self._model_results_parser is not None:
            extra_sections.append(
                "\nmodel-results command options:\n"
                + textwrap.indent(self._model_results_parser.format_help().strip(), "  ")
            )

        if extra_sections:
            text += "\n" + "\n".join(extra_sections) + "\n"
        return text


def auth_headers() -> dict[str, str]:
    token = os.getenv("HF_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def http_get_json(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{BASE_URL}{path}"
    if params:
        pairs: list[tuple[str, str]] = []
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                for item in value:
                    pairs.append((key, str(item)))
            else:
                pairs.append((key, str(value)))
        if pairs:
            url = f"{url}?{urllib.parse.urlencode(pairs)}"

    req = urllib.request.Request(url, headers=auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HfApiError(f"{exc.code} {exc.reason} for {url}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise HfApiError(f"Request failed for {url}: {exc}") from exc


def shorten(text: str, width: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


def first_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(first_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(first_text(v) for v in value.values())
    return str(value)


def benchmark_catalog(limit: int = 500) -> list[dict[str, Any]]:
    data = http_get_json(
        "/api/datasets",
        params={"filter": "benchmark:official", "limit": limit, "full": "true"},
    )
    if not isinstance(data, list):
        raise HfApiError("Unexpected response while listing benchmark datasets")
    return data


def dataset_search_blob(dataset: dict[str, Any]) -> str:
    card = dataset.get("cardData") or {}
    parts = [
        dataset.get("id", ""),
        dataset.get("description", ""),
        first_text(dataset.get("tags")),
        first_text(card.get("pretty_name")),
        first_text(card.get("tags")),
        first_text(card.get("task_categories")),
        first_text(card.get("task_ids")),
    ]
    return " ".join(parts).lower()


def dataset_search_fields(dataset: dict[str, Any]) -> dict[str, str]:
    card = dataset.get("cardData") or {}
    return {
        "id": first_text(dataset.get("id")).lower(),
        "pretty_name": first_text(card.get("pretty_name")).lower(),
        "tags": " ".join(
            [
                first_text(dataset.get("tags")),
                first_text(card.get("tags")),
                first_text(card.get("task_categories")),
                first_text(card.get("task_ids")),
                first_text(card.get("modality")),
            ]
        ).lower(),
        "description": first_text(dataset.get("description")).lower(),
    }


def collect_prefixed_tags(dataset: dict[str, Any], prefixes: Iterable[str]) -> list[str]:
    prefixes = tuple(prefixes)
    tags = dataset.get("tags") or []
    card = dataset.get("cardData") or {}

    out: list[str] = []
    for tag in tags:
        if isinstance(tag, str) and tag.startswith(prefixes):
            out.append(tag)

    for key, prefix in (
        ("task_categories", "task_categories:"),
        ("task_ids", "task_ids:"),
        ("modality", "modality:"),
    ):
        values = card.get(key)
        if isinstance(values, list):
            for value in values:
                full_tag = f"{prefix}{value}"
                if full_tag.startswith(prefixes):
                    out.append(full_tag)

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in out:
        if tag not in seen:
            deduped.append(tag)
            seen.add(tag)
    return deduped


def expand_aliases(aliases: list[str]) -> dict[str, list[str]]:
    expanded: dict[str, list[str]] = {}
    for alias in aliases:
        terms = ALIASES.get(alias.lower(), [alias])
        expanded[alias] = terms
    return expanded


def matches_term(blob: str, term: str) -> bool:
    candidate = term.lower().strip()
    if not candidate:
        return False
    if re.fullmatch(r"[a-z0-9_]+", candidate):
        return re.search(rf"(?<![a-z0-9_]){re.escape(candidate)}(?![a-z0-9_])", blob) is not None
    return candidate in blob


def score_dataset(
    dataset: dict[str, Any],
    queries: list[str],
    aliases: dict[str, list[str]],
    tasks: list[str],
    modalities: list[str],
) -> dict[str, Any]:
    blob = dataset_search_blob(dataset)
    fields = dataset_search_fields(dataset)
    task_tags = collect_prefixed_tags(dataset, ["task_categories:", "task_ids:"])
    modality_tags = collect_prefixed_tags(dataset, ["modality:"])

    score = 0
    reasons: list[str] = []

    for query in queries:
        q = query.lower().strip()
        if q and any(matches_term(value, q) for value in fields.values()):
            score += 3
            reasons.append(f"query:{query}")

    for alias_name, terms in aliases.items():
        matched_terms: list[str] = []
        alias_score = 0
        for term in terms:
            strong_match = any(
                matches_term(fields[field_name], term)
                for field_name in ("id", "pretty_name", "tags")
            )
            desc_match = matches_term(fields["description"], term)
            if strong_match:
                alias_score += 2
                matched_terms.append(term)
            elif desc_match:
                alias_score += 1
                matched_terms.append(term)
        if matched_terms:
            score += alias_score
            reasons.append(f"alias:{alias_name}=" + ",".join(matched_terms[:5]))

    lower_task_tags = [t.lower() for t in task_tags]
    for task in tasks:
        task = task.lower().strip()
        if not task:
            continue
        exact = [
            tag
            for tag in lower_task_tags
            if tag == f"task_categories:{task}" or tag == f"task_ids:{task}"
        ]
        fuzzy = matches_term(blob, task)
        if exact:
            score += 5
            reasons.append(f"task:{task}")
        elif fuzzy:
            score += 2
            reasons.append(f"task~:{task}")

    lower_modality_tags = [m.lower() for m in modality_tags]
    for modality in modalities:
        modality = modality.lower().strip()
        if not modality:
            continue
        if f"modality:{modality}" in lower_modality_tags:
            score += 4
            reasons.append(f"modality:{modality}")

    return {
        "dataset_id": dataset.get("id"),
        "score": score,
        "reasons": reasons,
        "task_tags": task_tags,
        "modality_tags": modality_tags,
        "benchmark_tags": collect_prefixed_tags(dataset, ["benchmark:"]),
        "pretty_name": (dataset.get("cardData") or {}).get("pretty_name"),
        "downloads": dataset.get("downloads"),
        "description": " ".join((dataset.get("description") or "").split()),
    }


def search_benchmarks(
    queries: list[str],
    aliases: list[str],
    tasks: list[str],
    modalities: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    datasets = benchmark_catalog(limit=500)
    alias_map = expand_aliases(aliases)

    results = [score_dataset(ds, queries, alias_map, tasks, modalities) for ds in datasets]

    active_filters = bool(queries or aliases or tasks or modalities)
    if active_filters:
        results = [row for row in results if row["score"] >= 2]

    results.sort(
        key=lambda row: (
            -row["score"],
            -(row["downloads"] or 0),
            row["dataset_id"] or "",
        )
    )
    return results[:limit]


def parse_repo_id(repo_id: str) -> tuple[str, str]:
    if "/" not in repo_id:
        raise ValueError(f"Expected <namespace>/<repo>, got: {repo_id}")
    namespace, repo = repo_id.split("/", 1)
    return namespace, repo


def get_leaderboard(repo_id: str, task_id: str | None = None) -> list[dict[str, Any]]:
    namespace, repo = parse_repo_id(repo_id)
    params = {"task_id": task_id} if task_id else None
    data = http_get_json(f"/api/datasets/{namespace}/{repo}/leaderboard", params=params)
    if not isinstance(data, list):
        raise HfApiError(f"Unexpected leaderboard response for {repo_id}")

    normalized: list[dict[str, Any]] = []
    for row in data:
        source = row.get("source") or {}
        normalized.append(
            {
                "dataset_id": repo_id,
                "task_id": task_id,
                "rank": row.get("rank"),
                "model_id": row.get("modelId"),
                "value": row.get("value"),
                "verified": row.get("verified"),
                "lower_is_better": row.get("lower_is_better"),
                "filename": row.get("filename"),
                "notes": row.get("notes"),
                "pull_request": row.get("pullRequest"),
                "source_name": source.get("name"),
                "source_url": source.get("url"),
                "source_is_external": source.get("isExternal"),
            }
        )
    return normalized


def get_model_results(model_id: str) -> list[dict[str, Any]]:
    namespace, repo = parse_repo_id(model_id)
    data = http_get_json(
        f"/api/models/{namespace}/{repo}",
        params={"expand[]": "evalResults"},
    )
    if not isinstance(data, dict):
        raise HfApiError(f"Unexpected model response for {model_id}")

    eval_results = data.get("evalResults") or []
    if not isinstance(eval_results, list):
        raise HfApiError(f"Unexpected evalResults payload for {model_id}")

    normalized: list[dict[str, Any]] = []
    for row in eval_results:
        payload = row.get("data") or {}
        dataset = payload.get("dataset") or {}
        source = payload.get("source") or {}
        normalized.append(
            {
                "model_id": model_id,
                "dataset_id": dataset.get("id"),
                "task_id": dataset.get("task_id"),
                "value": payload.get("value"),
                "date": payload.get("date"),
                "verified": row.get("verified"),
                "filename": row.get("filename"),
                "notes": payload.get("notes"),
                "pull_request": row.get("pullRequest"),
                "source_name": source.get("name"),
                "source_url": source.get("url"),
            }
        )
    return normalized


def read_repo_ids_from_stdin(*, json_keys: Iterable[str]) -> list[str]:
    if sys.stdin.isatty():
        return []

    key_list = list(json_keys)
    repo_ids: list[str] = []
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            candidate = None
            for key in key_list:
                value = obj.get(key)
                if isinstance(value, str) and "/" in value:
                    candidate = value
                    break
            if isinstance(candidate, str) and "/" in candidate:
                repo_ids.append(candidate)
            continue
        if "/" in line:
            repo_ids.append(line)
    return repo_ids


def print_json(data: Any) -> None:
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def print_ndjson(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        sys.stdout.write(json.dumps(row, ensure_ascii=False) + "\n")


def print_search_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No benchmark datasets matched.")
        return

    headers = ["dataset_id", "score", "modalities", "tasks", "reasons", "description"]
    widths = [34, 5, 18, 24, 30, 68]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        values = [
            shorten(row.get("dataset_id") or "", widths[0]),
            str(row.get("score", "")),
            shorten(", ".join(row.get("modality_tags") or []), widths[2]),
            shorten(", ".join(row.get("task_tags") or []), widths[3]),
            shorten(", ".join(row.get("reasons") or []), widths[4]),
            shorten(row.get("description") or "", widths[5]),
        ]
        print("  ".join(v.ljust(w) for v, w in zip(values, widths)))


def print_leaderboard_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No leaderboard rows returned.")
        return

    headers = ["dataset_id", "rank", "model_id", "value", "verified", "source"]
    widths = [30, 5, 38, 10, 8, 28]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        values = [
            shorten(str(row.get("dataset_id") or ""), widths[0]),
            str(row.get("rank") or ""),
            shorten(str(row.get("model_id") or ""), widths[2]),
            shorten(str(row.get("value") or ""), widths[3]),
            str(row.get("verified")),
            shorten(str(row.get("source_name") or ""), widths[5]),
        ]
        print("  ".join(v.ljust(w) for v, w in zip(values, widths)))


def print_model_results_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No model eval rows returned.")
        return

    headers = ["model_id", "dataset_id", "task_id", "value", "date", "verified"]
    widths = [34, 30, 22, 10, 12, 8]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        values = [
            shorten(str(row.get("model_id") or ""), widths[0]),
            shorten(str(row.get("dataset_id") or ""), widths[1]),
            shorten(str(row.get("task_id") or ""), widths[2]),
            shorten(str(row.get("value") or ""), widths[3]),
            shorten(str(row.get("date") or ""), widths[4]),
            str(row.get("verified")),
        ]
        print("  ".join(v.ljust(w) for v, w in zip(values, widths)))


def build_parser() -> argparse.ArgumentParser:
    parser = FullHelpArgumentParser(
        prog="hf_benchmarks.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """
            Search benchmark datasets and fetch leaderboard results from the Hugging Face Hub.

            Workflow ideas:
              1) Discover candidate benchmarks:
                   hf_benchmarks.py search --alias ocr
                   hf_benchmarks.py search --alias coding
                   hf_benchmarks.py search --task image-to-text --modality document

              2) Inspect a leaderboard:
                   hf_benchmarks.py leaderboard allenai/olmOCR-bench --top 10

              3) Chain search -> leaderboard:
                   hf_benchmarks.py search --alias coding --format ndjson \\
                     | hf_benchmarks.py leaderboard --stdin --top 5 --format table

              4) Fetch eval results for a list of models:
                   printf '%s\\n' Qwen/Qwen3.5-9B microsoft/Phi-3-medium-4k-instruct \\
                     | hf_benchmarks.py model-results --stdin --format ndjson

              5) Use hf CLI for model discovery, then enrich with this tool:
                   hf models list --search 'Phi-3' --filter eval-results --limit 5 --format json \\
                     | jq -r '.[].id' \\
                     | hf_benchmarks.py model-results --stdin --format table

              6) Use hf CLI for dataset discovery, then fetch leaderboards:
                   hf datasets list --search 'swe' --filter benchmark:official --limit 5 --format json \\
                     | jq -r '.[].id' \\
                     | hf_benchmarks.py leaderboard --stdin --top 5 --format table
            """
        ),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser(
        "search",
        help="Search benchmark datasets by query, alias, task, and modality",
    )
    search_parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Free-text query to match against benchmark dataset metadata. Repeatable.",
    )
    search_parser.add_argument(
        "--alias",
        action="append",
        default=[],
        help=(
            "Convenience alias for common benchmark domains. Known aliases: "
            + ", ".join(sorted(ALIASES))
            + ". Repeatable."
        ),
    )
    search_parser.add_argument(
        "--task",
        action="append",
        default=[],
        help="Task to match, e.g. text-generation, image-to-text, question-answering. Repeatable.",
    )
    search_parser.add_argument(
        "--modality",
        action="append",
        default=[],
        help="Modality to match, e.g. text, image, document, audio. Repeatable.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of rows to print (default: 20).",
    )
    search_parser.add_argument(
        "--format",
        choices=["table", "json", "ndjson"],
        default="table",
        help="Output format (default: table).",
    )

    leaderboard_parser = subparsers.add_parser(
        "leaderboard",
        help="Fetch normalized leaderboard rows for one or more benchmark datasets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """
            Fetch normalized leaderboard rows for one or more benchmark datasets.

            This command is designed to pair well with `hf datasets list`, where
            `hf` handles benchmark dataset discovery and this tool handles
            leaderboard retrieval / flattening.
            """
        ),
        epilog=textwrap.dedent(
            """
            Examples:
              hf_benchmarks.py leaderboard allenai/olmOCR-bench --top 10

              printf '%s\\n' openai/gsm8k SWE-bench/SWE-bench_Verified \\
                | hf_benchmarks.py leaderboard --stdin --top 5 --format ndjson

              hf datasets list --search 'swe' --filter benchmark:official --limit 5 --format json \\
                | jq -r '.[].id' \\
                | hf_benchmarks.py leaderboard --stdin --top 5 --format table
            """
        ),
    )
    leaderboard_parser.add_argument(
        "datasets",
        nargs="*",
        help="Dataset repo ids (<namespace>/<repo>). Can also be supplied via stdin with --stdin.",
    )
    leaderboard_parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read dataset ids from stdin. Accepts plain repo ids or NDJSON with dataset_id/id fields.",
    )
    leaderboard_parser.add_argument(
        "--task-id",
        default=None,
        help="Optional leaderboard task_id query parameter.",
    )
    leaderboard_parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Only keep the top N results per leaderboard.",
    )
    leaderboard_parser.add_argument(
        "--format",
        choices=["table", "json", "ndjson"],
        default="table",
        help="Output format (default: table).",
    )

    model_results_parser = subparsers.add_parser(
        "model-results",
        help="Fetch normalized evalResults rows for one or more models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """
            Fetch normalized evalResults rows for one or more model repos.

            This command is designed to pair well with `hf models list`, where
            `hf` handles discovery and this tool handles flattening / filtering
            per-model benchmark results.
            """
        ),
        epilog=textwrap.dedent(
            """
            Examples:
              hf_benchmarks.py model-results Qwen/Qwen3.5-9B

              printf '%s\\n' Qwen/Qwen3.5-9B microsoft/Phi-3-medium-4k-instruct \\
                | hf_benchmarks.py model-results --stdin --format ndjson

              hf models list --search 'Phi-3' --filter eval-results --limit 5 --format json \\
                | jq -r '.[].id' \\
                | hf_benchmarks.py model-results --stdin --dataset openai/gsm8k --format table
            """
        ),
    )
    model_results_parser.add_argument(
        "models",
        nargs="*",
        help="Model repo ids (<namespace>/<repo>). Can also be supplied via stdin with --stdin.",
    )
    model_results_parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read model ids from stdin. Accepts plain repo ids or NDJSON with model_id/id fields.",
    )
    model_results_parser.add_argument(
        "--dataset",
        action="append",
        default=[],
        help="Only keep eval rows whose dataset_id matches one of these values. Repeatable.",
    )
    model_results_parser.add_argument(
        "--task-id",
        action="append",
        default=[],
        help="Only keep eval rows whose task_id matches one of these values. Repeatable.",
    )
    model_results_parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Only keep the top N eval rows per model after filtering.",
    )
    model_results_parser.add_argument(
        "--format",
        choices=["table", "json", "ndjson"],
        default="table",
        help="Output format (default: table).",
    )

    parser._search_parser = search_parser
    parser._leaderboard_parser = leaderboard_parser
    parser._model_results_parser = model_results_parser

    return parser


def run_search(args: argparse.Namespace) -> int:
    rows = search_benchmarks(
        queries=args.query,
        aliases=args.alias,
        tasks=args.task,
        modalities=args.modality,
        limit=args.limit,
    )

    if args.format == "json":
        print_json(rows)
    elif args.format == "ndjson":
        print_ndjson(rows)
    else:
        print_search_table(rows)
    return 0


def run_leaderboard(args: argparse.Namespace) -> int:
    repo_ids = list(args.datasets)
    if args.stdin:
        repo_ids.extend(read_repo_ids_from_stdin(json_keys=["dataset_id", "id"]))

    deduped: list[str] = []
    seen: set[str] = set()
    for repo_id in repo_ids:
        if repo_id not in seen:
            deduped.append(repo_id)
            seen.add(repo_id)
    repo_ids = deduped

    if not repo_ids:
        print("Error: provide dataset ids or use --stdin.", file=sys.stderr)
        return 2

    rows: list[dict[str, Any]] = []
    for repo_id in repo_ids:
        dataset_rows = get_leaderboard(repo_id, task_id=args.task_id)
        if args.top is not None:
            dataset_rows = dataset_rows[: args.top]
        rows.extend(dataset_rows)

    if args.format == "json":
        print_json(rows)
    elif args.format == "ndjson":
        print_ndjson(rows)
    else:
        print_leaderboard_table(rows)
    return 0


def run_model_results(args: argparse.Namespace) -> int:
    model_ids = list(args.models)
    if args.stdin:
        model_ids.extend(read_repo_ids_from_stdin(json_keys=["model_id", "id"]))

    deduped: list[str] = []
    seen: set[str] = set()
    for model_id in model_ids:
        if model_id not in seen:
            deduped.append(model_id)
            seen.add(model_id)
    model_ids = deduped

    if not model_ids:
        print("Error: provide model ids or use --stdin.", file=sys.stderr)
        return 2

    dataset_filters = set(args.dataset or [])
    task_filters = set(args.task_id or [])

    rows: list[dict[str, Any]] = []
    for model_id in model_ids:
        model_rows = get_model_results(model_id)
        if dataset_filters:
            model_rows = [row for row in model_rows if row.get("dataset_id") in dataset_filters]
        if task_filters:
            model_rows = [row for row in model_rows if row.get("task_id") in task_filters]
        if args.top is not None:
            model_rows = model_rows[: args.top]
        rows.extend(model_rows)

    if args.format == "json":
        print_json(rows)
    elif args.format == "ndjson":
        print_ndjson(rows)
    else:
        print_model_results_table(rows)
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "search":
            return run_search(args)
        if args.command == "leaderboard":
            return run_leaderboard(args)
        if args.command == "model-results":
            return run_model_results(args)
        parser.error(f"Unknown command: {args.command}")
        return 2
    except HfApiError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
