"""
A skill-aware Gradio chat agent.

This is the starter. The student fills in `select_skills()` — the function
that decides which skills are relevant to a given message.
"""

from __future__ import annotations

import os
from pathlib import Path

import anthropic
import gradio as gr

from skill_loader import descriptions_block, load_skills, system_prompt_for

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
SKILLS_DIR = Path(__file__).parent / "skills"

client = anthropic.Anthropic()
skills = load_skills(SKILLS_DIR)


def select_skills(user_message: str) -> list[str]:
    """
    Decide which skills are relevant to this message.

    TODO: implement this. The simplest approach:
      1. Build a prompt with descriptions_block(skills) + the user message
      2. Ask Claude which skills (by name) are relevant
      3. Parse the response and return a list of names

    Return [] to load no skills (generic response).
    """
    _ = user_message
    _ = descriptions_block
    return []


def respond(user_message: str, history: list[tuple[str, str]]) -> tuple[str, str]:
    selected = select_skills(user_message)
    system_prompt = system_prompt_for(skills, selected)

    messages = []
    for user_turn, assistant_turn in history:
        messages.append({"role": "user", "content": user_turn})
        messages.append({"role": "assistant", "content": assistant_turn})
    messages.append({"role": "user", "content": user_message})

    kwargs = {"model": MODEL, "max_tokens": 2000, "messages": messages}
    if system_prompt:
        kwargs["system"] = system_prompt

    response = client.messages.create(**kwargs)
    text = "".join(block.text for block in response.content if getattr(block, "text", None))
    badge = f"*[skills: {', '.join(selected) if selected else 'none'}]*"
    return text, badge


def chat(message: str, history: list[tuple[str, str]] | None):
    history = history or []
    response, badge = respond(message, history)
    history = history + [(message, response)]
    return "", history, badge


with gr.Blocks() as demo:
    gr.Markdown("# Skill-Aware Agent\n\nAsk anything. Watch which skills load.")
    chatbot = gr.Chatbot(type="tuples")
    skill_badge = gr.Markdown("*[skills: none]*")
    inp = gr.Textbox(
        label="Message",
        placeholder="Build me a Gradio demo for a sentiment classifier",
    )
    inp.submit(chat, [inp, chatbot], [inp, chatbot, skill_badge])


if __name__ == "__main__":
    print("Loaded", len(skills), "skills:", ", ".join(skill.name for skill in skills))
    demo.launch()
