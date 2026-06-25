#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml==6.0.3"]
# ///
"""Build static skills distribution artifacts (SEP-2640 index format).

Single-file skills are emitted as ``<out>/<name>/SKILL.md`` for easy audit.
Multi-file skills are emitted as ``<out>/<name>.tar.gz`` archives to keep the
skill package atomic and avoid implying partial direct-resource support. The
``index.json`` follows SEP-2640: each entry carries verbatim ``frontmatter`` plus
either ``url`` + ``digest`` for direct ``SKILL.md`` entries, or an ``archives``
array for archive-only entries.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import shutil
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)
SKILL_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
IGNORE_DIRS = {"node_modules"}
IGNORE_FILES = {".DS_Store"}
SOURCE_REPO = "huggingface/skills"
ARCHIVE_MEDIA_TYPE = "application/gzip"


@dataclass(frozen=True)
class Skill:
	name: str
	description: str
	frontmatter: dict[str, Any]
	dir: Path
	files: list[Path]


def utc_now() -> str:
	return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_skill_md(path: Path) -> dict[str, Any]:
	text = path.read_text(encoding="utf-8")
	match = FRONTMATTER_RE.match(text)
	if not match:
		raise ValueError(f"{path} must start with YAML frontmatter")
	meta = yaml.safe_load(match.group(1)) or {}
	if not isinstance(meta, dict):
		raise ValueError(f"{path} frontmatter must be a mapping")
	return meta


def validate_skill_name(name: str, skill_dir: Path) -> None:
	if not SKILL_NAME_RE.fullmatch(name) or "--" in name:
		raise ValueError(f"{skill_dir}: invalid skill name {name!r}")
	if name != skill_dir.name:
		raise ValueError(f"{skill_dir}: SKILL.md name {name!r} must match directory name")


def rel_archive_path(skill_dir: Path, path: Path) -> str:
	rel = path.relative_to(skill_dir).as_posix()
	if rel.startswith("/") or ".." in rel.split("/"):
		raise ValueError(f"{path}: unsafe archive path {rel!r}")
	return rel


def discover_files(skill_dir: Path) -> list[Path]:
	files: list[Path] = []
	for path in sorted(skill_dir.rglob("*")):
		rel_parts = path.relative_to(skill_dir).parts
		if any(part in IGNORE_DIRS for part in rel_parts):
			continue
		if path.name in IGNORE_FILES:
			continue
		if path.is_symlink():
			continue
		if path.is_file():
			rel_archive_path(skill_dir, path)
			files.append(path)
	return files


def load_skills(skills_dir: Path) -> list[Skill]:
	skills: list[Skill] = []
	for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
		meta = parse_skill_md(skill_md)
		name = meta.get("name")
		description = meta.get("description")
		if not isinstance(name, str) or not name:
			raise ValueError(f"{skill_md}: missing required name")
		if not isinstance(description, str) or not description.strip():
			raise ValueError(f"{skill_md}: missing required description")
		validate_skill_name(name, skill_md.parent)
		files = discover_files(skill_md.parent)
		if skill_md not in files:
			raise ValueError(f"{skill_md}: SKILL.md was not included in discovered files")
		skills.append(
			Skill(
				name=name,
				description=description.strip(),
				frontmatter=meta,
				dir=skill_md.parent,
				files=files,
			)
		)
	return skills


def sha256_hex(path: Path) -> str:
	h = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			h.update(chunk)
	return h.hexdigest()


def write_skill_md(skill: Skill, out_dir: Path) -> Path:
	target_dir = out_dir / skill.name
	target_dir.mkdir(parents=True, exist_ok=True)
	target = target_dir / "SKILL.md"
	shutil.copyfile(skill.dir / "SKILL.md", target)
	return target


def tar_info(name: str, data: bytes, mode: int) -> tarfile.TarInfo:
	info = tarfile.TarInfo(name)
	info.size = len(data)
	info.mtime = 0
	info.mode = mode
	info.uid = 0
	info.gid = 0
	info.uname = ""
	info.gname = ""
	return info


def write_archive(skill: Skill, out_dir: Path) -> Path:
	target = out_dir / f"{skill.name}.tar.gz"
	with target.open("wb") as raw:
		with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
			with tarfile.open(fileobj=gz, mode="w") as tar:
				for path in skill.files:
					rel = rel_archive_path(skill.dir, path)
					data = path.read_bytes()
					tar.addfile(
						tar_info(rel, data, path.stat().st_mode & 0o777),
						fileobj=io.BytesIO(data),
					)
	return target


def uri_join(prefix: str, path: str) -> str:
	if prefix.endswith("://"):
		return prefix + path
	return prefix.rstrip("/") + "/" + path


def build_distribution(skills_dir: Path, out_dir: Path, uri_prefix: str) -> None:
	if out_dir.exists():
		shutil.rmtree(out_dir)
	out_dir.mkdir(parents=True)

	skills = load_skills(skills_dir)
	index_entries: list[dict[str, Any]] = []
	catalog_entries: list[dict[str, Any]] = []

	for skill in skills:
		if len(skill.files) == 1 and skill.files[0].name == "SKILL.md":
			skill_md_path = write_skill_md(skill, out_dir)
			skill_md_url = uri_join(uri_prefix, f"{skill.name}/SKILL.md")
			skill_md_digest = f"sha256:{sha256_hex(skill_md_path)}"

			index_entries.append(
				{
					"url": skill_md_url,
					"digest": skill_md_digest,
					"frontmatter": skill.frontmatter,
				}
			)
			catalog_url = skill_md_url
			catalog_media_type = "text/markdown"
			catalog_digest = skill_md_digest
			catalog_path = f"skills/{skill.name}/SKILL.md"
		else:
			archive_path = write_archive(skill, out_dir)
			archive_url = uri_join(uri_prefix, f"{skill.name}.tar.gz")
			archive_digest = f"sha256:{sha256_hex(archive_path)}"

			index_entries.append(
				{
					"frontmatter": skill.frontmatter,
					"archives": [
						{
							"url": archive_url,
							"mimeType": ARCHIVE_MEDIA_TYPE,
							"digest": archive_digest,
						}
					],
				}
			)
			catalog_url = archive_url
			catalog_media_type = ARCHIVE_MEDIA_TYPE
			catalog_digest = archive_digest
			catalog_path = f"skills/{skill.name}.tar.gz"

		catalog_entries.append(
			{
				"identifier": f"urn:huggingface:skill:{skill.name}",
				"displayName": skill.name,
				"mediaType": catalog_media_type,
				"url": catalog_url,
				"description": skill.description,
				"tags": ["huggingface", "skill"],
				"metadata": {
					"digest": catalog_digest,
					"source": SOURCE_REPO,
					"path": catalog_path,
				},
			}
		)

	generated_at = utc_now()
	write_json(out_dir / "index.json", {"skills": index_entries})
	write_json(
		out_dir / "ai-catalog.json",
		{
			"specVersion": "1.0",
			"host": {
				"displayName": "Hugging Face Skills",
				"identifier": f"https://github.com/{SOURCE_REPO}",
				"documentationUrl": f"https://github.com/{SOURCE_REPO}",
				"logoUrl": "https://huggingface.co/favicon.ico",
			},
			"entries": catalog_entries,
		},
	)
	write_json(
		out_dir / "manifest.json",
		{
			"schema_version": 1,
			"generated_at": generated_at,
			"source_repo": SOURCE_REPO,
			"skill_count": len(skills),
			"uri_prefix": uri_prefix,
			"artifacts": {
				"skills_index": "index.json",
				"ai_catalog": "ai-catalog.json",
			},
		},
	)
	(out_dir / "_SUCCESS").write_text(generated_at + "\n", encoding="utf-8")


def write_json(path: Path, value: dict[str, Any]) -> None:
	path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--skills-dir", type=Path, default=Path("skills"), help="directory containing skill subdirectories")
	parser.add_argument("--out-dir", type=Path, required=True, help="distribution output directory")
	parser.add_argument("--uri-prefix", default="skill://", help="URI prefix used in generated indexes")
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	build_distribution(args.skills_dir.resolve(), args.out_dir.resolve(), args.uri_prefix)


if __name__ == "__main__":
	main()
