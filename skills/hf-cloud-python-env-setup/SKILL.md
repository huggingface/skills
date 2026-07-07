---
name: hf-cloud-python-env-setup
description: 'Set up an isolated Python environment for SageMaker / AWS work, with the right Python version and current boto3. Use this skill whenever Python code will be executed for a SageMaker deployment, training job, or any AWS automation — including when about to run `pip install`, when about to invoke `boto3`, when creating or activating a virtualenv, or when the user asks to "set up the environment". Never use system Python and never `pip install` into it. Always isolate. This skill prevents the most common failure modes: wrong Python version, dependency conflicts, and stale SDKs.'
---

# Python Environment Setup for SageMaker

Most SageMaker deployment failures that look like AWS problems are actually Python environment problems: wrong Python version, broken dependency resolution, stale SDK that doesn't know about a current API. This skill makes env setup boring and correct.

## Core rules

1. **Never use the system Python.** Always work inside an isolated environment.
2. **Pin the Python version, not the package versions.** Use 3.10, 3.11, or 3.12. Avoid 3.13+ — ML libraries lag on wheel availability and dependency resolution breaks in confusing ways.
3. **Install the latest of each package.** Don't defensively pin `boto3` or `awscli`. Newer ones have current API surfaces and security fixes. Only pin if the user explicitly requires a specific version.
4. **Check installed versions correctly.** Use `importlib.metadata.version("package-name")`, never `module.__version__`. The latter is inconsistent across packages.
5. **The bundled scripts use `boto3` directly.** The SageMaker Python SDK is a valid alternative — see "boto3 vs the SageMaker SDK" below.

## boto3 vs the SageMaker SDK

The bundled deploy scripts (`deploy.py`, `deploy_async.py`, `teardown.py`) use `boto3` directly and read image URIs from [AWS's published Deep Learning Containers catalog](https://aws.github.io/deep-learning-containers/reference/available_images/). That fits this workflow's explicit-stages design — each skill produces a concrete value (region, role ARN, image URI) that the next one consumes — and `boto3` is the stable underlying API client.

The SageMaker Python SDK (v3) is fine to use when the user prefers it or their project already does. Since [PR #5960](https://github.com/aws/sagemaker-python-sdk/pull/5960) (June 2026), `ModelBuilder` auto-routes HuggingFace models to the current containers (text-generation → HuggingFace vLLM, multimodal → vLLM-Omni, embeddings → TEI). Don't avoid the SDK over stale-image or wrong-container concerns — that routing is fixed.

Two specific SDK cases that still need care:

- **Generative rerankers**: the SDK routes the `text-ranking` task to TEI unconditionally, which is wrong for causal-LM rerankers like Qwen3-Reranker — those need vLLM (see `hf-cloud-serving-image-selection`). Pass the container explicitly for these models.
- **SSO assumed-role credentials**: v3 has had credential-resolution regressions in `ModelTrainer` / `FrameworkProcessor` under SSO profiles. If SDK calls fail with credential errors while `aws sts get-caller-identity` succeeds in the same shell, suspect this rather than your AWS config.

If you use the SDK, install it into the isolated env like everything else (`.venv/bin/python -m pip install sagemaker`). The bundled scripts don't require it.

## How to set up

The fastest path is the bundled script — it's Python, so it runs the same on Windows, macOS, and Linux:

```bash
python3 scripts/setup_env.py        # macOS / Linux
python  scripts/setup_env.py        # Windows (PowerShell / cmd)
```

This script detects `uv` and uses it if available (faster), falls back to the stdlib `venv` module, creates `.venv/` with Python 3.12 (override: `python3 setup_env.py .venv 3.11`), refuses unsupported Python versions, installs from the bundled `requirements.txt`, and is idempotent. It also prints the correct interpreter path for the host OS (see below).

Manual equivalent:

```bash
# Preferred: uv
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python --upgrade boto3 awscli   # Windows: .venv\Scripts\python.exe

# Fallback: stdlib venv
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip boto3 awscli
```

After setup, **invoke the env's Python explicitly** rather than activating the venv. The interpreter path differs by platform:

```bash
.venv/bin/python deploy.py            # macOS / Linux
.venv\Scripts\python.exe deploy.py    # Windows
```

This works the same in scripts, interactive shells, and agent tool calls. The rest of this skill writes `.venv/bin/python` for brevity — on Windows substitute `.venv\Scripts\python.exe`.

## Verifying

```bash
.venv/bin/python scripts/check_versions.py
```

Prints versions of `boto3`, `botocore`, `awscli`. Uses `importlib.metadata.version()` so it works on every package, including ones without `__version__`. Pass arbitrary names: `... check_versions.py transformers huggingface_hub`.

## Deployment-specific extras

Default `requirements.txt` covers SageMaker orchestration. Some deployments need extras (`huggingface_hub` for model inspection, `transformers` for tokenizer validation). Add these to a deployment-specific requirements file in the project, install with the env's Python, don't pin unless there's a reason.

## Common pitfalls

**Mysterious `pip install` resolution errors**
Almost always Python 3.13+ trying to install packages without wheels yet, or installing into a polluted system Python. Recreate at 3.12: delete `.venv` and re-run `python3 setup_env.py .venv 3.12` (the script recreates the env when the version doesn't match, so you can also just re-run it).

**`pip install` succeeded but the script says "module not found"**
You installed into a different interpreter than the one running the script. Always invoke Python explicitly: `.venv/bin/python -m pip install ...` and `.venv/bin/python deploy.py`.

**Inline `python -c "..."` one-liners fail in PowerShell**
PowerShell's quoting rules mangle nested/escaped quotes in inline Python. Don't debug the quoting — write the snippet to a small `.py` file and run that. (All bundled helpers are files for exactly this reason.)

**boto3 call fails with "unknown parameter"**
Your boto3 is older than the API surface. Upgrade with `.venv/bin/python -m pip install --upgrade boto3`. Don't downgrade the script to match an old version.

**`sagemaker` (the SDK) installed but the bundled scripts fail**
The bundled scripts don't use the SDK — they only need `boto3`/`awscli` from `requirements.txt`. Installing `sagemaker` alongside is harmless, but it doesn't replace the requirements install.
