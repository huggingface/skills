# Model Card Metadata Reference

Quick reference for YAML frontmatter fields in Hugging Face model cards.

## Table of Contents

- [pipeline_tag](#pipeline_tag)
- [library_name](#library_name)
- [license](#license)
- [language](#language)
- [datasets](#datasets)
- [base_model](#base_model)
- [tags](#tags)
- [new_version](#new_version)
- [co2_eq_emissions](#co2_eq_emissions)

---

## pipeline_tag

Determines the task model solves, inference related functions (Inference Providers), search filtering, and code snippets. Pick the
single most accurate tag.

### Text and NLP

| Tag | Use when |
|-----|----------|
| `text-generation` | Autoregressive LLMs (GPT, LLaMA, Mistral) |
| `text-classification` | Sentiment analysis, topic classification |
| `token-classification` | NER, POS tagging |
| `question-answering` | Extractive QA |
| `fill-mask` | Masked language models (BERT, RoBERTa, DeBERTa) |
| `summarization` | Text summarization |
| `translation` | Machine translation |
| `conversational` | Dialogue / chat models |
| `sentence-similarity` | Sentence embeddings, semantic search |
| `feature-extraction` | Generic embeddings |
| `zero-shot-classification` | Zero-shot text classification (NLI-based) |
| `table-question-answering` | Answering questions about tabular data |

### Vision

| Tag | Use when |
|-----|----------|
| `image-classification` | Classify images into categories |
| `object-detection` | Detect and localize objects |
| `image-segmentation` | Semantic / instance / panoptic segmentation |
| `depth-estimation` | Monocular depth prediction |
| `image-feature-extraction` | Image embeddings (DINOv2, AIMv2, ViT) |
| `zero-shot-image-classification` | CLIP-style zero-shot classification |
| `keypoint-detection` | Keypoint detection models (e.g. ViTPose) |
| `image-to-3d` | Image-to-3D models |

### Vision-Language

| Tag | Use when |
|-----|----------|
| `image-text-to-text` | VLMs that take image+text and output text (LLaVA, Qwen-VL) and some OCR models that take in task prompts |
| `visual-question-answering` | Answer questions about images |
| `document-question-answering` | Answer questions about documents/scans |
| `image-to-text` | Image captioning |

### Image/Video Generation

| Tag | Use when |
|-----|----------|
| `text-to-image` | Generate images from text (FLUX.1, Z-Image, Qwen-Image) |
| `image-to-image` | Image transformation (style transfer, super-resolution) |
| `text-to-video` | Video generation from text |
| `unconditional-image-generation` | Generate images without conditioning |
| `text-to-3d` | Text-to-3D models |

### Audio

| Tag | Use when |
|-----|----------|
| `automatic-speech-recognition` | Speech-to-text (Whisper) |
| `text-to-speech` | Text-to-audio synthesis |
| `audio-classification` | Classify audio clips |
| `text-to-audio` | Generate audio from text descriptions |

### Multimodal

| Tag | Use when |
|-----|----------|
| `any-to-any` | Models handling arbitrary input/output modalities (Gemma-3n, Qwen-Omni, Janus-Pro, MiniCPM-o) |

### Others

| Tag | Use when |
|-----|----------|
| `robotics` | Robotics models, vision-language-action (VLA) models |
| `reinforcement-learning` | RL agents and policies |

---

## library_name

Specifies the framework. Enables "Use this model" code snippets on the model
page and allows download tracking.

| Value | Framework |
|-------|-----------|
| `transformers` | Hugging Face Transformers |
| `diffusers` | Hugging Face Diffusers (Stable Diffusion, etc.) |
| `sentence-transformers` | Sentence Transformers |
| `timm` | PyTorch Image Models |
| `peft` | PEFT adapters (LoRA, QLoRA) |
| `setfit` | SetFit few-shot classification |
| `spacy` | spaCy NLP |
| `fasttext` | FastText |
| `flair` | Flair NLP |
| `allennlp` | AllenNLP |
| `adapter-transformers` | Adapter-based fine-tuning |
| `onnx` | ONNX Runtime |
| `tensorrt` | NVIDIA TensorRT |
| `openvino` | Intel OpenVINO |
| `mlx` | Apple MLX |
| `gguf` | GGUF quantized models (llama.cpp) |

If the model doesn't use any registered library, omit this field.

---

## license

Use SPDX identifiers. Common choices:

| Identifier | License |
|------------|---------|
| `apache-2.0` | Apache License 2.0 |
| `mit` | MIT License |
| `cc-by-4.0` | Creative Commons Attribution 4.0 |
| `cc-by-sa-4.0` | CC Attribution-ShareAlike 4.0 |
| `cc-by-nc-4.0` | CC Attribution-NonCommercial 4.0 |
| `cc-by-nc-sa-4.0` | CC Attribution-NonCommercial-ShareAlike 4.0 |
| `gpl-3.0` | GNU GPL v3 |
| `llama3` | Meta Llama 3 Community License |
| `llama3.1` | Meta Llama 3.1 Community License |
| `llama3.2` | Meta Llama 3.2 Community License |
| `gemma` | Google Gemma License |
| `openrail` | Open RAIL License |
| `openrail++` | Open RAIL++ License |
| `bigscience-openrail-m` | BigScience OpenRAIL-M |
| `other` | Custom license (describe in model card) |

For custom or proprietary licenses, use `license: other` and add a
`license_name` and optionally `license_link` field:

```yaml
license: other
license_name: my-custom-license
license_link: https://example.com/license
```

---

## language

ISO 639-1 codes. Use a list for multilingual models:

```yaml
language:
  - en
  - fr
  - de
  - zh
```

Common codes: `en` (English), `zh` (Chinese), `es` (Spanish), `fr` (French),
`de` (German), `ja` (Japanese), `ko` (Korean), `ar` (Arabic), `hi` (Hindi),
`pt` (Portuguese), `ru` (Russian), `multilingual`.

---

## datasets

Link to Hub datasets used for training. Creates cross-links on both the model
and dataset pages:

```yaml
datasets:
  - username/my-dataset
```

Use the full `org/dataset-name` format for non-canonical datasets.

---

## base_model

Set when this model derives from another model on the Hub.

### Fine-tune

```yaml
base_model: meta-llama/Llama-3-8B
```

### Quantized version

```yaml
base_model: meta-llama/Llama-3-8B
base_model_relation: quantized
```

### Merge of multiple models

```yaml
base_model:
  - model-a/name
  - model-b/name
base_model_relation: merge
```

### Adapter (LoRA, etc.)

```yaml
base_model: meta-llama/Llama-3-8B
base_model_relation: adapter
```

This populates the **Model Tree** on the Hub, showing the lineage of derived
models.

---

## tags

Free-form tags for discoverability. Use lowercase, hyphenated strings:

```yaml
tags:
  - medical
  - code
  - biology
  - finance
  - multilingual
  - rlhf
  - dpo
  - lora
  - chat
```

Tags are searchable on the Hub. Combine domain tags (e.g. `medical`) with
technique tags (e.g. `lora`, `rlhf`).

---

## new_version

Set on the **older** model's card to point users to the updated version.
Displays a banner on the old model's page:

```yaml
new_version: org/updated-model-name
```

---

## co2_eq_emissions

Report carbon emissions from training:

```yaml
co2_eq_emissions:
  emissions: 123.45
  source: "CodeCarbon"
  training_type: "pre-training"
  geographical_location: "US-East"
  hardware_used: "8xA100 GPUs"
```

All sub-fields are optional except `emissions` (in kg CO2 equivalent).

---

## Full Example

A complete frontmatter block for a fine-tuned LLM:

```yaml
---
pipeline_tag: text-generation
library_name: transformers
license: apache-2.0
language:
  - en
datasets:
  - HuggingFaceH4/ultrachat_200k
  - HuggingFaceH4/ultrafeedback_binarized
base_model: meta-llama/Llama-3-8B
tags:
  - chat
  - rlhf
  - dpo
co2_eq_emissions:
  emissions: 85.2
  source: CodeCarbon
  training_type: fine-tuning
  hardware_used: 4xA100 80GB
---
```
