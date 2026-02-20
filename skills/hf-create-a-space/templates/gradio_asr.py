"""Automatic Speech Recognition with {model_id}"""
import gradio as gr
from transformers import pipeline

MODEL_ID = "{model_id}"

# Load ASR pipeline
asr = pipeline("automatic-speech-recognition", model=MODEL_ID)


def transcribe(audio, return_timestamps):
    """Transcribe audio to text."""
    if audio is None:
        return "Please upload or record audio."

    # Run transcription
    if return_timestamps:
        result = asr(audio, return_timestamps="word")
        # Format with timestamps
        if "chunks" in result:
            lines = []
            for chunk in result["chunks"]:
                start = chunk.get("timestamp", [0, 0])[0]
                end = chunk.get("timestamp", [0, 0])[1]
                text = chunk.get("text", "")
                lines.append(f"[{start:.2f}s - {end:.2f}s] {text}")
            return "\n".join(lines)
        return result.get("text", str(result))
    else:
        result = asr(audio)
        return result.get("text", str(result))


demo = gr.Interface(
    fn=transcribe,
    inputs=[
        gr.Audio(type="filepath", label="Upload or Record Audio"),
        gr.Checkbox(label="Return word timestamps", value=False),
    ],
    outputs=gr.Textbox(label="Transcription", lines=10),
    title="{title}",
    description="Transcribe audio to text using {model_id}",
    examples=[],
)

if __name__ == "__main__":
    demo.launch()
