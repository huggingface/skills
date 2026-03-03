# Hugging Face Skills Reference

You have additional SKILLs documented in directories containing a "SKILL.md" file.

## Available Skills

| Skill | Description |
|-------|-------------|
| hugging-face-cli | Execute Hugging Face Hub operations using the `hf` CLI. Use when the user needs to download models/datasets/spaces, upload files to Hub repositories, create repos, manage local cache, or run compute jobs on HF infrastructure. |
| hugging-face-datasets | Create and manage datasets on Hugging Face Hub. Supports initializing repos, defining configs/system prompts, streaming row updates, and SQL-based dataset querying/transformation. |
| hugging-face-evaluation | Add and manage evaluation results in Hugging Face model cards. Supports extracting eval tables from README content, importing scores from Artificial Analysis API, and running custom model evaluations. |
| hugging-face-jobs | Run any workload on Hugging Face Jobs infrastructure. Covers UV scripts, Docker-based jobs, hardware selection, cost estimation, authentication with tokens, secrets management, timeout configuration, and result persistence. |
| hugging-face-model-trainer | Train or fine-tune language models using TRL on Hugging Face Jobs infrastructure. Covers SFT, DPO, GRPO and reward modeling training methods, plus GGUF conversion for local deployment. |
| hugging-face-paper-publisher | Publish and manage research papers on Hugging Face Hub. Supports creating paper pages, linking papers to models/datasets, claiming authorship, and generating professional markdown-based research articles. |
| hugging-face-tool-builder | Build tool/scripts or achieve a task where using data from the Hugging Face API would help. Creates reusable scripts to fetch, enrich or process data. |
| hugging-face-trackio | Track and visualize ML training experiments with Trackio. Use when logging metrics during training (Python API) or retrieving/analyzing logged metrics (CLI). |
| gradio | Build Gradio web UIs and demos in Python. Use when creating or editing Gradio apps, components, event listeners, layouts, or chatbots. |
| hugging-face-dataset-viewer | Use this skill for Hugging Face Dataset Viewer API workflows that fetch subset/split metadata, paginate rows, search text, apply filters, download parquet URLs, and read size or statistics. |

## Usage

**IMPORTANT:** You MUST read the SKILL.md file whenever the description of the skills matches the user intent, or may help accomplish their task.

## Skill Paths

Paths referenced within SKILL folders are relative to that SKILL. For example the hf-datasets `scripts/example.py` would be referenced as `hf-datasets/scripts/example.py`.

## Skill Files

The skills are located in:
- `skills/hugging-face-cli/SKILL.md`
- `skills/hugging-face-datasets/SKILL.md`
- `skills/hugging-face-evaluation/SKILL.md`
- `skills/hugging-face-jobs/SKILL.md`
- `skills/hugging-face-model-trainer/SKILL.md`
- `skills/hugging-face-paper-publisher/SKILL.md`
- `skills/hugging-face-tool-builder/SKILL.md`
- `skills/hugging-face-trackio/SKILL.md`
- `skills/huggingface-gradio/SKILL.md`
- `skills/hugging-face-dataset-viewer/SKILL.md`
