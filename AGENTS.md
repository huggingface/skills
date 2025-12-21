<skills>

You have additional SKILLs documented in directories containing a "SKILL.md" file.

These skills are:
 - hf-tool-builder -> "hf-tool-builder/skills/hf-tool-builder/SKILL.md"
 - hugging-face-dataset-creator -> "hf_dataset_creator/skills/hugging-face-dataset-creator/SKILL.md"
 - hugging-face-evaluation-manager -> "hf_model_evaluation/skills/hugging-face-evaluation-manager/SKILL.md"
 - hugging-face-paper-publisher -> "hf-paper-publisher/skills/hugging-face-paper-publisher/SKILL.md"
 - model-trainer -> "hf-llm-trainer/skills/model-trainer/SKILL.md"
 - optuna-hpo -> "hf-optuna-hpo/skills/optuna-hpo/SKILL.md"

IMPORTANT: You MUST read the SKILL.md file whenever the description of the skills matches the user intent, or may help accomplish their task. 

<available_skills>

hf-tool-builder: `Use this skill when the user wants to build tool/scripts or achieve a task where using data from the Hugging Face API would help. This is especially useful when chaining or combining API calls or the task will be repeated/automated. This Skill creates a reusable script to fetch, enrich or process data.`
hugging-face-dataset-creator: `Create and manage datasets on Hugging Face Hub. Supports initializing repos, defining configs/system prompts, and streaming row updates. Designed to work alongside HF MCP server for comprehensive dataset workflows.`
hugging-face-evaluation-manager: `Add and manage evaluation results in Hugging Face model cards. Supports extracting eval tables from README content, importing scores from Artificial Analysis API, and running custom model evaluations with vLLM/lighteval. Works with the model-index metadata format.`
hugging-face-paper-publisher: `Publish and manage research papers on Hugging Face Hub. Supports creating paper pages, linking papers to models/datasets, claiming authorship, and generating professional markdown-based research articles.`
model-trainer: `This skill should be used when users want to train or fine-tune language models using TRL (Transformer Reinforcement Learning) on Hugging Face Jobs infrastructure. Covers SFT, DPO, GRPO and reward modeling training methods, plus GGUF conversion for local deployment. Includes guidance on the TRL Jobs package, UV scripts with PEP 723 format, dataset preparation and validation, hardware selection, cost estimation, Trackio monitoring, Hub authentication, and model persistence. Should be invoked for tasks involving cloud GPU training, GGUF conversion, or when users mention training on Hugging Face Jobs without local GPU setup.`
optuna-hpo: `Hyperparameter optimisation for LLM fine-tuning using Optuna. Orchestrates distributed HPO studies with cloud GPU backends (HuggingFace Jobs, Modal, RunPod). Features include TPE sampling, MedianPruner for early stopping, configurable search spaces (learning rate, batch size, LoRA parameters), budget management, Hub persistence, and Gradio visualisation. Use when users want to tune hyperparameters for transformer fine-tuning, find optimal training configurations, or run HPO studies with cost constraints.`
</available_skills>

Paths referenced within SKILL folders are relative to that SKILL. For example the hf_dataset_creator `scripts/example.py` would be referenced as `hf_dataset_creator/scripts/example.py`. 

</skills>
