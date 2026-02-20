---
name: hf-create-a-space
description: Create and deploy Hugging Face Spaces for ML models. Supports Gradio chat interfaces via Inference API (for supported models) or ZeroGPU (for any model). Guides you through deployment method selection and potential compatibility issues.
---

# HF Create a Space

Create and deploy Hugging Face Spaces for ML models with guided deployment method selection.

## When to Use This Skill

Use this skill when:
- A user wants to create a demo/Space for a HuggingFace model
- A user has fine-tuned a model and wants to showcase it
- A user wants to deploy a LoRA adapter with a base model
- A user needs help choosing between Inference API and ZeroGPU

## Key Workflow: ASK DEPLOYMENT METHOD FIRST

**CRITICAL: Before generating any code, ASK the user:**

> "How do you want to deploy this model?"
>
> 1. **Inference API** - Free, no GPU needed, but model must be supported by HF's serverless inference
> 2. **ZeroGPU** - Free with quota, loads model directly on GPU, works with any model

This choice determines the entire template structure. The two approaches are NOT interchangeable.

## Deployment Method Comparison

| Feature | Inference API | ZeroGPU |
|---------|--------------|---------|
| Cost | Free | Free (with quota) |
| Hardware | cpu-basic | zero-a10g (H200) |
| Model Support | Major providers only | Any model |
| LoRA Adapters | Never works | Fully supported |
| Fine-tuned models | Rarely works | Fully supported |
| Code Pattern | `InferenceClient` | `@spaces.GPU` + transformers |
| PRO Required | No | Yes (to host) |

## Quick Compatibility Checks

### For Inference API

Before recommending Inference API, verify:

**Likely to work:**
- Model is from major provider: `Qwen/`, `meta-llama/`, `mistralai/`, `google/`, `HuggingFaceH4/`
- Model page shows "Inference Providers" widget
- High download count (>10,000)

**Will NOT work:**
- Personal/fine-tuned models (e.g., `username/my-model`)
- LoRA adapters (NEVER work with Inference API)
- Models without `pipeline_tag` metadata

**Requires HF_TOKEN:**
- Gated models: `meta-llama/`, `mistralai/Mistral-`, `google/gemma-`

### For ZeroGPU

**Technical Specs:**
- GPU: Nvidia H200 slice with **70GB VRAM**
- SDK: **Gradio only** (not Streamlit or Docker)
- PyTorch: 2.1.0 to latest supported
- Python: 3.10.13

**Model Size Considerations:**
| Size | Compatibility | Notes |
|------|--------------|-------|
| < 3B params | Excellent | Fast loading, default duration=60 is fine |
| 3B - 7B params | Good | Use `duration=120` |
| 7B - 13B params | Possible | Use `duration=120`, may hit limits |
| > 13B params | Difficult | Likely OOM even with 70GB, consider quantization |

**Duration Parameter (IMPORTANT):**
- Default: **60 seconds** - function must complete within this time
- For larger models or longer generation: use `@spaces.GPU(duration=120)`
- Can use dynamic duration: `@spaces.GPU(duration=get_duration_func)`

**Usage Quotas (Daily):**
| Account Type | Daily Quota | Queue Priority |
|--------------|-------------|----------------|
| Unauthenticated | 2 min | Low |
| Free account | 3.5 min | Medium |
| PRO account | 25 min | Highest |
| Enterprise | 45 min | Highest |

**Limitations:**
- `torch.compile` is **NOT supported** (use ahead-of-time compilation with torch 2.8+)
- Max 10 ZeroGPU Spaces per PRO account
- Max 50 ZeroGPU Spaces per Enterprise org

**Special Cases:**
- **LoRA adapter?** → Needs `peft` dependency, must identify base model
- **Gated model?** → User must accept license + add `HF_TOKEN` secret

## Templates: These Are NOT Interchangeable

### Template 1: Inference API

**Use when:** Model has serverless inference support

```python
import os
import gradio as gr
from huggingface_hub import InferenceClient

MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"

# Token required for gated models (Llama, Mistral, Gemma, etc.)
HF_TOKEN = os.environ.get("HF_TOKEN")
client = InferenceClient(MODEL_ID, token=HF_TOKEN)


def respond(message, history, system_message, max_tokens, temperature, top_p):
    messages = [{"role": "system", "content": system_message}]

    for user_msg, assistant_msg in history:
        if user_msg:
            messages.append({"role": "user", "content": user_msg})
        if assistant_msg:
            messages.append({"role": "assistant", "content": assistant_msg})

    messages.append({"role": "user", "content": message})

    response = ""
    for token in client.chat_completion(
        messages,
        max_tokens=max_tokens,
        stream=True,
        temperature=temperature,
        top_p=top_p,
    ):
        delta = token.choices[0].delta.content or ""
        response += delta
        yield response


demo = gr.ChatInterface(
    respond,
    title="Chat Demo",
    additional_inputs=[
        gr.Textbox(value="You are a helpful assistant.", label="System message"),
        gr.Slider(minimum=1, maximum=4096, value=512, step=1, label="Max tokens"),
        gr.Slider(minimum=0.1, maximum=2.0, value=0.7, step=0.1, label="Temperature"),
        gr.Slider(minimum=0.1, maximum=1.0, value=0.95, step=0.05, label="Top-p"),
    ],
    examples=[["Hello!"], ["Write a poem"]],
)

if __name__ == "__main__":
    demo.launch()
```

**requirements.txt:**
```
gradio>=5.0.0
huggingface_hub>=0.26.0
```

**Hardware:** cpu-basic (free, no configuration needed)

---

### Template 2: ZeroGPU (Full Model)

**Use when:** Model doesn't have Inference API support, OR user wants direct model loading

```python
import gradio as gr
import spaces
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "username/my-finetuned-model"

# Load tokenizer at startup (lightweight)
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

# Model loaded lazily inside GPU context
model = None


def load_model():
    global model
    if model is None:
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.float16,
            device_map="auto",
        )
    return model


@spaces.GPU(duration=120)  # GPU allocated for up to 120 seconds
def generate_response(message, history, system_message, max_tokens, temperature, top_p):
    model = load_model()

    messages = [{"role": "system", "content": system_message}]
    for user_msg, assistant_msg in history:
        if user_msg:
            messages.append({"role": "user", "content": user_msg})
        if assistant_msg:
            messages.append({"role": "assistant", "content": assistant_msg})
    messages.append({"role": "user", "content": message})

    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer([text], return_tensors="pt").to(model.device)

    outputs = model.generate(
        **inputs,
        max_new_tokens=int(max_tokens),
        temperature=temperature,
        top_p=top_p,
        do_sample=True,
        pad_token_id=tokenizer.eos_token_id,
    )

    response = tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
    return response


demo = gr.ChatInterface(
    generate_response,
    title="Chat Demo",
    additional_inputs=[
        gr.Textbox(value="You are a helpful assistant.", label="System message"),
        gr.Slider(minimum=1, maximum=2048, value=512, step=1, label="Max tokens"),
        gr.Slider(minimum=0.1, maximum=2.0, value=0.7, step=0.1, label="Temperature"),
        gr.Slider(minimum=0.1, maximum=1.0, value=0.95, step=0.05, label="Top-p"),
    ],
    examples=[["Hello!"], ["Write a poem"]],
)

if __name__ == "__main__":
    demo.launch()
```

**requirements.txt:**
```
gradio>=5.0.0
torch
transformers
accelerate
spaces
```

**Hardware:** Must set to `ZeroGPU` in Space Settings after deployment!

---

### Template 3: ZeroGPU (LoRA Adapter)

**Use when:** Model is a LoRA/PEFT adapter

```python
import gradio as gr
import spaces
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

ADAPTER_ID = "username/my-lora-adapter"
BASE_MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"  # From adapter_config.json

tokenizer = AutoTokenizer.from_pretrained(ADAPTER_ID)
model = None


def load_model():
    global model
    if model is None:
        base_model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL_ID,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        peft_model = PeftModel.from_pretrained(base_model, ADAPTER_ID)
        model = peft_model.merge_and_unload()
    return model


@spaces.GPU(duration=120)
def generate_response(message, history, system_message, max_tokens, temperature, top_p):
    model = load_model()
    # ... same generation code as Template 2 ...


demo = gr.ChatInterface(generate_response, ...)

if __name__ == "__main__":
    demo.launch()
```

---

## ZeroGPU Best Practices

### Model Loading Patterns

**Pattern 1: Lazy Loading (Recommended for chat models)**
```python
model = None

def load_model():
    global model
    if model is None:
        model = AutoModelForCausalLM.from_pretrained(..., device_map="auto")
    return model

@spaces.GPU(duration=120)
def generate(prompt):
    model = load_model()
    # ... use model ...
```

**Pattern 2: Eager Loading (From HF docs, good for diffusion)**
```python
pipe = DiffusionPipeline.from_pretrained(...)
pipe.to('cuda')

@spaces.GPU
def generate(prompt):
    return pipe(prompt).images
```

### Duration Tips

```python
# Default: 60 seconds - fine for small models
@spaces.GPU
def quick_inference(x):
    ...

# For 7B+ models or long generation
@spaces.GPU(duration=120)
def longer_inference(x):
    ...

# Dynamic duration based on input
def calc_duration(prompt, max_tokens):
    return min(60 + (max_tokens // 100) * 10, 120)

@spaces.GPU(duration=calc_duration)
def dynamic_inference(prompt, max_tokens):
    ...
```

### Things That Don't Work on ZeroGPU

1. **`torch.compile()`** - Use ahead-of-time compilation (torch 2.8+) instead
2. **Streamlit/Docker SDK** - ZeroGPU is Gradio-only
3. **Persistent GPU state between requests** - GPU is released after each call

**requirements.txt:**
```
gradio>=5.0.0
torch
transformers
accelerate
spaces
peft
```

## Post-Deployment Checklist

### For Inference API Deployments
- [ ] Space builds successfully
- [ ] If gated model: Add `HF_TOKEN` as Repository Secret

### For ZeroGPU Deployments
- [ ] Go to Space Settings
- [ ] Set hardware to "ZeroGPU" (requires PRO subscription)
- [ ] If gated model: Add `HF_TOKEN` as Repository Secret
- [ ] Wait for build to complete

## Troubleshooting Reference

| Error | Likely Cause | Fix |
|-------|--------------|-----|
| `No @spaces.GPU function detected` | Inference API code running on ZeroGPU hardware | Switch to ZeroGPU template (Template 2 or 3) |
| `No API found` (Inference API) | Model doesn't support serverless inference | Use ZeroGPU instead |
| `No API found` (gated model) | Missing HF_TOKEN | Add HF_TOKEN secret in Space Settings |
| Model not loading | Wrong template for model type | Check if LoRA vs full model |
| `OSError: does not appear to have...safetensors` | LoRA adapter loaded as full model | Use Template 3 with PEFT |
| Out of memory | Model too large for hardware | Reduce max_tokens, use quantization, or larger GPU |
| Build succeeds but app errors | Hardware not set | Set hardware to ZeroGPU in Settings |
| `ImportError: cannot import name 'HfFolder'` | Version mismatch | Use gradio>=5.0.0, huggingface_hub>=0.26.0 |
| Function timeout / killed | Exceeded duration limit | Add `@spaces.GPU(duration=120)` for longer ops |
| `torch.compile` errors | Not supported on ZeroGPU | Remove torch.compile or use ahead-of-time compilation |
| Quota exceeded | Daily GPU quota used up | Wait for reset or upgrade to PRO (25 min/day) |

## Decision Flowchart

```
User wants to deploy model
│
├─→ ASK: "How do you want to deploy?"
│
├─→ User chooses INFERENCE API
│   │
│   ├─→ Check: Is model from major provider?
│   │   ├─→ YES → Proceed with Template 1
│   │   └─→ NO → Warn: "This model may not have Inference API support"
│   │
│   ├─→ Check: Is it a LoRA adapter?
│   │   └─→ YES → STOP: "LoRA adapters don't work with Inference API. Use ZeroGPU."
│   │
│   └─→ Check: Is model gated?
│       └─→ YES → Add note: "You'll need to add HF_TOKEN secret"
│
└─→ User chooses ZEROGPU
    │
    ├─→ Check: Is it a LoRA adapter?
    │   ├─→ YES → Use Template 3, identify base model
    │   └─→ NO → Use Template 2
    │
    ├─→ Check: Model size?
    │   └─→ > 7B → Warn about potential memory limits
    │
    └─→ Check: Is model gated?
        └─→ YES → Add note: "You'll need to add HF_TOKEN secret"
```

## Scripts Reference

### deploy_model.py

```bash
# Deploy with Inference API
python scripts/deploy_model.py MODEL_ID --type chat --method inference-api

# Deploy with ZeroGPU
python scripts/deploy_model.py MODEL_ID --type chat --method zerogpu

# Dry run to preview
python scripts/deploy_model.py MODEL_ID --type chat --dry-run
```

### manage_space.py

```bash
# Set hardware
python scripts/manage_space.py hardware username/space --tier zero-a10g

# Add secret
python scripts/manage_space.py secret username/space --key HF_TOKEN --value hf_xxx

# Restart space
python scripts/manage_space.py restart username/space
```

## Common Scenarios

### Scenario 1: Deploy Llama 3.1 (Gated, Inference API supported)

```
User: "Deploy meta-llama/Llama-3.1-8B-Instruct as a chat Space"

Response:
1. This model supports Inference API. Do you want to use:
   - Inference API (free, simple) - Recommended for this model
   - ZeroGPU (loads model directly)

2. Note: This is a gated model. After deployment:
   - Accept license at https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct
   - Add HF_TOKEN secret in Space Settings
```

### Scenario 2: Deploy a Fine-tuned Model (No Inference API)

```
User: "Deploy username/my-finetuned-llama as a chat Space"

Response:
1. This appears to be a personal/fine-tuned model. These typically don't have Inference API support.
   Recommended: ZeroGPU

2. Requirements:
   - PRO subscription to host ZeroGPU Space
   - Set hardware to ZeroGPU in Space Settings after deployment
```

### Scenario 3: Deploy a LoRA Adapter

```
User: "Deploy username/my-lora-adapter as a chat Space"

Response:
1. This is a LoRA adapter. LoRA adapters ONLY work with ZeroGPU (not Inference API).

2. I found the base model in adapter_config.json: Qwen/Qwen2.5-Coder-1.5B-Instruct

3. Using Template 3 (ZeroGPU + PEFT)
```
