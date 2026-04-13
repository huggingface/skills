"""
One working implementation of select_skills(). Not the only way.

Two-pass: show Claude the descriptions, ask which are relevant, parse names.
"""

from __future__ import annotations

import json
import os
import re

import anthropic

from skill_loader import descriptions_block

SELECTION_MODEL = os.getenv("CLAUDE_SELECTION_MODEL", "claude-haiku-4-5-20251001")


def select_skills(
    user_message: str,
    skills,
    client: anthropic.Anthropic | None = None,
) -> list[str]:
    if client is None:
        client = anthropic.Anthropic()

    prompt = (
        f"{descriptions_block(skills)}\n\n"
        f"User message: {user_message}\n\n"
        "Which skills (if any) are relevant to this message? Respond with a JSON list\n"
        "of skill names. If none are relevant, respond with [].\n\n"
        "Only the JSON list, nothing else."
    )

    message = client.messages.create(
        model=SELECTION_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    response = "".join(block.text for block in message.content if getattr(block, "text", None)).strip()
    match = re.search(r"\[.*?\]", response, re.DOTALL)
    if not match:
        return []

    try:
        names = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    valid = {skill.name for skill in skills}
    return [name for name in names if name in valid]
