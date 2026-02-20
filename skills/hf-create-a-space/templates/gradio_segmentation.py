"""Image Segmentation with {model_id}"""
import gradio as gr
from transformers import pipeline
from PIL import Image
import numpy as np

MODEL_ID = "{model_id}"

# Load segmentation pipeline
segmenter = pipeline("image-segmentation", model=MODEL_ID)


def segment_image(image):
    """Segment an image into different regions."""
    if image is None:
        return None, "Please upload an image"

    # Run segmentation
    results = segmenter(image)

    if not results:
        return image, "No segments detected"

    # Create colored segmentation mask
    # Combine all masks into one visualization
    width, height = image.size
    combined_mask = np.zeros((height, width, 3), dtype=np.uint8)

    segments_text = []
    for i, result in enumerate(results):
        label = result.get("label", f"Segment {{i}}")
        score = result.get("score", 1.0)
        mask = result.get("mask")

        if mask is not None:
            # Convert mask to numpy if needed
            if hasattr(mask, "numpy"):
                mask_array = np.array(mask)
            else:
                mask_array = np.array(mask)

            # Generate color for this segment
            import colorsys
            hue = i / max(len(results), 1)
            rgb = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
            color = tuple(int(c * 255) for c in rgb)

            # Apply color to mask
            if len(mask_array.shape) == 2:
                for c in range(3):
                    combined_mask[:, :, c] = np.where(
                        mask_array > 0,
                        color[c],
                        combined_mask[:, :, c]
                    )

            segments_text.append(f"{{label}}: {{score:.2%}}")

    # Blend with original image
    mask_image = Image.fromarray(combined_mask)
    blended = Image.blend(image.convert("RGB"), mask_image, alpha=0.5)

    summary = f"Found {{len(results)}} segment(s):\\n" + "\\n".join(segments_text)
    return blended, summary


demo = gr.Interface(
    fn=segment_image,
    inputs=gr.Image(type="pil", label="Upload Image"),
    outputs=[
        gr.Image(label="Segmentation"),
        gr.Textbox(label="Segments", lines=5),
    ],
    title="{title}",
    description="Segment images into different regions using {model_id}",
    examples=[],
)

if __name__ == "__main__":
    demo.launch()
