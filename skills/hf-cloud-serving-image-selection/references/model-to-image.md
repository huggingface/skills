# Model Family → Serving Container Decision Table

Consult this **before** writing deployment code that hardcodes an image URI.

The canonical source for AWS Deep Learning Container image URIs is:
**https://aws.github.io/deep-learning-containers/reference/available_images/**

This page is AWS-maintained and lists every published image family with example URIs, tags, CUDA versions, and platform (SageMaker vs EC2/ECS/EKS). Read URIs from there directly — substitute `<region>` with the user's region and pass to `deploy.py --image-uri`. The doc below explains *which* family to pick for which use case; the URI itself comes from the AWS page.

## Decision summary

| Model family | Container | Source |
|---|---|---|
| HuggingFace text-generation LLMs (Llama, Qwen, Mistral, Mixtral, DeepSeek, Phi, Gemma, GPT-OSS, etc.) | **HuggingFace vLLM DLC** | AWS catalog → "HuggingFace vLLM Inference" |
| Same as above, multimodal (vision-language, audio, any-to-any) | **HuggingFace vLLM-Omni DLC** | AWS catalog → "HuggingFace vLLM-Omni Inference" |
| Same family, when NO `huggingface-vllm` tag is compatible (verified) or the region has none | AWS vLLM DLC (fallback — never for version freshness) | AWS catalog → "vLLM" |
| Same family, alternative serving stack | DJL-LMI | AWS catalog → "DJL Inference" |
| HuggingFace embeddings + encoder cross-encoder rerankers | **TEI DLC** | AWS catalog → "HuggingFace Text Embeddings Inference" |
| Generative rerankers (causal-LM, e.g. Qwen3-Reranker) | **HuggingFace vLLM DLC** | Same as text-generation LLMs — see "Generative rerankers" below |
| HuggingFace classifiers, NER, QA, summarization | HF Inference Toolkit (CPU; GPU tags broken as of July 2026 — see SKILL.md "Known-broken images") | AWS catalog → "HuggingFace PyTorch Inference" |
| HuggingFace-curated SGLang build | HuggingFace SGLang | AWS catalog → "HuggingFace SGLang Inference" |
| SGLang (without HF wrapper) | SGLang | AWS catalog → "SGLang" |
| Amazon Nova (Lite, Micro, Pro) | SageMaker JumpStart | Use JumpStart deployment, not raw endpoint creation |
| Stable Diffusion / diffusion / image generation | **DJL Inference** | AWS catalog → "DJL Inference" — not the HF Inference Toolkit (GPU tags broken, see below); StabilityAI DLC exists but is stale |
| Inferentia / Trainium hardware | NeuronX variants | AWS catalog → search for "NeuronX" |
| Custom inference code | BYOC | User provides URI |

## Why vLLM, not TGI

Text Generation Inference (TGI) was the long-standing default for HuggingFace LLMs. As of late 2025 / early 2026, **TGI is archived** — no more major updates. Models released after the archive (Qwen3 most famously) fail health checks on TGI. Use vLLM instead.

The SageMaker SDK v2 helper `get_huggingface_llm_image_uri` returned TGI URIs; the v3 SDK removed it entirely. Since [sagemaker-python-sdk PR #5960](https://github.com/aws/sagemaker-python-sdk/pull/5960) (merged June 2026), v3's `ModelBuilder` auto-routes HuggingFace models by task: `text-generation` → HuggingFace vLLM DLC, multimodal tasks (`image-text-to-text`, `any-to-any`, `audio-text-to-text`) → vLLM-Omni, `feature-extraction` / `sentence-similarity` / `text-ranking` → TEI, SGLang opt-in only. Our decision table matches, with one deliberate divergence: the SDK sends **all** `text-ranking` models to TEI, which fails for generative rerankers (see below). Either way, don't use TGI for new deployments.

## Generative rerankers → vLLM, not TEI

Two reranker architectures exist:

- **Encoder cross-encoders** (BAAI/bge-reranker-*, mixedbread rerankers): BERT-family + classification head, `config.json` `architectures` ends in `ForSequenceClassification`. TEI serves these natively via its `/rerank` route.
- **Generative rerankers** (Qwen/Qwen3-Reranker-0.6B/4B/8B and similar): decoder-only causal LMs that emit a yes/no judgment token; relevance = P(yes)/(P(yes)+P(no)) from the logprobs. `config.json` `architectures` ends in `ForCausalLM`. These need **vLLM** — use the HuggingFace vLLM DLC, same as any text-generation LLM. TEI recognizes the Qwen3 architecture, starts loading it, then rejects the `classifier` model type — Qwen3 support in TEI is embeddings-only. That rejection costs a full endpoint-creation cycle (~20 min observed), so preflight with the model's `config.json` (`curl -s https://huggingface.co/<id>/raw/main/config.json`) before creating anything.

Deploy generative rerankers exactly like a vLLM LLM deployment (`SM_VLLM_*` env vars, AMI rule applies). The invocation pattern — raw completions API, `max_tokens=1`, logprobs scoring — is documented in `hf-cloud-sagemaker-production-defaults`.

## HuggingFace vLLM DLC (mandatory default for LLMs)

This is the default for **every** vLLM deployment, not a suggestion. The AWS vLLM repo further down is strictly a compatibility escape hatch.

URI pattern (from AWS catalog → "HuggingFace vLLM Inference"):
```
763104351884.dkr.ecr.<region>.amazonaws.com/huggingface-vllm:<version>-transformers<tv>-gpu-py<py>-cu<cuda>-ubuntu22.04
```

Example: `763104351884.dkr.ecr.us-east-1.amazonaws.com/huggingface-vllm:0.21.0-transformers5.8.1-gpu-py312-cu130-ubuntu22.04` (0.22.1 in the release pipeline as of July 2026 — read the newest tag from the catalog).

The image is built directly on the AWS vLLM DLC, so everything below about the AWS image applies to it too — same `SM_VLLM_*` env contract, same cu130 AMI requirement. On top of the base it carries current `transformers`, current `huggingface_hub` + `hf_xet` (current-generation Hub downloads; older images 403 against the XET CDN), ffmpeg for multimodal preprocessing, and HF performance defaults (expandable-segments allocator, LMCache CPU KV-offload). Model selection: `SM_VLLM_MODEL` as usual; if unset, the entrypoint auto-detects `/opt/ml/model` or falls back to `HF_MODEL_ID`.

For multimodal models (vision-language, audio, any-to-any) use the sibling `huggingface-vllm-omni` repo (catalog → "HuggingFace vLLM-Omni Inference") — same rules.

## AWS vLLM DLC (fallback only)

Use **only** when no `huggingface-vllm` tag is compatible with the model (a verified architecture/feature gap, not an assumed one) or the target region has no `huggingface-vllm` tag at all. This repo usually lists a **newer vLLM version** than `huggingface-vllm` — that alone is never a reason to pick it. If you are reading this section because the version number here is higher, go back to `huggingface-vllm`. URI pattern (from AWS catalog):
```
763104351884.dkr.ecr.<region>.amazonaws.com/vllm:<version>-gpu-py<py>-cu<cuda>-ubuntu22.04-sagemaker
```

Example: `763104351884.dkr.ecr.eu-west-1.amazonaws.com/vllm:0.23.0-gpu-py312-cu130-ubuntu22.04-sagemaker`

**vLLM AMI requirement (both repos)**: images with `cu130` or higher require setting `InferenceAmiVersion=al2-ami-sagemaker-inference-gpu-3-1` on the ProductionVariant. Without it the container dies on startup with no CloudWatch logs created. See the "vLLM AMI requirement" lookup table in the SKILL.md to map a tag to the right AMI version.

For environment variable configuration of the vLLM DLCs, see the SKILL.md.

## TEI DLC

Listed on the AWS catalog under "HuggingFace Text Embeddings Inference". The catalog row uses account ID `683313688378` (different from the main `763104351884` used by most other DLCs). TEI is published from its own account namespace and the per-region account IDs vary — if the canonical `683313688378` returns an ECR pull error for a non-us-east-1 region, check the [Region Availability page](https://aws.github.io/deep-learning-containers/reference/region_availability/) for the correct mapping.

Two variants:

- Repo `tei` — GPU build
- Repo `tei-cpu` — CPU build

Pick by instance type:
- `ml.g*`, `ml.p*`, `ml.inf*` → `tei` (GPU)
- `ml.c*`, `ml.m*`, `ml.t*` → `tei-cpu` (CPU)

CPU embeddings are dramatically cheaper than GPU and often fast enough — `ml.c6i.2xlarge` (~$0.20/hr) is a common starting point. GPU is needed for large embedding models (>1B params) or sustained high throughput.

### Supported architectures and staleness

TEI bakes architecture support into the image. The current upstream version supports BERT, CamemBERT, RoBERTa, XLM-RoBERTa, NomicBert, JinaBert, JinaCodeBert, Mistral, Qwen2/3, Gemma2/3, ModernBert. The AWS-published DLC sometimes lags upstream by months — if a recent architecture isn't supported, mirror the upstream image from `ghcr.io/huggingface/text-embeddings-inference:<version>` using `scripts/mirror_image.py` and pass the result to `deploy.py --image-uri` directly.

**Support is per (architecture, task), not per architecture.** Qwen3 appearing in the list means Qwen3 *embeddings*; TEI 1.8.x rejects Qwen3 with a classification head ("`classifier` model type is not supported"). Before picking TEI for a reranker, check the model's `config.json`: `architectures` ending in `ForSequenceClassification` on a BERT-family encoder is TEI territory; `ForCausalLM` means it's a generative reranker → vLLM (see above).

For environment variable configuration of TEI, see the SKILL.md.

## DJL Inference

Listed on the AWS catalog under "DJL Inference", published from the main `763104351884` account. Two reasons to reach for it:

1. **Diffusion / text-to-image models** — the recommended container for Stable Diffusion-class workloads (usually behind an async endpoint; see `hf-cloud-sagemaker-production-defaults`).
2. **Fallback when an HF DLC fails with CUDA/NCCL errors** — DJL images bundle their own complete CUDA/NCCL stack and don't depend on host libraries, so they sidestep the packaging-defect class entirely.

Configuration goes in a `serving.properties` file packaged alongside the model artifacts (or the equivalent `OPTION_*` env vars) rather than `SM_VLLM_*`/`HF_MODEL_ID` — check the [DJL Serving docs](https://docs.djl.ai/master/docs/serving/index.html) for the engine matching your model type rather than guessing keys.

## HF Inference Toolkit: GPU tags broken (NCCL packaging defect)

As of July 2026, every recently-tested GPU tag of `huggingface-pytorch-inference` (PT 2.3–2.6, cu121/cu124, transformers 4.48–5.5.3) fails at `import torch` with:

```
ImportError: libtorch_cuda.so: undefined symbol: ncclCommResume
```

torch in the image links NCCL 2.19+ symbols but the image ships an older NCCL. Verified on g5 **and** g6 — the defect is inside the container, so changing instance type, AMI, model, or inference code does not help, and neither does trying sibling tags. Worse, the MMS Java server keeps answering `/ping` while the Python worker crash-loops, so the endpoint can reach InService and silently serve nothing (async requests queue forever). Use DJL Inference or BYOC for GPU workloads until AWS ships fixed images; CPU tags are unaffected.
