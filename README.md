# Hugging Face Skills

Hugging Face Skills are definitions for AI/ML tasks like dataset creation, model training, and evaluation. They are interoperable with all major coding agent tools like OpenAI Codex, Anthropic's Claude Code, Google DeepMind's Gemini CLI, and Cursor.

The Skills in this repository follow the standardized format [Agent Skill](https://agentskills.io/home) format.

## How do Skills work?

In practice, skills are self-contained folders that package instructions, scripts, and resources together for an AI agent to use on a specific use case. Each folder includes a `SKILL.md` file with YAML frontmatter (name and description) followed by the guidance your coding agent follows while the skill is active. 

> [!NOTE]
> 'Skills' is actually an Anthropic term used within Claude AI and Claude Code and not adopted by other agent tools, but we love it! OpenAI Codex uses an `AGENTS.md` file to define the instructions for your coding agent. Google Gemini uses 'extensions' to define the instructions for your coding agent in a `gemini-extension.json` file. **This repo is compatible with all of them, and more!**

> [!TIP]
> If your agent doesn't support skills, you can use [`agents/AGENTS.md`](agents/AGENTS.md) directly as a fallback.

## Installation

Hugging Face skills are compatible with Claude Code, Codex, and Gemini CLI. With integrations Cursor, Windsurf, and Continue, on the way. 

### Claude Code

1. Register the repository as a plugin marketplace:  
   
```
/plugin marketplace add huggingface/skills
```

2. To install a skill, run:  
   
```
/plugin install <skill-name>@huggingface/skills
```

For example:  

```
/plugin install hugging-face-cli@huggingface/skills
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
| `hf-datasets/`   | Prompts, templates, and scripts for creating structured training datasets. | [SKILL.md](hf-datasets/skills/hugging-face-datasets/SKILL.md) |
| `hf-evaluation/`  | Instructions plus utilities for orchestrating evaluation jobs, generating reports, and mapping metrics. | [SKILL.md](hf-evaluation/skills/hugging-face-evaluation-manager/SKILL.md) |
| `hf-llm-trainer/`       | Comprehensive training skill with `SKILL.md` guidance, helper scripts (e.g., `train_sft_example.py`, `convert_to_gguf.py`, cost estimators). | [SKILL.md](hf-llm-trainer/skills/model-trainer/SKILL.md) |
| `hf-papers/`   | Tools for publishing and managing research papers on Hugging Face Hub. Index papers from arXiv, link papers to models/datasets, generate professional research articles from templates, and manage paper authorship. | [SKILL.md](hf-papers/skills/hugging-face-paper-publisher/SKILL.md) |

### Using skills in your coding agent

Once a skill is installed, mention it directly while giving your coding agent instructions:

- "Use the HF LLM trainer skill to estimate the GPU memory needed for a 70B model run."
- "Use the HF model evaluation skill to launch `run_eval_job.py` on the latest checkpoint."
- "Use the HF dataset creator skill to draft new few-shot classification templates."
- "Use the HF paper publisher skill to index my arXiv paper and link it to my model."

Your coding agent automatically loads the corresponding `SKILL.md` instructions and helper scripts while it completes the task.

### Contribute or customize a skill

1. Copy one of the existing skill folders (for example, `hf-datasets/`) and rename it.
2. Update the new folder's `SKILL.md` frontmatter:
   ```markdown
   ---
   name: my-skill-name
   description: Describe what the skill does and when to use it
   ---

   # Skill Title
   Guidance + examples + guardrails
   ```
3. Add or edit supporting scripts, templates, and documents referenced by your instructions.
4. Add an entry to `.claude-plugin/marketplace.json` with a concise, human-readable description.
5. Run `python scripts/generate_agents.py` to validate the structure.
6. Reinstall or reload the skill bundle in your coding agent so the updated folder is available.

### Marketplace

The `.claude-plugin/marketplace.json` file lists skills with human-readable descriptions for the plugin marketplace. The CI validates that skill names and paths match between `SKILL.md` files and `marketplace.json`, but descriptions are maintained separately: `SKILL.md` descriptions guide when Claude activates the skill, while marketplace descriptions are written for humans browsing available skills.

### Additional references
- Browse the latest instructions, scripts, and templates directly at [huggingface/skills](https://github.com/huggingface/skills).
- Review Hugging Face documentation for the specific libraries or workflows you reference inside each skill.
