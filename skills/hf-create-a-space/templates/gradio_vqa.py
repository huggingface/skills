"""Visual Question Answering with {model_id}"""
import gradio as gr
import spaces
import torch
from transformers import AutoProcessor, AutoModelForVision2Seq
from PIL import Image

MODEL_ID = "{model_id}"

# Load processor at startup
processor = AutoProcessor.from_pretrained(MODEL_ID)

# Global model - loaded lazily
model = None


def load_model():
    global model
    if model is None:
        model = AutoModelForVision2Seq.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.float16,
            device_map="auto",
        )
    return model


@spaces.GPU(duration=90)
def answer_question(image, question):
    """Answer a question about an image."""
    if image is None:
        return "Please upload an image."
    if not question or not question.strip():
        return "Please enter a question."

    model = load_model()

    # Prepare inputs
    inputs = processor(
        images=image,
        text=question,
        return_tensors="pt"
    ).to(model.device, torch.float16)

    # Generate answer
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            do_sample=False,
        )

    # Decode response
    response = processor.decode(outputs[0], skip_special_tokens=True)

    # Remove the question from the response if it's echoed
    if question in response:
        response = response.replace(question, "").strip()

    return response


demo = gr.Interface(
    fn=answer_question,
    inputs=[
        gr.Image(type="pil", label="Upload Image"),
        gr.Textbox(label="Question", placeholder="What do you see in this image?"),
    ],
    outputs=gr.Textbox(label="Answer", lines=5),
    title="{title}",
    description="Ask questions about images using {model_id} (powered by ZeroGPU)",
    examples=[
        [None, "What objects are in this image?"],
        [None, "Describe this image in detail."],
    ],
)

if __name__ == "__main__":
    demo.launch()
