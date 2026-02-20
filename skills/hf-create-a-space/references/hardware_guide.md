# Hugging Face Spaces Hardware Guide

Comprehensive reference for hardware options available on Hugging Face Spaces.

## Hardware Tiers Overview

### CPU Tiers

| Tier | vCPU | RAM | Disk | Cost | Best For |
|------|------|-----|------|------|----------|
| **cpu-basic** | 2 | 16GB | 50GB | Free | Inference API apps, simple demos |
| **cpu-upgrade** | 8 | 32GB | 50GB | $0.03/hr | Classification, embeddings, small models |

### GPU Tiers

| Tier | GPU | VRAM | vCPU | RAM | Disk | Cost | Best For |
|------|-----|------|------|-----|------|------|----------|
| **zero-a10g** | H200 slice | 70GB | Dynamic | Dynamic | 50GB | Free* | Most models <7B |
| **t4-small** | T4 | 16GB | 4 | 15GB | 50GB | $0.40/hr | Entry-level GPU |
| **t4-medium** | T4 | 16GB | 8 | 30GB | 100GB | $0.60/hr | More CPU/RAM |
| **l4** | L4 | 24GB | 8 | 30GB | 400GB | $0.80/hr | Great value for 3-7B |
| **l40s** | L40S | 48GB | 8 | 62GB | 380GB | $1.80/hr | 7-14B models |
| **a10g-small** | A10G | 24GB | 4 | 14GB | 110GB | $1.00/hr | 24GB alternative |
| **a10g-large** | A10G | 24GB | 12 | 46GB | 200GB | $1.50/hr | More CPU/RAM |
| **a100-large** | A100 | 80GB | 12 | 142GB | 1TB | $2.50/hr | Large 14-30B+ models |

*ZeroGPU requires PRO subscription to host.

## ZeroGPU Deep Dive

### What is ZeroGPU?

ZeroGPU is a shared GPU infrastructure that dynamically allocates NVIDIA H200 GPUs on-demand:

- **Free GPU access** for PRO subscribers
- GPU allocated when function is called
- GPU released when function returns
- Daily quota limits based on account tier

### ZeroGPU Specifications

- **GPU Type**: NVIDIA H200 slice
- **Available VRAM**: 70GB per workload
- **SDK Support**: Gradio only (no Streamlit/Docker)
- **Python Version**: 3.10.13
- **PyTorch Versions**: 2.1.0 - 2.8.0

### ZeroGPU Quotas

| Account Type | Daily Quota | Queue Priority |
|--------------|-------------|----------------|
| Unauthenticated | 2 min | Low |
| Free account | 3.5 min | Medium |
| PRO account | 25 min | Highest |
| Team organization | 25 min | Highest |
| Enterprise | 45 min | Highest |

### Hosting Requirements

| Account Type | Can HOST ZeroGPU? | Max Spaces |
|--------------|-------------------|------------|
| Free | No | 0 |
| PRO | Yes | 10 |
| Enterprise | Yes | 50 |

### Using ZeroGPU

```python
import spaces

@spaces.GPU(duration=120)  # Max seconds for GPU allocation
def generate(prompt):
    # GPU is available inside this function
    output = model.generate(...)
    return output
    # GPU released after function returns
```

### ZeroGPU Limitations

1. **No torch.compile** - Use ahead-of-time compilation instead
2. **No streaming** - GPU held for entire function duration
3. **Gradio only** - Streamlit and Docker not supported
4. **Queue delays** - High demand can cause wait times
5. **Duration limits** - Default 60s, max configurable

## Hardware Selection Guidelines

### By Model Size

| Model Parameters | Minimum VRAM | Recommended Tier |
|------------------|--------------|------------------|
| < 500M | CPU works | cpu-upgrade |
| 500M - 1B | ~4GB | zero-a10g or t4-small |
| 1B - 3B | ~8GB | zero-a10g or t4-small |
| 3B - 7B | ~16GB | zero-a10g or l4 |
| 7B - 13B | ~28GB | l40s |
| 13B - 30B | ~60GB | a100-large |
| > 30B | 80GB+ | a100-large + quantization |

### By Use Case

| Use Case | Recommended Tier |
|----------|-----------------|
| Inference API demo | cpu-basic |
| Classification model | cpu-upgrade |
| Embedding model | cpu-upgrade |
| Chat model (supported provider) | cpu-basic |
| Chat model (custom) | zero-a10g |
| Image generation | zero-a10g or l4 |
| Video generation | l40s or a100 |
| Vision-language model | zero-a10g or l4 |
| Speech recognition | cpu-upgrade or zero-a10g |

### Cost Optimization

1. **Use Inference API when available** - Free, no GPU needed
2. **Use ZeroGPU for PRO users** - Free GPU access
3. **Choose L4 over A10G** - Better value at $0.80/hr
4. **Use smaller tiers for development** - Scale up for production
5. **Set sleep time** - Auto-pause when inactive
6. **Use quantization** - Reduce VRAM requirements

## VRAM Estimation

### Formula

For transformer models in FP16:
```
VRAM (GB) ≈ Parameters (B) × 2 × 1.2
```

The 1.2 factor accounts for overhead (KV cache, gradients, etc.)

### Examples

| Model | Parameters | Estimated VRAM |
|-------|------------|----------------|
| GPT-2 | 124M | ~0.3GB |
| Llama-3-8B | 8B | ~19GB |
| Llama-3-70B | 70B | ~168GB |
| Mixtral-8x7B | 47B | ~113GB |

### Reducing VRAM

1. **Quantization** - INT8 halves VRAM, INT4 quarters it
2. **Smaller batch size** - Less KV cache
3. **Shorter context** - Less KV cache
4. **Flash Attention** - More efficient memory

## Changing Hardware

### Via UI

1. Go to Space Settings
2. Scroll to "Space Hardware"
3. Select new tier
4. Space will restart with new hardware

### Via API

```python
from huggingface_hub import request_space_hardware

request_space_hardware(
    repo_id="username/space-name",
    hardware="l4"
)
```

### Via CLI

```bash
python scripts/manage_space.py hardware username/space-name --tier l4
```

## Sleep Behavior

### Free Tiers (cpu-basic)

- Sleeps after 48 hours of inactivity
- Wakes automatically on visitor

### Paid Tiers

- Never sleeps by default
- Can set custom sleep time in Settings
- Not billed while sleeping/paused

### Pausing Manually

```bash
python scripts/manage_space.py pause username/space-name
python scripts/manage_space.py restart username/space-name
```

## Framework-Specific Setup

### PyTorch CUDA

```
--extra-index-url https://download.pytorch.org/whl/cu118
torch
```

### JAX CUDA

```
-f https://storage.googleapis.com/jax-releases/jax_cuda_releases.html
jax[cuda12_pip]
```

### TensorFlow

TensorFlow auto-detects CUDA, just add:
```
tensorflow
```

## Persistent Storage

In addition to hardware, you can add persistent storage:

| Storage Tier | Size | Monthly Cost |
|--------------|------|--------------|
| Ephemeral (default) | 50GB | Free |
| Small | +20GB | $5 |
| Medium | +150GB | $25 |
| Large | +1TB | $100 |

Ephemeral storage is wiped on restart; persistent storage survives.
