# Unit 2 Starter — Claude Code

## What's Here

```text
app.py                     # minimal Gradio scaffold with mock inference
requirements.txt           # dependencies for the Space exercise
skills/
  hf-brand/SKILL.md        # Hugging Face visual identity for Gradio
  brutalist/SKILL.md       # alternate aesthetic (monochrome, hard edges)
  no-fluff/SKILL.md        # strips disclaimers and filler
agent/
  app.py                   # skill-aware mini chat app with a TODO selector
  skill_loader.py          # parse, load, and compose helpers
  solution_select_skills.py
  skills/
    hf-brand/SKILL.md
    domain-qwen/SKILL.md
```

## Space Workflow

Copy the skill you want into `.claude/skills/` inside a working copy of this starter:

```bash
mkdir -p .claude/skills
cp -r skills/hf-brand .claude/skills/
```

Then open Claude Code and ask it to turn `app.py` into a polished Gradio demo.

## Under-the-Hood Workflow

The `agent/` directory is a separate exercise for the "Inside the Box" chapter. It lets you inspect a minimal load, select, compose loop directly:

```bash
cd agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

`app.py` in that directory ships with a `select_skills()` TODO. Compare your answer with `solution_select_skills.py` when you are done.
