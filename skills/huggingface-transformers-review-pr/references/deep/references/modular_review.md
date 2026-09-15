# Modular Refactor and Output-Capture Review

Reference for `model_refactor` PRs: modular roots, regenerated families, decorator stacks, backbones, and conversion-mapping changes. Anchors below name symbols, not line numbers — re-locate with `grep -n "<symbol>"` before citing; line numbers drift between branches.

Companion: `new_model_review.md` covers registration, tests, and loading; `processing_review.md` covers processors. This file covers what those do not: the converter's derivation rules and the exact semantics of the output-capture decorators.

## Workspace and environment preflight (run before any check)

Two environment failures produce false review results. Both occurred in the PR #46266 review (June 2026).

1. **Do not mutate the user's checkout.** `gh pr checkout` and `git checkout` switch the user's working tree. Before fetching the branch, run `git branch --show-current` and `git status --short`. If the tree is on another branch or dirty, review from an isolated worktree instead:

   ```bash
   git fetch origin pull/"$PR_NUMBER"/head:review-pr-"$PR_NUMBER"   # or fetch the branch ref
   git worktree add /tmp/review-pr-"$PR_NUMBER" review-pr-"$PR_NUMBER"
   cd /tmp/review-pr-"$PR_NUMBER"
   ```

   Remove the worktree when done is a `[HUMAN ACTION NEEDED]` item, not an action to take (worktree removal rewrites state).

2. **Verify which tree `python` imports.** A dev machine can have several transformers worktrees; the active environment may resolve `import transformers` to a different one. Every converter check, pytest run, and MRE then silently executes against the wrong tree.

   ```bash
   python -c "import transformers; print(transformers.__file__)"
   ```

   If the printed path is not under the reviewed tree, prefix every command with `PYTHONPATH=<reviewed-tree>/src`. **False-drift signature:** `utils/check_modular_conversion.py` reports "Differences found" for most or all dependent models, and the `_generated` side of the diff looks like the *base ref* (old idioms the PR removed). That means the converter resolved the parent model's source from another tree — fix `PYTHONPATH` and re-run before reporting drift. Observed concretely: 7 of 8 modulars reported drift until `PYTHONPATH=src` was set, after which all were clean.

## Generated files: collective disposition

A clean converter check dispositions every symbol in the generated files at once; review effort goes to the `modular_*.py` sources.

```bash
PYTHONPATH=src python utils/check_modular_conversion.py --files \
  src/transformers/models/<a>/modular_<a>.py src/transformers/models/<b>/modular_<b>.py ...
# exit 0, no output → every generated modeling/configuration file matches its modular source
```

- Run it for **every** modular the diff touches, in one invocation (dependents regenerate against the root).
- In the Symbol Coverage Ledger, generated-file symbols get one collective row: "generated from `modular_<x>.py`; `check_modular_conversion` clean". Modular-file symbols still get individual rows.
- If the check fails after the environment preflight passed, the generated files were hand-edited or the modular lags the generated file — that is a `warning`-severity finding (`Never edit generated files`).

## Converter auto-derivation: redundant declarations

`utils/modular_model_converter.py` renames the parent's class attributes when generating. A declaration in the modular that equals the parent's value renamed is dead weight.

Auto-derived (verified June 2026 via ijepa: `modular_ijepa.py` declares none of these on `IJepaPreTrainedModel(ViTPreTrainedModel)`, yet generated `modeling_ijepa.py` carries all of them correctly renamed):

- `base_model_prefix` (`"vit"` → `"ijepa"`)
- `_no_split_modules` (`["ViTEmbeddings", "ViTLayer"]` → `["IJepaEmbeddings", "IJepaLayer"]`)
- `_can_record_outputs` (`{"hidden_states": ViTLayer, "attentions": ViTAttention}` → IJepa classes)
- `_input_embed_layer`, `_supports_*`, `_can_compile_fullgraph` (inherited verbatim)

Review rule: for each class attribute declared in a modular `PreTrainedModel` subclass, compare with the parent's value renamed. Equal → flag for removal (`discussion`, category `modular`). Different → keep, and the difference is the thing to review. Proof template for the finding: cite the parent's declaration, the modular's declaration, and one sibling modular that omits it with a correct generated file.

## Read the root before judging the leaf

When `modular_X.py` inherits from model `Y`, open `modeling_Y.py` first and read the corresponding classes. Convention questions resolve against the root, not against taste:

- `pixel_values: torch.Tensor | None = None` with no explicit raise — ViT root does the same (`ViTModel.forward`); not a finding, an inherited convention.
- `getattr(config, "head_dim", hidden_size // num_heads)`, `attention_dropout` attribute naming — verbatim `ViTAttention`; renames that match the root are standardization, not churn.
- fp32-softmax `eager_attention_forward` — adopting the root's numerics changes integration slices; expect re-baselined tests in the same PR, with the cause stated.
- A deliberate divergence from the root (extra attribute, different decorator stack, kept Encoder class) needs a stated reason in the PR or code; absent reason → `discussion` finding.

For a new model file with near-duplicate modules, run `utils/modular_model_detector.py` on the whole file — the reviewer names the source model per class where known, the tool finds the rest; demand modular adoption per hit.

For every **new** `nn.Module` in a modular, name the nearest existing implementation and state why it is or is not inherited. Reviewers ask exactly this ("can this be `CLIPMLP`?", "inherit `BeitEmbeddings`?"). The disposition is mechanical: count what survives inheritance. `CLIPMLP` forward identical modulo attribute name with an `__init__` override → viable, suggest. `BeitEmbeddings` where `__init__`, `interpolate_pos_encoding`, and `forward` would all be overridden → zero reuse, answer no with that count.

**Inheritance floor (file-level finding).** A `modular_*.py` that is almost entirely bare `nn.Module` definitions inheriting from nothing defeats the purpose of the modular mechanism and is a finding *about the file*, not a property to accept because "the architecture is novel." Novelty raises the bar for the per-module reuse analysis above; it does not remove the requirement to do it. Two failure modes to separate:
- **Genuinely novel block, no parent exists.** The per-module count returns zero reuse against every candidate. Disposition: keep the bare module, record the candidate checked and the override count that killed reuse. Provable, neutral.
- **No parent because the analysis was not done.** The reviewer (or author) wrote "novel, bare `nn.Module`" without naming a candidate. Disposition: file-level finding — require the nearest-implementation + survival-count for each bare module. The absence of a named candidate is the tell that the work was skipped.
A modular where the second case dominates (most modules bare, none with a stated reuse count) is `Request changes` on structure alone. Do not disposition the whole file "neutral, novel architecture"; that is the exact move the `../review_deep.md` "novelty is not a waiver" section forbids.

## Modular authoring idioms (converter-friendliness)

Recurring reviewer suggestions on `modular_*.py` files; each is a `nit`/`discussion` finding with the concrete rewrite:

- **`**super_kwargs` override.** An override that only changes the docstring or return annotation takes `def forward(self, **super_kwargs)` and calls `super().forward(**super_kwargs)` — no copied signature to drift.
- **Ternary over `if/else`** for small config-dependent assignments (`config = config.vision_config if isinstance(config, Tipsv2Config) else config`) — the converter handles expressions better than statement branches.
- **`attr = AttributeError()`** is the mechanism to *un-inherit* a parent config attribute; it is only valid for attributes the parent actually declares (a nonexistent one crashes the converter). Extra checkpoint attributes need no declaration — config kwargs set them eagerly.
- **Identical-body overrides are deleted.** An override whose body matches the parent modulo renames the converter already performs ("Why are we overriding the forward? Looks pretty identical") is dead weight.
- **Inheritance with zero reuse is dropped.** Inheriting a parent class and overriding every member ("why are we inheriting if we don't use anything from that other module?") converts to a bare definition or a closer parent.
- **Re-declared `config_class`/attributes the PreTrainedModel base already carries** are removed (the generated class inherits them).

Converter naming mechanics (multimodal modulars with mixed-family parents):

- A modular class inheriting `<Parent>Model` must itself end in `Model`; a non-`Model` name makes the converter emit redundant pass-through classes.
- Tower suffixes must not collide with module vocabulary: a bare `Text` suffix clashes with vision-module naming — use the full `<Model>TextModel` shape, and check per-tower prefix captures produce real class names, not garbage.
- Two `eager_attention_forward` variants landing in one generated file need one renamed (`vision_eager_attention_forward`, the Llama4 idiom).
- To inherit a class while skipping its parent-init side effects, call `<Own>PreTrainedModel.__init__(self, config)` explicitly — and the named grandparent must match the generated file's actual parent class.

## Output-capture decorator semantics

Source of truth: `src/transformers/utils/output_capturing.py` (`capture_outputs`, `install_all_output_capturing_hooks`, `OutputRecorder`) and `src/transformers/utils/generic.py` (`merge_with_config_defaults`, `can_return_tuple`). Read them before flagging a decorator stack; the mechanics below were verified June 2026.

- **`@capture_outputs` pops `return_dict` and converts to tuple itself** — it supersedes `@can_return_tuple`. Stacking both on one forward is the "double decorator" finding. A forward with `@capture_outputs` needs no `@can_return_tuple`; a forward without it does.
- **Exactly one `@capture_outputs` per call chain.** The collector is a ContextVar (`_active_collector`); an inner decorated forward (Encoder) shadows an outer one (Model), and the outer's `hidden_states` comes back empty. The decorator lives on one level — for encoder-retaining vision families that is the Encoder; the Model stays bare and threads `encoder_outputs.hidden_states` manually.
- **`output_*` defaults are resolved inside `capture_outputs`** (`kwargs.get(f"output_{k}", getattr(self.config, ...))`). `@merge_with_config_defaults` does **not** merge them — it only handles `use_cache` and `vision_feature_*` args (see `args_with_config_defaults` in `generic.py`). Do not claim a missing `merge_with_config_defaults` breaks `output_hidden_states` config defaults.
- **Recorder name matching is boundary-anchored:** `layer_name` matches only on `.name.`/`.name` module-path boundaries, so `attention` never matches `crossattention`; unanchored substring matching on module paths is a finding, and implicit conventions (a 2-element attentions list meaning attn + cross-attn) give way to explicit keys.
- **Hook index defaults** (`install_all_output_capturing_hooks`): `hidden_states` → tuple index 0, `attentions` → index 1. `{"attentions": XxxAttention}` on an attention returning `(attn_output, attn_weights)` records the weights; correct without an `OutputRecorder`. An attention returning a different tuple shape needs an explicit `OutputRecorder(index=...)`.
- **`capture_initial_hidden_state=True`** (default) prepends the first hooked module's input — hidden_states tuples have N+1 entries (embedding output + N layer outputs) without manual collection.
- **`tie_last_hidden_states=False`** keeps `hidden_states[-1]` as the raw final-layer output (pre final norm). Required when the Model applies a `layernorm`/`norm` after the encoder (CLIP/SigLIP/dino families). With `True`, the last entry is overwritten by `outputs.last_hidden_state`.
- **`filter_output_hidden_states`** (`src/transformers/backbone_utils.py`) reads `kwargs.get("output_hidden_states", config.output_hidden_states)` *before* the body runs, then strips `hidden_states` from the returned output when the user did not request them. It needs a dict-like return (pair with `@can_return_tuple` or `@capture_outputs` above it).

### Backbone layouts (two valid patterns)

1. **Encoder-capture + filter (default).** Backbone forward: `@can_return_tuple @filter_output_hidden_states @auto_docstring`; body sets `kwargs["output_hidden_states"] = True`, calls `self.encoder(...)`, builds `feature_maps` from `output.hidden_states`, returns `BackboneOutput(feature_maps, hidden_states, attentions)`; the filter strips unrequested hidden_states. dinov2/dinov2_with_registers/dinov3_vit idiom.
2. **Backbone-capture + inline loop.** When the Backbone cannot call `Encoder.forward` (window partitioning, per-layer surgery): `@merge_with_config_defaults @capture_outputs(tie_last_hidden_states=False)` on the Backbone forward, body iterates `self.encoder.layer` and builds feature maps manually, returns `BackboneOutput(feature_maps=...)` only; capture injects `hidden_states`/`attentions` post-hoc when requested. rf_detr idiom. No nesting occurs because `Encoder.forward` is never invoked on this path.

**Dead-filter detection:** in pattern 2, `@filter_output_hidden_states` below `@capture_outputs` is a no-op — the body never sets `hidden_states` and capture injects only when requested, after the filter ran. Flag for removal (`nit`).

**Attention-mask conversion gap:** the Model forward converts a user 2-D `attention_mask` via `create_bidirectional_mask` before the encoder; a Backbone that forwards `**kwargs` straight to the encoder/layers skips the conversion — an integer mask then crashes in sdpa, a float 0/1 mask is silently read as an additive bias. Check every public forward that newly accepts or forwards `attention_mask`: either it converts, or it does not accept the kwarg. MRE shape: tiny config, `Model(px, attention_mask=torch.ones(1, S, dtype=torch.long))` passes, `Backbone(px, attention_mask=...)` raises.

### Redundant-surface checklist (per Model/Backbone class in the modular)

- `get_input_embeddings` override returning `self.embeddings.<x>` where the inherited `_input_embed_layer = "<x>"` already resolves it (`PreTrainedModel.get_input_embeddings`, `src/transformers/modeling_utils.py`, resolution order: direct attr → `self.embeddings.<name>` → `self.model.<name>`). The root (`ViTModel`) defines no override; neither should the leaf.
- Attributes assigned but never read and absent on the base ref (`self.pooler = None` on a model that computes `pooler_output` by slicing). `git show <base>:<file> | grep` proves it is new; grep the tree for readers before flagging.
- `__init__` lines duplicating the parent verbatim (`self.num_labels = config.num_labels`) — removable only if the modular `__init__` does not fully replace the parent's; a full override that drops the line also drops the public attribute from the generated class — state the BC consequence instead of asserting "redundant".
- Re-assignments the base class already performs (`self.config = config` after `PreTrainedModel.__init__`), and method overrides where a class attribute suffices (`supports_gradient_checkpointing = True`) — findings, cite the base-class line.
- Classes in the generated `modeling_*.py` that are neither in `__all__` nor referenced by another class — dead weight from over-broad modular inheritance; flag for removal from the modular.

## Conversion mapping: validation has a coverage hole

- `test_reverse_loading_mapping` (`tests/test_modeling_common.py`) **skips** when any class in `all_model_classes` lacks a conversion entry ("No conversion found for `<X>Backbone`"). A green fast suite therefore does not validate a new mapping entry. Run the test explicitly, report pass/skip/fail per model, and when it skips, the only validation is the slow integration test on a real checkpoint — put `RUN_SLOW=1 pytest tests/models/<name>/ -k Integration -x` in SUGGESTED CHECKS and say why.
- A wrong or missing entry produces a deterministic signature in the load report: legacy keys (`attention.attention.query`) UNEXPECTED + new keys (`attention.q_proj`) MISSING → the submodule is randomly initialized → integration slices mismatch at ~100% of elements with O(1) absolute error. Distinguish from numeric drift (re-baseline territory: <1e-3, few elements). Never recommend re-baselining a slice over a load-report failure.
- Unanchored rename patterns (`"attention.attention.query"`) apply to every matching key under the entry's scope. Grep the model's modeling file for other submodules whose checkpoint path could contain the pattern before accepting; cite the non-colliding naming (`self_attn`, `encoder_attn`) in the disposition.

## Reviewer-thread dispositions specific to refactor PRs

- **Author replied "pushed a fix" → verify on the head.** The reply is a claim, not evidence; commits land on the wrong branch ("woops, wrong PR" is a real commit message). Grep the head for the described change; absent → the row stays `outstanding` with "author reply claims a push not present on the head".
- **Reviewer self-withdrawal closes the row.** A reviewer replying to their own comment with a retraction ("I was wrong, the backbone forces keeping this") dispositions the row `addressed`; quote the withdrawal as the evidence.
- **Design-state churn invalidates replies, not remarks.** On a PR that reverts its own design ("re-re-revert"), an author reply describing an intermediate state ("decorators remain on the Model") may contradict the final head (decorators on the Encoder). Disposition rows against the head, never against the reply's description of the code.
