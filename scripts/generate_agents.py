#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Generate AGENTS.md and marketplace metadata from SKILL.md frontmatter.

Also validates that client marketplace entries stay curated, validates that
the internal Hub marketplace contains every skill, and updates README.md.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "scripts" / "AGENTS_TEMPLATE.md"
OUTPUT_PATH = ROOT / "agentsmd" / "AGENTS.md"
INTERNAL_MARKETPLACE_PATH = ROOT / ".claude-plugin" / "marketplace-internal.json"
EXTERNAL_MARKETPLACE_PATHS = [
    ROOT / ".claude-plugin" / "marketplace.json",
    ROOT / ".cursor-plugin" / "marketplace.json",
]
PLUGIN_MANIFEST_PATH = ROOT / ".claude-plugin" / "plugin.json"
README_PATH = ROOT / "README.md"
REQUIRED_MARKETPLACE_SKILLS = {"hf-cli"}

# Markers for the auto-generated skills table in README
README_TABLE_START = "<!-- BEGIN_SKILLS_TABLE -->"
README_TABLE_END = "<!-- END_SKILLS_TABLE -->"


def load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse a minimal YAML-ish frontmatter block without external deps."""
    match = re.search(r"^---\s*\n(.*?)\n---\s*", text, re.DOTALL)
    if not match:
        return {}
    data: dict[str, str] = {}
    lines = match.group(1).splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if ":" not in line:
            index += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value in {">", "|"}:
            folded: list[str] = []
            index += 1
            while index < len(lines):
                continuation = lines[index]
                if continuation and not continuation.startswith((" ", "\t")):
                    break
                folded.append(continuation.strip())
                index += 1
            data[key] = " ".join(part for part in folded if part)
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        data[key] = value
        index += 1
    return data


def concise_description(description: str) -> str:
    """Return a compact README description from activation-oriented frontmatter."""
    description = " ".join(description.split())
    sentence = re.search(r"(?<=[.!?])\s+", description)
    if sentence:
        return description[: sentence.start()]
    return description


def collect_skills() -> list[dict[str, str]]:
    skills: list[dict[str, str]] = []
    for skill_md in ROOT.glob("skills/*/SKILL.md"):
        meta = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        name = meta.get("name")
        description = meta.get("description")
        if not name or not description:
            continue
        skills.append(
            {
                "name": name,
                "description": description,
                "path": skill_md.parent.relative_to(ROOT).as_posix(),
            }
        )
    # Keep deterministic order for consistent output
    return sorted(skills, key=lambda s: s["name"].lower())


def render(template: str, skills: list[dict[str, str]]) -> str:
    """Very small Mustache-like renderer that only supports a single skills loop."""
    def repl(match: re.Match[str]) -> str:
        block = match.group(1).strip("\n")
        rendered_blocks = []
        for skill in skills:
            rendered = (
                block.replace("{{name}}", skill["name"])
                .replace("{{description}}", skill["description"])
                .replace("{{path}}", skill["path"])
            )
            rendered_blocks.append(rendered)
        return "\n".join(rendered_blocks)

    # Render loop blocks
    content = re.sub(r"{{#skills}}(.*?){{/skills}}", repl, template, flags=re.DOTALL)
    return content


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def render_json(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def load_marketplace(path: Path = INTERNAL_MARKETPLACE_PATH) -> dict:
    """Load marketplace.json and return parsed structure."""
    if not path.exists():
        raise FileNotFoundError(f"marketplace.json not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def marketplace_descriptions(path: Path) -> dict[str, str]:
    data = load_json(path)
    plugins = data.get("plugins", [])
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


def build_internal_marketplace(skills: list[dict[str, str]]) -> dict:
    """Build the full marketplace used by hf skills, MCP, and discovery."""
    plugin_manifest = load_json(PLUGIN_MANIFEST_PATH)
    existing_descriptions = marketplace_descriptions(INTERNAL_MARKETPLACE_PATH)

    return {
        "name": "huggingface-skills",
        "owner": {
            "name": "Hugging Face",
        },
        "metadata": {
            "description": (
                "Full Hugging Face Skills manifest for hf skills, MCP, and discovery. "
                "Client plugin marketplaces use curated manifests."
            ),
            "version": plugin_manifest.get("version", "0.0.0"),
        },
        "plugins": [
            {
                "name": skill["name"],
                "source": f"./{skill['path']}",
                "skills": "./",
                "description": existing_descriptions.get(
                    skill["name"],
                    concise_description(skill["description"]),
                ),
            }
            for skill in skills
        ],
    }


def write_internal_marketplace(skills: list[dict[str, str]]) -> None:
    INTERNAL_MARKETPLACE_PATH.write_text(
        render_json(build_internal_marketplace(skills)),
        encoding="utf-8",
    )


def generate_readme_table(skills: list[dict[str, str]]) -> str:
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
        description = plugin.get("description") or concise_description(skill["description"])
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


def validate_external_marketplace(skills: list[dict[str, str]], path: Path) -> list[str]:
    """
    Validate client marketplace entries against discovered skills.

    Client marketplace manifests intentionally expose a small install-time
    surface. The remaining repo skills are installed through
    `hf skills add <skill-name>` or consumed through skill-aware clients over
    CLI/MCP.
    Returns list of error messages (empty = passed).
    """
    errors: list[str] = []
    marketplace = load_marketplace(path)
    plugins = marketplace.get("plugins", [])

    # Build lookups (normalize paths: skill uses "skills/x", marketplace uses "./skills/x")
    skill_by_source = {f"./{s['path']}": s for s in skills}
    plugin_by_source: dict[str, dict] = {}
    plugin_names: set[str] = set()

    # Check: every marketplace plugin has a corresponding skill with matching name.
    for plugin in plugins:
        source = plugin.get("source")
        name = plugin.get("name")

        if source in plugin_by_source:
            errors.append(f"{path}: duplicate marketplace source '{source}'")
        else:
            plugin_by_source[source] = plugin

        if name in plugin_names:
            errors.append(f"{path}: duplicate marketplace skill name '{name}'")
        else:
            plugin_names.add(name)

        if source not in skill_by_source:
            errors.append(
                f"{path}: marketplace plugin '{name}' at '{source}' has no SKILL.md"
            )
            continue

        skill = skill_by_source[source]
        if name != skill["name"]:
            errors.append(
                f"Name mismatch at '{source}': "
                f"SKILL.md='{skill['name']}', marketplace.json='{name}'"
            )

    missing_required = REQUIRED_MARKETPLACE_SKILLS - plugin_names
    for name in sorted(missing_required):
        errors.append(f"{path}: required marketplace skill '{name}' is missing")

    extra = plugin_names - REQUIRED_MARKETPLACE_SKILLS
    for name in sorted(extra):
        errors.append(f"{path}: client marketplace must not expose '{name}'")

    return errors


def validate_internal_marketplace(skills: list[dict[str, str]]) -> list[str]:
    """Validate the internal marketplace includes every discovered skill."""
    errors: list[str] = []
    marketplace = load_marketplace(INTERNAL_MARKETPLACE_PATH)
    plugins = marketplace.get("plugins", [])
    if not isinstance(plugins, list):
        return [f"{INTERNAL_MARKETPLACE_PATH}: plugins must be a list"]

    skill_by_source = {f"./{s['path']}": s for s in skills}
    plugin_by_source: dict[str, dict] = {}

    for plugin in plugins:
        if not isinstance(plugin, dict):
            errors.append(f"{INTERNAL_MARKETPLACE_PATH}: plugin entries must be objects")
            continue

        source = plugin.get("source")
        name = plugin.get("name")
        if source in plugin_by_source:
            errors.append(f"{INTERNAL_MARKETPLACE_PATH}: duplicate source '{source}'")
        else:
            plugin_by_source[source] = plugin

        skill = skill_by_source.get(source)
        if skill is None:
            errors.append(f"{INTERNAL_MARKETPLACE_PATH}: '{name}' at '{source}' has no SKILL.md")
        elif name != skill["name"]:
            errors.append(
                f"{INTERNAL_MARKETPLACE_PATH}: name mismatch at '{source}': "
                f"SKILL.md='{skill['name']}', marketplace='{name}'"
            )

    missing = set(skill_by_source) - set(plugin_by_source)
    for source in sorted(missing):
        errors.append(f"{INTERNAL_MARKETPLACE_PATH}: missing skill at '{source}'")

    return errors


def main() -> None:
    template = load_template()
    skills = collect_skills()
    output = render(template, skills)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(output, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {len(skills)} skills.")
    write_internal_marketplace(skills)
    print(f"Wrote {INTERNAL_MARKETPLACE_PATH} with {len(skills)} skills.")

    # Validate marketplace manifests
    errors = [
        error
        for marketplace_path in EXTERNAL_MARKETPLACE_PATHS
        for error in validate_external_marketplace(skills, marketplace_path)
    ]
    errors.extend(validate_internal_marketplace(skills))
    if errors:
        print("\nMarketplace validation errors:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)
    print("Marketplace validation passed.")

    # Update README.md skills table
    if update_readme(skills):
        print(f"Updated {README_PATH} skills table.")


if __name__ == "__main__":
    main()
