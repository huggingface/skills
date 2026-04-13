"""
Starter scaffold for the Unit 2 Space.

You fine-tuned a model in Unit 1. This scaffold gives you a Gradio shell
to demo it. The `predict()` function is a mock — swap it for your model.

Ask Claude Code to fill this out. With the hf-brand skill installed,
it'll style it to match the Hub.
"""

from __future__ import annotations

import gradio as gr


def predict(text: str) -> dict[str, float]:
    """Mock inference. Replace with your fine-tuned model."""
    words = text.lower().split()
    pos = sum(1 for w in words if w in {"good", "great", "love", "excellent"})
    neg = sum(1 for w in words if w in {"bad", "terrible", "hate", "awful"})
    total = max(pos + neg, 1)
    return {
        "positive": pos / total if total else 0.33,
        "negative": neg / total if total else 0.33,
        "neutral": 1 - (pos + neg) / max(len(words), 1),
    }


with gr.Blocks() as demo:
    gr.Markdown("# Model Demo")
    inp = gr.Textbox(label="Input")
    out = gr.Label(label="Prediction")
    inp.submit(predict, inp, out)


if __name__ == "__main__":
    demo.launch()
