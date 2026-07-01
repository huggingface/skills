#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = ["markdown-it-py==4.2.0", "pyyaml==6.0.3"]
# ///
"""Build Agent Finder search artifacts for Hugging Face Skills."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from markdown_it import MarkdownIt

SCHEMA_VERSION = 1
SOURCE_REPO = "huggingface/skills"
SOURCE_URL = "https://github.com/huggingface/skills.git"
DEFAULT_INDEX = "hf_skills"
MARKETPLACE_PATH = ".claude-plugin/marketplace-internal.json"
MAX_CHARS = 12_000
OVERLAP_CHARS = 800
MAX_SUPPORTING_CHARS = 200_000
SUPPORTING_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)
NON_ID_RE = re.compile(r"[^a-z0-9]+")
MARKDOWN = MarkdownIt()


@dataclass(frozen=True)
class Section:
    title: str
    heading_path: list[str]
    content: str
    ordinal: int


def run_git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo_root), *args],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def git_value(repo_root: Path, *args: str, default: str) -> str:
    try:
        return run_git(repo_root, *args)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return default


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_skill(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"Frontmatter must be a mapping: {path}")
    return meta, text[match.end() :]


def clean_heading(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def heading_text(inline: Any) -> str:
    if inline is None:
        return ""
    if not inline.children:
        return clean_heading(inline.content)

    parts: list[str] = []
    for child in inline.children:
        if child.type in {"text", "code_inline"}:
            parts.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append(" ")
        elif child.content:
            parts.append(child.content)
    return clean_heading("".join(parts))


def split_sections(body: str, fallback_title: str) -> list[Section]:
    lines = body.splitlines()
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    current_title = fallback_title
    current_path: list[str] = []
    current_start = 0
    ordinal = 0

    def flush(end: int) -> None:
        nonlocal ordinal, current_start
        content = "\n".join(lines[current_start:end]).strip()
        if not content:
            return
        sections.append(
            Section(
                title=current_title,
                heading_path=list(current_path),
                content=content,
                ordinal=ordinal,
            )
        )
        ordinal += 1

    tokens = MARKDOWN.parse(body)
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.map is None:
            continue

        heading_start = token.map[0]
        flush(heading_start)

        level = int(token.tag[1:])
        inline = tokens[index + 1] if index + 1 < len(tokens) else None
        title = heading_text(inline if inline and inline.type == "inline" else None)
        stack = [(depth, text) for depth, text in stack if depth < level]
        stack.append((level, title))
        current_title = title
        current_path = [text for _, text in stack]
        current_start = heading_start

    flush(len(lines))
    return sections


def chunk_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n\n", start, end), text.rfind("\n", start, end))
            if boundary > start + max_chars // 2:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return chunks


def stable_id(rel_path: str, ordinal: int, part: int) -> str:
    source = f"{SOURCE_REPO}-{rel_path}-{ordinal:03d}-{part:03d}".lower()
    return NON_ID_RE.sub("-", source).strip("-")


def stable_skill_id(skill: str) -> str:
    source = f"{SOURCE_REPO}-skill-{skill}".lower()
    return NON_ID_RE.sub("-", source).strip("-")


def github_url(rel_path: str) -> str:
    return f"https://github.com/{SOURCE_REPO}/blob/main/{rel_path}"


def github_skill_url(skill: str) -> str:
    return f"https://github.com/{SOURCE_REPO}/tree/main/skills/{skill}"


def raw_github_url(rel_path: str) -> str:
    return f"https://raw.githubusercontent.com/{SOURCE_REPO}/main/{rel_path}"


def load_marketplace(repo_root: Path) -> dict[str, Any]:
    path = repo_root / MARKETPLACE_PATH
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected object: {MARKETPLACE_PATH}")
    return data


def marketplace_version(marketplace: dict[str, Any]) -> str | None:
    metadata = marketplace.get("metadata")
    if not isinstance(metadata, dict):
        return None
    version = metadata.get("version")
    return version if isinstance(version, str) else None


def marketplace_descriptions(marketplace: dict[str, Any]) -> dict[str, str]:
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list):
        return {}

    descriptions: dict[str, str] = {}
    for plugin in plugins:
        if not isinstance(plugin, dict):
            continue
        name = plugin.get("name")
        description = plugin.get("description")
        if isinstance(name, str) and isinstance(description, str):
            descriptions[name] = description
    return descriptions


def read_supporting_files(skill_dir: Path, repo_root: Path) -> tuple[list[str], str]:
    files: list[str] = []
    chunks: list[str] = []
    total = 0

    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.name == "SKILL.md" or path.suffix.lower() not in SUPPORTING_SUFFIXES:
            continue

        rel_path = path.relative_to(repo_root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        remaining = MAX_SUPPORTING_CHARS - total
        if remaining <= 0:
            break

        text = text.strip()
        if not text:
            continue

        if len(text) > remaining:
            text = text[:remaining].rstrip()

        files.append(rel_path)
        chunks.append(f"# {rel_path}\n\n{text}")
        total += len(text)

    return files, "\n\n".join(chunks)


def build_documents(repo_root: Path, marketplace: dict[str, Any], updated_at: str) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    version = marketplace_version(marketplace)
    descriptions = marketplace_descriptions(marketplace)

    for skill_md in sorted((repo_root / "skills").glob("*/SKILL.md")):
        meta, body = load_skill(skill_md)
        rel_path = skill_md.relative_to(repo_root).as_posix()
        skill = skill_md.parent.name
        skill_name = str(meta.get("name") or skill)
        skill_description = str(meta.get("description") or "")
        marketplace_description = descriptions.get(skill, skill_description)
        skill_meta = {k: v for k, v in meta.items() if k not in {"name", "description"}}
        url = github_url(rel_path)
        raw_url = raw_github_url(rel_path)
        supporting_files, supporting_content = read_supporting_files(skill_md.parent, repo_root)

        text = "\n".join(
            value
            for value in [
                skill_name,
                marketplace_description,
                skill_description,
                rel_path,
                body.strip(),
                supporting_content,
            ]
            if value
        )

        document = {
            "id": stable_skill_id(skill),
            "repo": SOURCE_REPO,
            "skill": skill,
            "skill_name": skill_name,
            "skill_description": skill_description,
            "marketplace_description": marketplace_description,
            "skill_meta": skill_meta,
            "path": rel_path,
            "url": url,
            "raw_url": raw_url,
            "kind": "skill",
            "title": skill_name,
            "heading_path": [],
            "content": body.strip(),
            "supporting_files": supporting_files,
            "supporting_content": supporting_content,
            "text": text,
            "ordinal": 0,
            "part": 0,
            "updated_at": updated_at,
        }
        if version:
            document["version"] = version
        documents.append(document)

        for section in split_sections(body, skill_name):
            for part, content in enumerate(chunk_text(section.content, MAX_CHARS, OVERLAP_CHARS)):
                title = section.title or skill_name
                heading_text = " > ".join(section.heading_path)
                section_text = "\n".join(
                    value
                    for value in [skill_name, rel_path, heading_text, title, content]
                    if value
                )
                section_document = {
                    "id": stable_id(rel_path, section.ordinal, part),
                    "repo": SOURCE_REPO,
                    "skill": skill,
                    "skill_name": skill_name,
                    "skill_description": skill_description,
                    "marketplace_description": marketplace_description,
                    "skill_meta": skill_meta,
                    "path": rel_path,
                    "url": url,
                    "raw_url": raw_url,
                    "kind": "skill_section",
                    "title": title,
                    "heading_path": section.heading_path,
                    "content": content,
                    "supporting_files": [],
                    "supporting_content": "",
                    "text": section_text,
                    "ordinal": section.ordinal,
                    "part": part,
                    "updated_at": updated_at,
                }
                if version:
                    section_document["version"] = version
                documents.append(section_document)

    return documents


def build_catalog(
    documents: list[dict[str, Any]],
    marketplace: dict[str, Any],
    updated_at: str,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    version = marketplace_version(marketplace)
    descriptions = marketplace_descriptions(marketplace)
    for doc in documents:
        skill = doc["skill"]
        if skill in seen:
            continue
        seen.add(skill)
        description = descriptions.get(skill, doc["skill_description"])
        entry = {
            "identifier": github_skill_url(skill),
            "displayName": doc["skill_name"],
            "mediaType": "application/ai-skill",
            "url": doc["url"],
            "description": description,
            "tags": ["huggingface", "skill"],
            "updatedAt": updated_at,
            "metadata": {
                "source": SOURCE_REPO,
                "path": doc["path"],
                "rawUrl": doc["raw_url"],
            },
        }
        if version:
            entry["version"] = version
            entry["tags"].append(f"version:{version}")
        entries.append(entry)

    return {
        "specVersion": "1.0",
        "host": {
            "displayName": "Hugging Face Skills",
            "identifier": f"https://github.com/{SOURCE_REPO}",
            "documentationUrl": "https://github.com/huggingface/skills",
            "logoUrl": "https://huggingface.co/favicon.ico",
        },
        "entries": entries,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_ndjson(path: Path, documents: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n")


def build_artifacts(repo_root: Path, out_dir: Path, branch: str | None) -> None:
    repo_root = repo_root.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    commit = git_value(repo_root, "rev-parse", "HEAD", default="unknown")
    source_branch = branch or git_value(repo_root, "rev-parse", "--abbrev-ref", "HEAD", default="main")
    if source_branch == "HEAD":
        source_branch = branch or "main"

    updated_at = git_value(repo_root, "show", "-s", "--format=%cI", "HEAD", default=utc_now())
    marketplace = load_marketplace(repo_root)
    documents = build_documents(repo_root, marketplace, updated_at)
    generated_at = utc_now()

    write_ndjson(out_dir / "hf-skills.ndjson", documents)
    write_json(out_dir / "ai-catalog.json", build_catalog(documents, marketplace, updated_at))
    write_json(
        out_dir / "manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "source_repo": SOURCE_REPO,
            "source_url": SOURCE_URL,
            "source_branch": source_branch,
            "source_commit": commit,
            "generated_at": generated_at,
            "document_count": len(documents),
            "index": DEFAULT_INDEX,
            "artifacts": {
                "catalog": "ai-catalog.json",
                "documents": "hf-skills.ndjson",
            },
        },
    )
    (out_dir / "_SUCCESS").write_text(generated_at + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="skills repo root")
    parser.add_argument("--out-dir", type=Path, required=True, help="artifact output directory")
    parser.add_argument("--branch", help="source branch name, default from git or main")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_artifacts(args.repo_root, args.out_dir, args.branch)


if __name__ == "__main__":
    main()
