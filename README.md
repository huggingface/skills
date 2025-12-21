# Hugging Face Skills

Hugging Face Skills are Agent Context Protocol (ACP) definitions for AI/ML tasks like dataset creation, model training, and evaluation. They are interoperable with all major coding agent tools like OpenAI Codex, Anthropic's Claude Code, Google DeepMind's Gemini CLI, and Cursor.

## How do Skills work?

In practice, skills are self-contained folders that package instructions, scripts, and resources together for an AI agent to use on a specific use case. Each folder includes a `SKILL.md` file with YAML frontmatter (name and description) followed by the guidance your coding agent follows while the skill is active. 

> [!NOTE]
> 'Skills' is actually an Anthropic term used within Claude AI and Claude Code and not adopted by other agent tools, but we love it! OpenAI Codex uses an `AGENTS.md` file to define the instructions for your coding agent. Google Gemini uses 'extensions' to define the instructions for your coding agent in a `gemini-extension.json` file. **This repo is compatible with all of them, and more!**

## Installation

Hugging Face skills are compatible with Claude Code, Codex, and Gemini CLI. With integrations Cursor, Windsurf, and Continue, on the way.

### Claude Code

1. Register the repository as a plugin marketplace:  
   
```
/plugin marketplace add huggingface/skills
```

2. To install a skill, run:  
   
```
/plugin install <skill-folder>@huggingface-skills
```

For example:  

```
/plugin install model-trainer@huggingface-skills
```

### Codex

1. Codex will identify the skills via the `AGENTS.md` file. You can verify the instructions are loaded with:

```
codex --ask-for-approval never "Summarize the current instructions."
```

2. For more details, see the [Codex AGENTS guide](https://developers.openai.com/codex/guides/agents-md).

### Gemini CLI

1. This repo includes `gemini-extension.json` to integrate with the Gemini CLI.

2. Install locally:  

```
gemini extensions install . --consent
```

or use the GitHub URL:

```
gemini extensions install https://github.com/huggingface/skills.git --consent
```

4. See [Gemini CLI extensions docs](https://geminicli.com/docs/extensions/#installing-an-extension) for more help.

## Skills

This repository contains a few skills to get you started. You can also contribute your own skills to the repository.

### Available skills

| Skill Folder            | Description                                                                                                                | Documentation                                          |
|-------------------------|----------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------|
| `hf_dataset_creator/`   | Prompts, templates, and scripts for creating structured training datasets. | [SKILL.md](hf_dataset_creator/skills/hugging-face-dataset-creator/SKILL.md) |
| `hf_model_evaluation/`  | Instructions plus utilities for orchestrating evaluation jobs, generating reports, and mapping metrics. | [SKILL.md](hf_model_evaluation/skills/hugging-face-evaluation-manager/SKILL.md) |
| `hf-llm-trainer/`       | Comprehensive training skill with `SKILL.md` guidance, helper scripts (e.g., `train_sft_example.py`, `convert_to_gguf.py`, cost estimators). | [SKILL.md](hf-llm-trainer/skills/model-trainer/SKILL.md) |
| `hf-optuna-hpo/`        | Hyperparameter optimisation for LLM fine-tuning using Optuna. Orchestrates distributed HPO studies with cloud GPU backends, budget management, and Gradio visualisation. | [SKILL.md](hf-optuna-hpo/skills/optuna-hpo/SKILL.md) |
| `hf-paper-publisher/`   | Tools for publishing and managing research papers on Hugging Face Hub. Index papers from arXiv, link papers to models/datasets, generate professional research articles from templates, and manage paper authorship. | [SKILL.md](hf-paper-publisher/skills/hugging-face-paper-publisher/SKILL.md) |

### Using skills in your coding agent

Once a skill is installed, mention it directly while giving your coding agent instructions:

- "Use the HF LLM trainer skill to estimate the GPU memory needed for a 70B model run."
- "Use the HF model evaluation skill to launch `run_eval_job.py` on the latest checkpoint."
- "Use the HF dataset creator skill to draft new few-shot classification templates."
- "Use the HF paper publisher skill to index my arXiv paper and link it to my model."
- "Use the Optuna HPO skill to find optimal learning rate and LoRA parameters for my fine-tuning job."

Your coding agent automatically loads the corresponding `SKILL.md` instructions and helper scripts while it completes the task.

### Contribute or customize a skill

1. Copy one of the existing skill folders (for example, `hf_dataset_creator/`) and rename it.
2. Update the new folder’s `SKILL.md` frontmatter:
   ```markdown
   ---
   name: my-skill-name
   description: Describe what the skill does and when to use it
   ---

   # Skill Title
   Guidance + examples + guardrails
   ```
3. Add or edit supporting scripts, templates, and documents referenced by your instructions.
4. Reinstall or reload the skill bundle in your coding agent so the updated folder is available.

### Additional references
- Browse the latest instructions, scripts, and templates directly at [huggingface/skills](https://github.com/huggingface/skills).
- Review Hugging Face documentation for the specific libraries or workflows you reference inside each skill.
