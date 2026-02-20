"""Audio Classification with {model_id}"""
import gradio as gr
from transformers import pipeline

MODEL_ID = "{model_id}"

# Load audio classification pipeline
classifier = pipeline("audio-classification", model=MODEL_ID)


def classify_audio(audio):
    """Classify audio into categories."""
    if audio is None:
        return {{"error": "Please upload or record audio"}}

    # Run classification
    results = classifier(audio)

    # Format as dict for label output
    return {{r["label"]: r["score"] for r in results}}


demo = gr.Interface(
    fn=classify_audio,
    inputs=gr.Audio(type="filepath", label="Upload or Record Audio"),
    outputs=gr.Label(label="Classification Results", num_top_classes=5),
    title="{title}",
    description="Classify audio using {model_id}",
    examples=[],
)

if __name__ == "__main__":
    demo.launch()
