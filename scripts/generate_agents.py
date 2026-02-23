#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Generate AGENTS.md from AGENTS_TEMPLATE.md and SKILL.md frontmatter.

Also validates that marketplace.json is in sync with discovered skills,
and updates the skills table in README.md.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "scripts" / "AGENTS_TEMPLATE.md"
OUTPUT_PATH = ROOT / "agents" / "AGENTS.md"
MARKETPLACE_PATH = ROOT / ".claude-plugin" / "marketplace.json"
README_PATH = ROOT / "README.md"

# Markers for the auto-generated skills table in README
README_TABLE_START = "<!-- BEGIN_SKILLS_TABLE -->"
README_TABLE_END = "<!-- END_SKILLS_TABLE -->"


def load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse a minimal YAML-ish frontmatter block without external deps.

    Supports:
    - Simple key: value pairs
    - Nested lists (tools, dependencies)
    - Nested dicts (performance, prerequisites)
    """
    match = re.search(r"^---\s*\n(.*?)\n---\s*", text, re.DOTALL)
    if not match:
        return {}

    frontmatter_text = match.group(1)
    data: dict[str, Any] = {}
    current_list: str | None = None
    current_item: dict[str, Any] | None = None
    indent_stack: list[tuple[str, int]] = []

    for line in frontmatter_text.splitlines():
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if stripped.startswith("- "):
            value = stripped[2:].strip()
            if ":" in value:
                current_item = {"_raw": value}
                key = value.split(":")[0].strip()
                current_item["_key"] = key
                if current_list and current_list not in data:
                    data[current_list] = []
                if current_list:
                    data[current_list].append(current_item)
            else:
                if current_list:
                    if current_list not in data:
                        data[current_list] = []
                    data[current_list].append(value)
            continue

        if ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()

            if not value and not key.startswith(" "):
                current_list = key
                current_item = None
            elif current_item is not None:
                current_item[key] = value.strip("\"'")
            else:
                data[key] = value.strip("\"'")
                current_list = None

    for key in data:
        if isinstance(data[key], list):
            cleaned = []
            for item in data[key]:
                if isinstance(item, dict) and "_raw" in item:
                    clean_item = {
                        k: v for k, v in item.items() if not k.startswith("_")
                    }
                    cleaned.append(clean_item)
                else:
                    cleaned.append(item)
            data[key] = cleaned

    return data


def collect_skills() -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for skill_md in ROOT.glob("skills/*/SKILL.md"):
        meta = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        name = meta.get("name")
        description = meta.get("description")
        if not name or not description:
            continue

        tools = meta.get("tools", [])

        skill_deps = []
        dependencies = meta.get("dependencies", {})
        if isinstance(dependencies, dict):
            for dep in dependencies.get("skills", []):
                if isinstance(dep, dict):
                    skill_deps.append(
                        {
                            "name": dep.get("name", ""),
                            "required": dep.get("required", True),
                            "reason": dep.get("reason", ""),
                            "auto_load": dep.get("auto_load", False),
                        }
                    )

        env_deps = []
        if isinstance(dependencies, dict):
            for env in dependencies.get("environment", []):
                if isinstance(env, dict):
                    env_deps.append(env.get("name", ""))

        has_tools = isinstance(tools, list) and len(tools) > 0
        tool_count = len(tools) if isinstance(tools, list) else 0
        tool_categories = (
            list(
                set(t.get("category", "unknown") for t in tools if isinstance(t, dict))
            )
            if isinstance(tools, list)
            else []
        )

        skills.append(
            {
                "name": name,
                "description": description,
                "path": str(skill_md.parent.relative_to(ROOT)),
                "tools": tools if isinstance(tools, list) else [],
                "skill_deps": skill_deps,
                "dependencies": env_deps,
                "has_tools": has_tools,
                "tool_count": tool_count,
                "tool_categories": ", ".join(tool_categories)
                if tool_categories
                else "none",
            }
        )
    return sorted(skills, key=lambda s: s["name"].lower())


def render(template: str, skills: list[dict[str, Any]]) -> str:
    """Enhanced Mustache-like renderer supporting nested loops and conditionals."""

    def render_simple_block(block: str, context: dict[str, Any]) -> str:
        result = block
        for key, value in context.items():
            if isinstance(value, str):
                result = result.replace("{{" + key + "}}", value)
            elif isinstance(value, bool):
                result = result.replace("{{" + key + "}}", str(value).lower())
            elif isinstance(value, (int, float)):
                result = result.replace("{{" + key + "}}", str(value))
            elif isinstance(value, list):
                if value:
                    result = result.replace(
                        "{{" + key + "}}", ", ".join(str(v) for v in value)
                    )
                else:
                    result = result.replace("{{" + key + "}}", "")
        return result

    def process_nested_loops(block: str, context: dict[str, Any]) -> str:
        result = block

        inner_loops = re.findall(r"{{#(\w+)}}(.*?){{/\1}}", result, flags=re.DOTALL)

        for loop_var, inner_block in inner_loops:
            items = context.get(loop_var, [])

            if isinstance(items, bool):
                if items:
                    result = result.replace(
                        "{{#" + loop_var + "}}" + inner_block + "{{/" + loop_var + "}}",
                        inner_block.strip(),
                    )
                else:
                    result = result.replace(
                        "{{#" + loop_var + "}}" + inner_block + "{{/" + loop_var + "}}",
                        "",
                    )
                continue

            if not items:
                result = result.replace(
                    "{{#" + loop_var + "}}" + inner_block + "{{/" + loop_var + "}}", ""
                )
                continue

            rendered_parts = []
            for item in items:
                if isinstance(item, dict):
                    item_rendered = render_simple_block(inner_block, item)
                else:
                    item_rendered = inner_block.replace("{{.}}", str(item))
                rendered_parts.append(item_rendered.strip())

            combined = "\n".join(rendered_parts)
            result = result.replace(
                "{{#" + loop_var + "}}" + inner_block + "{{/" + loop_var + "}}",
                combined,
            )

        return result

    def repl_skills_loop(match: re.Match[str]) -> str:
        block = match.group(1)
        rendered_blocks = []

        for skill in skills:
            skill_rendered = process_nested_loops(block, skill)
            skill_rendered = render_simple_block(skill_rendered, skill)
            rendered_blocks.append(skill_rendered)

        return "\n".join(rendered_blocks)

    content = re.sub(
        r"{{#skills}}(.*?){{/skills}}", repl_skills_loop, template, flags=re.DOTALL
    )

    return content


def load_marketplace() -> dict:
    """Load marketplace.json and return parsed structure."""
    if not MARKETPLACE_PATH.exists():
        raise FileNotFoundError(f"marketplace.json not found at {MARKETPLACE_PATH}")
    return json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))


def generate_readme_table(skills: list[dict[str, Any]]) -> str:
    """Generate the skills table for README.md using marketplace.json names."""
    marketplace = load_marketplace()
    plugins = {p["source"]: p for p in marketplace.get("plugins", [])}

    lines = [
        "| Name | Description | Documentation |",
        "|------|-------------|---------------|",
    ]

    for skill in skills:
        source = f"./{skill['path']}"
        plugin = plugins.get(source, {})
        name = plugin.get("name", skill["name"])
        description = plugin.get("description", skill["description"])
        doc_link = f"[SKILL.md]({skill['path']}/SKILL.md)"
        lines.append(f"| `{name}` | {description} | {doc_link} |")

    return "\n".join(lines)


def update_readme(skills: list[dict[str, str]]) -> bool:
    """
    Update the README.md skills table between markers.
    Returns True if the file was updated, False if markers not found.
    """
    if not README_PATH.exists():
        print(f"Warning: README.md not found at {README_PATH}", file=sys.stderr)
        return False

    content = README_PATH.read_text(encoding="utf-8")

    start_idx = content.find(README_TABLE_START)
    end_idx = content.find(README_TABLE_END)

    if start_idx == -1 or end_idx == -1:
        print(
            f"Warning: README.md markers not found. Add {README_TABLE_START} and "
            f"{README_TABLE_END} to enable table generation.",
            file=sys.stderr,
        )
        return False

    if end_idx < start_idx:
        print("Warning: README.md markers are in wrong order.", file=sys.stderr)
        return False

    table = generate_readme_table(skills)
    new_content = (
        content[: start_idx + len(README_TABLE_START)]
        + "\n"
        + table
        + "\n"
        + content[end_idx:]
    )

    README_PATH.write_text(new_content, encoding="utf-8")
    return True


def validate_marketplace(skills: list[dict[str, str]]) -> list[str]:
    """
    Validate marketplace.json against discovered skills.
    Returns list of error messages (empty = passed).
    """
    errors: list[str] = []
    marketplace = load_marketplace()
    plugins = marketplace.get("plugins", [])

    # Build lookups (normalize paths: skill uses "skills/x", marketplace uses "./skills/x")
    skill_by_source = {f"./{s['path']}": s for s in skills}
    plugin_by_source = {p["source"]: p for p in plugins}

    # Check: every skill has a marketplace entry with matching name
    for skill in skills:
        expected_source = f"./{skill['path']}"
        if expected_source not in plugin_by_source:
            errors.append(
                f"Skill '{skill['name']}' at '{skill['path']}' is missing from marketplace.json"
            )
        elif plugin_by_source[expected_source]["name"] != skill["name"]:
            errors.append(
                f"Name mismatch at '{expected_source}': "
                f"SKILL.md='{skill['name']}', marketplace.json='{plugin_by_source[expected_source]['name']}'"
            )

    # Check: every marketplace plugin has a corresponding skill
    for plugin in plugins:
        if plugin["source"] not in skill_by_source:
            errors.append(
                f"Marketplace plugin '{plugin['name']}' at '{plugin['source']}' has no SKILL.md"
            )

    return errors


def main() -> None:
    template = load_template()
    skills = collect_skills()
    output = render(template, skills)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(output, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {len(skills)} skills.")

    # Validate marketplace.json
    errors = validate_marketplace(skills)
    if errors:
        print("\nMarketplace.json validation errors:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)
    print("Marketplace.json validation passed.")

    # Update README.md skills table
    if update_readme(skills):
        print(f"Updated {README_PATH} skills table.")


if __name__ == "__main__":
    main()
