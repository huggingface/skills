---
name: huggingface-spaces
description: Find and call Hugging Face Spaces to generate AI artifacts (images, audio, 3D models, etc). Uses semantic search to discover Spaces, then calls their Gradio APIs.
user-invocable: true
allowed-tools: Bash WebFetch Read Write
argument-hint: <prompt describing what to generate>
---

# Hugging Face Spaces Tool

You have access to thousands of AI apps hosted on Hugging Face Spaces. Use them to generate artifacts like images, audio, 3D models, videos, text, and more.

## Authentication

Install the latest `hf` CLI and log in:

```bash
curl -LsSf https://hf.co/cli/install.sh | bash
hf auth login
```

Always include the user's HF token in API requests:
- **REST calls**: `Authorization: Bearer $(hf auth token)`
- **Python client**: `Client("space-url", hf_token=subprocess.check_output(["hf", "auth", "token"]).decode().strip())`

## Workflow

### Step 1: Find the right Space

Use the `hf` CLI to search for a Space matching the user's request:

```bash
hf spaces search --sdk gradio "<search query>"
```

- Always filter by `--sdk gradio` (only Gradio spaces have callable APIs)
- The output lists Space IDs sorted by relevance with descriptions
- Prefer spaces that are running and have high trending scores
- The space domain is derived from the `id`: `owner-spacename.hf.space` (replace `/` with `-`, lowercase)

### Step 2: Call the Space

Fetch the Space's `agents.md` and follow its instructions to call the Space:

```bash
curl https://huggingface.co/spaces/<owner>/<spacename>/agents.md
```

This returns a Markdown document with everything needed to call the Space: available endpoints, parameters, input/output types, and usage examples — purpose-built for agents like this one.

### Step 3: Handle the output

- **Files (images, audio, 3D models)**: Download from the returned URL and save locally
- **Open/play the result**: Use `open <file>` (macOS) or `afplay <file>` (audio)
- File URLs from Gradio look like: `https://<space>.hf.space/gradio_api/file=<path>`

## Tips

- Read `agents.md` carefully — it often documents exact parameter names, accepted values, and example calls
- For the Python client, use `handle_file("/path/to/file")` or `handle_file("https://url")` for file/image inputs
- ZeroGPU spaces have usage quotas — if you get "GPU quota exceeded", wait or try another space
- Multi-step pipelines (e.g., image-to-3D) often require session state — use the Python client
- If a user provides a specific Space URL, skip the search step and use it directly

## Examples

**User says**: "generate an image of a sunset"
1. Search: `hf spaces search --sdk gradio "text to image generation"`
2. Pick a top result (e.g., `mrfakename/Z-Image-Turbo`)
3. Fetch `agents.md`, follow its instructions, download and open the result

**User says**: "convert this image to 3D"
1. Search: `hf spaces search --sdk gradio "image to 3d model"`
2. Pick a result (e.g., a Trellis space)
3. Fetch `agents.md` and follow its instructions

**User says**: "say hello world in speech"
1. Search: `hf spaces search --sdk gradio "text to speech"`
2. Pick a TTS space, call the generate endpoint, download and play the audio
