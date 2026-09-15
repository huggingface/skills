# Modeling Conventions Review

Reference for code-level conventions in modeling files. Owns dimensions D3, D6, D7, D8, D9, D13, D14, D15, D16, D17, D18, D24, D25, D26, D27, D29, D33, D34, D36, D40, D41 of `REVIEW_DIMENSIONS.md`. Every rule below was mined from recurring maintainer review comments (July 2026); the PR numbers in the matrix file are the provenance. Anchors name symbols; re-locate with `grep -n` before citing.

## D3 — Canonical attention shape pattern

The llama-standard forward shape: `input_shape = hidden_states.shape[:-1]`, `hidden_shape = (*input_shape, -1, self.head_dim)`, projections reshaped via `.view(hidden_shape).transpose(1, 2)`, then the interface call `ALL_ATTENTION_FUNCTIONS.get_interface(...)`. An attention forward computing QKV or reshapes differently, without an architectural reason (MLA, linear attention), is a finding — cite `modeling_llama.py` / `modeling_gemma2.py` as the pattern.

One rotary module per model: a rotary embedding instantiated (or freqs recomputed) per attention layer is a finding — the Model owns a single `rotary_emb`, builds/caches `inv_freq` once in buffers, and passes `cos/sin` down as `position_embeddings` (qwen2_vl for the mm-rope form).

## D6 — Dead branches vs released checkpoints

Every config flag, `if/else`, and optional parameter in a new model must be exercised by a released checkpoint. Check: list the converted checkpoints' config values for each flag the diff introduces; a flag with one value across all of them, or an unreachable `else`, is a finding — delete the attribute and the branch. New models get no back-compat shims. For existing models under edit this check is scoped to flags the diff adds.

Processor-output trust is the multimodal form of this rule: modeling code that None-checks or ndim-branches on an input its own processor always emits (`if pixel_values is None`, `if pixel_values.dim() == 4`) is a dead branch — verify the processor's output shape/keys, then delete the guard.

Test fakes are the third form: a modeling branch whose only exerciser is a test fixture (mock cache class, synthetic input format) is a dead branch — delete it and make the test construct the real object or real-life-formatted input.

The delete side has the same burden: removing a conversion/quantization op or branch (a scale-format handler) requires an explicit statement that no released checkpoint in that format depends on it. For distributed helpers the reachability domain is parallelism-mode combinations, not checkpoints — enumerate the layout matrix that reaches the code before deleting.

## D7 — Config discipline

- Config attributes use the standard names of the family (`num_experts`, not `n_routed_experts`); a nonstandard name on a variant gets an `attribute_map` entry so shared infra (quantization, TP) keyed on the standard name still works. A new attr duplicating a canonical one is a finding ("do we really need both?").
- RoPE settings use the `rope_parameters` format (scaling + theta, nestable), not loose top-level attrs.
- Derived hyperparameters are computed in the config (`__post_init__`/properties), not re-derived in module `__init__` math; the config is not mutated after construction.
- Attributes live in the right substructure (vision knobs in `vision_config`, generation knobs in the generation config). The generation config is model-centered; hardware/runtime tuning knobs (block counts, memory percents, batch tokens) belong in their runtime config (`DistributedConfig`, CB config), never in `GenerationConfig`.
- Constraints on config/generation-config values are enforced once, at the config boundary (`validate()` / config `__init__`), not re-checked ad hoc in hot paths; the runtime check reduces to `is not None`.
- **v5 config form:** configs are dataclasses decorated with `@auto_docstring`; arg documentation lives in the class body, not module-level `*_CONFIG_ARGS` docstring variables; no manual `rope_config_validation` call (auto-invoked).
- **Composite-config hygiene:** no proxy properties on a composite config mirroring sub-config attrs (`hasattr` heuristics in the codebase misfire on them — read `config.text_config.x` directly); config `__init__` never force-sets `attn_implementation` (it comes from the config file or user kwargs); sub-config keys use the canonical names (`text_config`/`vision_config` — shared infra assumes them); a sub-model is typed to exactly its own sub-config, never a union with the composite.
- **Sub-config only for a real sub-model:** a nested config that parametrizes a single `nn.Module` (a lone MLP projector) is flattened into the parent config. A per-checkpoint hardcoded variant in code is resolved by fixing the hub config, not by keeping the workaround.
- **`get_text_config()` placement:** generation-relevant attributes (vocab size, special-token ids, rope/text hyperparams) live on the sub-config that `config.get_text_config()` resolves; declaring them only top-level breaks every generic utility keyed on that accessor.
- **Saved-config JSON audit:** when a composite config `__init__` consumes `**kwargs` or a config gains private/derived properties, check what `save_pretrained`/`to_dict()` actually emits — sub-config fields not popped duplicate onto the top-level JSON, and private properties must not serialize. Verify with a save round-trip, not by reading `__init__`.

## D8 — Layer-type taxonomy

Per-layer behavioral variation goes through `config.layer_types` with distinct, explicit type names. Findings: branching on layer index (`if layer_idx % 2:`), ad-hoc boolean flags per layer, and conflating two mechanisms under one type name (a conv1d layer is not a linear-attention layer). The reference pattern is modernbert/gemma2 sliding-vs-full layer types.

Topology is a config contract: per-layer heterogeneity in `head_dim`, `num_key_value_heads`, or attention type that exists only in model-construction code (implicit indexing, hardcoded patterns) is a finding — downstream consumers (vLLM) must derive the full layer topology from the config without instantiating the model.

## D9 — Signature stability and the kwargs contract

- Existing public signatures are append-only: no reordering, no removal, no new named parameter in the middle. New inputs route through `**kwargs`.
- `position_ids` is never declared in decoder-layer or attention signatures — it flows via kwargs so flash-attention padding-free training can consume it downstream. A layer/attention `def forward(..., position_ids=...)` in the diff is a finding.
- New optional model inputs go into `TransformersKwargs`-typed `**kwargs`, not the positional list.
- `cache_position` is dead framework surface: any `cache_position` parameter, `torch.arange(past_seen_tokens, ...)` creation, or threading of it through layers or `past_key_values.update(...)` in new modeling code is a finding — removed in all models; the update call is `past_key_values.update(key_states, value_states, self.layer_idx)` bare.

## D13 — Naming pass

Run file-wide on new code, not per-symbol:

- Full words; no single-letter or abbreviated identifiers (`tgt`, `N_ctxt`, `c`). The finding names the concrete replacement.
- Every class in `models/<name>/` carries the CamelCase model prefix (`PPDocLayoutV3ConvLayer`, not `ConvLayer`) — required for later modular reuse.
- Names state what the object is, not what it does approximately (`EncoderCache` holding embeddings is a finding; the name follows the content).
- Class-name taxonomy: `<Model>Model` is the bare backbone with no task head; anything bundling heads is `<Model>For<Task>` (a multi-head variant needs its own `For*` name, not an overloaded `Model`). `base_model_prefix` matches the actual base model class.

## D14 — Good defaults, fail loudly, no warnings

- A new public parameter needs a reason a good default cannot cover; the least number of arguments wins.
- A `logger.warning` where a sensible default or a hard error applies is a finding: warn-and-continue is the worst of both.
- A user-requested capability that silently degrades (kernel not downloadable → empty, unsupported dropout → ignored) raises at init, with a dependency version gate where relevant.
- Error messages name the actual values and the allowed set (`must be in {ALLOWED_LAYER_TYPES} but got {layers}`); a bare "invalid value" raise is a finding.
- No bare `assert` in `src/` (modeling or processing): a dev-leftover assert is deleted, or replaced with a raise carrying an actionable message when a real user path hits the condition.
- Trust internal callers: validation or fallback added on an argument that only internal code produces is removed — the internal contract is guaranteed; validation belongs at the user boundary.
- Accepted-but-ignored arguments raise: mutually exclusive parameters both set, or kwargs dead on some path after an early conversion, get an explicit error — silent precedence is a finding.
- Failure states are distinct and reachable: every status/error-enum variant must be reachable and distinct causes map to distinct states; a probe returning `None`/undetectable errors out rather than proceeding; a workaround for a hypothesized failure is not accepted without the reproducing log, and an upstream root cause gets attributed.
- No library-level rank-conditional output suppression: `if rank == 0:` (or env-var toggles) guarding print/logging setup defaults to output on all ranks — filtering belongs to the launcher (`torchrun --local-ranks-filter`).
- A new public method or kwarg on a shared class (Cache, `PreTrainedModel`, masking API) with no caller in the diff and no linked repro is a finding: request the concrete motivating case before accepting the surface.
- Warning triage is two-sided: a warning narrating what the library always does (pad=eos fallback) is deleted as noise, but a warning guarding silent numerical corruption (batched generation without an attention mask) is kept and scoped exactly to the hazardous case — removing a corruption-guarding warning is itself a finding.

## D15 — Algorithmic directness, no premature generalization

- A helper called once wrapping a stdlib expression is inlined.
- Two passes over the same mapping/config merge into one.
- A shared helper or base class with exactly one consumer stays local until a second model needs it.
- The inverse also holds: when a new processor/feature-extractor computation already exists in ≥2 sibling models (audio length/token-count math, mel windows — grep before dispositioning), flag the shared-util candidate in-PR or as a follow-up instead of silently accepting the third copy; three consumers is past the premature-generalization bar.
- Check in-flight refactors before accepting a new shared abstraction: `gh pr list --search "<area keywords>"` — a collision with an open core refactor is a coordination finding, not a code finding.
- Presence checks use `hasattr`/`getattr`, not `try/except AttributeError` — exceptions are for exceptional paths, not control flow.
- Imports live at the top of the file; a function-local import of a non-optional module is a finding — only optional-dep gating justifies deferred import.
- A local helper duplicating an existing util (even one in an odd location, e.g. `torch_compilable_check` in import utils) is a migration finding, not a rewrite finding — point at the existing symbol.
- Library code drilling three or more attribute levels into a wrapped third-party object (`tokenizer.tokenizer.instruct_tokenizer.audio_encoder`) gets a `nit` proposing a property on the wrapper.

## D16 — Loading/saving-path discipline

- No `from_pretrained` override; the general path (`_from_pretrained`, missing-key init, dispatch) handles custom needs. An override is a finding that names which step of the general flow allegedly cannot express the need — verify the claim.
- Model instantiation before weight load happens on the meta device; real-tensor `__init__` followed by a load is a finding.
- The checkpoint is scanned once; a second read of the weight files (pre-scan for shapes, separate index walk) is a finding.
- Backbone construction goes through `load_backbone(config)`, not manual sub-model `from_pretrained`.
- No `device:` parameter on module constructors, and no `.to(self.device)` device-properties consumed in forward — meaningless under meta-device init, and it blocks verbatim modular copy from a parent that lacks it.
- Composite/omni models declare all no-split modules once in the top-level `PreTrainedModel`'s `_no_split_modules`; sub-model overrides with partial lists are removed — backbone loading filters from the unified list.
- A distributed/rank-conditional branch added to a core generic method (`save_pretrained`, the `from_pretrained` flow) reduces to a single call into a named function in the distributed module, receiving what it needs as parameters; a multi-line `if distributed_checkpoint:` body or an inline rank gate in `modeling_utils.py` is a finding ("anything happening in this if → in a separated function").
- Parallelism knobs are never `from_pretrained` kwargs: they ride `distributed_config=DistributedConfig(...)` (the `tp_plan`/`tp_size` kwargs were removed); a diff adding one is a finding.
- Plain `save_pretrained(dir)` always writes a fully-gathered standard safetensors checkpoint that loads anywhere — single GPU, different parallelism, vLLM; a distributed-save change that makes the default export mesh-dependent is a finding.
- Subsystem-specific names (DeepGEMM, a kernel backend) do not appear in global utils files (`utils/import_utils.py`); the logic lives in the integration's own module.

## D17 — State and hoisting

- No module attribute is written during `forward` (hidden statefulness breaks batching, compile, and reasoning about the module). Carried state is passed explicitly (cache objects, generate loop).
- A value computed in `forward` that depends only on config or static shapes is hoisted to `__init__` (also makes modular overrides cleaner).
- Image/video processors are stateless: `self.<attr> =` inside `preprocess`/`_preprocess` is a finding (preprocess-then-postprocess batching breaks).
- Class-level plan dicts (`_tp_plan`, `_ep_plan`, `_fsdp_plan`) are shared by all instances; code that mutates them copies at `post_init` first.
- No invariant allocation inside a per-module distribution loop: a dict/list literal built inside a function called from the `named_modules()` walk of `distribute_model` is a finding — hoist it.

## D18 — `_init_weights` placement and completeness

- Initialization arithmetic (`+1` offsets, trunc-normal, constant fills) lives in `_init_weights`, never in `__init__` or forward. The reason is mechanical: models instantiate on the meta device, so values written in `__init__` are discarded — allocate parameters/buffers with `torch.empty` there and initialize in `_init_weights`.
- Non-persistent buffers are re-initialized explicitly on load (they are not in the checkpoint); a computed buffer whose value only exists via `__init__` arithmetic has random content after meta-device reload.
- Every new head/module with weights appears in `_init_weights` (fine-tuning from scratch must work); compare against the family's scheme (rt_detr is the detection reference).
- Use checkpoint-aware `init.*` helpers, not raw `nn.init.*`; the modular base-init idiom is `PreTrainedModel._init_weights(self, module)`.
- Config-derived hyperparameters read at init (`temperature`, scales) come from named config fields (`config.temperature_init_value`), not literals.

## D24 — Module container discipline

- Layer collections are `nn.ModuleList`; `setattr(self, f"layer_{i}", ...)` in `__init__` or `getattr` in `forward` is a finding.
- A conditionally-applied layer resolves to `nn.Identity()` at init; an `if self.use_x:` around a module call in forward is a finding.
- Modules are declared in usage order.
- No anonymous `nn.Sequential` chains in modeling code — decompose into named submodules or reuse a ConvNorm-style layer with optional pool/activation.
- Structural variants are two module classes selected at init, never `hasattr(self, ...)` branching in forward.

## D25 — Explicit path plans over introspection

A feature that needs to target submodules uses an explicit glob-path dict (`{"layers.*.self_attn.q_proj": ...}`, the `_tp_plan` idiom), not a walk of `named_modules()` with class matching. When matching many patterns, join them into one regex with numbered group capture instead of looping patterns per key. Weight tying is consulted through `tied_weight_keys`, never re-derived or applied twice.

Plan completeness for new decoder LMs includes FSDP: `base_model_fsdp_plan` in the Config class and `_fsdp_plan` (e.g. `{"lm_head": "keep_full_weight"}`) under the head class — placement is checked exactly. Plan demands stay proportional to real shardability: a full tp_plan is not demanded when the architecture caps the TP degree.

## D26 — Return-type honesty

- The return annotation matches what the code returns on every path; `outputs[-1]` re-derivations that break the annotation are findings.
- Internal sub-model calls are annotated with the output class (`outputs: BaseModelOutput = self.encoder(...)`) and indexed by field, never by position.
- Multi-tensor tuple returns from module forwards are findings (tracing hazards); use the output dataclass, tuple conversion happens once at the top level via the decorator.
- `ModelOutput` is reserved for `PreTrainedModel`-level forwards; an internal bare `nn.Module` returning one is a finding — internal modules return tensors or small tuples consumed positionally by the owning `PreTrainedModel`.

## D33 — Hybrid cache/mask layer-type coverage

New cache, mask, or generation logic is verified against every layer type the config system supports, not only full attention. The recurring failure: logic indexed by absolute position that is wrong past a sliding window.

- Any position arithmetic in cache/mask code accounts for `kv_offset` (`kv_length + kv_offset` for padding lengths); absolute indexing without the offset is a finding.
- Check the diff's behavior for sliding-window, chunked, and linear/recurrent layers explicitly; "works for full attention" is the untested default.
- Layer-type names must stay in sync across cache layer classes, mask functions, and `config.layer_types`; a new type registered in one place but not the others is a finding.
- Cache API discipline over introspection: generic cache code that isinstance-matches concrete layer classes, shape-peeks for past length, or mutates arbitrary `Cache` subclasses is a finding — branch on a capability property (`self.is_linear`), probe length via `get_seq_length(layer_idx)`, and scope generic mutation (snapshot/copy) to the exact known classes, skipping unknown subclasses.
- Presence is not enablement: dispatch reading a config attribute via `getattr` must guard on the value, not the attribute existing — an attribute present with a disabled value (0/None) must not create a degenerate cache.

## D34 — Mask-input plumbing via masking_utils

A new mask-affecting kwarg on a model forward follows the `masking_utils` pattern end to end:

- Padded once at entry, alongside `padding_mask` — not checked repeatedly downstream.
- Composed with the existing mask via the primitives (`or_masks`, `and_masks`), not by scattering conditionals into mask construction.
- Sets `allow_is_causal_skip=False` when the composed mask invalidates the causal fast path.
- Forwarded by `prepare_inputs_for_generation` — a kwarg the generation loop never forwards is dead on the generate path; check it or the feature silently no-ops under `generate()`.
- Composition has a cost: `or_mask_function`/`and_mask_function` on a hot path triggers torch.vmap overhead. When the composed pattern is exclusive to one model family, amend the internal mask creator (`create_sliding_window_mask`) instead of composing per-model — after verifying sibling-family correctness.

## D36 — VLM composition and multimodal feature API

Composite VLMs follow a shared model-side contract that third-party libraries (vLLM among them) consume directly:

- Class layout is exactly `<Model>Model` (towers + projector + merge, raw logits path) and `<Model>ForConditionalGeneration` (lm head, generation) — the llava layout. A `ForCausalLM` class or a monolithic single class on a VLM is a finding; `ForConditionalGeneration` handles text-only inputs.
- Tower attributes use the canonical names `vision_tower` and `language_model` (shared infra locates towers by name heuristics — rename via conversion mapping, not code); the vision tower is a `<Model>VisionModel(PreTrainedModel)`, the adapter/connector its own class. Each tower is initialized from exactly one sub-config.
- Multimodal features exposed via `get_image_features` / `get_video_features`. Since #46405 the output shape is a fixed contract, enforced by `test_get_image_features_output` / `test_get_video_features_output` in `tests/test_modeling_common.py`: a `ModelOutput` carrying `last_hidden_state`, `pooler_output`, `hidden_states`, and `attentions`, where `len(features) == number of images` (or videos, not video frames), each entry is 2-D, and its shape is `(actual seq length of that item, LM hidden size)`. A tuple is returned only when `return_dict=False`. Returning one flat concatenated tensor across the batch, or one entry per video frame, is a finding. The only opt-out is `skip_test_image_features_output_shape` on the tester, and it needs a stated architectural reason.
- Feature insertion via `get_placeholder_mask` + `masked_scatter` inline in `forward` — not a bespoke splice helper.
- Per-sample pixel splitting/unpadding lives in the image/video processor (nested `list[list[image]]` inputs, `pixel_attention_mask`); modeling code re-deriving pixel layout by scanning `input_ids` or example ids is a finding.

Mechanical rule: a new `<Model>Model`/`ForConditionalGeneration` lacking `get_image_features`/`get_placeholder_mask`, containing a feature-splitting/unpadding method over processor outputs, initializing a tower from two configs, or naming towers anything but `vision_tower`/`language_model` → finding naming the recommended helper and the processor as the owner of pixel layout.

**Multimodal RoPE / position-id pipeline** (models with mrope/xdrope or 3-D T/H/W positions — follow the qwen2_vl / PaddleOCR-VL idiom):

- Position-id construction lives in the modeling file, never the processor (settled by maintainer discussion — centralization in the model file).
- Exactly one rope path: in decode, all axes of multi-dim position ids become identical and strictly increasing, reducing to 1-D rope — a parallel `else`-branch 1-D implementation is dead code.
- Generation-side handling goes through the dedicated hooks: `prepare_inputs_for_generation` calls `super()` and only drops pixel inputs after prefill; position deltas via `prepare_position_ids_for_generation`. Nonstandard keys smuggled through `model_kwargs` (`imgs`/`imgs_pos`) are findings.
- Name the nearest mrope sibling and copy its `Model`/helper layout rather than reimplementing.

## D40 — Continuous-batching runtime contracts

Trigger: diff touches `src/transformers/generation/continuous_batching/`, paged attention interfaces, or `serve`.

- No dense attention-mask construction over ragged batch dimensions — CB assumes paged flash (a dense mask is `total_query_tokens × total_kv_tokens`); an implementation switch is automatic-with-warning, never silent.
- Cache slot/index accounting: padding tokens never read from a slot they also write to; read-trash and write-trash indices stay disjoint, or NaNs contaminate the softmax block of real tokens.
- Request lifecycle: objects handed to consumers are snapshots — no live aliases of growing per-request buffers, no mutation of `RequestState` from output conversion.
- Entry-point capability gating: unsupported model families are rejected or fall back to `generate()` before the CB worker launches; no test asserts an unsupported combo works.
- Cross-thread shared state (output queues, handlers) is owned by one dedicated object with its own lock; worker death surfaces via an explicit `fatal_error`, never silence.
- Per-request sampling params only take effect if the corresponding logits processor exists (global `GenerationConfig` value non-default); docs stating CB behavior state the memory-accounting consequences (CUDA graphs roughly double input-tensor VRAM).

## D41 — Distributed plan/runtime contract

Trigger: diff touches `src/transformers/distributed/`, `integrations/tensor_parallel.py`, plan dicts, or DTensor/mesh code.

- Style registry over inline branching: parallel behavior is a declarative `{module_pattern: style_name}` dict resolved through `ALL_PARALLEL_STYLES` / `ParallelInterface.register`; new sharding behavior is a new `ParallelStyle` subclass, never rank- or mesh-conditional code in modeling/loading files. `if device_mesh`/`if rank` logic outside the distributed modules is a finding.
- Plan-matrix completeness: every supported mode combination resolves to a named plan (`_tp_plan`, `_sp_plan`, `_tp_ep_plan`, `_sp_ep_plan`), at param level for packed expert weights (`gate_up_proj` grouped_gemm). A MoE edit touching one plan dict without the sibling plans, or a new plan kind without `verify_tp_plan`/`verify_fsdp_plan` coverage, is a finding.
- Shard-on-read loading: each rank reads only its DTensor slice from the checkpoint — no full-tensor materialization on rank 0, no post-load redistribute.
- Loss/gradient reduction semantics: changes to loss computation or grad accumulation state their behavior under TP and EP-as-TP (over-counting is the documented bug); `clip_grad_norm` and optimizer save/load are DTensor-aware across the full mesh.
- The e2e contract is the topology round-trip: save under one mesh (`FSDP=2×TP=2`), reload under another (`TP=4`), greedy generation verbatim / training continues (see `tests_bc_review.md`, D12).

## D29 — Design-level Occam, with numbers

For any new subsystem (a cache class, an allocator, a scheduler, a registry), ask the existence question before the line-level review: what is the simplest design that satisfies the stated constraints, and does the constraint justifying the complexity have a measurement? A block allocator for buffers that are written once, read once, and freed is a per-request store wearing a page table. The review asks for the number ("how often does fragmentation occur? can we measure it?") — a complexity-justifying claim without a measurement is a `discussion` finding, and the simpler design is named concretely. Resource math is checked where allocation sizes appear: bytes = elements × itemsize of the *actual* dtype (activation dtype is not always model dtype), and the worst case is stated.

Perf-affecting runtime/CB changes ship the measured table: accuracy + tok/s over standard workloads (gsm8k, ifeval, rollouts at several lengths). "No perf change" is also demonstrated by the table, and removals are justified with allocator behavior, not intuition.

## D27 — Code-comment hygiene

- An unexplained magic constant or an intentional oddity (a cast, an off-by-one, a non-obvious clamp) needs one flat line stating the invariant — otherwise the next contributor "fixes" it as a typo.
- A comment that would be true of every model file (boilerplate narration) is deleted.
- Both directions are findings: missing comment on magic, present comment on noise.
- Over-detailed mechanism-walkthrough comments and docstrings (typical agent output — "it sounds a bit AI-written") are condensed to a short human-readable version; a multi-paragraph comment explaining what a readable error message or name already says is a finding.
- A modular override nearly identical to its parent (<~10 changed lines) carries a one-line comment at each divergence point (`# Uses additional projection compared to dfine`) and retains the parent's original section comments; an uncommented near-copy override is a finding on both counts.
