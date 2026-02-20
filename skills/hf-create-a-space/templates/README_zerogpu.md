---
title: {{TITLE}}
emoji: {{EMOJI}}
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 5.9.1
app_file: app.py
pinned: false
license: apache-2.0
short_description: {{SHORT_DESCRIPTION}}
suggested_hardware: zero-a10g
---

# {{TITLE}}

{{DESCRIPTION}}

## Model

This Space uses [{{MODEL_ID}}](https://huggingface.co/{{MODEL_ID}}).

## How It Works

This Space uses **ZeroGPU** - a free GPU allocation system:
- The app runs on CPU by default (free)
- When you send a message, a GPU is allocated on-demand
- After generation completes, the GPU is released
- You get a daily quota of free GPU time

## Usage

Simply type your message in the chat box and press Enter!

## License

{{LICENSE}}
