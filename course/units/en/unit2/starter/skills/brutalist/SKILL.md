---
name: brutalist
description: Build Gradio interfaces in a stark brutalist style — monochrome, monospace, hard edges, no decoration. Use when the user asks for "minimal", "brutalist", "no-frills", "terminal-style", or explicitly rejects friendly/soft UI.
---

# Brutalist Gradio

## Core principles

- **Monochrome only.** Black `#000`, white `#fff`, one mid-gray `#888`. No accent colors.
- **Monospace everywhere.** JetBrains Mono or Consolas.
- **Hard edges.** Zero border-radius. 2px solid black borders, or none.
- **No decoration.** No icons, no emoji, no shadows, no gradients.

## Copy

- Labels are COMMANDS: "ENTER TEXT" not "Your text here"
- No exclamation marks. No friendly microcopy.
- Descriptions are one sentence, declarative, period at end.

## Gradio theme (Gradio 6.x)

```python
import gradio as gr

theme = gr.themes.Monochrome(
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "Consolas", "monospace"],
    radius_size=gr.themes.sizes.radius_none,
).set(
    button_primary_background_fill="#000000",
    button_primary_text_color="#ffffff",
    border_color_primary="#000000",
    block_border_width="2px",
)

css = """
.gradio-container { font-family: "JetBrains Mono", monospace !important; max-width: 720px; margin: auto; }
label { text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; }
h1 { font-size: 2.5rem; font-weight: 900; text-transform: uppercase; }
* { border-radius: 0 !important; }
"""

with gr.Blocks(theme=theme, css=css) as demo:
    ...
demo.launch()
```

## Layout

- Single column, max 720px
- Input above output, always. No side-by-side.
- Generous vertical whitespace
