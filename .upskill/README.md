# Upskill CI

This directory contains the smoke-eval manifest and supporting files for the
skills performance workflow.

## What runs

- Internal pull requests only: the workflow skips fork PRs entirely.
- Pushes to `main`: the workflow reruns changed scenarios and persists a
  normalized history record to a Hugging Face dataset.

## Required secrets

- `ANTHROPIC_API_KEY` for local `upskill` evaluation and LLM-as-a-judge.
- `HF_TOKEN` for history uploads on `main` pushes.

## Files

- `evals.json` maps skills to smoke scenarios.
- `../evals/**` contains the fixed test cases used by CI.
