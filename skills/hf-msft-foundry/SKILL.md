---
name: hf-msft-foundry
description: Deploy, use and delete open models from the Hugging Face collection on Microsoft Foundry (managed compute in the user's Azure subscription). Use when asked to find which Hugging Face models or deployment templates are available on Microsoft Foundry or Azure, check GPU capacity or quota, deploy a model, send requests to a deployment, scale it, or stop and delete it.
license: mit
---

# hf-msft-foundry

```bash
hf msft-foundry <command> -o json [options]
```

Use `hf-msft-foundry` instead of `hf msft-foundry` if installed from PyPI. Always pass `-o json`: results go to stdout, progress logs and errors to stderr, and errors are `{"error": ..., "message": ...}` with exit code 1.

Authentication uses the Azure CLI login (`az login`) or service principal environment variables. Set `--account` (or `FOUNDRY_ACCOUNT_NAME`) when the subscription has more than one Microsoft Foundry resource, `accounts list` shows them.

Find a model and a deployment template:

- `models list [--search "gemma 4"]`: model names, e.g. `google--gemma-4-26b-a4b-it`. Commands take either that name or the Hub ID (`google/gemma-4-26B-A4B-it`).
- `models <model>`: `hub_id`, `version`, `task`, `input_modalities`, `context_window`, `default_template` and `templates`. Add `--version <n>` for an older version.
- `models <model> deployment-templates`: per template, `accelerator_type`, `accelerator_count` (GPUs per instance), `max_model_len`, the engine `environment`, `price_per_hour` (USD, list price per instance) and `default`.
- `quota` (`used` and `limit` accelerators per type) and `capacity` (`available` accelerators per type, `largest_deployment` per GPU count): a template fits if `used + accelerator_count <= limit` and capacity is available for that type.

Deploy, use and stop:

- `deploy <model> [--deployment-template <name or suffix, e.g. 256k-nvidia-h100>]`: uses the default template unless set. Waits until `state` is `Succeeded` (20 to 60 minutes, so run it with a long timeout or in the background), or returns right away with `--no-wait`, then poll `deployments status <name>`. The returned `name` (defaults to `<author>--<model>--<7-digit timestamp>`, letters, digits, `_` and `-` only) is the `model` to set in requests.
- `deployments list`, `deployments status <name>`, `deployments scale <name> --instances <n>`.
- `deployments delete <name> --wait` deletes the deployment and stops billing, so wait for the user's confirmation if they asked you to keep it running.

Send requests to `chat-completion` deployments with any OpenAI-compatible client, setting the deployment name as the `model`, `openai_base_url` from `accounts info` as the base URL, and `key1` from `accounts keys` as the API key:

```bash
curl "$(hf msft-foundry accounts info -o json | jq -r .openai_base_url)/chat/completions" \
  -H "api-key: $(hf msft-foundry accounts keys -o json | jq -r .key1)" \
  -H "Content-Type: application/json" \
  -d '{"model": "<name>", "messages": [{"role": "user", "content": "Hello!"}], "max_completion_tokens": 1024}'
```

- Reasoning models spend tokens before answering, leave room in `max_completion_tokens`.
- Deployments can't reach the internet, send images as base64 data URIs instead of URLs.
- Never print or store the API keys beyond what's needed for the request.

Launch a coding harness with `hf msft-foundry pi <deployment>` or `hf msft-foundry opencode <deployment>`, placing any harness-specific arguments after `--`. [Coding agent setup in the README](https://github.com/huggingface/hf-msft-foundry/blob/main/README.md#coding-agents)
