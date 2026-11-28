# Model Card Template

Use this template when creating a README.md for a new model repo. Replace all
bracketed placeholders. Remove sections that do not apply.

---

````markdown
---
pipeline_tag: [PIPELINE_TAG]
library_name: [LIBRARY_NAME]
license: [LICENSE]
language:
  - [LANG_CODE]
datasets:
  - [username/dataset-name]
base_model: [org/base-model-name]
tags:
  - [tag1]
  - [tag2]
---

# [Model Name]

[One-paragraph summary: what the model does, what architecture it uses,
and what it was trained on. Keep it concise — this is the first thing
users see.]

## Model Details

- **Architecture**: [e.g. Transformer decoder, ViT-B/16, UNet]
- **Parameters**: [e.g. 7B, 125M]
- **Training framework**: [e.g. PyTorch, JAX]
- **Precision**: [e.g. float16, bfloat16]

## Intended Uses

- [Primary intended use case]
- [Secondary use case, if any]

### Out-of-Scope Uses

- [Uses the model is NOT designed for or should NOT be used for]

## Usage

### Installation

```bash
pip install transformers torch
```

### Inference Example

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

model = AutoModelForCausalLM.from_pretrained("[org/model-name]")
tokenizer = AutoTokenizer.from_pretrained("[org/model-name]")

inputs = tokenizer("[Your prompt]", return_tensors="pt")
outputs = model.generate(**inputs, max_new_tokens=100)
print(tokenizer.decode(outputs[0], skip_special_tokens=True))
```

### Pipeline Example

```python
from transformers import pipeline

pipe = pipeline("[PIPELINE_TAG]", model="[org/model-name]")
result = pipe("[Your input]")
print(result)
```

## Training Details

### Training Data

[Describe the dataset(s) used. Link to Hub datasets when possible.]

### Training Procedure

- **Hardware**: [e.g. 8x A100 80GB GPUs]
- **Training time**: [e.g. 72 hours]
- **Optimizer**: [e.g. AdamW]
- **Learning rate**: [e.g. 2e-5]
- **Batch size**: [e.g. 32]
- **Epochs**: [e.g. 3]
- **Precision**: [e.g. bfloat16 mixed precision]

### Training Hyperparameters

| Parameter | Value |
|-----------|-------|
| Learning rate | [value] |
| Batch size | [value] |
| Weight decay | [value] |
| Warmup steps | [value] |
| Max sequence length | [value] |

## Evaluation

### Benchmarks

| Benchmark | Metric | Score |
|-----------|--------|-------|
| [benchmark] | [metric] | [score] |

### Qualitative Examples

[Include 2-3 example inputs and outputs that demonstrate the model's
capabilities and limitations.]

## Limitations and Biases

- [Known limitation 1]
- [Known limitation 2]
- [Known bias or ethical consideration]

## Environmental Impact

<!-- Remove this section if not applicable -->

- **Hardware used**: [e.g. 8x A100 GPUs]
- **Training duration**: [e.g. 72 hours]
- **Carbon emissions**: [e.g. estimated using CodeCarbon]

## Citation

```bibtex
@article{[key],
  title={[Paper Title]},
  author={[Author, First and Author, Second]},
  journal={arXiv preprint arXiv:[XXXX.XXXXX]},
  year={[YEAR]}
}
```

## References

- [Paper Title](https://arxiv.org/abs/[XXXX.XXXXX])

## License

This model is released under the [[LICENSE_NAME]]([LICENSE_URL]) license.
````

---

## Gallery Section (for image/video models)

Add this section after the summary if the model generates visual outputs:

````markdown
<Gallery>
![Example prompt 1](./images/example1.png)
![Example prompt 2](./images/example2.png)
![Example prompt 3](./images/example3.png)
</Gallery>
````

## Notebook Section

If including a notebook for inference or fine-tuning, add it to the repo root
and reference it:

````markdown
## Notebooks

| Notebook | Description |
|----------|-------------|
| [inference.ipynb](./inference.ipynb) | Run inference with this model |
| [finetune.ipynb](./finetune.ipynb) | Fine-tune on your own data |
````

Notebooks in the repo automatically get "Open in Colab" and "Open in Kaggle"
buttons on the model page.
