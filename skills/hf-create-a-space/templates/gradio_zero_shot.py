"""Zero-Shot Classification with {model_id}"""
import gradio as gr
from transformers import pipeline

MODEL_ID = "{model_id}"

# Load zero-shot classification pipeline
classifier = pipeline("zero-shot-classification", model=MODEL_ID)


def classify(text, labels, multi_label):
    """Classify text into custom categories."""
    if not text or not text.strip():
        return {{"error": "Please enter some text"}}
    if not labels or not labels.strip():
        return {{"error": "Please enter at least one label"}}

    # Parse labels (comma or newline separated)
    label_list = [l.strip() for l in labels.replace("\\n", ",").split(",") if l.strip()]

    if not label_list:
        return {{"error": "Please enter valid labels"}}

    # Run classification
    result = classifier(text, label_list, multi_label=multi_label)

    # Format as dict for label output
    return dict(zip(result["labels"], result["scores"]))


demo = gr.Interface(
    fn=classify,
    inputs=[
        gr.Textbox(
            label="Text to classify",
            placeholder="Enter the text you want to classify...",
            lines=3,
        ),
        gr.Textbox(
            label="Candidate labels",
            placeholder="Enter labels (comma or newline separated)\\ne.g., positive, negative, neutral",
            lines=3,
        ),
        gr.Checkbox(
            label="Multi-label (text can belong to multiple categories)",
            value=False,
        ),
    ],
    outputs=gr.Label(label="Classification Results", num_top_classes=10),
    title="{title}",
    description="Classify text into any categories you define using {model_id}",
    examples=[
        ["I love this product! It's amazing.", "positive, negative, neutral", False],
        ["The new policy will affect healthcare and education.", "politics, healthcare, education, sports, technology", True],
    ],
)

if __name__ == "__main__":
    demo.launch()
