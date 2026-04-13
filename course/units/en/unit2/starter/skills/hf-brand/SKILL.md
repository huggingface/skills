---
name: hf-brand
description: Apply Hugging Face visual identity to Gradio apps. Use when building demos, Spaces, or any Gradio UI that should feel native on the Hub. Triggers on "Gradio", "demo", "Space", "Hub UI", "make it look like HuggingFace".
---

# Hugging Face Brand — Gradio

When building Gradio demos, apply HF's visual identity.

## Colors (from huggingface.co/brand)

- Primary yellow: `#FFD21E` — buttons, highlights
- Secondary orange: `#FF9D00` — hover states, accents
- Text gray: `#6B7280` — secondary text

Backgrounds stay white or `#f9fafb`. Let the yellow do the work.

## Typography

- Font: Source Sans Pro (via `gr.themes.GoogleFont`)
- Headings: bold, sentence case — NOT uppercase
- Body: 16px, comfortable line-height

## The 🤗

Use the hugging face emoji in the title. It's the brand mark.

## Shape & tone

- Soft rounded corners (8-12px radius)
- Warm, welcoming copy: "Try it out!" not "ENTER TEXT"
- Gentle emoji are fine. Exclamation points are fine.
- Explain what's happening — HF users like transparency.

## Gradio theme (Gradio 6.x)

```python
import gradio as gr

theme = gr.themes.Soft(
    primary_hue=gr.themes.Color(
        c50="#fffbeb", c100="#fef3c7", c200="#fde68a", c300="#fcd34d",
        c400="#fbbf24", c500="#FFD21E", c600="#FF9D00", c700="#d97706",
        c800="#b45309", c900="#92400e", c950="#78350f",
    ),
    font=[gr.themes.GoogleFont("Source Sans Pro"), "system-ui", "sans-serif"],
    radius_size=gr.themes.sizes.radius_md,
).set(
    button_primary_background_fill="#FFD21E",
    button_primary_text_color="#111827",
    button_primary_background_fill_hover="#FF9D00",
)

# Gradio 6.x prefers app-level presentation settings at launch():
with gr.Blocks() as demo:
    ...
demo.launch(theme=theme)
```

## Layout

- Max-width ~860px, centered
- Breathing room between sections
- Examples as inviting cards, not a dropdown
