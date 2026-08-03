# Inference Providers — when not to host the model

Some Spaces don't need a GPU at all. If the model is available through HF Inference Providers (Cerebras, Fireworks, Together, Replicate, OpenRouter, etc.), the Space can be a thin Gradio shell that proxies to a hosted endpoint:

- Zero VRAM, no real work inside `@spaces.GPU`, no model download.
- Works for models too large to fit on ZeroGPU (120B+).
- No GPU at all — see [Hardware](#hardware) below for which flavor to pick.

## When to use this pattern

- **Stateless chat or text completion** with a big model.
- **The user wants a public demo of a frontier-scale model** that obviously doesn't fit on a single 48 GB MIG.
- **The user wants to ship something fast** without worrying about quantization / sharding.

## When NOT to use this pattern

- The model isn't available on any Inference Provider. Check with:
  ```bash
  curl "https://huggingface.co/api/models/<ns>/<repo>?expand[]=inferenceProviderMapping"
  ```
- The Space needs **custom decoding** (special sampling, tool use, retrieval, anything stateful or interactive across calls).
- The Space needs **multimodal** beyond what the provider exposes.
- The user explicitly wants to own the inference stack (model loading, decoding, performance tuning).

For those, host the model yourself on ZeroGPU — see [`zerogpu.md`](zerogpu.md).

## Two billing modes

Choose based on who pays for inference.

### Mode A — Space creator pays (simple)

Set `HF_TOKEN` as a Space secret. The Space uses `InferenceClient` directly. Every visitor's call is billed to the Space creator's account.

```python
import os, gradio as gr
from huggingface_hub import InferenceClient

client = InferenceClient(api_key=os.environ["HF_TOKEN"], provider="fireworks-ai")

def chat(msg, history):
    return client.chat_completion(
        model="<org>/<model>",
        messages=[*history, {"role": "user", "content": msg}],
        max_tokens=512,
    ).choices[0].message.content

gr.ChatInterface(chat).launch()
```

Use when you want users to "just click and try it" — no sign-in friction. Cost is on you.

### Mode B — Visitor pays (recommended for public demos)

`gr.LoginButton` + `gr.load("models/...")` with `accept_token=button`. Each visitor signs in with their HF account; inference is billed to **their** account.

```python
import gradio as gr

with gr.Blocks(fill_height=True) as demo:
    with gr.Sidebar():
        button = gr.LoginButton("Sign in")
    gr.load("models/<org>/<model>", accept_token=button, provider="fireworks-ai")
demo.launch()
```

README frontmatter needs:

```yaml
hf_oauth: true
hf_oauth_scopes:
  - inference-api
```

This is the **recommended pattern for public demos** — sustainable cost-wise, and visitors get to use their own provider quotas (which most have paid for or get free).

## Hardware

No GPU needed, so `cpu-basic` is the natural fit — but it requires a paid plan.

On a free account, create the Space with `--flavor zero-a10g` instead. ZeroGPU refuses to start without at least one decorated function, so add a no-op one and leave the provider calls outside it:

```python
import spaces

@spaces.GPU(duration=1)
def _noop():  # ZeroGPU requires ≥1 decorated function; never called
    pass
```

Nothing ever requests a GPU, so no quota is burned. Just remember the Space still counts against the free 2-Space ZeroGPU cap — don't spend a slot here if the user is saving it for a real GPU demo.

## Anti-pattern: `@spaces.GPU` wrapping a provider call

If you do use Inference Providers, do **not** wrap the call in `@spaces.GPU`. The decorator reserves a GPU slot on your Space for the full `duration=`, but the function does no GPU work — just an HTTP call out. You burn your own ZeroGPU quota for nothing.

Whatever hardware a provider-proxy Space sits on, no provider call belongs inside `@spaces.GPU`.
