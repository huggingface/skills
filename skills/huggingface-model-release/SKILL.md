---
name: huggingface-model-release
description: >-
  Autonomously migrate machine learning models to the Hugging Face Hub from
  GitHub repositories. Clones the repo, analyzes code/configs/README to extract
  all metadata, uploads raw weights (one repo per checkpoint/variant), writes
  model cards with proper YAML metadata, creates collections, and verifies the
  release. Use when the user provides a GitHub repository URL and wants the
  model uploaded/published/released on Hugging Face.
---

# Hugging Face Model Release

Autonomously migrate ML models from GitHub repositories to the Hugging Face Hub
following official best practices. This skill relies on the `hf` CLI for all
Hub operations. It is based on https://huggingface.co/docs/hub/model-release-checklist.

## Prerequisites

Before starting, ensure the `hf` CLI is installed (`curl -LsSf https://hf.co/cli/install.sh` on MacOS and Linux, see also https://huggingface.co/docs/huggingface_hub/en/guides/cli for details). Next, verify the environment:

```bash
hf auth whoami
hf version
```

Authenticate via `hf auth login` or the `HF_TOKEN` environment variable. You need **write** access in order to upload weights to the Hugging Face hub. Ask the user in case you need to obtain one, and ask them to which Hugging Face user or organization the weights can be pushed.

## Core Workflow

Follow these steps for every model release:

1. **Clone and analyze** the GitHub repository
2. **Download weights** (from GitHub releases, LFS, or external links found in the repo)
3. **Create repo(s)** on the Hub — one per checkpoint/variant
4. **Write model card** (README.md) with proper YAML metadata
5. **Upload** raw weights + model card
6. **Create collection** (if multiple variants)
7. **Post-release verification**

---

## Step 1: Clone and Analyze the GitHub Repository

Clone the repo and systematically extract all information needed for the release.
**Do not ask the user** — infer everything from the repo contents.

```bash
git clone https://github.com/org/repo.git --depth 1
cd repo
```

### What to look for

Scan the repository for the following. Use the table below as a checklist — every
field must be resolved before proceeding to Step 2.

| Field | Where to find it |
|-------|-----------------|
| **Model architecture / framework** | Config files (`config.json`, `config.yaml`), model definition source code, README |
| **Task the model solves** | README, paper abstract, demo scripts, config files |
| **License** | `LICENSE` file, README badge/section, `setup.py`/`pyproject.toml` |
| **Associated paper (arXiv ID)** | README citations, `CITATION.cff`, BibTeX blocks, links in docs |
| **Training dataset** | README training section, config files, data-loading scripts |
| **Base model (if fine-tune)** | Config files (`_name_or_path`, `base_model`), README, training scripts |
| **Weight file locations** | GitHub Releases assets, Git LFS files, download URLs in README/scripts, Google Drive/Dropbox links in README |
| **Multiple variants / checkpoints** | Subdirectories, release tags, README sections listing variants |
| **Target repo name** | Derive from GitHub `org/repo` name, following Hub naming conventions |
| **Language(s)** | README, paper, dataset metadata |
| **Library / framework** | Imports in source code (`import transformers`, `import diffusers`, etc.), `requirements.txt`, `setup.py` |

### Extraction strategy

1. **Read `README.md`** (or `README.rst`) — this is the richest source. Look for
   architecture descriptions, benchmark tables, usage examples, paper links,
   dataset references, and download instructions.
2. **Read `LICENSE`** — map to an SPDX identifier (see metadata reference).
3. **Read config files** — `config.json`, `*.yaml`, `hparams.yaml`, etc. for
   architecture, parameter counts, training hyperparameters.
4. **Check GitHub Releases** — `gh release list` and `gh release view <tag>` to
   find weight files and changelogs.
5. **Scan source code** — identify the framework (`transformers`, `diffusers`,
   `timm`, `torch`, `jax`, etc.) from imports.
6. **Check `CITATION.cff`** or BibTeX blocks for the paper reference.
7. **Check for multiple variants** — look for size suffixes in filenames,
   separate release tags, or subdirectories with different configs.

If a piece of information is genuinely not available in the repo, use a sensible
default or omit the optional field. Never block the workflow waiting for user input.

## Step 2: Download Weights

Based on what you found in Step 1, download the model weights. Keep each
checkpoint/variant in its own directory — these map 1:1 to Hub repos in Step 3.

### GitHub Releases

```bash
# List available releases
gh release list --repo org/repo

# Download all assets from a release
gh release download v1.0 --repo org/repo --dir ./weights

# Download a specific asset
gh release download v1.0 --repo org/repo --pattern "*.bin" --dir ./weights
```

### Git LFS files (already in the cloned repo)

```bash
git lfs pull
```

### External links found in README

If the README points to Google Drive, Dropbox, or other hosts:

```bash
# Google Drive
pip install gdown
gdown "https://drive.google.com/uc?id=FILE_ID" -O model_weights.bin

# Dropbox (replace dl=0 with dl=1)
curl -L "https://www.dropbox.com/scl/fi/XXXXX/model.bin?dl=1" -o model.bin

# Direct URL
curl -L "https://example.com/model_weights.bin" -o model_weights.bin
```

### Organizing variants

If the repo contains multiple checkpoints (e.g. small, base, large), download
each into a separate directory:

```bash
mkdir -p variants/model-small variants/model-base variants/model-large
# Move or download the corresponding files into each directory
```

## Step 3: Create Repos on the Hub

**One repo per checkpoint/variant.** Do NOT upload multiple variants into
subdirectories of the same repo.

Naming convention: `org/model-name` or `org/model-name-size-variant`

Examples:
- `google/vit-base-patch16-224`
- `meta-llama/Llama-3-8B`
- `meta-llama/Llama-3-8B-Instruct`

```bash
hf repos create org/model-name --private
# Add --private to prepare the repo before making it public
```

For multiple variants, create each repo separately:

```bash
hf repos create org/model-name-small
hf repos create org/model-name-base
hf repos create org/model-name-large
```

## Step 4: Write the Model Card

The model card is the `README.md` in the repo root. It consists of YAML
frontmatter (metadata) and markdown body.

For the full template, see [references/model-card-template.md](references/model-card-template.md).
For metadata field details, see [references/metadata-reference.md](references/metadata-reference.md).

### Critical YAML Metadata

Every model card MUST include these fields:

```yaml
---
pipeline_tag: text-generation       # The task — determines widgets and search
library_name: transformers          # The library — enables code snippets
license: apache-2.0                 # The license
language:
  - en                              # Language(s) the model handles
---
```

### Conditional Metadata

Add these fields when applicable:

```yaml
datasets:
  - username/dataset-name           # Training dataset(s) — creates cross-links

base_model: meta-llama/Llama-3-8B  # If this is a fine-tune or adaptation

base_model_relation: quantized      # If this is a quantized version
                                    # (use with base_model)

tags:
  - vision
  - medical                         # Domain-specific tags for discoverability

new_version: org/newer-model        # Set on OLD model to point to its successor
```

### Model Card Body

Write sections in this order:

1. **Title and summary** — one-paragraph description of what the model does
2. **Usage examples** — copy-and-run code snippets for inference:

```python
from transformers import pipeline
pipe = pipeline("text-generation", model="org/model-name")
result = pipe("Your prompt here")
```

3. **Training details** — dataset, hyperparameters, hardware used
4. **Evaluation results** — benchmarks with quantitative metrics
5. **Limitations and biases** — known failure modes and ethical considerations
6. **Citation** — BibTeX entry if there's an associated paper:

```bibtex
@article{author2024model,
  title={Model Title},
  author={Author, First and Author, Second},
  journal={arXiv preprint arXiv:XXXX.XXXXX},
  year={2024}
}
```

### For Image/Video Models

Add visual examples using the Gallery component:

```markdown
<Gallery>
![Example 1](./images/example1.png)
![Example 2](./images/example2.png)
</Gallery>
```

## Step 5: Upload

Upload raw weight files and the model card as-is — no conversion needed.

```bash
# Upload everything in a variant's directory
hf upload org/model-name ./variants/model-name --commit-message "Initial release"

# Or upload specific files
hf upload org/model-name checkpoint.pth --commit-message "Add model weights"
hf upload org/model-name README.md --commit-message "Add model card"
hf upload org/model-name config.json --commit-message "Add config"
```

For very large uploads (>50 GB or unreliable connection), use resumable upload:

```bash
hf upload-large-folder org/model-name ./variants/model-name
```

After upload, make the repo public when ready:

```bash
hf repos settings org/model-name --no-private
```

For models requiring controlled access:

```bash
hf repos settings org/model-name --gated auto
```

## Step 6: Create a Collection

If releasing multiple related variants, group them:

```bash
hf collections create "Model Family Name" \
  --namespace org \
  --description "Collection of Model variants including base, large, and instruct versions"

# Note the returned collection slug, then add items:
hf collections add-item org/model-family-XXXX org/model-name-base model
hf collections add-item org/model-family-XXXX org/model-name-large model
hf collections add-item org/model-family-XXXX org/model-name-instruct model
```

## Step 7: Post-Release Verification

Run through this checklist after uploading:

- [ ] **Verify the model loads**: run the code snippet from the model card in a clean environment
- [ ] **Check metadata renders**: visit `hf.co/org/model-name` and confirm the pipeline tag, library, and license display correctly
- [ ] **Test the widget**: if the pipeline tag supports it, confirm the inference widget works on the model page
- [ ] **Verify cross-links**: confirm linked datasets and base models appear on the model page
- [ ] **Check download**: `hf download org/model-name --dry-run` to confirm files are accessible

### Add Evaluation Results (optional)

Create `.eval_results/` YAML files in the repo to show benchmark scores on the
model page:

```yaml
# .eval_results/mmlu.yaml
- dataset:
    id: cais/mmlu
    task_id: college_chemistry
  value: 76.1
  date: "2024-06-15"
  source:
    url: https://huggingface.co/org/model-name
    name: Model Card
    user: your-username
```

Upload via:

```bash
hf upload org/model-name .eval_results/ .eval_results/ \
  --commit-message "Add evaluation results"
```

---

## Decision Tree

Use this to handle common variations:

**Is this a fine-tune of an existing model?**
- Yes → set `base_model: original-org/original-model` in metadata

**Is this a quantized version?**
- Yes → set both `base_model` and `base_model_relation: quantized`
- Upload to a separate repo (e.g. `org/model-name-GGUF`)

**Are there multiple model sizes or variants?**
- Yes → create one repo per variant, then create a collection

**Does the model have an associated paper?**
- Yes → add arXiv link in the model card body; the Hub auto-generates `arxiv:ID` tags
- Add BibTeX citation block

**Is this an image/video generation model?**
- Yes → include example outputs using `<Gallery>` component
- Add example images to the repo under `./images/`

**Does the model need gated access?**
- Yes → set gated access via `hf repos settings org/model-name --gated auto`
- Document access conditions in the model card

**Is this replacing an older model?**
- Yes → add `new_version: org/newer-model` to the OLD model's metadata

## Naming Conventions

| Pattern | When to use | Example |
|---------|------------|---------|
| `org/model` | Single model | `google/gemma-2b` |
| `org/model-size` | Size variants | `meta-llama/Llama-3-8B` |
| `org/model-size-variant` | Functional variants | `meta-llama/Llama-3-8B-Instruct` |
| `org/model-GGUF` | Quantized formats | `bartowski/Llama-3-8B-GGUF` |

## Common Pitfalls

- **Mixing variants in one repo**: use separate repos (one per checkpoint), group with collections
- **Missing `pipeline_tag`**: model won't appear in task-filtered searches or get a widget
- **Missing `library_name`**: no code snippets shown on the model page
- **Forgetting `base_model`**: fine-tunes won't link back to the original in the model tree
- **Uploading without a model card**: always include a README.md, even a minimal one
