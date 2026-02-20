"""
Gradio Chat Interface with ZeroGPU Template

Use this template for models that DON'T have Inference API support.
This is FREE with daily GPU quota on Hugging Face Spaces.

Requirements:
- gradio>=5.0.0
- torch
- transformers
- accelerate
- spaces

README.md must include: suggested_hardware: zero-a10g

IMPORTANT: Hardware must be set to ZeroGPU in Space Settings after deployment!
"""

import gradio as gr
import spaces
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# ============================================================================
# CONFIGURATION - Modify these values
# ============================================================================
MODEL_ID = "YOUR_USERNAME/YOUR_MODEL"  # Your fine-tuned model
TITLE = "My Fine-Tuned Model"
DESCRIPTION = "Chat with my custom model, powered by ZeroGPU (free!)"
DEFAULT_SYSTEM_MESSAGE = "You are a helpful assistant."

# ============================================================================
# MODEL LOADING - Lazy loading inside GPU context
# ============================================================================
# Load tokenizer at startup (lightweight, no GPU needed)
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

# Model will be loaded lazily on first request
model = None


def load_model():
    """Load model - called inside GPU context."""
    global model
    if model is None:
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.float16,
            device_map="auto",
        )
    return model


# ============================================================================
# GENERATION FUNCTION - GPU allocated only during this function
# ============================================================================
@spaces.GPU(duration=120)  # GPU allocated for up to 120 seconds
def generate_response(
    message: str,
    history: list[tuple[str, str]],
    system_message: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
) -> str:
    """Generate response using the model. GPU is allocated only during this call."""

    # Load model on GPU
    model = load_model()

    # Build conversation history
    messages = [{"role": "system", "content": system_message}]

    for user_msg, assistant_msg in history:
        if user_msg:
            messages.append({"role": "user", "content": user_msg})
        if assistant_msg:
            messages.append({"role": "assistant", "content": assistant_msg})

    messages.append({"role": "user", "content": message})

    # Apply chat template (model-specific formatting)
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )

    # Tokenize and move to GPU
    inputs = tokenizer([text], return_tensors="pt").to(model.device)

    # Generate response (no streaming with ZeroGPU)
    outputs = model.generate(
        **inputs,
        max_new_tokens=int(max_tokens),
        temperature=temperature,
        top_p=top_p,
        do_sample=True,
        pad_token_id=tokenizer.eos_token_id,
    )

    # Decode only the new tokens (skip the input)
    response = tokenizer.decode(
        outputs[0][inputs['input_ids'].shape[1]:],
        skip_special_tokens=True
    )

    return response


# ============================================================================
# GRADIO INTERFACE
# ============================================================================
demo = gr.ChatInterface(
    generate_response,
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
            maximum=2048,
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
    # IMPORTANT: Examples must be nested lists in Gradio 5.x!
    examples=[
        ["Hello! How are you today?"],
        ["Can you help me write a Python function?"],
        ["Explain this code to me."],
    ],
)

if __name__ == "__main__":
    demo.launch()
