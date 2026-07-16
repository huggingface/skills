---
name: hf-cloud-serving-image-selection
description: 'Pick the right serving container for a SageMaker model deployment and find its current image URI. Use this skill whenever about to deploy a model to a SageMaker endpoint and an image URI needs to be chosen — including when the user says "deploy this LLM", "host this HuggingFace model", "serve this fine-tuned model", "deploy this embedding model", "host a reranker", "serve a sentence-transformers model", or when about to hardcode any container URI in deployment code. HuggingFace-curated Deep Learning Containers are ALWAYS preferred: HuggingFace vLLM (LLMs and generative rerankers), HuggingFace vLLM-Omni (multimodal), TEI (embeddings/cross-encoder rerankers), HF Inference Toolkit (other transformers). Generic images (AWS vLLM, DJL-LMI, SGLang) are used only when no HuggingFace image is compatible — never merely because they carry a newer version. Never hardcode a container URI from memory and never default to TGI. Prevents stale-image failures and wrong-region URIs.'
---

# Serving Image Selection

The serving container is the single thing most likely to break a SageMaker deployment that "looked correct on paper". Wrong container, stale tag, or the wrong AMI — all produce the same opaque `Failed to pass health check` error.

## Rule zero: HuggingFace images always win

When both a HuggingFace-curated family (`huggingface-vllm`, `huggingface-vllm-omni`, `huggingface-sglang`, `tei`, `huggingface-pytorch-inference`) and a generic family (`vllm`, `vllm-omni`, `sglang`, `djl-inference`) can serve the model, **the HuggingFace one is mandatory, not preferred**. The only valid reasons to use a generic image:

1. **Verified incompatibility** — the model needs an architecture/modality/feature no available HuggingFace tag supports, confirmed against the catalog (not assumed).
2. **No HuggingFace tag exists in the target region** and mirroring is not an option.
3. **The HuggingFace image is in "Known-broken images"** below.

A **newer version number on the generic repo is not a reason**. The AWS `vllm` repo often publishes a higher vLLM version than `huggingface-vllm`; an older-but-compatible `huggingface-vllm` tag still wins. "Latest vLLM" is not a requirement anyone stated — compatibility with the model is. If you fall back, record in the deployment log which of the three reasons applied.

## Where image URIs come from

**Primary source: AWS's official Deep Learning Containers catalog.**

URL: https://aws.github.io/deep-learning-containers/reference/available_images/

This page is AWS-maintained and lists every image family with example URIs, tags, CUDA versions, Python versions, and platform (SageMaker vs EC2/ECS/EKS). When picking a URI for a deployment, **read it from this page directly** — copy the example URL, substitute `<region>` with the user's region, and pass it to `deploy.py --image-uri`.

The example URLs use `763104351884` as the account ID for most regions. A few regions use different accounts (e.g. `eu-south-1` uses `692866216735`). Check the [Region Availability page](https://aws.github.io/deep-learning-containers/reference/region_availability/) when in doubt.

**Exception: none currently.** Every image family used by this workflow is now on the AWS catalog page (TEI was added in late 2026). If you encounter a new family that isn't there, mirror it via `mirror_image.py` and pass the resulting URI directly.

## Quick decision

| Model | Container family | How to get the URI |
|---|---|---|
| HuggingFace text-generation LLM (Llama, Qwen, Mistral, etc.) | **HuggingFace vLLM** | AWS catalog → "HuggingFace vLLM Inference" (ECR repo `huggingface-vllm`) |
| Same as above, multimodal | **HuggingFace vLLM-Omni** | AWS catalog → "HuggingFace vLLM-Omni Inference" (ECR repo `huggingface-vllm-omni`) |
| HuggingFace embeddings | TEI | AWS catalog → "HuggingFace Text Embeddings Inference" |
| Encoder / cross-encoder rerankers (BERT-family `*ForSequenceClassification`) | TEI | Same as embeddings |
| **Generative rerankers** (causal-LM, e.g. Qwen3-Reranker) | HuggingFace vLLM | Same as text-generation LLMs — **not TEI**, see "Rerankers: TEI or vLLM?" |
| Text-to-image / diffusion (Stable Diffusion, FLUX) | DJL Inference | AWS catalog → "DJL Inference" — **not** HF Inference Toolkit, see "Known-broken images" |
| HuggingFace classifiers, NER, QA, summarization | HF Inference Toolkit (CPU) | AWS catalog → "HuggingFace PyTorch Inference"; GPU tags currently broken — see "Known-broken images" |
| User specifically wants SGLang | HuggingFace SGLang | AWS catalog → "HuggingFace SGLang Inference" |
| No compatible `huggingface-vllm` tag (verified incompatibility or region gap — see "Rule zero") | vLLM (AWS) | AWS catalog → "vLLM" section — fallback only, never for version freshness |
| User specifically wants DJL-LMI | DJL Inference | AWS catalog → "DJL Inference" |
| Amazon Nova | SageMaker JumpStart | Use JumpStart, not raw endpoint creation |
| Custom inference code | BYOC | User provides URI |

**HuggingFace-curated DLCs are mandatory when one is compatible (see "Rule zero").** `huggingface-vllm` is layered directly on the AWS vLLM DLC — **identical `SM_VLLM_*` env contract and the same cu130 AMI rule** — and adds current `transformers`, current `huggingface_hub` + `hf_xet` (avoids the XET-CDN 403 download failures older images hit), and HF performance defaults. It is also what SageMaker SDK v3 auto-routes to. The AWS `vllm` image is a compatibility escape hatch only; it usually shows a higher vLLM version than `huggingface-vllm`, and that is not a reason to pick it.

**Do not use TGI.** Text Generation Inference is archived. Models released after the archive (Qwen3 most famously) fail ping health checks on TGI. Use vLLM instead. (The SageMaker SDK v3 agrees: since [PR #5960](https://github.com/aws/sagemaker-python-sdk/pull/5960), June 2026, its `ModelBuilder` auto-routes `text-generation` to the HuggingFace vLLM DLC and multimodal tasks to HuggingFace vLLM-Omni.)

Full reasoning for each family in `references/model-to-image.md`.

## Rerankers: TEI or vLLM?

"Reranker" covers two very different architectures, and picking wrong wastes a full endpoint-creation cycle (~20 min) before TEI rejects the model:

- **Encoder cross-encoders** (BAAI/bge-reranker-*, mixedbread, most `sentence-transformers` rerankers) — BERT-family models with a classification head. `config.json` has `architectures: [..ForSequenceClassification]` on a TEI-supported encoder type. → **TEI**.
- **Generative rerankers** (Qwen/Qwen3-Reranker-*, and similar causal-LM judges) — decoder LLMs that score relevance via the logprob of a yes/no token. `config.json` has `architectures: [..ForCausalLM]`. → **HuggingFace vLLM**, deployed exactly like a text-generation LLM. TEI will load the architecture then reject the `classifier` model type (Qwen3 support in TEI is *embeddings-only*). Invocation pattern (raw completions API, `max_tokens=1`, logprobs scoring) is in `hf-cloud-sagemaker-production-defaults`.

**Preflight before creating any resources** — one HTTP GET settles it:

```bash
curl -s https://huggingface.co/<model-id>/raw/main/config.json
# "architectures": ["Qwen3ForCausalLM"]              → vLLM
# "architectures": ["XLMRobertaForSequenceClassification"] → TEI
```

For TEI also confirm the *(architecture, task)* pair: an architecture appearing in TEI's supported list means embeddings support, not necessarily classification/reranking support.

Heads-up: SageMaker SDK v3 (PR #5960) routes the `text-ranking` task to TEI **unconditionally** — correct for cross-encoders, wrong for generative rerankers. Don't treat the SDK's routing as evidence that TEI can serve a given reranker.

## Workflow

For every family: **read the URI from the AWS catalog page**.

1. Open https://aws.github.io/deep-learning-containers/reference/available_images/
2. Find the section for the right family (e.g. "HuggingFace vLLM Inference" for HuggingFace LLMs, "HuggingFace Text Embeddings Inference" for embeddings)
3. Pick the newest row marked `SageMaker` for the platform column — newest **within that family**. Do not switch to another family's section because it lists a higher engine version (see "Rule zero")
4. Substitute `<region>` with the user's region (from `hf-cloud-aws-context-discovery`)
5. For vLLM: also check the AMI requirement (see "vLLM AMI requirement" below)
6. Pass the URI to `deploy.py --image-uri` (real-time) or `deploy_async.py --image-uri` (async)

### TEI: pick the right variant

The TEI catalog row lists two URIs — GPU (`tei` repo) and CPU (`tei-cpu` repo). Pick based on the instance type:

- `ml.g*`, `ml.p*`, `ml.inf*` → GPU variant
- `ml.c*`, `ml.m*`, `ml.t*` → CPU variant

Mixing them fails: CPU image on a GPU instance wastes hardware, GPU image on a CPU instance fails to start.

**Note on the TEI account ID**: the catalog page shows `683313688378` as the example account, but TEI is published from a different account namespace than the main AWS DLCs and the per-region account IDs vary. If `683313688378.dkr.ecr.<region>.amazonaws.com/tei:...` returns an ECR pull error for a region other than us-east-1, check the [Region Availability page](https://aws.github.io/deep-learning-containers/reference/region_availability/) for the correct account ID for that region.

## vLLM AMI requirement

vLLM DLC images with **CUDA 13 or higher** (current default: `cu130`) require setting `InferenceAmiVersion=al2-ami-sagemaker-inference-gpu-3-1` on the ProductionVariant. This applies equally to `huggingface-vllm` and `huggingface-vllm-omni` (layered on the same cu130 base) and to the AWS `vllm` repo. Without it the container dies on startup with no CloudWatch logs ever created. The failure looks identical to many other things (account-level issues, quota, networking) and routinely sends people down wrong diagnostic paths.

Lookup table:

| Tag contains | InferenceAmiVersion to pass |
|---|---|
| `cu130` (or higher) | `al2-ami-sagemaker-inference-gpu-3-1` |
| `cu129` or lower | (omit the flag; default AMI works) |

Rule of thumb: if the vLLM tag you picked contains `cu130` or later, pass `--inference-ami-version al2-ami-sagemaker-inference-gpu-3-1` to `deploy.py`. If a future CUDA version (cu140+) needs a different AMI, add a row to the table when AWS publishes the new image.

This is a vLLM-specific concern. TEI and HF Inference Toolkit images don't need an AMI override.

## Configuring the vLLM DLCs (HuggingFace vLLM and AWS vLLM)

Both images share the same contract: configuration as environment variables on the SageMaker model definition, `SM_VLLM_*` mapped to vLLM CLI flags. The `huggingface-vllm` entrypoint additionally auto-detects the model when `SM_VLLM_MODEL` is unset — from `/opt/ml/model` if artifacts are mounted, else from `HF_MODEL_ID` — but setting `SM_VLLM_MODEL` explicitly works on both and is what our examples use.

### Required for every HuggingFace LLM deployment

| Env var | Purpose | Notes |
|---|---|---|
| `SM_VLLM_MODEL` | HF model ID (e.g. `Qwen/Qwen3-0.6B`) or `/opt/ml/model` if loading from S3 | — |
| `SM_VLLM_HOST` | **Must be `0.0.0.0`** | Otherwise vLLM binds localhost only, ping fails, container dies before logs. Top cause of mystery failures with this image. |
| `SM_VLLM_TRUST_REMOTE_CODE` | `true` for Qwen and several recent architectures | Set unconditionally — downside negligible, upside is the model loads. |
| `HUGGING_FACE_HUB_TOKEN` | HF token | Required for gated models. |

### Tuning (optional)

| Env var | Purpose |
|---|---|
| `SM_VLLM_MAX_MODEL_LEN` | Max sequence length — set this; defaults can be wrong for fine-tunes |
| `SM_VLLM_GPU_MEMORY_UTILIZATION` | Float 0.0–1.0, ~0.9 reasonable |
| `SM_VLLM_TENSOR_PARALLEL_SIZE` | GPU count for multi-GPU instances |
| `SM_VLLM_DTYPE` | `auto`, `bfloat16`, `float16` |

Any vLLM CLI flag works — uppercase, replace dashes with underscores, prepend `SM_VLLM_`.

## Configuring TEI

Simpler env contract than vLLM:

| Env var | Purpose | Required |
|---|---|---|
| `HF_MODEL_ID` | HF model ID (e.g. `BAAI/bge-large-en-v1.5`) or `/opt/ml/model` | Yes |
| `HF_TOKEN` | HF auth token | Only for gated models |
| `MAX_BATCH_TOKENS` | Max tokens per batch (default 16384) | No |
| `MAX_CLIENT_BATCH_SIZE` | Max requests per client batch (default 32) | No |

No host-binding to configure, no trust-remote-code flag. The architectures TEI supports (BERT, CamemBERT, RoBERTa, XLM-RoBERTa, NomicBert, JinaBert, JinaCodeBert, Mistral, Qwen2/3, Gemma2/3, ModernBert) are baked into the image.

## CUDA / instance compatibility

Critical and easy to get wrong:

| CUDA in image tag | Default AMI | With `al2-ami-sagemaker-inference-gpu-3-1` |
|---|---|---|
| cu124 / cu128 | g5, g6, p5 all work | (not needed) |
| cu129 | g6, p5; g5 fails (driver mismatch → CannotStartContainerError) | expected to fix g5 (unverified) |
| cu130+ | fails everywhere — AMI flag is mandatory | g5, g6, p5 all work (cu130-on-g5 verified June 2026) |

The driver comes from the host AMI, not the instance family — so passing the gpu-3-1 AMI (which vLLM cu130 images require anyway) also makes `ml.g5.*` viable for cu129+ images.

## VPC / NAT gateway problem

SageMaker endpoints inside a VPC **without** a NAT gateway can't pull from `public.ecr.aws`. The deployment fails with an image-pull error that doesn't mention "VPC" or "egress".

For images on AWS's regional ECR (everything in the catalog): SageMaker reaches them through built-in routing, no NAT needed. Use the regional URI pattern (`<account>.dkr.ecr.<region>.amazonaws.com/...`), not the `public.ecr.aws/...` pattern.

For images requiring `public.ecr.aws` access (less common): mirror to a private ECR repo in your account with `scripts/mirror_image.py` (cross-platform; needs Docker + the `aws` CLI). Run it from the shell where the AWS CLI works.

```bash
# macOS / Linux
PRIVATE_URI=$(python3 scripts/mirror_image.py \
    public.ecr.aws/deep-learning-containers/vllm:<tag> \
    vllm-mirror)
```

```powershell
# Windows (PowerShell) — capture stdout into a variable
$PRIVATE_URI = python scripts\mirror_image.py `
    public.ecr.aws/deep-learning-containers/vllm:<tag> vllm-mirror
```

## When the catalog page won't render, is stale, or is wrong

**The page won't render / fetch returns junk**: the catalog page is JavaScript-heavy and some fetch tools get an empty shell. Fallbacks, in order:

1. **The catalog's source data on GitHub** — the page is generated from one YAML file per version, listing exact tags, CUDA, and Python versions. List a family's files, then fetch the newest:
   ```bash
   curl -s https://api.github.com/repos/aws/deep-learning-containers/contents/docs/src/data/huggingface-vllm
   curl -s https://raw.githubusercontent.com/aws/deep-learning-containers/main/docs/src/data/huggingface-vllm/0.21.0-gpu-sagemaker.yml
   ```
   Directory names match ECR repos (`huggingface-vllm`, `huggingface-vllm-omni`, `huggingface-tei`, `vllm`, `djl-inference`, ...).
2. **Query ECR directly** for current tags in the target region (works with credentials that can read the DLC registry; if it returns AccessDenied, use the YAML files):
   ```bash
   aws ecr describe-images --registry-id 763104351884 --repository-name huggingface-vllm \
       --region <region> --query 'sort_by(imageDetails,&imagePushedAt)[-5:].imageTags' --output json
   ```
3. [Release notes on the DLC GitHub repo](https://github.com/aws/deep-learning-containers/releases).

**A tag was just released and isn't on the page yet**: rare; AWS updates the page on each release. Check the release notes above.

**An architecture you need isn't supported by the listed image yet**: for TEI specifically, you can mirror the upstream image from GHCR (`ghcr.io/huggingface/text-embeddings-inference:<version>`) into private ECR and pass the resulting URI directly to `deploy.py --image-uri`. Same `mirror_image.py` script.

## Known-broken images (last checked July 2026)

| Image | Defect | Use instead |
|---|---|---|
| `huggingface-pytorch-inference` **GPU** tags — all recent ones tested (PT 2.3–2.6, cu121/cu124, transformers 4.48–5.5.3) | `ImportError: libtorch_cuda.so: undefined symbol: ncclCommResume` at `import torch`. The NCCL bundled in the image is older than what torch links against — a packaging defect *inside the container*, on g5 **and** g6, regardless of AMI, model, or inference code. The MMS Java front-end keeps answering `/ping`, so the endpoint can reach InService while the Python worker crash-loops and serves nothing. | DJL Inference (bundles its own complete CUDA/NCCL stack) or BYOC. CPU tags are unaffected. |

Re-check when AWS publishes new `huggingface-pytorch-inference` GPU tags — remove the row once a fixed image is confirmed.

**General fallback rule**: when an HF DLC fails with CUDA/NCCL linker errors, switch to DJL Inference rather than iterating over sibling tags — the defect class is per-repo, not per-tag (three different tags were tried for the case above; all broken).

**Related HF Hub gotcha**: older DLCs can fail model download with `403 Forbidden` from HF's XET CDN (their bundled `huggingface_hub` predates XET auth). Set `HF_HUB_ENABLE_HF_TRANSFER=0` to force the standard download path, or pre-stage weights in S3.

## Hub download time at first boot

Loading the model from HF Hub happens *inside the container after the endpoint starts* — expect **5–15+ minutes** before InService even for small models, longer for multi-GB ones. A slow first boot is not a failure; don't tear down or re-diagnose before the deploy script's 30-minute wait expires.

For production or repeated deployments, pre-stage the weights in S3 and pass `--model-s3-uri` to `deploy.py` (the model then loads from `/opt/ml/model`) — faster, immune to Hub rate limits/outages, and no `HUGGING_FACE_HUB_TOKEN` needed at runtime.
