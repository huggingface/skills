"""Image-to-Image generation with {model_id}"""
import gradio as gr
from huggingface_hub import InferenceClient

MODEL_ID = "{model_id}"
client = InferenceClient()


def transform_image(image, prompt, negative_prompt, strength, guidance_scale, num_steps):
    """Transform an image based on a text prompt."""
    if image is None:
        raise gr.Error("Please upload an image")
    if not prompt or not prompt.strip():
        raise gr.Error("Please enter a prompt")

    try:
        result = client.image_to_image(
            image=image,
            prompt=prompt,
            negative_prompt=negative_prompt or None,
            model=MODEL_ID,
            strength=strength,
            guidance_scale=guidance_scale,
            num_inference_steps=num_steps,
        )
        return result
    except Exception as e:
        raise gr.Error(f"Image transformation failed: {e}")


demo = gr.Interface(
    fn=transform_image,
    inputs=[
        gr.Image(type="pil", label="Input Image"),
        gr.Textbox(label="Prompt", placeholder="Describe the transformation..."),
        gr.Textbox(label="Negative Prompt", placeholder="What to avoid..."),
        gr.Slider(0.1, 1.0, value=0.8, step=0.05, label="Strength (how much to change)"),
        gr.Slider(1, 20, value=7.5, step=0.5, label="Guidance Scale"),
        gr.Slider(10, 50, value=30, step=1, label="Steps"),
    ],
    outputs=gr.Image(label="Transformed Image"),
    title="{title}",
    description="Transform images using {model_id}. Higher strength = more change from original.",
)

if __name__ == "__main__":
    demo.launch()
