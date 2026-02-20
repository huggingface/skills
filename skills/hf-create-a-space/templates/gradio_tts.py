"""Text-to-Speech with {model_id}"""
import gradio as gr
from huggingface_hub import InferenceClient

MODEL_ID = "{model_id}"
client = InferenceClient()


def synthesize(text):
    """Convert text to speech."""
    if not text or not text.strip():
        return None

    try:
        # Use Inference API for TTS
        audio = client.text_to_speech(text, model=MODEL_ID)
        return audio
    except Exception as e:
        raise gr.Error(f"TTS failed: {e}")


demo = gr.Interface(
    fn=synthesize,
    inputs=gr.Textbox(
        label="Text to speak",
        placeholder="Enter text to convert to speech...",
        lines=3,
    ),
    outputs=gr.Audio(label="Generated Speech", type="filepath"),
    title="{title}",
    description="Convert text to speech using {model_id}",
    examples=[
        ["Hello! Welcome to this text-to-speech demo."],
        ["The quick brown fox jumps over the lazy dog."],
    ],
)

if __name__ == "__main__":
    demo.launch()
