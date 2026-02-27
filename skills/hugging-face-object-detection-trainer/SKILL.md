---
name: hugging-face-object-detection-trainer
description: Trains and fine-tunes object detection models (D-FINE, RT-DETR v2, DETR, YOLOS) using Hugging Face Transformers on Hugging Face Jobs cloud GPUs. Covers COCO-format dataset preparation, Albumentations augmentation, mAP/mAR evaluation, hardware selection, cost estimation, Trackio monitoring, and Hub persistence. Use when users mention training object detection, DETR, D-FINE, RT-DETR, bounding box models, or fine-tuning on Hugging Face Jobs.
---

# Object Detection Training on Hugging Face Jobs

Train object detection models on managed cloud GPUs. No local GPU setup required—results are automatically saved to the Hugging Face Hub.

## When to Use This Skill

Use this skill when users want to:
- Fine-tune object detection models (D-FINE, RT-DETR v2, DETR, YOLOS) on cloud GPUs or local
- Train bounding-box detectors on custom datasets
- Run object detection training jobs on Hugging Face Jobs infrastructure
- Ensure trained vision models are permanently saved to the Hub

## Related Skills

- **`hugging-face-jobs`** — General HF Jobs infrastructure: token authentication, hardware flavors, timeout management, cost estimation, secrets, environment variables, scheduled jobs, and result persistence. **Refer to the Jobs skill for any non-training-specific Jobs questions** (e.g., "how do secrets work?", "what hardware is available?", "how do I pass tokens?").
- **`hugging-face-model-trainer`** — TRL-based language model training (SFT, DPO, GRPO). Use that skill for text/language model fine-tuning.

## Local Script Dependencies

To run helper scripts locally (like `dataset_inspector.py`, `estimate_cost.py`), install dependencies:
```bash
pip install -r requirements.txt
```

## Prerequisites Checklist

Before starting any training job, verify:

### Account & Authentication
- Hugging Face Account with [Pro](https://hf.co/pro), [Team](https://hf.co/enterprise), or [Enterprise](https://hf.co/enterprise) plan (Jobs require paid plan)
- Authenticated login: Check with `hf_whoami()` (tool) or `hf auth whoami` (terminal)
- Token has **write** permissions
- **MUST pass token in job secrets** — see directive #3 below for syntax (MCP tool vs Python API)

### Dataset Requirements
- Dataset must exist on Hub
- Annotations must use the `objects` column with `bbox`, `category` (and optionally `area`) sub-fields
- Bboxes can be in **xywh (COCO)** or **xyxy (Pascal VOC)** format — auto-detected and converted
- Categories can be **integers or strings** — strings are auto-remapped to integer IDs
- `image_id` column is **optional** — generated automatically if missing
- **ALWAYS validate unknown datasets** before GPU training (see Dataset Validation section)

### Critical Settings
- **Timeout must exceed expected training time** — Default 30min is TOO SHORT. See directive #6 for recommended values.
- **Hub push must be enabled** — `push_to_hub=True`, `hub_model_id="username/model-name"`, token in `secrets`

## Dataset Validation

**Validate dataset format BEFORE launching GPU training to prevent the #1 cause of training failures: format mismatches.**

**ALWAYS validate for** unknown/custom datasets or any dataset you haven't trained with before. **Skip for** `cppe-5` (the default in the training script).

### Running the Inspector

**Option 1: Via HF Jobs (recommended — avoids local SSL/dependency issues):**
```python
hf_jobs("uv", {
    "script": "path/to/dataset_inspector.py",
    "script_args": ["--dataset", "username/dataset-name", "--split", "train"]
})
```

**Option 2: Locally:**
```bash
python scripts/dataset_inspector.py --dataset username/dataset-name --split train
```

**Option 3: Via `HfApi().run_uv_job()` (if hf_jobs MCP unavailable):**
```python
from huggingface_hub import HfApi
api = HfApi()
api.run_uv_job(
    script="scripts/dataset_inspector.py",
    script_args=["--dataset", "username/dataset-name", "--split", "train"],
    flavor="cpu-basic",
    timeout=300,
)
```

### Reading Results

- **`✓ READY`** — Dataset is compatible, use directly
- **`✗ NEEDS FORMATTING`** — Needs preprocessing (mapping code provided in output)

## Automatic Bbox Preprocessing

The training script (`scripts/training.py`) automatically handles bbox format detection (xyxy→xywh conversion), bbox sanitization, `image_id` generation, string category→integer remapping, and dataset truncation. **No manual preprocessing needed** — just ensure the dataset has `objects.bbox` and `objects.category` columns.

## Training workflow

Copy this checklist and track progress:

```
Training Progress:
- [ ] Step 1: Verify prerequisites (account, token, dataset)
- [ ] Step 2: Validate dataset format (run dataset_inspector.py)
- [ ] Step 3: Ask user about dataset size and validation split
- [ ] Step 4: Prepare training script (use scripts/training.py as template)
- [ ] Step 5: Save script locally, submit job, and report details
```

**Step 1: Verify prerequisites**

Follow the Prerequisites Checklist above.

**Step 2: Validate dataset**

Run the dataset inspector BEFORE spending GPU time. See "Dataset Validation" section above.

**Step 3: Ask user preferences**

ALWAYS use the AskUserQuestion tool with option-style format:

```python
AskUserQuestion({
    "questions": [
        {
            "question": "Do you want to run a quick test with a subset of the data first?",
            "header": "Dataset Size",
            "options": [
                {"label": "Quick test run (10% of data)", "description": "Faster, cheaper (~30-60 min, ~$2-5) to validate setup"},
                {"label": "Full dataset (Recommended)", "description": "Complete training for best model quality"}
            ],
            "multiSelect": false
        },
        {
            "question": "Do you want to create a validation split from the training data?",
            "header": "Split data",
            "options": [
                {"label": "Yes (Recommended)", "description": "Automatically split 15% of training data for validation"},
                {"label": "No", "description": "Use existing validation split from dataset"}
            ],
            "multiSelect": false
        },
        {
            "question": "Which GPU hardware do you want to use?",
            "header": "Hardware Flavor",
            "options": [
                {"label": "t4-small ($0.40/hr)", "description": "1x T4, 16 GB VRAM — sufficient for all OD models under 100M params"},
                {"label": "l4x1 ($0.80/hr)", "description": "1x L4, 24 GB VRAM — more headroom for large images or batch sizes"},
                {"label": "a10g-large ($1.50/hr)", "description": "1x A10G, 24 GB VRAM — faster training, more CPU/RAM"},
                {"label": "a100-large ($2.50/hr)", "description": "1x A100, 80 GB VRAM — fastest, for very large datasets or image sizes"}
            ],
            "multiSelect": false
        }
    ]
})
```

**Step 4: Prepare training script**

Use [scripts/training.py](scripts/training.py) as the production-ready template. This script uses `HfArgumentParser` — all configuration is passed via CLI arguments in `script_args`, NOT by editing Python variables.

**Step 5: Save script, submit job, and report**

1. **Save the script locally** to `submitted_jobs/` in the workspace root (create if needed) with a descriptive name like `training_<dataset>_<YYYYMMDD_HHMMSS>.py`. Tell the user the path.
2. **Submit** using `hf_jobs` MCP tool (preferred) or `HfApi().run_uv_job()` — see directive #1 for both methods. Pass all config via `script_args`.
3. **Report** the job ID (from `.id` attribute), monitoring URL, Trackio dashboard (`https://huggingface.co/spaces/{username}/trackio`), expected time, and estimated cost.
4. **Wait for user** to request status checks — don't poll automatically. Training jobs run asynchronously and can take hours.

## Critical directives

These rules prevent common failures. Follow them exactly.

### 1. Job submission: `hf_jobs` MCP tool vs Python API

**`hf_jobs()` is an MCP tool, NOT a Python function.** Do NOT try to import it from `huggingface_hub`. Call it as a tool:

```
hf_jobs("uv", {"script": training_script_content, "flavor": "a10g-large", "timeout": "4h", "secrets": {"HF_TOKEN": "$HF_TOKEN"}})
```

**If `hf_jobs` MCP tool is unavailable**, use the Python API directly:

```python
from huggingface_hub import HfApi, get_token
api = HfApi()
job_info = api.run_uv_job(
    script="path/to/training_script.py",  # file PATH, NOT content
    script_args=["--dataset_name", "cppe-5", ...],
    flavor="a10g-large",
    timeout=14400,  # seconds (4 hours)
    env={"PYTHONUNBUFFERED": "1"},
    secrets={"HF_TOKEN": get_token()},  # MUST use get_token(), NOT "$HF_TOKEN"
)
print(f"Job ID: {job_info.id}")
```

**Critical differences between the two methods:**

| | `hf_jobs` MCP tool | `HfApi().run_uv_job()` |
|---|---|---|
| `script` param | Python code string or URL (NOT local paths) | File path to `.py` file (NOT content) |
| Token in secrets | `"$HF_TOKEN"` (auto-replaced) | `get_token()` (actual token value) |
| Timeout format | String (`"4h"`) | Seconds (`14400`) |

**Rules for both methods:**
- The training script MUST include PEP 723 inline metadata with dependencies
- Do NOT use `image` or `command` parameters (those belong to `run_job()`, not `run_uv_job()`)

### 2. Authentication via job secrets + explicit hub_token injection

**Job config** MUST include the token in secrets — syntax depends on submission method (see table above).

**Object-detection-specific requirement:** The Transformers `Trainer` calls `create_repo(token=self.args.hub_token)` during `__init__()` when `push_to_hub=True`. The training script MUST inject `HF_TOKEN` into `training_args.hub_token` AFTER parsing args but BEFORE creating the `Trainer`. The template `scripts/training.py` already includes this:

```python
hf_token = os.environ.get("HF_TOKEN")
if training_args.push_to_hub and not training_args.hub_token:
    if hf_token:
        training_args.hub_token = hf_token
```

If you write a custom script, you MUST include this token injection before the `Trainer(...)` call.

- Do NOT call `login()` in custom scripts unless replicating the full pattern from `scripts/training.py`
- Do NOT rely on implicit token resolution (`hub_token=None`) — unreliable in Jobs
- See the `hugging-face-jobs` skill → *Token Usage Guide* for full details

### 3. JobInfo attribute

Access the job identifier using `.id` (NOT `.job_id` or `.name` — these don't exist):

```python
job_info = api.run_uv_job(...)  # or hf_jobs("uv", {...})
job_id = job_info.id  # Correct -- returns string like "687fb701029421ae5549d998"
```

### 4. Required training flags and HfArgumentParser boolean syntax

`scripts/training.py` uses `HfArgumentParser` — all config is passed via `script_args`. Boolean arguments have two syntaxes:

- **`bool` fields** (e.g., `push_to_hub`, `do_train`): Use as bare flags (`--push_to_hub`) or negate with `--no_` prefix (`--no_remove_unused_columns`)
- **`Optional[bool]` fields** (e.g., `greater_is_better`): MUST pass explicit value (`--greater_is_better True`). Bare `--greater_is_better` causes `error: expected one argument`

Required flags for object detection:

```
--no_remove_unused_columns          # MUST: preserves image column for pixel_values
--no_eval_do_concat_batches         # MUST: images have different numbers of target boxes
--push_to_hub                       # MUST: environment is ephemeral
--hub_model_id username/model-name
--metric_for_best_model eval_map
--greater_is_better True            # MUST pass "True" explicitly (Optional[bool])
--do_train
--do_eval
```

### 5. Timeout management

Default 30 min is TOO SHORT for object detection. Set minimum 2-4 hours. Add 30% buffer for model loading, preprocessing, and Hub push.

| Scenario | Timeout |
|----------|---------|
| Quick test (100-200 images, 5-10 epochs) | 1h |
| Development (500-1K images, 15-20 epochs) | 2-3h |
| Production (1K-5K images, 30 epochs) | 4-6h |
| Large dataset (5K+ images) | 6-12h |

### 6. Trackio monitoring

Trackio is **always enabled** — the training script calls `trackio.init()` and `trackio.finish()` automatically. No need to pass `--report_to trackio`. The project name is taken from `--output_dir` and the run name from `--run_name`.

Dashboard at: `https://huggingface.co/spaces/{username}/trackio`

## Model & hardware selection

### Recommended models

| Model | Params | Use case |
|-------|--------|----------|
| `ustc-community/dfine-small-coco` | 10.4M | Best starting point — fast, cheap, SOTA quality |
| `PekingU/rtdetr_v2_r18vd` | 20.2M | Lightweight real-time detector |
| `ustc-community/dfine-large-coco` | 31.4M | Higher accuracy, still efficient |
| `PekingU/rtdetr_v2_r50vd` | 43M | Strong real-time baseline |
| `ustc-community/dfine-xlarge-obj365` | 63.5M | Best accuracy (pretrained on Objects365) |
| `PekingU/rtdetr_v2_r101vd` | 76M | Largest RT-DETR v2 variant |

Start with `ustc-community/dfine-small-coco` for fast iteration. Move to D-FINE Large or RT-DETR v2 R50 for better accuracy.

### Hardware recommendation

All these models are under 100M params — **`t4-small` (16 GB VRAM, $0.40/hr) is sufficient for all of them.** Only upgrade if you hit OOM from large image sizes, dense annotations, or large batch sizes — reduce batch size first before switching hardware. Common upgrade path: `t4-small` → `l4x1` ($0.80/hr, 24 GB) → `a10g-large` ($1.50/hr, 24 GB).

For full hardware flavor list: refer to the `hugging-face-jobs` skill. For cost estimation: run `scripts/estimate_cost.py`.

## Quick start

The `script_args` below are the same for both submission methods. See directive #1 for the critical differences between them.

```python
SCRIPT_ARGS = [
    "--model_name_or_path", "ustc-community/dfine-small-coco",
    "--dataset_name", "cppe-5",
    "--image_square_size", "640",
    "--output_dir", "dfine_finetuned",
    "--num_train_epochs", "30",
    "--per_device_train_batch_size", "8",
    "--learning_rate", "5e-5",
    "--eval_strategy", "epoch",
    "--save_strategy", "epoch",
    "--save_total_limit", "2",
    "--load_best_model_at_end",
    "--metric_for_best_model", "eval_map",
    "--greater_is_better", "True",
    "--no_remove_unused_columns",
    "--no_eval_do_concat_batches",
    "--push_to_hub",
    "--hub_model_id", "username/model-name",
    "--do_train",
    "--do_eval",
]
```

**Via `HfApi().run_uv_job()` (recommended when script is local):**

```python
from huggingface_hub import HfApi, get_token
api = HfApi()
job_info = api.run_uv_job(
    script="scripts/training.py",
    script_args=SCRIPT_ARGS,
    flavor="t4-small",
    timeout=14400,
    env={"PYTHONUNBUFFERED": "1"},
    secrets={"HF_TOKEN": get_token()},
)
print(f"Job ID: {job_info.id}")
```

**Via `hf_jobs` MCP tool:**

```python
hf_jobs("uv", {
    "script": open("scripts/training.py").read(),
    "script_args": SCRIPT_ARGS,
    "flavor": "t4-small",
    "timeout": "4h",
    "secrets": {"HF_TOKEN": "$HF_TOKEN"}
})
```

### Key `script_args` to customize per task

- `--model_name_or_path` — recommended: `"ustc-community/dfine-small-coco"` (see model table above)
- `--dataset_name` — the Hub dataset ID
- `--image_square_size` — 480 (fast iteration) or 800 (better accuracy)
- `--hub_model_id` — `"username/model-name"` for Hub persistence
- `--num_train_epochs` — 30 typical for convergence
- `--train_val_split` — fraction to split for validation (default 0.15), set if dataset lacks a validation split
- `--max_train_samples` — truncate training set (useful for quick test runs, e.g. `"785"` for ~10% of a 7.8K dataset)
- `--max_eval_samples` — truncate evaluation set

## Checking job status

**MCP tool (if available):**
```
hf_jobs("ps")                                   # List all jobs
hf_jobs("logs", {"job_id": "your-job-id"})      # View logs
hf_jobs("inspect", {"job_id": "your-job-id"})   # Job details
```

**Python API fallback:**
```python
from huggingface_hub import HfApi
api = HfApi()
api.list_jobs()                                  # List all jobs
api.get_job_logs(job_id="your-job-id")           # View logs
api.get_job(job_id="your-job-id")                # Job details
```

## Common failure modes

### OOM (CUDA out of memory)
Reduce `per_device_train_batch_size` (try 4, then 2), reduce `IMAGE_SIZE`, or upgrade hardware.

### Dataset format errors
Run `scripts/dataset_inspector.py` first. The training script auto-detects xyxy vs xywh, converts string categories to integer IDs, and adds `image_id` if missing. Ensure `objects.bbox` contains 4-value coordinate lists in absolute pixels and `objects.category` contains either integer IDs or string labels.

### Hub push failures (401)
Verify: (1) job secrets include token (see directive #2), (2) script sets `training_args.hub_token` BEFORE creating the `Trainer`, (3) `push_to_hub=True` is set, (4) correct `hub_model_id`, (5) token has write permissions.

### Job timeout
Increase timeout (see directive #5 table), reduce epochs/dataset, or use checkpoint strategy with `hub_strategy="every_save"`.

### KeyError: 'test' (missing test split)
The training script handles this gracefully — it falls back to the `validation` split. Ensure you're using the latest `scripts/training.py`.

### Single-class dataset: "iteration over a 0-d tensor"
`torchmetrics.MeanAveragePrecision` returns scalar (0-d) tensors for per-class metrics when there's only one class. The template `scripts/training.py` handles this by calling `.unsqueeze(0)` on these tensors. Ensure you're using the latest template.

### Poor detection performance (mAP < 0.15)
Increase epochs (30-50), ensure 500+ images, check per-class mAP for imbalanced classes, try different learning rates (1e-5 to 1e-4), increase image size.

For comprehensive troubleshooting: see [references/reliability_principles.md](references/reliability_principles.md)

## Reference files

- [scripts/training.py](scripts/training.py) — Production-ready training script with all configurations
- [scripts/dataset_inspector.py](scripts/dataset_inspector.py) — Validate dataset format before GPU training
- [scripts/estimate_cost.py](scripts/estimate_cost.py) — Estimate training costs
- [references/training_notebook.md](references/training_notebook.md) — Complete training workflow, augmentation strategies, and training patterns
- [references/hub_saving.md](references/hub_saving.md) — Detailed Hub persistence guide and verification checklist
- [references/reliability_principles.md](references/reliability_principles.md) — Failure prevention principles from production experience

## External links

- [Transformers Object Detection Guide](https://huggingface.co/docs/transformers/tasks/object_detection)
- [DETR Model Documentation](https://huggingface.co/docs/transformers/model_doc/detr)
- [HF Jobs Guide](https://huggingface.co/docs/huggingface_hub/guides/jobs) — Main Jobs documentation
- [HF Jobs Configuration](https://huggingface.co/docs/hub/en/jobs-configuration) — Hardware, secrets, timeouts, namespaces
- [HF Jobs CLI Reference](https://huggingface.co/docs/huggingface_hub/guides/cli#hf-jobs) — Command line interface
- [Object Detection Models](https://huggingface.co/models?pipeline_tag=object-detection)
- [Object Detection Datasets](https://huggingface.co/datasets?task_categories=task_categories:object-detection)
