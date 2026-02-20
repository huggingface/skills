"""Depth Estimation with {model_id}"""
import gradio as gr
from transformers import pipeline
import numpy as np
from PIL import Image

MODEL_ID = "{model_id}"

# Load depth estimation pipeline
depth_estimator = pipeline("depth-estimation", model=MODEL_ID)


def estimate_depth(image, colormap):
    """Estimate depth from a single image."""
    if image is None:
        return None

    # Run depth estimation
    result = depth_estimator(image)
    depth = result["depth"]

    # Convert to numpy array
    depth_array = np.array(depth)

    # Normalize to 0-255
    depth_normalized = ((depth_array - depth_array.min()) /
                        (depth_array.max() - depth_array.min()) * 255).astype(np.uint8)

    # Apply colormap
    if colormap == "Grayscale":
        depth_colored = Image.fromarray(depth_normalized)
    else:
        import matplotlib.pyplot as plt
        cmap = plt.get_cmap(colormap.lower())
        depth_colored = (cmap(depth_normalized / 255.0)[:, :, :3] * 255).astype(np.uint8)
        depth_colored = Image.fromarray(depth_colored)

    return depth_colored


demo = gr.Interface(
    fn=estimate_depth,
    inputs=[
        gr.Image(type="pil", label="Upload Image"),
        gr.Radio(
            choices=["Grayscale", "Viridis", "Plasma", "Inferno", "Magma"],
            value="Viridis",
            label="Colormap",
        ),
    ],
    outputs=gr.Image(label="Depth Map"),
    title="{title}",
    description="Estimate depth from a single image using {model_id}. Brighter = closer, darker = farther.",
    examples=[],
)

if __name__ == "__main__":
    demo.launch()
