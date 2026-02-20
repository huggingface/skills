# Error Patterns Reference

Comprehensive catalog of common errors in Hugging Face Spaces and their solutions.

## Package & Import Errors

### ModuleNotFoundError

**Pattern**: `ModuleNotFoundError: No module named 'X'`

**Example**:
```
ModuleNotFoundError: No module named 'transformers'
```

**Cause**: Package not in requirements.txt

**Fix**: Add the package to requirements.txt
```bash
python scripts/remediate.py fix-requirements username/space --add transformers
```

**Common missing packages**:
| Import | Package to add |
|--------|---------------|
| `torch` | `torch` |
| `transformers` | `transformers>=4.40.0` |
| `peft` | `peft` |
| `spaces` | `spaces` |
| `PIL` | `Pillow>=10.0.0` |
| `cv2` | `opencv-python>=4.8.0` |

---

### ImportError: cannot import name 'HfFolder'

**Pattern**: `ImportError: cannot import name 'HfFolder' from 'huggingface_hub'`

**Cause**: Version mismatch between gradio and huggingface_hub

**Fix**: Update both packages:
```
gradio>=5.0.0
huggingface_hub>=0.26.0
```

**Auto-fix**:
```bash
python scripts/remediate.py auto-fix username/space
```

---

### ImportError: cannot import name 'X' from 'Y'

**Pattern**: `ImportError: cannot import name 'AutoModel' from 'transformers'`

**Cause**: Usually version mismatch or API change

**Fix**: Pin a compatible version or update code

---

## Model Loading Errors

### OSError: does not appear to have a file named...

**Pattern**: `OSError: username/model does not appear to have a file named pytorch_model.bin, model.safetensors`

**Cause**: Trying to load a LoRA adapter as a full model

**Detection**: Check for `adapter_config.json` in the model repo

**Fix**: Use PEFT to load the adapter:
```python
from peft import PeftModel
from transformers import AutoModelForCausalLM

# Load base model first
base_model = AutoModelForCausalLM.from_pretrained("base-model-id")

# Then apply adapter
model = PeftModel.from_pretrained(base_model, "adapter-id")
model = model.merge_and_unload()  # Optional: merge for faster inference
```

---

### Cannot access gated repo

**Pattern**: `Cannot access gated repo for url ... Access to model ... is restricted`

**Cause**: Model is gated and user hasn't accepted terms

**Fix**:
1. Go to model page on HF Hub
2. Accept the terms/license
3. Add HF_TOKEN secret to Space with a token that has access

---

### Repository Not Found

**Pattern**: `404 Client Error: Repository Not Found`

**Cause**: Model ID is incorrect or model is private

**Fix**:
1. Verify model ID is correct
2. If private, add HF_TOKEN secret with access

---

## GPU & CUDA Errors

### CUDA out of memory

**Pattern**: `torch.cuda.OutOfMemoryError: CUDA out of memory`

**Cause**: Model too large for GPU VRAM

**Fixes**:
1. **Upgrade hardware**: Use l40s (48GB) or a100 (80GB)
2. **Use quantization**:
```python
model = AutoModel.from_pretrained(MODEL_ID, load_in_8bit=True)
```
3. **Reduce batch size / context length**
4. **Use flash attention**:
```python
model = AutoModel.from_pretrained(MODEL_ID, attn_implementation="flash_attention_2")
```

---

### CUDA is not available

**Pattern**: `AssertionError: Torch not compiled with CUDA enabled` or `CUDA is not available`

**Cause**: Space running on CPU but code requires GPU

**Fix**: Set hardware to GPU tier in Space Settings
- ZeroGPU (free with PRO)
- T4/L4/A10G/A100 (paid)

---

### GPU allocation timed out

**Pattern**: `GPU allocation timed out` or `Queue timeout`

**Cause**: ZeroGPU queue is backed up

**Fixes**:
1. Try again later
2. Use paid GPU tier for guaranteed access
3. Optimize code to complete faster

---

### Duration exceeded

**Pattern**: Function terminated due to exceeding duration limit

**Cause**: `@spaces.GPU(duration=X)` is too short

**Fix**: Increase duration:
```python
@spaces.GPU(duration=120)  # Up from default 60
def generate(...):
    ...
```

---

## Gradio Errors

### ValueError: examples must be nested list

**Pattern**: `ValueError: examples must be nested list`

**Cause**: Gradio 5.x changed examples format

**Fix**: Use nested lists:
```python
# WRONG (Gradio 4.x style):
examples=["Example 1", "Example 2"]

# CORRECT (Gradio 5.x style):
examples=[["Example 1"], ["Example 2"]]
```

---

### No API found

**Pattern**: `No API found for this Space`

**Cause**: Gradio app not exposing API properly, often due to hardware mismatch

**Fix**:
1. Go to Space Settings
2. Set correct hardware (ZeroGPU or paid GPU)
3. Restart Space

---

### Address already in use

**Pattern**: `OSError: [Errno 98] Address already in use`

**Cause**: Explicit port binding in code

**Fix**: Remove port specification:
```python
# WRONG:
demo.launch(server_port=7860)

# CORRECT:
demo.launch()  # Let Spaces handle the port
```

---

## Authentication Errors

### 401 Unauthorized

**Pattern**: `401 Client Error: Unauthorized`

**Cause**: Missing or invalid HF token

**Fix**:
1. Generate a token at https://huggingface.co/settings/tokens
2. Add as secret in Space Settings: `HF_TOKEN`
3. Or use environment variable in code:
```python
import os
token = os.environ.get("HF_TOKEN")
```

---

### 403 Forbidden

**Pattern**: `403 Client Error: Forbidden`

**Causes**:
- Token doesn't have required permissions
- Model is gated and access not granted
- Organization restrictions

**Fix**: Check token permissions and model access

---

## Model-Specific Errors

### Cannot use chat template

**Pattern**: `Cannot use chat template` or `Chat template is not defined`

**Cause**: Model doesn't have a chat template defined

**Fixes**:
1. Use base completion instead of chat
2. Manually apply a chat template:
```python
def format_prompt(message, history):
    prompt = ""
    for user_msg, assistant_msg in history:
        prompt += f"User: {user_msg}\nAssistant: {assistant_msg}\n"
    prompt += f"User: {message}\nAssistant:"
    return prompt
```

---

### Tokenizer not found

**Pattern**: `Can't load tokenizer for 'model-id'`

**Cause**: Tokenizer files missing or model ID wrong

**Fix**: Verify model ID and that tokenizer files exist in repo

---

## Disk Space Errors

### No space left on device

**Pattern**: `OSError: [Errno 28] No space left on device`

**Cause**: Model too large for disk quota

**Fixes**:
1. Use streaming download
2. Upgrade storage tier
3. Use smaller model or quantized version

---

## Network Errors

### Connection timeout

**Pattern**: `requests.exceptions.ConnectTimeout`

**Cause**: HF Hub or external service timeout

**Fix**: Add retry logic or increase timeout

---

### Rate limit exceeded

**Pattern**: `429 Too Many Requests`

**Cause**: Too many API calls

**Fix**: Add backoff/retry logic or reduce request frequency

---

## How to Use This Reference

### Manual Lookup

1. Find the error pattern in your logs
2. Search this document for the pattern
3. Apply the recommended fix

### Automated Detection

```bash
# Analyze Space logs for known patterns
python scripts/monitor_space.py analyze-errors username/space-name

# Auto-fix what can be fixed automatically
python scripts/remediate.py auto-fix username/space-name
```

### Adding New Patterns

To add a new error pattern to automated detection, edit `scripts/monitor_space.py`:

```python
ERROR_PATTERNS = {
    # Add new pattern here
    "new_error_type": {
        "pattern": r"regex pattern here",
        "description": "Human readable description",
        "fix_template": "How to fix this error",
        "auto_fixable": False,  # or True if can be auto-fixed
    },
}
```
