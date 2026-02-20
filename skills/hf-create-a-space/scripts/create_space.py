#!/usr/bin/env python3
"""
Create a new Hugging Face Space with proper configuration.

Usage:
    python create_space.py <space_name> --sdk gradio --hardware cpu-basic
    python create_space.py my-demo --sdk streamlit --private
"""

import argparse
import os
from huggingface_hub import create_repo, upload_file, HfApi


SPACE_TEMPLATE_README = """---
title: {title}
emoji: {emoji}
colorFrom: {color_from}
colorTo: {color_to}
sdk: {sdk}
sdk_version: {sdk_version}
app_file: app.py
pinned: false
license: mit
short_description: {description}
---

# {title}

{description}

## Usage

Describe how to use your Space here.

## Model

Describe the model(s) used in this Space.
"""

GRADIO_TEMPLATE = '''import gradio as gr

def greet(name: str) -> str:
    """Simple greeting function."""
    return f"Hello, {name}! Welcome to this Hugging Face Space."

demo = gr.Interface(
    fn=greet,
    inputs=gr.Textbox(label="Your Name", placeholder="Enter your name..."),
    outputs=gr.Textbox(label="Greeting"),
    title="My Gradio Space",
    description="A simple demo Space. Replace this with your own functionality!",
    examples=[["World"], ["Hugging Face"]],
)

if __name__ == "__main__":
    demo.launch()
'''

STREAMLIT_TEMPLATE = '''import streamlit as st

st.set_page_config(page_title="My Space", page_icon="🤗")

st.title("🤗 My Streamlit Space")

st.write("Welcome to this Hugging Face Space!")

name = st.text_input("Enter your name:", placeholder="Your name...")

if name:
    st.success(f"Hello, {name}! Welcome to this Space.")

st.markdown("---")
st.markdown("Replace this template with your own functionality!")
'''

DOCKER_TEMPLATE = '''import gradio as gr

def greet(name: str) -> str:
    return f"Hello from Docker, {name}!"

demo = gr.Interface(fn=greet, inputs="text", outputs="text")

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
'''

DOCKERFILE_TEMPLATE = '''FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 7860

CMD ["python", "app.py"]
'''

REQUIREMENTS = {
    "gradio": "gradio>=4.0.0\nhuggingface_hub>=0.26.0\n",
    "streamlit": "streamlit>=1.28.0\nhuggingface_hub>=0.26.0\n",
    "docker": "gradio>=4.0.0\nhuggingface_hub>=0.26.0\n",
}

SDK_VERSIONS = {
    "gradio": "4.44.0",
    "streamlit": "1.40.0",
    "docker": None,
}

EMOJIS = ["🚀", "🤖", "🔥", "✨", "💡", "🎯", "🌟", "⚡", "🎨", "🧠"]
COLORS = ["red", "yellow", "green", "blue", "indigo", "purple", "pink", "gray"]


def create_space(
    space_name: str,
    sdk: str = "gradio",
    hardware: str = "cpu-basic",
    private: bool = False,
    description: str = "A Hugging Face Space",
    emoji: str = "🚀",
    color_from: str = "blue",
    color_to: str = "purple",
    organization: str | None = None,
) -> str:
    """Create a new Hugging Face Space with all necessary files."""

    api = HfApi()
    user = api.whoami()
    username = organization or user["name"]
    repo_id = f"{username}/{space_name}"

    print(f"Creating Space: {repo_id}")
    print(f"  SDK: {sdk}")
    print(f"  Hardware: {hardware}")
    print(f"  Private: {private}")

    # Create the Space repository
    create_repo(
        repo_id=repo_id,
        repo_type="space",
        space_sdk=sdk,
        space_hardware=hardware if hardware != "cpu-basic" else None,
        private=private,
        exist_ok=False,
    )
    print(f"✓ Created repository: {repo_id}")

    # Generate README.md
    readme_content = SPACE_TEMPLATE_README.format(
        title=space_name.replace("-", " ").title(),
        emoji=emoji,
        color_from=color_from,
        color_to=color_to,
        sdk=sdk,
        sdk_version=SDK_VERSIONS.get(sdk, ""),
        description=description,
    )

    # Upload README.md
    upload_file(
        path_or_fileobj=readme_content.encode(),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="space",
    )
    print("✓ Uploaded README.md")

    # Upload app file
    if sdk == "gradio":
        app_content = GRADIO_TEMPLATE
    elif sdk == "streamlit":
        app_content = STREAMLIT_TEMPLATE
    elif sdk == "docker":
        app_content = DOCKER_TEMPLATE
    else:
        app_content = GRADIO_TEMPLATE

    upload_file(
        path_or_fileobj=app_content.encode(),
        path_in_repo="app.py",
        repo_id=repo_id,
        repo_type="space",
    )
    print("✓ Uploaded app.py")

    # Upload requirements.txt
    requirements_content = REQUIREMENTS.get(sdk, REQUIREMENTS["gradio"])
    upload_file(
        path_or_fileobj=requirements_content.encode(),
        path_in_repo="requirements.txt",
        repo_id=repo_id,
        repo_type="space",
    )
    print("✓ Uploaded requirements.txt")

    # Upload Dockerfile for Docker SDK
    if sdk == "docker":
        upload_file(
            path_or_fileobj=DOCKERFILE_TEMPLATE.encode(),
            path_in_repo="Dockerfile",
            repo_id=repo_id,
            repo_type="space",
        )
        print("✓ Uploaded Dockerfile")

    space_url = f"https://huggingface.co/spaces/{repo_id}"
    print(f"\n✅ Space created successfully!")
    print(f"   URL: {space_url}")
    print(f"\n   Clone with: git clone https://huggingface.co/spaces/{repo_id}")

    return space_url


def main():
    parser = argparse.ArgumentParser(
        description="Create a new Hugging Face Space",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python create_space.py my-demo
    python create_space.py my-demo --sdk streamlit
    python create_space.py my-demo --sdk gradio --hardware t4-small
    python create_space.py my-demo --private --org my-organization
        """,
    )

    parser.add_argument("name", help="Name of the Space (e.g., my-awesome-demo)")
    parser.add_argument(
        "--sdk",
        choices=["gradio", "streamlit", "docker"],
        default="gradio",
        help="SDK to use (default: gradio)",
    )
    parser.add_argument(
        "--hardware",
        choices=[
            "cpu-basic",
            "cpu-upgrade",
            "t4-small",
            "t4-medium",
            "a10g-small",
            "a10g-large",
            "a100-large",
        ],
        default="cpu-basic",
        help="Hardware tier (default: cpu-basic)",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Make the Space private",
    )
    parser.add_argument(
        "--description",
        default="A Hugging Face Space",
        help="Short description of the Space",
    )
    parser.add_argument(
        "--emoji",
        default="🚀",
        help="Emoji for the Space card",
    )
    parser.add_argument(
        "--org",
        dest="organization",
        help="Organization to create the Space under",
    )

    args = parser.parse_args()

    # Check for HF token
    if not os.environ.get("HF_TOKEN") and not os.path.exists(
        os.path.expanduser("~/.cache/huggingface/token")
    ):
        print("Error: No Hugging Face token found.")
        print("Please set HF_TOKEN environment variable or run `huggingface-cli login`")
        return 1

    try:
        create_space(
            space_name=args.name,
            sdk=args.sdk,
            hardware=args.hardware,
            private=args.private,
            description=args.description,
            emoji=args.emoji,
            organization=args.organization,
        )
    except Exception as e:
        print(f"Error creating Space: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
