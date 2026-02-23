#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Skill Dependency Resolver and Validator.

Implements automated skill dependency resolution for the skills framework.
Validates skill schemas, resolves dependencies, and generates dependency graphs.

Usage:
    uv run scripts/skill_resolver.py validate --skill <name>
    uv run scripts/skill_resolver.py check-deps
    uv run scripts/skill_resolver.py graph
    uv run scripts/skill_resolver.py resolve --skill <name>
    uv run scripts/skill_resolver.py tools --skill <name>
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None


ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"


@dataclass
class ToolParameter:
    name: str
    type: str = "string"
    required: bool = False
    default: Any = None
    description: str = ""


@dataclass
class ToolDefinition:
    name: str
    category: str
    description: str
    command: str = ""
    parameters: list[ToolParameter] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


@dataclass
class SkillDependency:
    name: str
    required: bool = True
    reason: str = ""
    auto_load: bool = False


@dataclass
class PackageDependency:
    name: str
    version: str = ""
    install: str = ""


@dataclass
class EnvironmentRequirement:
    name: str
    required: bool = True
    description: str = ""


@dataclass
class SkillMeta:
    """Parsed skill metadata from frontmatter."""

    name: str
    description: str
    version: str = "1.0.0"
    path: Path = None
    tools: list[ToolDefinition] = field(default_factory=list)
    dependencies: dict[str, list] = field(default_factory=dict)
    prerequisites: dict[str, list] = field(default_factory=dict)
    performance: dict[str, Any] = field(default_factory=dict)
    raw_frontmatter: dict[str, Any] = field(default_factory=dict)


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse YAML frontmatter from skill markdown."""
    match = re.search(r"^---\s*\n(.*?)\n---\s*", text, re.DOTALL)
    if not match:
        return {}

    frontmatter_text = match.group(1)

    if yaml:
        try:
            return yaml.safe_load(frontmatter_text) or {}
        except yaml.YAMLError:
            pass

    data: dict[str, Any] = {}
    for line in frontmatter_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip("\"'")
    return data


def parse_tool(tool_data: dict[str, Any]) -> ToolDefinition:
    """Parse a tool definition from frontmatter."""
    params = []
    for p in tool_data.get("parameters", []):
        params.append(
            ToolParameter(
                name=p.get("name", ""),
                type=p.get("type", "string"),
                required=p.get("required", False),
                default=p.get("default"),
                description=p.get("description", ""),
            )
        )

    return ToolDefinition(
        name=tool_data.get("name", ""),
        category=tool_data.get("category", "cli"),
        description=tool_data.get("description", ""),
        command=tool_data.get("command", ""),
        parameters=params,
        examples=tool_data.get("examples", []),
        aliases=tool_data.get("aliases", []),
    )


def parse_skill(skill_path: Path) -> SkillMeta | None:
    """Parse a skill directory and extract metadata."""
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return None

    content = skill_md.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(content)

    if not frontmatter.get("name"):
        return None

    tools = []
    for tool_data in frontmatter.get("tools", []):
        tools.append(parse_tool(tool_data))

    deps = frontmatter.get("dependencies", {})
    if isinstance(deps, dict):
        parsed_deps = {
            "skills": [
                SkillDependency(
                    name=d.get("name", ""),
                    required=d.get("required", True),
                    reason=d.get("reason", ""),
                    auto_load=d.get("auto_load", False),
                )
                for d in deps.get("skills", [])
            ],
            "packages": [
                PackageDependency(
                    name=p.get("name", ""),
                    version=p.get("version", ""),
                    install=p.get("install", ""),
                )
                for p in deps.get("packages", [])
            ],
            "environment": [
                EnvironmentRequirement(
                    name=e.get("name", ""),
                    required=e.get("required", True),
                    description=e.get("description", ""),
                )
                for e in deps.get("environment", [])
            ],
        }
    else:
        parsed_deps = {"skills": [], "packages": [], "environment": []}

    return SkillMeta(
        name=frontmatter.get("name", ""),
        description=frontmatter.get("description", ""),
        version=frontmatter.get("version", "1.0.0"),
        path=skill_path,
        tools=tools,
        dependencies=parsed_deps,
        prerequisites=frontmatter.get("prerequisites", {}),
        performance=frontmatter.get("performance", {}),
        raw_frontmatter=frontmatter,
    )


def collect_all_skills() -> dict[str, SkillMeta]:
    """Collect and parse all skills."""
    skills = {}
    for skill_dir in SKILLS_DIR.iterdir():
        if skill_dir.is_dir():
            meta = parse_skill(skill_dir)
            if meta:
                skills[meta.name] = meta
    return skills


def validate_skill(skill_name: str, skills: dict[str, SkillMeta]) -> list[str]:
    """Validate a single skill's schema and dependencies."""
    errors = []

    if skill_name not in skills:
        return [f"Skill '{skill_name}' not found"]

    skill = skills[skill_name]

    for dep in skill.dependencies.get("skills", []):
        if dep.name not in skills:
            errors.append(
                f"Missing dependency: '{dep.name}' required by '{skill_name}'"
            )

    for env in skill.dependencies.get("environment", []):
        if env.required:
            import os

            if not os.environ.get(env.name):
                errors.append(f"Missing required environment variable: {env.name}")

    for tool in skill.tools:
        if not tool.name:
            errors.append(f"Tool missing 'name' in skill '{skill_name}'")
        if not tool.category:
            errors.append(
                f"Tool '{tool.name}' missing 'category' in skill '{skill_name}'"
            )

    return errors


def check_all_dependencies(skills: dict[str, SkillMeta]) -> dict[str, list[str]]:
    """Check dependencies for all skills."""
    results = {}
    for skill_name in skills:
        errors = validate_skill(skill_name, skills)
        if errors:
            results[skill_name] = errors
    return results


def detect_circular_dependencies(skills: dict[str, SkillMeta]) -> list[list[str]]:
    """Detect circular dependency chains."""
    cycles = []

    def dfs(skill_name: str, visited: set[str], path: list[str]) -> None:
        if skill_name in path:
            cycle_start = path.index(skill_name)
            cycles.append(path[cycle_start:] + [skill_name])
            return

        if skill_name in visited:
            return

        visited.add(skill_name)
        path.append(skill_name)

        skill = skills.get(skill_name)
        if skill:
            for dep in skill.dependencies.get("skills", []):
                if dep.name in skills:
                    dfs(dep.name, visited, path.copy())

    for skill_name in skills:
        dfs(skill_name, set(), [])

    return cycles


def generate_dependency_graph(skills: dict[str, SkillMeta]) -> str:
    """Generate a Mermaid dependency graph."""
    lines = ["graph TD"]

    for skill_name, skill in skills.items():
        safe_name = skill_name.replace("-", "_")

        for dep in skill.dependencies.get("skills", []):
            if dep.name in skills:
                dep_safe = dep.name.replace("-", "_")
                style = " -->|" if dep.required else " -.->|"
                label = "required|" if dep.required else "optional|"
                auto = " (auto)" if dep.auto_load else ""
                lines.append(f"    {dep_safe}{style}{label}{auto} {safe_name}")

    return "\n".join(lines)


def resolve_skill_dependencies(
    skill_name: str,
    skills: dict[str, SkillMeta],
    resolved: set[str] | None = None,
    unresolved: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Resolve skill dependencies in topological order.

    Returns (resolution_order, missing_dependencies).
    """
    if resolved is None:
        resolved = set()
    if unresolved is None:
        unresolved = set()

    missing = []
    order = []

    if skill_name in unresolved:
        return [], [f"Circular dependency detected: {skill_name}"]

    if skill_name in resolved:
        return [], []

    if skill_name not in skills:
        return [], [f"Skill not found: {skill_name}"]

    unresolved.add(skill_name)
    skill = skills[skill_name]

    for dep in skill.dependencies.get("skills", []):
        if dep.required or dep.auto_load:
            dep_order, dep_missing = resolve_skill_dependencies(
                dep.name, skills, resolved, unresolved
            )
            order.extend(dep_order)
            missing.extend(dep_missing)

    unresolved.remove(skill_name)
    resolved.add(skill_name)
    order.append(skill_name)

    return order, missing


def get_tools_for_skill(
    skill_name: str, skills: dict[str, SkillMeta]
) -> list[ToolDefinition]:
    """Get all tools available for a skill, including from dependencies."""
    all_tools = []
    resolved = set()

    def collect_tools(name: str) -> None:
        if name in resolved or name not in skills:
            return
        resolved.add(name)

        skill = skills[name]
        for dep in skill.dependencies.get("skills", []):
            if dep.auto_load:
                collect_tools(dep.name)

        all_tools.extend(skill.tools)

    collect_tools(skill_name)
    return all_tools


def generate_tool_manifest(
    skill_name: str, skills: dict[str, SkillMeta]
) -> dict[str, Any]:
    """Generate a structured tool manifest for agent consumption."""
    tools = get_tools_for_skill(skill_name, skills)

    manifest = {
        "skill": skill_name,
        "tools": [],
        "tool_index": {},
    }

    for tool in tools:
        tool_def = {
            "name": tool.name,
            "category": tool.category,
            "description": tool.description,
            "command": tool.command,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                    "description": p.description,
                }
                for p in tool.parameters
            ],
            "examples": tool.examples,
            "aliases": tool.aliases,
        }
        manifest["tools"].append(tool_def)
        manifest["tool_index"][tool.name] = tool_def
        for alias in tool.aliases:
            manifest["tool_index"][alias] = tool_def

    return manifest


def print_resolution_report(skill_name: str, skills: dict[str, SkillMeta]) -> None:
    """Print a detailed resolution report for a skill."""
    skill = skills.get(skill_name)
    if not skill:
        print(f"Error: Skill '{skill_name}' not found")
        return

    print(f"\n{'=' * 60}")
    print(f"SKILL RESOLUTION REPORT: {skill_name}")
    print(f"{'=' * 60}")

    print(f"\nDescription: {skill.description[:100]}...")
    print(f"Version: {skill.version}")

    order, missing = resolve_skill_dependencies(skill_name, skills)

    print(f"\n{'DEPENDENCY RESOLUTION':-^60}")
    if order:
        print("Load order:")
        for i, name in enumerate(order, 1):
            marker = " <<" if name == skill_name else ""
            print(f"  {i}. {name}{marker}")
    else:
        print("No dependencies")

    if missing:
        print(f"\nMissing dependencies:")
        for m in missing:
            print(f"  - {m}")

    tools = get_tools_for_skill(skill_name, skills)
    print(f"\n{'AVAILABLE TOOLS':-^60}")
    if tools:
        for tool in tools:
            print(f"  [{tool.category}] {tool.name}: {tool.description[:60]}...")
    else:
        print("  No structured tools defined")

    env_reqs = skill.dependencies.get("environment", [])
    if env_reqs:
        print(f"\n{'ENVIRONMENT REQUIREMENTS':-^60}")
        for env in env_reqs:
            import os

            status = "OK" if os.environ.get(env.name) else "MISSING"
            req = "required" if env.required else "optional"
            print(f"  [{status}] {env.name} ({req}): {env.description}")

    perf = skill.performance
    if perf:
        print(f"\n{'PERFORMANCE HINTS':-^60}")
        if "typical_duration" in perf:
            print(f"  Duration: {perf['typical_duration']}")
        if "cost_range" in perf:
            print(f"  Cost: {perf['cost_range']}")
        if "complexity" in perf:
            print(f"  Complexity: {perf['complexity']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Skill Dependency Resolver and Validator"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    validate_parser = subparsers.add_parser("validate", help="Validate a skill")
    validate_parser.add_argument(
        "--skill", required=True, help="Skill name to validate"
    )

    check_parser = subparsers.add_parser("check-deps", help="Check all dependencies")

    graph_parser = subparsers.add_parser("graph", help="Generate dependency graph")
    graph_parser.add_argument(
        "--format", default="mermaid", choices=["mermaid", "json"]
    )

    resolve_parser = subparsers.add_parser("resolve", help="Resolve skill dependencies")
    resolve_parser.add_argument("--skill", required=True, help="Skill to resolve")

    tools_parser = subparsers.add_parser("tools", help="Get tools for a skill")
    tools_parser.add_argument("--skill", required=True, help="Skill name")
    tools_parser.add_argument("--format", default="text", choices=["text", "json"])

    cycles_parser = subparsers.add_parser("cycles", help="Detect circular dependencies")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    skills = collect_all_skills()

    if args.command == "validate":
        errors = validate_skill(args.skill, skills)
        if errors:
            print(f"Validation errors for '{args.skill}':")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print(f"Skill '{args.skill}' is valid")

    elif args.command == "check-deps":
        results = check_all_dependencies(skills)
        if results:
            print("Dependency issues found:")
            for skill, errors in results.items():
                print(f"\n{skill}:")
                for e in errors:
                    print(f"  - {e}")
            sys.exit(1)
        else:
            print("All skill dependencies are satisfied")

    elif args.command == "graph":
        if args.format == "mermaid":
            print(generate_dependency_graph(skills))
        else:
            graph = {}
            for name, skill in skills.items():
                graph[name] = {
                    "dependencies": [
                        d.name for d in skill.dependencies.get("skills", [])
                    ],
                    "tools": [t.name for t in skill.tools],
                }
            print(json.dumps(graph, indent=2))

    elif args.command == "resolve":
        print_resolution_report(args.skill, skills)

    elif args.command == "tools":
        manifest = generate_tool_manifest(args.skill, skills)
        if args.format == "json":
            print(json.dumps(manifest, indent=2))
        else:
            print(f"\nTools for '{args.skill}':")
            for tool in manifest["tools"]:
                print(f"\n  [{tool['category']}] {tool['name']}")
                print(f"    {tool['description']}")
                if tool["parameters"]:
                    print("    Parameters:")
                    for p in tool["parameters"]:
                        req = "required" if p["required"] else "optional"
                        print(f"      - {p['name']} ({p['type']}, {req})")

    elif args.command == "cycles":
        cycles = detect_circular_dependencies(skills)
        if cycles:
            print("Circular dependencies detected:")
            for cycle in cycles:
                print(f"  -> {' -> '.join(cycle)}")
            sys.exit(1)
        else:
            print("No circular dependencies detected")


if __name__ == "__main__":
    main()
