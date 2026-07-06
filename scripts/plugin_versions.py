#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Manage plugin/extension manifest versions."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

VERSION_PATHS = [
    (ROOT / ".claude-plugin" / "plugin.json", ("version",)),
    (ROOT / ".claude-plugin" / "marketplace.json", ("metadata", "version")),
    (ROOT / ".claude-plugin" / "marketplace-internal.json", ("metadata", "version")),
    (ROOT / ".cursor-plugin" / "plugin.json", ("version",)),
    (ROOT / ".cursor-plugin" / "marketplace.json", ("metadata", "version")),
    (ROOT / "gemini-extension.json", ("version",)),
]

BUMP_RELEVANT_PATHS = (
    "skills/",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".claude-plugin/marketplace-internal.json",
    ".cursor-plugin/marketplace.json",
    "gemini-extension.json",
    "scripts/AGENTS_TEMPLATE.md",
    "scripts/generate_agents.py",
    "scripts/generate_cursor_plugin.py",
    "scripts/publish.sh",
)

GENERATED_PATHS = (
    "agentsmd/AGENTS.md",
    "README.md",
    ".claude-plugin/marketplace-internal.json",
    ".cursor-plugin/plugin.json",
    ".mcp.json",
)

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def get_nested(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            raise KeyError(".".join(keys))
        cur = cur[key]
    return cur


def set_nested(data: dict[str, Any], keys: tuple[str, ...], value: str) -> None:
    cur: Any = data
    for key in keys[:-1]:
        if key not in cur or not isinstance(cur[key], dict):
            cur[key] = {}
        cur = cur[key]
    cur[keys[-1]] = value


def read_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for path, keys in VERSION_PATHS:
        if not path.exists():
            continue
        value = get_nested(load_json(path), keys)
        if not isinstance(value, str):
            raise TypeError(f"{rel(path)} {'.'.join(keys)} must be a string")
        versions[f"{rel(path)}:{'.'.join(keys)}"] = value
    return versions


def canonical_version() -> str:
    return get_nested(load_json(ROOT / ".claude-plugin" / "plugin.json"), ("version",))


def parse_semver(version: str) -> tuple[int, int, int]:
    match = SEMVER_RE.match(version)
    if not match:
        raise ValueError(f"Expected semantic version MAJOR.MINOR.PATCH, got: {version}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_version(version: str, part: str) -> str:
    major, minor, patch = parse_semver(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if not SEMVER_RE.match(part):
        raise ValueError(f"Bump must be major, minor, patch, or explicit semver; got: {part}")
    return part


def set_all_versions(version: str) -> None:
    parse_semver(version)
    for path, keys in VERSION_PATHS:
        if not path.exists():
            continue
        data = load_json(path)
        set_nested(data, keys, version)
        write_json(path, data)


def check_versions() -> int:
    versions = read_versions()
    bad_semver = [f"{where}={version}" for where, version in versions.items() if not SEMVER_RE.match(version)]
    if bad_semver:
        print("Manifest versions must be semantic versions:", file=sys.stderr)
        for item in bad_semver:
            print(f"  - {item}", file=sys.stderr)
        return 1

    unique = sorted(set(versions.values()))
    if len(unique) > 1:
        print("Plugin/extension manifest versions are out of sync:", file=sys.stderr)
        for where, version in versions.items():
            print(f"  - {where} = {version}", file=sys.stderr)
        print("Run: uv run scripts/plugin_versions.py bump patch", file=sys.stderr)
        return 1

    print(f"Plugin manifest versions are in sync: {unique[0] if unique else 'none'}")
    return 0


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def git_lines(*args: str) -> list[str]:
    out = git(*args)
    return [line for line in out.splitlines() if line]


def changed_paths(base_ref: str, include_worktree: bool = False) -> list[str]:
    paths = set(git_lines("diff", "--name-only", f"{base_ref}...HEAD"))
    if include_worktree:
        paths.update(git_lines("diff", "--name-only"))
        paths.update(git_lines("diff", "--cached", "--name-only"))
        paths.update(git_lines("ls-files", "--others", "--exclude-standard"))
    return sorted(paths)


def requires_bump(path: str) -> bool:
    if path in GENERATED_PATHS:
        return False
    return path in BUMP_RELEVANT_PATHS or any(path.startswith(prefix) for prefix in BUMP_RELEVANT_PATHS if prefix.endswith("/"))


def version_at(ref: str) -> str | None:
    try:
        text = git("show", f"{ref}:.claude-plugin/plugin.json")
    except subprocess.CalledProcessError:
        return None
    data = json.loads(text)
    value = get_nested(data, ("version",))
    return value if isinstance(value, str) else None


def check_bump(base_ref: str) -> int:
    relevant = [path for path in changed_paths(base_ref) if requires_bump(path)]
    if not relevant:
        print("No version-relevant published content changed.")
        return 0

    before = version_at(base_ref)
    after = canonical_version()
    if before is None:
        print(f"Version bumped: {before} -> {after}")
        return 0

    try:
        before_semver = parse_semver(before)
        after_semver = parse_semver(after)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if after_semver > before_semver:
        print(f"Version bumped: {before} -> {after}")
        return 0

    print("Published plugin content changed without an increased version:", file=sys.stderr)
    print(f"  - version: {before} -> {after}", file=sys.stderr)
    for path in relevant:
        print(f"  - {path}", file=sys.stderr)
    print("Run: uv run scripts/plugin_versions.py bump patch && ./scripts/publish.sh", file=sys.stderr)
    return 1


def bump_if_needed(base_ref: str, part: str = "patch") -> int:
    relevant = [path for path in changed_paths(base_ref, include_worktree=True) if requires_bump(path)]
    if not relevant:
        print("No version-relevant published content changed; version unchanged.")
        return 0

    before = version_at(base_ref)
    after = canonical_version()
    if before is None:
        print("Base manifest version not found; version unchanged.")
        return 0

    try:
        before_semver = parse_semver(before)
        after_semver = parse_semver(after)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if after_semver > before_semver:
        print(f"Version already bumped: {before} -> {after}")
        return 0

    next_version = bump_version(before, part)
    set_all_versions(next_version)
    print(f"Version bumped: {before} -> {next_version}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="Check that all manifest versions are valid and in sync")

    bump = sub.add_parser("bump", help="Bump or set all manifest versions")
    bump.add_argument("part", choices=["major", "minor", "patch"], nargs="?", default="patch")
    bump.add_argument("--set", dest="set_version", help="Set an explicit semantic version")

    changed = sub.add_parser("check-bump", help="Require a version bump when published content changed")
    changed.add_argument("base_ref")

    auto = sub.add_parser("bump-if-needed", help="Bump manifest versions when published content changed")
    auto.add_argument("base_ref")
    auto.add_argument("part", choices=["major", "minor", "patch"], nargs="?", default="patch")

    args = parser.parse_args()

    if args.cmd == "check":
        raise SystemExit(check_versions())
    if args.cmd == "check-bump":
        raise SystemExit(check_bump(args.base_ref))
    if args.cmd == "bump-if-needed":
        raise SystemExit(bump_if_needed(args.base_ref, args.part))
    if args.cmd == "bump":
        version = args.set_version or bump_version(canonical_version(), args.part)
        set_all_versions(version)
        print(f"Set plugin manifest versions to {version}")
        return


if __name__ == "__main__":
    main()
