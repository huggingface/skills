# Unit 2 Starter — Claude Code

## What's here

```
skills/
  hf-brand/SKILL.md      — HuggingFace visual identity for Gradio
  brutalist/SKILL.md     — alternate aesthetic (monochrome, hard edges)
  no-fluff/SKILL.md      — strips disclaimers and filler
app_scaffold.py          — minimal Gradio shell with mock inference
```

## Setup

Copy the skills you want into your project's `.claude/skills/`:

```bash
mkdir -p .claude/skills
cp -r skills/hf-brand .claude/skills/
```

Or into `~/.claude/skills/` to use them everywhere.

## Gradio 6 notes

Things Claude sometimes gets wrong with Gradio 6.x:

1. **`theme` and `css` go on `Blocks()`**, not `launch()`. `gr.Blocks(theme=theme, css=css)` is correct; passing them to `launch()` raises a TypeError.
2. **Fonts need `gr.themes.GoogleFont("Name")`**, not bare strings. `font=["Source Sans Pro"]` will crash; `font=[gr.themes.GoogleFont("Source Sans Pro")]` works.
3. **Nested quotes in placeholders** — if Claude writes `placeholder="e.g. "hello""`, that's a syntax error. Use single quotes outside or escape.

The `hf-brand` skill already encodes #1 and #2.
