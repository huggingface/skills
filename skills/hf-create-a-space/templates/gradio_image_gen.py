"""
Gradio Text-to-Image Template

A ready-to-use image generation interface.
Uses Hugging Face Inference API for serverless generation.
"""

import gradio as gr
from huggingface_hub import InferenceClient

# ============================================================================
# CONFIGURATION - Modify these values
# ============================================================================
MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"  # Change to your model
TITLE = "Image Generator"
DESCRIPTION = "Generate images from text descriptions using Stable Diffusion."

# ============================================================================
# APPLICATION CODE - Modify if needed
# ============================================================================
client = InferenceClient()


def generate(
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    guidance_scale: float,
    num_steps: int,
):
    """Generate an image from the prompt."""
    if not prompt.strip():
        return None

    image = client.text_to_image(
        prompt,
        negative_prompt=negative_prompt if negative_prompt.strip() else None,
        model=MODEL_ID,
        width=width,
        height=height,
        guidance_scale=guidance_scale,
        num_inference_steps=num_steps,
    )
    return image


# Build the Gradio interface
with gr.Blocks(title=TITLE) as demo:
    gr.Markdown(f"# {TITLE}")
    gr.Markdown(DESCRIPTION)

    with gr.Row():
        with gr.Column(scale=1):
            prompt = gr.Textbox(
                label="Prompt",
                placeholder="A majestic castle on a floating island in the sky...",
                lines=3,
            )
            negative_prompt = gr.Textbox(
                label="Negative Prompt",
                placeholder="blurry, low quality, distorted, ugly",
                lines=2,
            )

            with gr.Row():
                width = gr.Slider(512, 1024, value=1024, step=64, label="Width")
                height = gr.Slider(512, 1024, value=1024, step=64, label="Height")

            with gr.Row():
                guidance_scale = gr.Slider(
                    1, 20, value=7.5, step=0.5, label="Guidance Scale"
                )
                num_steps = gr.Slider(10, 50, value=30, step=1, label="Steps")

            generate_btn = gr.Button("Generate", variant="primary")

        with gr.Column(scale=1):
            output_image = gr.Image(label="Generated Image", type="pil")

    # Example prompts
    gr.Examples(
        examples=[
            ["A serene Japanese garden with cherry blossoms and a koi pond", ""],
            ["A cyberpunk cityscape at night with neon lights", "blurry, low quality"],
            ["A cozy cabin in a snowy forest with warm light from windows", ""],
            ["An astronaut riding a horse on Mars, digital art", "photorealistic"],
        ],
        inputs=[prompt, negative_prompt],
    )

    generate_btn.click(
        generate,
        inputs=[prompt, negative_prompt, width, height, guidance_scale, num_steps],
        outputs=output_image,
    )

if __name__ == "__main__":
    demo.launch()
