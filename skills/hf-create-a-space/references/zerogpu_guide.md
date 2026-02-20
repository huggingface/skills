# ZeroGPU Complete Guide

Everything you need to know about using ZeroGPU on Hugging Face Spaces.

## What is ZeroGPU?

ZeroGPU is a shared GPU infrastructure that provides free on-demand GPU access for Hugging Face Spaces. Instead of dedicating a GPU to your Space 24/7, ZeroGPU dynamically allocates an NVIDIA H200 GPU slice only when your code needs it.

## Key Benefits

1. **Free GPU access** - No per-hour charges (PRO subscription required to host)
2. **70GB VRAM** - H200 slice provides significant GPU memory
3. **On-demand allocation** - Pay nothing when idle
4. **Efficient sharing** - Better resource utilization across HF

## Requirements

### To HOST a ZeroGPU Space

| Account Type | Can Host? | Max Spaces |
|--------------|-----------|------------|
| Free | No | 0 |
| PRO ($9/month) | Yes | 10 |
| Team/Enterprise | Yes | 50 |

### To USE a ZeroGPU Space (as visitor)

Anyone can use ZeroGPU Spaces, with daily quotas:

| Account Type | Daily Quota |
|--------------|-------------|
| Unauthenticated | 2 minutes |
| Free account | 3.5 minutes |
| PRO | 25 minutes |
| Team/Enterprise | 25-45 minutes |

## Technical Specifications

- **GPU**: NVIDIA H200 slice
- **VRAM**: 70GB available per workload
- **SDK**: Gradio only (Streamlit/Docker not supported)
- **Python**: 3.10.13
- **PyTorch**: 2.1.0 through 2.8.0
- **Default duration**: 60 seconds per call
- **Max duration**: Configurable via decorator

## How to Use ZeroGPU

### 1. Install the spaces package

```
# requirements.txt
gradio>=5.0.0
spaces
torch
transformers
```

### 2. Import and decorate

```python
import spaces

@spaces.GPU
def my_gpu_function(input):
    # GPU is allocated when this function is called
    output = model.generate(input)
    return output
    # GPU is released when function returns
```

### 3. Set duration (optional)

```python
@spaces.GPU(duration=120)  # Allow up to 120 seconds
def slow_generation(input):
    # Long-running GPU operation
    return output
```

### 4. Dynamic duration

```python
def calculate_duration(text, num_steps):
    return min(num_steps * 2, 120)  # Scale with steps, max 120s

@spaces.GPU(duration=calculate_duration)
def generate(text, num_steps):
    return model.generate(text, steps=num_steps)
```

## Code Patterns

### Basic Chat Model

```python
import gradio as gr
import spaces
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "your-model-id"

# Load on CPU at startup (this is free)
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16,
)

@spaces.GPU(duration=120)
def generate(message, history):
    # GPU allocated here
    # Model automatically moved to GPU by spaces library

    inputs = tokenizer(message, return_tensors="pt").to(model.device)
    outputs = model.generate(**inputs, max_new_tokens=512)
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)

    return response
    # GPU released here

demo = gr.ChatInterface(generate)
demo.launch()
```

### Image Generation

```python
import spaces
from diffusers import DiffusionPipeline

pipe = DiffusionPipeline.from_pretrained(
    "stabilityai/stable-diffusion-xl-base-1.0",
    torch_dtype=torch.float16,
)

@spaces.GPU(duration=60)
def generate_image(prompt):
    pipe.to("cuda")
    image = pipe(prompt).images[0]
    return image
```

### LoRA Adapter

```python
import spaces
from transformers import AutoModelForCausalLM
from peft import PeftModel

BASE_MODEL_ID = "meta-llama/Llama-3.1-8B"
ADAPTER_ID = "your-adapter-id"

# Load base model on CPU
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL_ID,
    torch_dtype=torch.float16,
)

# Apply adapter
model = PeftModel.from_pretrained(base_model, ADAPTER_ID)
model = model.merge_and_unload()

tokenizer = AutoTokenizer.from_pretrained(ADAPTER_ID)

@spaces.GPU(duration=120)
def generate(text):
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    outputs = model.generate(**inputs)
    return tokenizer.decode(outputs[0])
```

## Important Limitations

### 1. No torch.compile()

ZeroGPU does not support `torch.compile()`. Use ahead-of-time (AOT) compilation instead:

```python
# DON'T do this with ZeroGPU
model = torch.compile(model)  # Will fail

# DO use AOT compilation for PyTorch 2.8+
# See: https://huggingface.co/blog/zerogpu-aoti
```

### 2. No Streaming

With ZeroGPU, the GPU is held for the entire function duration. You cannot stream tokens because:

```python
# This won't work well with ZeroGPU:
@spaces.GPU
def generate_stream(text):
    for token in model.generate_streaming(...):
        yield token  # GPU held until all tokens done
```

Instead, generate the full response and return it:

```python
@spaces.GPU
def generate(text):
    return model.generate(text)  # Return full response
```

### 3. Gradio Only

ZeroGPU is only compatible with Gradio SDK. Streamlit and Docker Spaces cannot use ZeroGPU.

### 4. Queue Delays

During high demand, there may be wait times for GPU allocation. PRO users get highest priority.

### 5. Duration Limits

If your function exceeds the specified duration, it will be terminated. Set appropriate durations:

```python
# For quick operations (classification, short generation)
@spaces.GPU(duration=30)

# For medium operations (standard generation)
@spaces.GPU(duration=60)  # default

# For slow operations (long generation, large models)
@spaces.GPU(duration=120)
```

## Best Practices

### 1. Load models on CPU at startup

```python
# Good: Load on CPU outside the GPU function
model = AutoModel.from_pretrained(MODEL_ID)

@spaces.GPU
def infer(x):
    return model(x)  # Model moved to GPU automatically
```

### 2. Use appropriate dtypes

```python
# Good: Use float16 to reduce VRAM
model = AutoModel.from_pretrained(MODEL_ID, torch_dtype=torch.float16)
```

### 3. Set realistic durations

```python
# Match duration to expected inference time
@spaces.GPU(duration=30)  # For fast models
def quick_inference(x):
    return model(x)

@spaces.GPU(duration=120)  # For slow models
def slow_inference(x):
    return large_model(x)
```

### 4. Handle errors gracefully

```python
@spaces.GPU
def generate(text):
    try:
        return model.generate(text)
    except RuntimeError as e:
        if "out of memory" in str(e):
            return "Error: Input too long. Please try shorter text."
        raise
```

### 5. Optimize for batch processing if possible

```python
# If you have multiple inputs, batch them
@spaces.GPU
def batch_inference(inputs):
    return model(inputs)  # Single GPU allocation for all inputs
```

## Troubleshooting

### "GPU allocation timed out"

**Cause**: High demand, queue is long
**Fix**: Try again later, or use paid GPU tier

### "Duration exceeded"

**Cause**: Function took longer than specified duration
**Fix**: Increase `@spaces.GPU(duration=X)` or optimize code

### "CUDA out of memory"

**Cause**: Model too large for 70GB VRAM
**Fix**: Use quantization or smaller model

### Model not using GPU

**Cause**: Model loaded outside @spaces.GPU function
**Fix**: The spaces library should auto-move models. Ensure you're using latest version.

### "spaces module not found"

**Cause**: Missing from requirements.txt
**Fix**: Add `spaces` to requirements.txt

## Setting Up a New ZeroGPU Space

### 1. Create Space with Gradio SDK

```bash
hf repo create my-space --repo-type space --space-sdk gradio
```

### 2. Add requirements.txt

```
gradio>=5.0.0
spaces
torch
transformers
accelerate
```

### 3. Create app.py with @spaces.GPU

```python
import gradio as gr
import spaces
# ... your code with @spaces.GPU decorator
```

### 4. Upload to Space

```bash
hf upload username/my-space . --repo-type space
```

### 5. Set hardware to ZeroGPU

Go to Space Settings > Hardware > Select "ZeroGPU"

## Resources

- [Official ZeroGPU Documentation](https://huggingface.co/docs/hub/spaces-zerogpu)
- [ZeroGPU with AOT Compilation](https://huggingface.co/blog/zerogpu-aoti)
- [ZeroGPU Spaces Gallery](https://huggingface.co/spaces/enzostvs/zero-gpu-spaces)
- [Feedback & Discussion](https://huggingface.co/spaces/zero-gpu-explorers/README/discussions)
