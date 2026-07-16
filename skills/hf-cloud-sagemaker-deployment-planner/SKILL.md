---
name: hf-cloud-sagemaker-deployment-planner
description: 'Plan and coordinate the deployment of a model to Amazon SageMaker AI. Use this skill whenever the user wants to deploy, host, serve, or expose a model on SageMaker or AWS — including phrases like "deploy a model", "host this LLM on AWS", "serve this embedding model", "deploy a reranker", "deploy a text-to-image / diffusion model", "host this for async inference", "create an endpoint", "serve my fine-tuned model", or any request that involves making a model available for inference on AWS. Use this even when the user is vague (e.g. "I just want to get this running on AWS, you figure it out"). Works for text-generation LLMs, embedding models, rerankers, classifiers, text-to-image / diffusion models — picks the right serving stack and chooses between real-time and async inference. This is the entry-point skill for SageMaker deployment work — it asks clarifying questions, picks a deployment pathway, and coordinates the other deployment skills.'
---

# SageMaker Deployment Planner

You are helping a user deploy a model to Amazon SageMaker. Most users invoking this skill want the model deployed with reasonable defaults, in as few questions as possible. Ask only what you need, recommend a pathway honestly, and hand off to the specialized skills.

## Workflow phases

1. **Discovery** — what is being deployed and what are the constraints (this skill)
2. **Pathway selection** — real-time / serverless / async / batch / Bedrock CMI (this skill)
3. **Context preflight** — `hf-cloud-aws-context-discovery`, then `hf-cloud-python-env-setup`
4. **IAM preflight** — `hf-cloud-sagemaker-iam-preflight`
5. **Image selection** — `hf-cloud-serving-image-selection`
6. **Deployment** — `hf-cloud-sagemaker-production-defaults`

Phases 1–2 are this skill's job. The others activate when their patterns match.

## Discovery: ask only what you need

You will eventually need to know:

- **What model**: HuggingFace ID, S3 path to artifacts, or model name. If the user is vague ("the model I fine-tuned"), ask for the artifact location.
- **Model type**: text-generation LLM, embedding/reranker, or other (classifier, NER, etc.). This determines the serving stack — usually inferable from the model name (anything ending in `-embed-*`, starting with `BAAI/bge-`, `sentence-transformers/*` etc. is embeddings; chat/instruct models are LLMs). Only ask if it's genuinely ambiguous.
- **Traffic shape**: roughly how often will this be called?
- **Latency tolerance**: interactive, near-real-time, or async?
- **Cost sensitivity**: ask only if the user signals it or the traffic pattern is ambiguous.

Region comes from `hf-cloud-aws-context-discovery` — don't ask unless the user volunteers it.

Do **not** front-load all of these. A common minimal set is just: *what model, and roughly how often will it be called?* The model name usually settles the model-type question. That alone is often enough to narrow the pathway to two candidates. If the user already told you something, don't ask again.

## Pathway selection

| Pathway | When it fits | When it does not |
|---|---|---|
| **Real-time endpoint** | Steady traffic, sub-second to few-second latency, always-on | Very spiky or very sparse traffic (wastes money on idle) |
| **Serverless inference** | Spiky/intermittent, tolerates cold starts (~10s+), simpler models | LLMs above a few B params (memory/cold-start limits), strict SLAs |
| **Async inference** | Long inference (>60s), large payloads, queue-friendly | Interactive synchronous calls |
| **Batch transform** | Offline scoring over a dataset | Anything online or interactive |
| **Bedrock Custom Model Import** | Wants Bedrock-compatible API, supported base family, weights only | Custom inference logic, unsupported architectures |

For LLMs, **real-time endpoints are the default** unless traffic is explicitly spiky/sparse or inference is long-running. Serverless looks attractive for "low traffic" cases but most LLMs exceed its memory limits.

For **embeddings**, real-time is again the default — but CPU instances are usually the right choice (much cheaper, fast enough for most embedding workloads). Don't reflexively recommend GPU instances for embedding models; ask `hf-cloud-serving-image-selection` to consider CPU variants if the model is small (<1B params) and traffic is moderate.

For **text-to-image, video generation, or other long-inference workloads** (>30s per request) where traffic is also bursty: async inference is the right answer. It supports genuine scale-to-zero between batches and queues requests via S3, so you don't pay for idle GPU. `hf-cloud-sagemaker-production-defaults` has a dedicated `deploy_async.py` for this.

Real-time and async are the two scripted pathways. Serverless, batch transform, and Bedrock Custom Model Import are not currently scripted — for those, hand the user off with a brief explanation rather than trying to deploy them through this workflow.

If two pathways are both reasonable, say so in one sentence each and pick one. Don't bury the recommendation in options.

## Instance selection: check quota before recommending

Endpoint quotas are per instance type, per region, and default to **0** for GPU types in many accounts. Recommending an instance the account can't launch wastes a full deploy cycle on `ResourceLimitExceeded`. Check first:

```bash
aws service-quotas list-service-quotas --service-code sagemaker --region <region> \
    --query "Quotas[?contains(QuotaName, 'for endpoint usage') && Value > \`0\`].[QuotaName, Value]" \
    --output table
```

If the type you want isn't in the result, recommend one that is — or tell the user to request an increase (hours to days) *before* creating anything.

GPU family notes for the common 24 GB tier:

- `ml.g5.*` (A10G) and `ml.g6.*` (L4) both work with current vLLM images when the gpu-3-1 AMI is set (see `hf-cloud-serving-image-selection`). g6 is the newer generation and slightly cheaper per hour; g5 has roughly double the memory bandwidth, which usually means better LLM token throughput. Pick whichever has quota; when both do, either is defensible — g5 for throughput, g6 for cost.
- `ml.g6e.*` (L40S, 48 GB) when the model doesn't fit in 24 GB.

Once you have enough to recommend, state it plainly:

> Based on what you've told me, I'd recommend a real-time endpoint on `ml.g5.xlarge`. The model is small enough that this is cost-effective, and your traffic pattern is steady enough that you won't be paying for idle. Alternative: serverless would be cheaper if traffic dries up for hours at a time, but Qwen3-0.6B is at the edge of serverless memory limits and cold starts would be 15–30s. Want me to proceed with the real-time endpoint?

Then wait for confirmation. The user should know what they're about to spend money on before you create anything.

The plan lives in the conversation — don't generate `plan.yaml` or similar artifacts unless explicitly asked.

## Style

- Users invoking this skill are deferring to the agent because they don't want to do AWS plumbing. Match that energy: efficient, not exhaustive.
- One round of clarifying questions is usually enough. Three rounds is interrogation.
- When you don't know something specific (current image URI, SDK API surface, quotas), check it rather than guess. Other skills handle the "how to check" details.
- If the user pushes back on a recommendation, accept it. They know their constraints better than you do.
