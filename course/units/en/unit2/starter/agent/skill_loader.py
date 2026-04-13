"""
A minimal skill loader. This is what Claude Code does — simplified.

Read SKILL.md frontmatter from a directory. Present descriptions to the
model. Let it pick. Load the chosen ones into the system prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: Path


def parse_skill(path: Path) -> Skill:
    """Parse a SKILL.md: frontmatter + body."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path} is missing YAML frontmatter")

    frontmatter, body = match.group(1), match.group(2)
    name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
    description_match = re.search(
        r"^description:\s*(.+?)(?=\n\w+:|\Z)",
        frontmatter,
        re.MULTILINE | re.DOTALL,
    )
    if not name_match or not description_match:
        raise ValueError(f"{path} must define name and description")

    description = " ".join(line.strip() for line in description_match.group(1).splitlines())
    return Skill(
        name=name_match.group(1).strip(),
        description=description.strip(),
        body=body.strip(),
        path=path,
    )


def load_skills(skills_dir: Path) -> list[Skill]:
    """Find all SKILL.md files under skills_dir."""
    skills: list[Skill] = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skills.append(parse_skill(skill_md))
    return skills


def descriptions_block(skills: list[Skill]) -> str:
    """Format skill descriptions for the selection prompt."""
    lines = ["Available skills:\n"]
    for skill in skills:
        lines.append(f"- **{skill.name}**: {skill.description}")
    return "\n".join(lines)


def system_prompt_for(skills: list[Skill], selected: list[str]) -> str:
    """Build a system prompt from the selected skills' full content."""
    chosen = [skill for skill in skills if skill.name in selected]
    if not chosen:
        return ""

    parts = [f"# Skill: {skill.name}\n\n{skill.body}" for skill in chosen]
    return "\n\n---\n\n".join(parts)
