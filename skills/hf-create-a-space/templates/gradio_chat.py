"""
Gradio Chat Interface Template

A ready-to-use chat interface for conversational models.
Replace MODEL_ID with your model of choice.

IMPORTANT: For gated models (Llama, Mistral, Gemma, etc.):
1. Accept the model's license on its HuggingFace page
2. Add HF_TOKEN as a Repository Secret in Space Settings
"""

import os
import gradio as gr
from huggingface_hub import InferenceClient

# ============================================================================
# CONFIGURATION - Modify these values
# ============================================================================
MODEL_ID = "HuggingFaceH4/zephyr-7b-beta"  # Change to your model
TITLE = "Chat Demo"
DESCRIPTION = "Chat with an AI assistant powered by Hugging Face."
DEFAULT_SYSTEM_MESSAGE = "You are a helpful, harmless, and honest assistant."

# ============================================================================
# APPLICATION CODE - Modify if needed
# ============================================================================

# Token required for gated models (Llama, Mistral, Gemma, etc.)
# Add HF_TOKEN as a Repository Secret in Space Settings
HF_TOKEN = os.environ.get("HF_TOKEN")
client = InferenceClient(MODEL_ID, token=HF_TOKEN)


def respond(
    message: str,
    history: list[tuple[str, str]],
    system_message: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
):
    """Generate a streaming response to the user's message."""
    messages = [{"role": "system", "content": system_message}]

    for user_msg, assistant_msg in history:
        if user_msg:
            messages.append({"role": "user", "content": user_msg})
        if assistant_msg:
            messages.append({"role": "assistant", "content": assistant_msg})

    messages.append({"role": "user", "content": message})

    response = ""
    for token in client.chat_completion(
        messages,
        max_tokens=max_tokens,
        stream=True,
        temperature=temperature,
        top_p=top_p,
    ):
        delta = token.choices[0].delta.content or ""
        response += delta
        yield response


# Build the Gradio interface
demo = gr.ChatInterface(
    respond,
    title=TITLE,
    description=DESCRIPTION,
    additional_inputs=[
        gr.Textbox(
            value=DEFAULT_SYSTEM_MESSAGE,
            label="System message",
            lines=2,
        ),
        gr.Slider(
            minimum=1,
            maximum=4096,
            value=512,
            step=1,
            label="Max tokens",
        ),
        gr.Slider(
            minimum=0.1,
            maximum=2.0,
            value=0.7,
            step=0.1,
            label="Temperature",
        ),
        gr.Slider(
            minimum=0.1,
            maximum=1.0,
            value=0.95,
            step=0.05,
            label="Top-p (nucleus sampling)",
        ),
    ],
    examples=[
        ["Hello! How are you today?"],
        ["Can you explain quantum computing in simple terms?"],
        ["Write a haiku about programming."],
    ],
)

if __name__ == "__main__":
    demo.launch()
