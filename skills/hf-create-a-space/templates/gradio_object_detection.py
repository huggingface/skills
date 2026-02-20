"""Object Detection with {model_id}"""
import gradio as gr
from transformers import pipeline
from PIL import Image, ImageDraw, ImageFont

MODEL_ID = "{model_id}"

# Load object detection pipeline
detector = pipeline("object-detection", model=MODEL_ID)


def detect_objects(image, threshold):
    """Detect objects in an image and draw bounding boxes."""
    if image is None:
        return None, "Please upload an image"

    # Run detection
    results = detector(image, threshold=threshold)

    if not results:
        return image, "No objects detected above threshold"

    # Draw bounding boxes on image
    draw = ImageDraw.Draw(image)

    # Generate colors for different labels
    labels = list(set(r["label"] for r in results))
    colors = {{}}
    for i, label in enumerate(labels):
        # Generate distinct colors
        hue = i / len(labels)
        import colorsys
        rgb = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
        colors[label] = tuple(int(c * 255) for c in rgb)

    # Draw each detection
    detections_text = []
    for result in results:
        box = result["box"]
        label = result["label"]
        score = result["score"]

        # Draw rectangle
        draw.rectangle(
            [box["xmin"], box["ymin"], box["xmax"], box["ymax"]],
            outline=colors[label],
            width=3
        )

        # Draw label
        label_text = f"{{label}} ({{score:.2f}})"
        draw.text((box["xmin"], box["ymin"] - 15), label_text, fill=colors[label])

        detections_text.append(f"{{label}}: {{score:.2%}}")

    summary = f"Detected {{len(results)}} object(s):\\n" + "\\n".join(detections_text)
    return image, summary


demo = gr.Interface(
    fn=detect_objects,
    inputs=[
        gr.Image(type="pil", label="Upload Image"),
        gr.Slider(0.1, 0.9, value=0.5, step=0.05, label="Confidence Threshold"),
    ],
    outputs=[
        gr.Image(label="Detections"),
        gr.Textbox(label="Results", lines=5),
    ],
    title="{title}",
    description="Detect objects in images using {model_id}",
    examples=[],
)

if __name__ == "__main__":
    demo.launch()
