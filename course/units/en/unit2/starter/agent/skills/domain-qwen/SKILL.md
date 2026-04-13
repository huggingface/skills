---
name: domain-qwen
description: Use when the request is about Qwen models, choosing a Qwen variant, tokenizer and chat-template mismatches, or building demos around Qwen checkpoints.
---

# Qwen Domain Notes

Use this skill when the user is working specifically with the Qwen family of models.

## Default Guidance

- Distinguish base versus instruct checkpoints
- Mention tokenizer and chat-template alignment when generation output looks wrong
- Prefer smaller instruct checkpoints for quick demos unless the user asks for a larger model
- Keep demo examples short and multilingual-friendly when relevant

## Common Failure Modes

- Wrong chat template for an instruct model
- Tokenizer not matching the checkpoint
- Using a model that is too large for the requested latency target
