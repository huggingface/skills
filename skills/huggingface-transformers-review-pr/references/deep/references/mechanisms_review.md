# Framework Mechanisms Review

Reference for the mechanism-coverage pass: hub kernels, `integrations/`, fusion mapping, monkey patching, the conversion-mapping registry, `PreTrainedModel` class flags, and `EmbeddingAccessMixin`. Anchors name symbols, not line numbers — re-locate with `grep -n "<symbol>"` before citing. Facts below verified July 2026.

The scope rule this file exists for: **a mechanism is in scope when the diff reimplements what the mechanism owns, not only when the diff touches the mechanism's files.** A diff-scoped review cannot see reimplementation-by-absence; this pass checks each trigger below against the whole diff, and each check produces either a finding or a one-line provable disposition.

## Trigger table

| Diff contains | Run section | Contract doc |
|---|---|---|
| new/edited normalization, activation, rotary, or MoE-expert module | Hub kernels; MoE experts | `docs/source/en/kernels.md`, `docs/source/en/kernel_doc/` |
| vendored kernel source (Triton/CUDA/C++), inline `triton` import, custom `autograd.Function` for a fusable op | Hub kernels (module-level) | `docs/source/en/kernels.md` |
| attention class, dispatch, `_attn_implementation` read, mask creation | Attention interface | `docs/source/en/attention_interface.md` |
| load-time module-structure swap, fused runtime layout, `if config.fuse_*` in `__init__` | Fusion mapping; monkey patching | `docs/source/en/fusion_mapping.md`, `docs/source/en/monkey_patching.md` |
| checkpoint key renames, `state_dict` rewriting, conversion scripts, duplicated parent architecture | Conversion-mapping registry | `docs/source/en/weightconverter.md` |
| new or edited `PreTrainedModel` subclass | Flags audit; EmbeddingAccessMixin | — |
| processor `__call__` or token-expansion override | `processing_review.md` | `docs/source/en/multimodal_processing.md` |
| attention forward, weight names, processor call signature, auto-class loading | Downstream consumability (D38) | — |
| `auto_factory.py`, `configuration_utils.py`, `tokenization_auto.py` registration or config-mutation paths | External extension points (D39) | — |

**Docs are part of the contract.** When a trigger fires, read the doc in the third column: it states the intended API. Divergence between doc and code is a finding on whichever is stale (category `docs` when the doc lags the code). A PR that changes a mechanism's public behavior without updating its doc is a finding.

## Hub kernels

Source of truth: `src/transformers/integrations/hub_kernels.py`; user-side config `src/transformers/utils/kernel_config.py` (`KernelConfig`).

The idiom (LlamaRMSNorm / LlamaRotaryEmbedding / `apply_rotary_pos_emb` in `modeling_llama.py`; 123 modeling files carry it):

- `@use_kernel_forward_from_hub("RMSNorm")` on the `nn.Module` class — `kernelize` swaps the forward for the hub kernel when the user opts in (`use_kernels=True`).
- `@use_kernel_func_from_hub("rotary_pos_emb")` on the rotary embedding class plus `@use_kernelized_func(apply_rotary_pos_emb)` on the attention class that calls the function.
- The default layer-name → repo table is `_build_kernel_mapping` in `hub_kernels.py`. Mapped layer names include `RMSNorm`, `FastGELU`, `QuickGELU`, `NewGELU`, `SiLU`, `GeLU`, `GeluTanh`, `MultiScaleDeformableAttention`, `MegaBlocksMoeMLP`, and functions `rotary_pos_emb`, `ForCausalLMLoss`.
- Module-level kernels (mamba-ssm, causal-conv1d, finegrained-fp8, deep-gemm) go through `_HUB_KERNEL_MAPPING` + `lazy_load_kernel(kernel_name)`, not vendored source.
- Attention kernels arrive as `attn_implementation="org/repo@rev:name"` strings (`is_kernel`, `load_and_register_attn_kernel`) and register into `ALL_ATTENTION_FUNCTIONS` / `ALL_MASK_ATTENTION_FUNCTIONS`.

Review hooks:

- A new model defining an RMSNorm/activation/rotary matching a mapped layer name, with no decorator and no decorated parent, loses `use_kernels=True` support silently — finding (`warning` in a new model).
- A modular override that re-defines a class whose parent carries a kernel decorator must keep it; grep the **generated** modeling file for the decorator to confirm it survived conversion. A dropped decorator is a finding.
- Vendored kernel source in a model directory, or an inline `import triton` in modeling code, is a finding: route through the kernels hub (`_HUB_KERNEL_MAPPING` + `lazy_load_kernel` for modules, `LayerRepository` for layers).
- `KernelConfig.kernel_mapping` keys must match the `kernel_layer_name` attributes the decorators install; `kernel_config.py` validates this — a mapping keyed on a class name no decorator declares never fires.
- Do **not** flag undecorated MLPs: no in-tree model applies `@use_kernel_forward_from_hub("SwiGLUMLP")`/`("GeGLUMLP")` (the mapping entries exist for kernels-side classes). Grade decoration against the inherited family parent, not against the mapping table.

## Attention interface and `integrations/`

- Current dispatch is `ALL_ATTENTION_FUNCTIONS.get_interface(self.config._attn_implementation, eager_attention_forward)` inside the attention module. Registration is `ALL_ATTENTION_FUNCTIONS.register(name, fn)` paired with `ALL_MASK_ATTENTION_FUNCTIONS.register` (see `load_and_register_attn_kernel`).
- Legacy `*_ATTENTION_CLASSES = {...}` dispatch dicts survive in ~10 legacy models (sam among them). In **new** code this is a finding even when the modular inherits it from such a parent — the new-code-vs-legacy rule applies; the parent's dict is the thing to not propagate. State the current-standard replacement in the finding.
- The shared backend wrappers live in `src/transformers/integrations/`: `flash_attention.py`, `sdpa_attention.py`, `flex_attention.py`, `eager_paged.py`, `sdpa_paged.py`, `npu_flash_attention.py`. A per-model wrapper that re-prepares the same arguments is a finding; import the shared one.
- Inline backend branching in modeling code (`if self.config._attn_implementation == "flash_attention_2":`) is a finding; the interface owns dispatch. The same applies to backend-conditional tensor munging: an `is_flash_attention_requested(config)` conditional that pads, reshapes, or slices tensors inside a model's attention forward is a finding — the transformation belongs in the interface implementation under `integrations/` (`flash_attention_forward`, `paged_attention_forward`), so the model body stays kernel-agnostic.

## MoE experts

Source of truth: `src/transformers/integrations/moe.py` — `ExpertsInterface(GeneralInterface)`, `@use_experts_implementation` on the `Experts` module class (51 models), backing `grouped_mm_experts_forward` / `batched_mm_experts_forward`; quantizers override per-dtype (`fp8_grouped_mm_experts_forward` in `finegrained_fp8.py`).

Review hook: a new MoE model iterating experts in a Python loop, or hand-rolling a gather/scatter experts forward inside the model file, is a finding — define an `Experts` module compatible with `@use_experts_implementation`. A deviation needs the stated reason the shared contract cannot express it (shared-expert fusion, non-standard routing tensor layout), verified against `moe.py`, not asserted.

Whole-model setter walks (`set_experts_implementation`, attention setters) check per-module capability (`_can_set_*`) before applying — heterogeneous multimodal models (MoE text + dense vision) are the test case. A context manager inside a generation loop is checked for per-iteration entry: optimize-for-decode wrappers belong around the decode loop, not around each token.

## Fusion mapping and monkey patching

Source of truth: `src/transformers/fusion_mapping.py`, `src/transformers/monkey_patching.py`.

- Load-time module-structure replacement goes through `fusion_config={...}` in `from_pretrained` → `register_fusion_patches` → a `ModuleFusionSpec` in `_FUSION_REGISTRY`. The spec contract: `is_fusable(module)` structural predicate, optional `target_modules_patterns` pre-filter, `make_fused_class(original_cls)`, `make_transforms(config)` returning `WeightTransform` rules for both load and reverse-save.
- `register_patch_mapping(mapping)` is the class-swap primitive: keys are exact class names or regex patterns, exact match wins. Fusion is class-level — one module class maps to one fused class.
- `save_pretrained` restores the original checkpoint layout by default; a fused layout without reverse transforms breaks the round-trip.

Review hooks:

- A config flag plus an `if config.fuse_x:` branch in `__init__` that swaps module structure at load is a finding — that is a `ModuleFusionSpec` (or, for kernel-backed fusion, `register_kernel_replacements_and_fusions` in `hub_kernels.py`).
- A new fusion spec whose `make_transforms` source patterns collide with an existing conversion entry must fail fast; `_register_module_fusion` raises on conflict — a spec that appends silently is a finding.
- A fusion without `make_transforms` (or with load-only transforms) is a finding; state the failing round-trip: `from_pretrained(fusion_config=...)` → `save_pretrained` → reload without fusion.
- Ad hoc `model.some_module = Replacement(...)` after instantiation in library code (not user scripts) is a finding; `register_patch_mapping` exists for this.

## Conversion-mapping registry

Source of truth: `src/transformers/conversion_mapping.py`. Extends `modular_review.md` (Conversion mapping), which carries the `test_reverse_loading_mapping` coverage hole and the load-report failure signature.

- **Alias first.** `_MODEL_TO_CONVERSION_PATTERN` maps a model type or class name to an existing pattern (`"deepseek_v3": "qwen2_moe"`, `"SiglipVisionModel": "CLIPVisionModel"`, `"PaliGemmaModel": "LlavaModel"`). Before accepting a new `WeightRenaming`/`WeightConverter` block, check whether an alias line reaches an existing pattern; a duplicated block reachable by one alias line is a finding.
- Class-name keys take precedence over `model_type` strings (`extract_weight_conversions_for_model` resolution order) — task-head-specific mappings ride on this; a bespoke per-class conversion attribute on the model is a finding when the registry expresses it.
- Runtime registration is `register_checkpoint_conversion_mapping(model_type_or_class_name, mapping)`; it raises on existing keys without `overwrite=True`.
- A `convert_*_to_hf.py` script performing pure renames that a registry entry could express means the checkpoint contract lives in the wrong place — finding, cite `weightconverter.md`.
- **Mechanism separation.** `base_model_prefix` is the load-fallback prefix, never a conversion device — prefix handling in the mapping is `PrefixChange(prefix_to_add=..., model_prefix=...)`. `WeightRenaming` and `WeightConverter` are independent: a matching `WeightConverter` owns its renaming; a rule that relies on another rule firing first is a finding. Loading logic that reaches into conversion (or the reverse) becomes unmaintainable — flag the coupling itself.
- **Pattern hygiene.** Prefer plain prefix renames (`r"transformer\.resblocks\."` → `"encoder.layers."`) over capture-group patterns (`(\d+)`) when the layer index passes through unchanged. When a mapping is expected to fail the reverse-loading test (one-to-many renames on a functional model), the test gets an explicit override/skip with the reason — not a silent red.
- **Mutation safety.** Code extending a mapping extracted from the shared registry copies it first; in-place extension mutates the cached global for every later consumer.
- **Fused-weight split, parity-gated.** Original checkpoints with fused qkv/MLP weights (`Wqkv`) preferably split via a `Chunk` converter entry to the standard `q_proj/k_proj/v_proj` (or `gate/up`) modules — but splitting changes numerics, so acceptance is gated on the integration-parity run; if parity degrades, keep the fused layout and say why.

## PreTrainedModel flags audit

Authoritative list (class body of `PreTrainedModel`, `src/transformers/modeling_utils.py`): `config_class`, `generation_config_class`, `base_model_prefix`, `main_input_name`, `input_modalities`, `_is_stateful`, `_no_split_modules`, `_skip_keys_device_placement`, `_tied_weights_keys` (a `dict[str, str]`), `_keys_to_ignore_on_load_missing`, `_keys_to_ignore_on_load_unexpected`, `_keys_to_ignore_on_save`, `_supports_sdpa`, `_supports_flash_attn`, `_supports_flex_attn`, `_compatible_flash_implementations`, `_tp_plan`, `_pp_plan`, `_fsdp_plan`, `supports_gradient_checkpointing`, `_can_compile_fullgraph`, `_supports_attention_backend`, `_can_record_outputs`. Re-derive the list from the class body before citing a flag; names drift.

Every new or edited `PreTrainedModel` subclass gets one audit row per flag the diff sets, plus a check for flags it should set:

- `_supports_sdpa` / `_supports_flash_attn` / `_supports_flex_attn` / `_supports_attention_backend`: `True` requires the attention modules to route through `ALL_ATTENTION_FUNCTIONS.get_interface` and forward `**kwargs`. Copied-`True` over a bespoke attention that ignores the interface is a finding; standard dispatch with the flags left `False` withholds backends from users — also a finding.
- `_can_compile_fullgraph = True` with any data-dependent branch in forward (../review_deep.md, torch.compile section) is a finding; `test_torch_export` is the check.
- `_tied_weights_keys` is a dict mapping target → source; the pre-v5 list form is a finding in new code. Tying is declarative only: any `def tie_weights` override is a finding (it breaks loading and device_map computation). On composite models, `tie_word_embeddings` must live on the config level that owns the tied modules — main-model `_tied_weights_keys` with the flag on a sub-config is the documented false-pass. `tie_word_embeddings=True` in the config of a model class with no LM head is a finding: downstream frameworks tie weights from the config flag alone, without checking whether a head exists.
- A renamed weight or buffer needs `_keys_to_ignore_on_load_unexpected` or a conversion-registry entry (tenet 7); neither present with a rename in the diff is a finding.
- `input_modalities` set for any non-text-only model; `main_input_name` set when the first input is not `input_ids`.
- `_tp_plan` / `_pp_plan`: carried by modular inheritance; a modular override of the class that silently drops the parent's plan is a finding (diff the generated file's attributes against the parent's).
- A flag declaration equal to the parent's value renamed is converter-derived and removable — `modular_review.md` (Converter auto-derivation) carries the proof template.

## Downstream consumability (D38)

Transformers models are a modeling backend for vLLM, executorch, and others; a diff can be correct in-repo and still break or degrade downstream consumption. When the trigger fires:

- Computation a downstream kernel may replace (MLA latent expansion `expand_kv`, projections) lives in named override-able methods, never inlined in forward — vLLM nullifies these methods to feed its own kernels.
- `_supports_attention_backend` reflects reality whenever attention code is touched; a stale flag gates the whole vLLM backend for that model.
- Checkpoint weights map to canonical names (`lm_head`, not `embed_out`) or a `conversion_mapping.py` entry is added.
- Multimodal processors are callable text-only with placeholders present — media kwargs optional, N media per prompt — because vLLM encodes each modality separately (see `processing_review.md`, vLLM decoupling).
- Per-layer heterogeneity (`head_dim`, `num_key_value_heads`, attention type) is discoverable from the config alone (`layer_types` / per-layer config), never implicit in model-construction code — consumers must derive the topology without instantiating the model.
- Changes to core loading/config/tokenizer paths consult the dependents smoke test (`.github/workflows/dependents-smoke-test.yml`).

## External extension points (D39)

The BC surface includes code that plugs INTO transformers: downstream `register()` calls and hub custom-code (`trust_remote_code`) models.

- Registration APIs (`_LazyAutoMapping.register`, `AutoConfig.register`) stay append-only in the input shapes they accept — downstream registrants use `str` keys (model type); an early exit or type check that breaks them is a finding.
- An explicitly registered local class always wins over remote code, regardless of `trust_remote_code`.
- Framework code that rewrites config attributes is defensive for custom models: write only when the value actually changes, tolerate read-only properties.
- Renaming config vocabulary (layer-type names) ships an automatic legacy remap — custom-code models predate the rename and never opt in.
- Hub-override tables (`MODEL_IDS_TO_TOKENIZERS_BACKEND`, `MODELS_WITH_INCORRECT_HUB_TOKENIZER_CLASS`) are family-complete: an entry keyed to one checkpoint id when the defect (wrong `tokenizer_class` in `tokenizer_config.json`) affects the whole family is a finding. Removing a loading fallback requires auditing every table entry that silently depended on it — verify what each model actually loaded pre-change.

## Loss functions

`self.loss_function` owns label shifting. Modeling code that manually shifts labels before the call is a finding — pass `labels=None, shift_labels=labels` instead; never shift twice, and never keep a `do_shift_labels` flag for a nonexistent unshifted-train use case. Double-shift is the recurring training-loss bug (Git/Florence2/Moonshine family).

## EmbeddingAccessMixin

Source of truth: `class EmbeddingAccessMixin`, `src/transformers/modeling_utils.py`.

`get_input_embeddings` resolves `_input_embed_layer` (default `"embed_tokens"`) in order: direct attribute → `self.embeddings.<name>` → `self.model.<name>` → `self.language_model.get_input_embeddings()` → base-model recursion. `set_input_embeddings` mirrors it.

Review hooks:

- A `get_input_embeddings`/`set_input_embeddings` override returning what the resolution order already finds is a finding — set `_input_embed_layer` to the attribute name instead, or delete the override when the default name matches.
- An override is legitimate only when the embedding lives outside every resolution path; the finding's disposition states which path fails.
- A model with a getter override but no matching setter breaks `resize_token_embeddings`; the check is `model.resize_token_embeddings(new_size)` on a tiny config, not prose.
