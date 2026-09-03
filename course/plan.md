# Agent Skills Course

**Build, evaluate, and share agent skills for the world's hardest AI problems.**

Building on the success of the [Agents Course](https://huggingface.co/learn/agents-course) (100k+ participants), this course teaches you how to create portable skills that make coding agents expert at specialized AI tasks like LLM fine-tuning.

## Prerequisites

- Familiarity with Python and the command line  
- A Hugging Face account ([hf.co/join](https://hf.co/join))  
- Access to a coding agent

## Course Outline

### Unit 0: Welcome & Setup

- Course overview and goals  
- Setting up your environment (agent CLI, `hf` CLI, HF token)  
- Joining the community (Discord, Hub)

### Unit 1: What Are Agent Skills?

- Why skills matter: from prompts to portable knowledge  
- The `SKILL.md` format and [Agent Skills Specification](https://agentskills.io)  
- Anatomy of a skill: frontmatter, instructions, scripts, references  
- Progressive disclosure: how agents load and activate skills  
- **Hands-on:** Write your first skill from scratch  
- **Hands-on:** Find and install skills from the [Hub](https://huggingface.co/hf-skills)  
- Sharing Skills 101

### Unit 2: Using Skills with Coding Agents

- Overview: skills across agent platforms  
- **Claude Code:** Installing HF Skills, slash commands, MCP integration  
- **Hands-on:** Fine-tune an LLM using the `hugging-face-model-trainer` skill ([blog](https://huggingface.co/blog/hf-skills-training))  
- **Hands-on:** Run SFT → evaluation → GGUF conversion as a single agent workflow

### Unit 3: Sharing Skills

- Publishing patterns across Hub repos and community registries

### Unit 4: Deep Dive Challenge

- Why kernels? The hardware gap and the [Kernel Hub](https://huggingface.co/blog/hello-hf-kernels)  
- Installing the `cuda-kernels` skill via `kernels skills add`  
- Architecture-aware optimization: H100, A100, T4  
- Integration patterns for `transformers` and `diffusers`  
- **Hands-on:** Build an RMSNorm kernel, benchmark it, publish to the Hub ([blog](https://huggingface.co/blog/custom-cuda-kernels-agent-skills))

## Certification

| Certificate | Requirements |
| :---- | :---- |
| **Skills Fundamentals** | Pass the Unit 1 quiz |
| **Skills Completion** | Pass Unit 1 quiz \+ complete a hands-on project \+ submit to the hackathon leaderboard |

## Key Tools & Resources

- [huggingface/skills](https://github.com/huggingface/skills) — HF Skills repository (Claude Code, Codex, Gemini CLI)  
- [huggingface/upskill](https://github.com/huggingface/upskill) — Generate and evaluate agent skills  
- [huggingface/kernels](https://github.com/huggingface/kernels) — CUDA kernel builder and Hub  
- [agentskills.io](https://agentskills.io) — Agent Skills Specification  
- [TRL](https://huggingface.co/docs/trl) / [Trackio](https://huggingface.co/docs/trackio) / [HF Jobs](https://huggingface.co/docs/huggingface_hub/guides/jobs) — Training infrastructure
