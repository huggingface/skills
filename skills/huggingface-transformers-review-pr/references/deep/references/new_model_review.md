# New Model and Modular Review

Reference for new model additions, model refactors, generated files, and conversion mapping changes.

## First Pass

- Closest existing model family. Does it have `modular_<name>.py`?
- Changed generated files: do they contain the auto-generated banner?
- Can the new model inherit from a closer existing parent with fewer overrides?
- Does the PR add only necessary public API surface?

Implementation lives in `modular_<name>.py`. Generated files come from `utils/modular_model_converter.py`. Do not hand-edit generated files.

## Held to the current standard (novelty is not a waiver)

A new model is graded against the current framework convention, never against what legacy models contain. Full treatment in `../review_deep.md` ("New-model standard: novelty is not a waiver"); the mechanical new-model checks:

- **Legacy idioms are findings in new code:** `return_dict`/`output_*` in signatures, manual flag resolution, dict/intermediate-tuple output without decorator BC, bespoke output dataclasses. Not graded against legacy prevalence — `grep` count across old models is not a defense for a new file.
- **Modules take `config`,** not loose scalar dims; architecture knobs are config fields, not constructor defaults or call-site literals.
- **Sampling/inference hyperparameters** belong in a `GenerationConfig`, not as method arguments.
- **Forward decomposition:** a `forward` over ~100 LOC or with ≳10 positional args is a finding before per-line review.
- **Codepath count (tenet 6):** chunked/unchunked, varlen/dense, multiple inference entrypoints, bespoke setup/toggle methods the standard flow does not require — each parallel path is a finding; a method mutating global/process state as an instance side effect is `warning`.
- **Hardcoded tables/constants** belong in the checkpoint config on the hub, not baked into source.
- **Generated `modeling_*.py` is self-contained:** a surviving `from ..other_model.modeling_other import X` in the generated file is a finding.
- **Modular inheritance floor:** a `modular_*.py` that inherits from almost nothing is a file-level finding (see `modular_review.md`).
- **Framework mechanisms apply by absence** (see `mechanisms_review.md`): hub-kernel decorators on norm/rotary modules, `ALL_ATTENTION_FUNCTIONS` dispatch (no `*_ATTENTION_CLASSES` dicts, even inherited from a legacy parent), `@use_experts_implementation` for MoE experts, fusion mapping over `if config.fuse_x` swaps, conversion-registry aliases over duplicated blocks.
- **Flags and embeddings access:** every `PreTrainedModel` subclass gets the flags audit (`_supports_*` vs actual dispatch, dict-form `_tied_weights_keys`, `_can_compile_fullgraph`, `input_modalities`, `main_input_name`, `_tp_plan` survival through modular) and the `EmbeddingAccessMixin` check (`mechanisms_review.md`).

## Modular Quality

- Inherit from the closest existing model, not the most famous one.
- Override only architectural differences.
- Reuse existing attention, MLP, normalization, rotary embedding, output, and task-head helpers where they match.
- Do not reimplement registration, init, or forward behavior the parent handles.
- Imports from established model files: explicit and minimal.

Flag copied code if a conversion rename would allow reuse.

## Generic Layers

Check `src/transformers/modeling_layers.py` before accepting custom heads or layers.

- `GradientCheckpointingLayer` for transformer blocks that need checkpointing.
- `GenericForSequenceClassification` for last-token sequence classification.
- `GenericForTokenClassification` for token classification.
- `GenericForQuestionAnswering` for extractive QA.

Custom heads are acceptable when pooling, logits, loss, or model composition differs.

## Decorators and Output Capture

Forward methods use the decorator stack, not manual output plumbing. The exact runtime semantics (what `capture_outputs` pops, hook index defaults, the one-level rule, backbone layouts) are in `modular_review.md` — read it before flagging a stack as wrong or redundant.

- Base model forwards returning `ModelOutput` with config defaults: `@merge_with_config_defaults`.
- Base model forwards exposing hidden states or attentions: `@capture_outputs`.
- Head forwards supporting `return_dict=False`: `@can_return_tuple`.
- `@capture_outputs(tie_last_hidden_states=False)` when the last captured hidden state must remain pre-final-normalization (common in vision encoders).
- `_can_record_outputs` points to the module classes that produce the outputs.
- `OutputRecorder` is required for tuple index, submodule name, class-name suffix, or `capture_initial_hidden_state=False`.
- Composite models use submodel `_can_record_outputs`, not a single top-level mapping.

Bugs:

- Recording attentions from the pre-consolidation attention class.
- Capturing hidden states from the wrong block: off-by-one hidden-state tuples.
- Missing `@can_return_tuple` on a head forward returning `ModelOutput`.
- Manually threading `output_hidden_states`, `output_attentions`, `return_dict` when decorators own BC behavior.

## Conversion Mapping

`src/transformers/conversion_mapping.py` owns checkpoint name compatibility.

- New mappings use `WeightRenaming`, `WeightConverter`, `PrefixChange`, or operation classes from `core_model_loading.py`.
- Class-name mappings when a task head differs from the shared `model_type` baseline.
- `_MODEL_TO_CONVERSION_PATTERN` aliases point to an existing pattern.
- Submodel conversions stay scoped by `get_model_conversion_mapping`.
- Reverse save conversion works for converters that split, concatenate, transpose, or merge module lists.
- Mapping order: a broad prefix rule does not steal a later specific reverse match.
- No model class defines ad hoc checkpoint conversion attributes when the centralized mapping applies.

Reuse via rename:

- `query/key/value/output.dense` → `q_proj/k_proj/v_proj/o_proj`.
- `intermediate.dense` + `output.dense` → `mlp.fc1`, `mlp.fc2`.
- Encoder namespaces → flattened `layers`.
- Vision/text tower prefixes via `PrefixChange` or anchored `WeightRenaming`.

If a small rename set matches an existing parent's checkpoint layout, use mapping + inheritance over copied modeling code.

## Loading and Saving

Inspect `src/transformers/core_model_loading.py` for diffs touching loading or conversions.

- Missing and unexpected keys updated when a conversion consumes or produces weights.
- Converters collect all required tensors before loading.
- Quantizer-added conversions compose with static conversions.
- Base model prefixes do not double-apply or skip mappings.
- Sibling submodels with the same `model_type` get scoped transforms.
- Save round-trip uses the reverse transform in the intended order.

## Attention Backend

Only when the diff touches attention:

- Attention uses `ALL_ATTENTION_FUNCTIONS.get_interface` when claiming backend support.
- SDPA and eager paths use the same mask semantics and dropout.
- `output_attentions=True` is correct for backends that cannot return attention weights.
- Cache updates, `is_causal`, GQA, and position embeddings are consistent.
- `_supports_sdpa`, `_supports_flash_attn`, `_supports_attention_backend` are not set unless the implementation supports them.

## Tests for New Models

- Config / model instantiation and save / load.
- Shape tests plus slow integration tests on a real checkpoint when available.
- Numerical preprocessing tests with representative slices, not `pixel_values.shape`.
- Numerical forward tests: logits, hidden states, boxes, masks, or task outputs.
- Conversion / load tests for missing or unexpected keys and wrong renames.
- Generation tests for causal or conditional generation models.
- Processor tests for multimodal placeholder counts and token replacement.

Shape-only integration tests do not constitute coverage. If the output is expensive to compute, include a small deterministic slice.

## Registration Checklist

For new public models:

- `src/transformers/models/__init__.py`
- `src/transformers/__init__.py`
- auto config / model / tokenizer / processor / image / video mappings
- `utils/check_repo.py` when required
- docs index and model docs
- tests under `tests/models/<name>/`

## Docs and metadata coherence (D28)

- One name, everywhere: directory name, `model_type`, class prefix, doc page title, and doc filename agree. Any disagreement is a finding ("any name is fine as long as it is consistent").
- Doc page has an abstract, a runnable usage snippet (executed when the checkpoint is public — see `fidelity_review.md`), and the toctree entry.
- Snippets use `Auto*` classes, `device_map="auto"`, and current API names (`dtype`, never the deprecated `torch_dtype`); no inline benchmark scripts or near-duplicate per-variant sections — link out instead.
- When the checkpoint ships a chat template, snippets and integration tests go through `processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt")` — not manual prompt strings + `processor(text=..., images=...)`. No manual `Image.open`/requests fetching (processors accept URLs/paths directly); no generation kwargs the generation config already sets.
- A broken hub asset (jinja template, processor defaults) is fixed upstream on the hub — never shimmed by mutating the template string in processor code.
- Docstrings do not advertise unimplemented knobs (an `sp_plan` arg documented before the plan kind exists is a finding).
- Docs, default checkpoint, and integration tests target the most-used released variant — check hub download counts, not the author's default.
- New `.py` files carry the Apache license header with the current year; stale copyright years on new files are findings.
- Checkpoint names in docs, config docstrings, and integration tests agree and are public.
- Generation logic beyond the standard flow lives in a `generation_<name>.py`, not in `modeling_<name>.py`.
- Every public exported class is either registered in the matching auto mapping or the omission is a stated decision (niche sub-model, add on adoption); the model dir `__init__.py` surfaces every component file (a missing image-processing export is a finding).
- Output dataclasses use `@auto_docstring` with the per-field docstring block, not hand-maintained class docstrings.

Private helper subconfigs and non-public internals do not require registration.
