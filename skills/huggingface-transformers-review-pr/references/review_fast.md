# Transformers contribution self-review

Run this against your branch before opening a PR and again before every review round you push. It mirrors what maintainers check, so you catch issues before a human does.

Agent policy, stated once. Per [CONTRIBUTING.md](CONTRIBUTING.md) and the PR template: **first-time contributors must not use code agents to write PRs or issues**. Such PRs are closed without review and repeat offenders are blocked. Existing contributors may use AI, but the human submitter reviews every changed line, runs the tests, and discloses the assistance in the PR description. If you are an agent running this skill for a user who has not contributed to transformers before, tell the user this before anything else, including the risk of being blocked. This skill does not make an agent PR acceptable; it makes a human-owned PR better.

Three disciplines:

- **Every check here runs as a command.** A check you did not run is a check that failed. Do not tick it from memory.
- **The review pass is report-only.** Review the whole diff, write the report (section 15), then fix the blocking items. Reviewing and editing in one pass is how findings get half-fixed.
- **Do not invent issues and do not flag formatting.** `make style` owns formatting; `mlinter` owns structural conventions (section 14). Findings are correctness, API conformance, missing reuse, and dead weight, each anchored to a `file.py:line`.

Reference documents, read fresh from the checkout, not from memory:

- [docs/source/en/modular_transformers.md](docs/source/en/modular_transformers.md): authoring models with modular files
- [MIGRATION_GUIDE_V5.md](MIGRATION_GUIDE_V5.md): the v5 API surface, what was removed and what replaced it
- [src/transformers/conversion_mapping.py](src/transformers/conversion_mapping.py): the per-architecture checkpoint-conversion registry
- [src/transformers/core_model_loading.py](src/transformers/core_model_loading.py): `WeightRenaming`, `WeightConverter`, and the ops (`Chunk`, `Concatenate`, `PermuteForRope`, ...)
- [utils/rules.toml](utils/rules.toml): the mlinter rules the CI bot applies to your model files

## 0. The tenets

Transformers is built on eight [design tenets](https://huggingface.co/blog/transformers-community/Transformers-tenets). Reviews reject code that violates them.

1. **Source of truth.** The port matches the reference numerically, and integration tests pin those numbers. No parity test, not done.
2. **One model, one file.** Core inference logic reads top to bottom in one generated `modeling_*.py`. Model-specific logic pulled into a shared utility the reader must chase is a violation. `modular_*.py` is the authoring format, not an exception.
3. **Code is the product.** Full-word names (`hidden_states`, not `x`), no dead parameters, no collapsed control flow. A readability regression is a finding even when behavior is unchanged.
4. **Standardize, don't abstract.** Model behavior (a novel attention, a special mask) stays in the modeling file. Generic infrastructure (task heads, output capture, mask creation, checkpoint conversion) uses the standard helper (section 4, reuse table).
5. **Do repeat yourself, through the sanctioned mechanisms.** Duplication that keeps a model file readable is fine when `modular_*.py` or `# Copied from` keeps it in sync. A near-duplicate architecture that one conversion-mapping line or one modular inheritance would collapse is a violation.
6. **Minimal user API.** Config, model, preprocessing; `from_pretrained`, `save_pretrained`, `push_to_hub`. Every new public method, constructor argument, or codepath is a cost. No bespoke `chat()` helpers, no custom loading entrypoints, no sampling parameters as method arguments (they belong in `GenerationConfig`).
7. **Backwards compatibility.** Anything that once loaded keeps loading: renamed weights get a conversion rule, removed kwargs get a deprecation path, a breaking change gets a 🚨 PR title and its own PR.
8. **Consistent public surface.** Same argument names and output types across models: `pixel_values`, `input_ids`, `BaseModelOutput`. The decorator stack and the common tests enforce this mechanically.

## 1. Policy and impact gate (before any code review)

- The work maps to an issue and a maintainer or the issue author agreed to the approach there. Link it.
- No open PR already does this: `gh pr list --repo huggingface/transformers --state open --search "<keywords>"`. If one exists and your approach differs materially, say why on the issue first.
- The change moves the library: a defect users hit, a model people asked for, a refactor that removes code across models, a test that catches a regression. A single typo, one isolated lint fix, one mutable-default fix: not a PR. Bundle mechanical cleanups into a systematic scope, and never as a first contribution.
- If AI tools were used, the PR description says so and includes the coordination link, the differentiation from existing PRs, and the test commands with their results.

If any of these fails, stop. Fix the coordination, not the code.

### The bug must exist

Maintainers receive a steady stream of agent-written fixes for theoretical bugs. Each costs a review round and nobody ever hit it. Before opening a bugfix PR:

- A fix needs a demonstrated failure: a user report, a failing test, or an MRE (section 9) on a released checkpoint or a configuration people use. "This path would misbehave if..." is a hypothesis, not a bug. If no published checkpoint hits it, file an issue with the MRE instead of a PR.
- Reproduce before fixing. User reports often misdiagnose the cause, and agents trust the report. Run the reproducer, then find the first bad commit (`git bisect`) when the failure is a regression. State the root cause in the PR, not the symptom.
- One fix in one model does not mean the siblings are broken. A guard that is dead in one model is load-bearing in another. Propagate only after reproducing per model on a real checkpoint, and coordinate before a sweep PR.
- Compare against other models. If the fix is "the same approach as `<model>`", say so with a link. It tells the maintainer the fix is consistent with the codebase, and it is the step agents skip.
- The PR fixes the bug it claims. The new test fails on `main` and passes on the branch; run both.
- Never let an agent write the "I have reviewed this PR" line. The disclosure and the report are the human's own statement.

## 2. Environment and ground rules

Your checkout is the source of truth, not your memory and not your assistant's training data.

```bash
PYTHONPATH=src python -c "import transformers; print(transformers.__file__)"
```

must print a path inside your checkout; prefix every python command with `PYTHONPATH=src` otherwise. A test that imported the pip-installed transformers proves nothing about your branch.

Before citing or inheriting from any class, helper, or decorator, grep for it. A symbol from six months ago may be gone or renamed (v5 removed head masking, head pruning, relative position biases in Bert-likes, TensorFlow/Jax, torchscript and torch.fx, `cache_position` threading; do not reintroduce any of them):

```bash
grep -rn "<symbol>" src/transformers/ --include="*.py" | head
```

When unsure of the current idiom, open a recently merged model and copy what it does:

```bash
git log --diff-filter=A --name-only --format="" -- 'src/transformers/models/*/modular_*.py' | tail -5
```

Three hard rules: never edit a generated file (a `modeling_*.py` / `configuration_*.py` with a `modular_*.py` next to it: edit the modular and regenerate); never edit code under a `# Copied from` comment without updating its source; never modify an existing model to make inheritance work for your new one.

## 3. Scope the diff

```bash
git diff main...HEAD
git diff main...HEAD --name-only
```

Review the whole diff: code, tests, docs, scripts. If the branch trails `main` and the diff carries unrelated merged files, scope to your commits (`git log main..HEAD --oneline`, then `git show <commit>`). Every file in the list is one you can explain. Debug scripts, notebooks, and generated artifacts come out before review.

## 4. Reuse before you write

New or refactored models are authored in `src/transformers/models/<name>/modular_<name>.py`; everything else is generated. Full guide: [modular_transformers.md](docs/source/en/modular_transformers.md). The essentials:

- Every class inherits from the closest existing implementation, cross-family if needed. `class XAttention(LlamaAttention): pass` is the most common line in real modular files, and one file routinely pulls parents from four unrelated families. A modular file that is mostly bare `nn.Module` definitions means the parent search was not done. Grep distinctive identifiers (`layer_scale`, `q_norm`, gating patterns, codebook ops) across `src/transformers/models/` before writing anything, and use the parent table in the guide (MoE → Mixtral/Qwen2-MoE, sliding window → Gemma2/Cohere2, QK norm → Olmo2/Cohere, SSM → Mamba2/Bamba, ...).
- "A standard model except for X" inherits the standard model and expresses X as the override. "The architecture is novel" raises the bar for how conventions apply, never whether.
- The converter's grammar: `pass` copies the parent with renames. `super().__init__(...)` copies the parent body and appends your lines; reassigning an attribute after it swaps a submodule. `del self.attribute` removes the assignment (override methods that still read it). A config drops an inherited field with `removed_attr = AttributeError()`; a method is deleted by overriding it with `raise AttributeError("...")`. `**super_kwargs` inherits a full signature. One class-name prefix per file, `logger = logging.get_logger(__name__)` and a complete `__all__` at module level.
- RoPE or attention that looks different is usually the same math up to a fixed weight permutation. Inherit the existing class and absorb the layout in a load-time conversion (`PermuteForRope`, `Chunk`, `Concatenate`). Verify the permutation standalone in float64 before trusting it. Two embedding tables the reference keeps separate become one `nn.Embedding` with a `Concatenate` rule: a non-standard structure that a conversion can flatten costs every downstream integration (vLLM, SGLang), so flatten it.
- When porting from a research repo, delete its experimental flags and ablation branches. Keep the standard training surface (`labels`, loss through `self.loss_function`, gradient checkpointing). Transformers models train; reference-repo scaffolding does not ship.

Before writing anything in the left column, grep for the right column and use it:

| You are about to write | Use instead |
| --- | --- |
| an attention mask, a padding or block mask | `masking_utils` (`create_causal_mask`, `create_bidirectional_mask`, `blockwise_overlay`) |
| a rotary embedding | the parent's rotary class + `config.rope_parameters`; one rotary module per model |
| an eager / SDPA / FA branch | `ALL_ATTENTION_FUNCTIONS.get_interface(...)`, one attention class per shape |
| an experts loop | an `Experts` module under `@use_experts_implementation` (`integrations/moe.py`) |
| a norm, activation, or RoPE kernel | keep the parent's `@use_kernel_forward_from_hub`; check the generated file still has it |
| a classification / token / QA head | `GenericForSequenceClassification` and siblings in `modeling_layers.py` |
| image-token merging with loops | `get_placeholder_mask` + `masked_scatter`; `torch.gather` with `pixel_attention_mask` to unpad |
| label shifting or a loss | `self.loss_function` |
| a config-flag module swap in `__init__` | `ModuleFusionSpec` (`fusion_mapping.py`) or `register_patch_mapping` |
| a rename in a conversion script | a `WeightRenaming` line in `conversion_mapping.py` (section 7) |
| a resize / crop / normalize in numpy or PIL | the backend functional (`TorchvisionBackend`, `PilBackend`), shared `XImageProcessorKwargs` |
| a `unittest.TestCase` with a few asserts | `ModelTesterMixin`, `ImageProcessingTestMixin`, `ProcessorTesterMixin` |
| a one-call helper wrapping a literal or one expression | inline it |

Regenerate and check sync; this must exit 0:

```bash
PYTHONPATH=src python utils/modular_model_converter.py <name>
PYTHONPATH=src python utils/check_modular_conversion.py --files src/transformers/models/<name>/modular_<name>.py
```

Read the generated file once in full: your prefix on every class, no cross-model imports (the converter inlines parents), no parent semantics that do not apply to your model, no deleted attribute still read by an inherited method.

## 5. v5 API conformance

The v5 surface is in [MIGRATION_GUIDE_V5.md](MIGRATION_GUIDE_V5.md). mlinter (section 14) catches the mechanical half; these are the points reviews still reject by hand.

**Output plumbing is owned by decorators.** No `output_attentions`, `output_hidden_states`, or `return_dict` in any forward signature, no manual collection loops, no manual defaulting (`x = x if x is not None else self.config.x`; `@merge_with_config_defaults` owns that). Forwards take `**kwargs: Unpack[TransformersKwargs]`. The `PreTrainedModel` subclass declares `_can_record_outputs` mapping output keys to class references, never strings. Encoder forwards producing the captured stream carry `@merge_with_config_defaults` + `@capture_outputs`; head forwards returning a `ModelOutput` carry `@can_return_tuple` + `@auto_docstring`. Never stack `@capture_outputs` with `@can_return_tuple`, and never put `@capture_outputs` on two levels of one call chain: the inner capture empties the outer one. Attention modules return `attn_output, attn_weights` unconditionally, receive `position_ids` through `**kwargs`, and layers are called with hidden states as the first positional argument (the capture hook reads `args[0]`).

**Attention goes through the interface.** No `if self.config._attn_implementation == "sdpa":` branches, no vendored eager/FA2/SDPA triplets, no `*_ATTENTION_CLASSES` dicts. A per-backend dtype cast from the reference belongs at the call site around the single interface call, and only if the parity run at that precision needs it.

**Capability flags are claims.** `_supports_sdpa` / `_supports_flash_attn` / `_supports_flex_attn` / `_can_compile_fullgraph` / `_supports_gradient_checkpointing` set `True` without the matching code path do not error; they silently no-op or mis-run. Each flag you set gets one verification run (section 10 for compile; a training step with checkpointing on).

**Configs are dataclass-style.** Class-level annotated fields with defaults, no `__init__`, `__post_init__` for derived values and BC logic, `validate_architecture` for consistency checks, `@auto_docstring` + `@strict` on every config class (not inherited; declare on each). Rotary settings live in `config.rope_parameters`; a bare `rope_theta` field is the v4 format. Composite models declare `sub_configs`, one sub-config per submodel with its own `model_type` and `base_config_key`, and read nested values through it (`config.text_config.vocab_size`). Sub-config names follow the framework's assumptions (`vision_config`, `text_config`, not `vit_config`). Non-generative models have no `generation_config`. Every field is read by something. Every config-gated branch is exercised by a released checkpoint and carries a `# CODEPATH:` note naming which checkpoints take each side (section 12). Architecture knobs are config fields, not constructor defaults or call-site literals. Modules take `config`, not loose scalar dims. The model class binds its config by annotation, `config: XConfig`, not by assignment.

**Weights.** `_tied_weights_keys` is a dict (`{"lm_head.weight": "model.embed_tokens.weight"}`); never override `tie_weights`, and `tie_word_embeddings` lives on the config level that owns the tied modules. Buffers are `nn.Buffer(...)` attributes, not `register_buffer` calls. `_init_weights` covers every parameter your model adds (custom tokens, layer-scale lambdas, modality embeddings, non-persistent buffers) with the checkpoint-aware `init.*` primitives (`from ... import initialization as init`), never raw `nn.init`, never `torch.empty` for a default. Delegate the standard cases first (`PreTrainedModel._init_weights(self, module)`), branch for the special ones, and never change the parent's init for the whole family as a side effect. The trap: `from_pretrained` uses meta-device init that does not re-run `__init__`, so a parameter missing from both the checkpoint and `_init_weights` loads as uninitialized memory. Prove coverage with the MRE in section 9.

**Loading logic stays out of model PRs.** `base_model_prefix` never participates in checkpoint renaming; that is `conversion_mapping.py`. A model PR does not touch `core_model_loading.py` or `modeling_utils.py`. If it must, split it: a loading change can break every real-world checkpoint at once, and it needs slow tests on real checkpoints.

**Dependencies.** No `einops`: rewrite with `reshape`/`permute`/`unflatten`. No `torch.einsum` in modeling or processing hot paths (backend-dependent accumulation order breaks parity tests): use `@` and broadcasting. An unavoidable optional dependency is gated with `is_<dep>_available()` + `requires_backends`, imported at module top, never inside a function.

**Tokenizers.** One file per model on the named backends (`TokenizersBackend` preferred, `SentencePieceBackend` / `PythonBackend` as fallbacks); no slow/fast pairs, no `special_tokens_map.json` / `added_tokens.json`, `encode_plus` is `__call__`.

## 6. Processing

- Image and video processors sit on the named backends (`TorchvisionBackend` / `PilBackend`); the default `image_processing_<name>.py` is torchvision, the PIL variant is `image_processing_pil_<name>.py`. Override `_preprocess`, not `preprocess`, so the base class resolves kwarg defaults and runtime `rescale_factor`/`image_mean`/`image_std` work. No numpy in per-pixel paths, no `use_fast` (that is `backend=` now). Processors are stateless: `_preprocess` and `post_process_*` never write `self`.
- The generic methods need no override. A video processor defines its sampling logic and, if needed, patching or cropping; it does not reload videos or reimplement resizing. Kwargs classes are shared (`XImageProcessorKwargs`, no `Fast` variant) and carry no `_defaults`: defaults ship in `processor_config.json` on the hub.
- Multimodal processors use the generic `ProcessorMixin` flow; prompt construction, conversation handling, and placeholder expansion live in `processing_<name>.py` and the chat template, never in the model class. Stopping criteria, streaming, and image loading belong to `generate` and the processor stack; delete them from ported code.
- `model_input_names` lists every emitted key. Class-default attributes are JSON-native (`[2, 2]`, not `(2, 2)`) or save/load round-trips fail dict equality.

## 7. Checkpoint loading and conversion

The v5 loading stack applies declarative transforms at load time, so `from_pretrained` consumes upstream checkpoints directly. The registry is [conversion_mapping.py](src/transformers/conversion_mapping.py).

- Prefer a registry entry over a conversion script when the delta is renames, splits, or merges. A rename is `WeightRenaming("attention.output.dense", "attention.o_proj")`; a structural change is a `WeightConverter` with ops:

```python
WeightConverter(
    ["self_attn.q_proj", "self_attn.k_proj", "self_attn.v_proj"],
    "self_attn.qkv_proj",
    operations=[Concatenate(dim=0)],
)
```

  An architecture that matches an existing mapping up to renames gets an alias line in `_MODEL_TO_CONVERSION_PATTERN`, not a copied block. `WeightRenaming` and `WeightConverter` are independent: a converter owns its own renaming.
- Conversions are reversible: load then save round-trips to the same checkpoint. `test_reverse_loading_mapping` checks this; a skip there is a coverage gap. Keep converters leaf-scoped (`"wqkv.weight"` → `["q_proj.weight", ...]`) and let renamings handle prefixes.
- Load with `strict=True` during development and read the load report. A clean load (no MISSING, no UNEXPECTED) is half the parity proof. A MISSING q/k/v plus an UNEXPECTED fused weight means the conversion no-oped and the layer runs on random init, producing garbage with the right shape. Never loosen to non-strict to make a load pass.
- Verify final parity through `from_pretrained` on the real checkpoint, not only a manual `load_state_dict`: only `from_pretrained` exercises your conversion entries and the `_init_weights` path.
- A rename rule matches by substring across the whole model. Before adding or removing one, grep every submodule (text, vision, audio towers) for the target name.

## 8. Numerical parity (the non-negotiable)

Integration tests compare numbers, never shapes. The ladder:

1. Tiny-config forward runs (CPU, random init) through the full path. For multimodal, `input_ids` + `pixel_values` with correctly counted placeholder tokens, not the text tower alone.
2. Same weights, same seeded input, your port against the reference, `torch.allclose` at fp32. Noise is ~1e-5; a ~1e-2 gap is a real divergence (norm order, RoPE parameterization, wrong slice). Find it; never widen the tolerance. Across devices, 100% argmax agreement plus matching top-5 is the bar.
3. Integration tests pin expected slices (logits, hidden states, boxes, decoded text) from the verified parity run, with a comment giving the reproducing command. Device-dependent values use the `Expectations` helper, not widened tolerances. Checkpoint-dependent tests are `@slow` and pass under `RUN_SLOW=1`.
4. Reproduce the reference's arithmetic where weights were trained against it (cast order, fp32 boundaries, the exact `x * sigmoid(x)` form). A one-line dtype difference is an architecture delta to port, not noise. Every cast you add or remove needs stated parity evidence. When refactoring code the weights were trained against (positional embeddings, RoPE tables), keep a path that returns the original tensor at the training shape, bit-exact.

Tests use the common mixins; a hand-rolled `unittest.TestCase` with a few asserts is not coverage. Every `@unittest.skip` names a concrete blocker; "flaky" or "not needed" is not one. Every bugfix ships the test that reproduces it.

### When outputs don't match

Consult when the port diverges and the cause isn't obvious:

- A ~1e-3 logit diff feeding `generate` flips a token and cascades. Check whether a precision diff feeds argmax or sampling before accepting it.
- RoPE cos/sin depend on the dtype of the position coordinates, not only of q/k.
- The published `config.json` overrides code defaults. Read it before reasoning about which branches run.
- Match the RNG mechanism (global `torch.manual_seed` vs `generator=`), not only the seed.
- "Generated in fp32 then cast to bf16" differs from "generated in bf16". Match where the reference casts.
- Same device, dtype, attention backend, eval mode, no dropout, deterministic input. Half of parity failures are harness asymmetries.

## 9. Prove it with an MRE

Any claim of the form "this breaks under X", "this loads wrong", "this shifts silently", in the PR description, a review reply, or your own head, is settled by a minimal reproducible example, not by prose:

- Self-contained: runs against the current tree on a laptop, no hub downloads, no GPU, no datasets. Construct the failing object directly: a tiny config, zero tensors, a saved-and-reloaded local checkpoint.
- Ends in a `print(...)` or `assert ...` that materializes the failure. The reader runs it and sees the bug.
- Under ~25 lines; longer means two claims, split it.

Example, proving `_init_weights` coverage for a new parameter (the section 5 trap):

```python
import torch
from transformers import MyConfig, MyModel

common = dict(hidden_size=32, num_hidden_layers=2, num_attention_heads=2, intermediate_size=64)
MyModel(MyConfig(**common)).save_pretrained("/tmp/tiny")          # checkpoint WITHOUT the new keys
config_new = MyConfig(use_my_new_embedding=True, **common)        # config that CREATES them
model = MyModel.from_pretrained("/tmp/tiny", config=config_new)   # missing-key init path
assert (model.my_new_embedding == 0).all(), "not zero-initialized"  # whatever the ctor specifies
```

If this fails on your branch, the parameter loads as uninitialized memory for every user who warm-starts from an older checkpoint, and no shape test or fp32 parity test catches it. Ship the MRE-derived test with the fix.

## 10. torch.compile

If you touched a `forward`, run it compiled before claiming it works:

```python
import torch, torch._dynamo as dynamo
model = YourModel(tiny_config).eval()
explained = dynamo.explain(model)(inputs)
print(explained.graph_break_count, [r.reason for r in explained.break_reasons])
torch.compile(model, fullgraph=True, backend="eager")(inputs)
```

Break patterns to remove from forwards: Python `if` on any tensor expression (including `and`/`or` chains), `.item()` / `.tolist()` / `.cpu()` / `.numpy()`, `range(tensor)`, `int(tensor)`, slicing with a tensor step, data-dependent loops. Restructure with masking, `torch.where`, or hoist into processing / `_expand_inputs_for_generation`. Compare the break count against `main`: pre-existing breaks are not yours, new ones are. Do not fork the code on `is_torchdynamo_compiling()`: two paths diverge numerically, and one path that compiles is the fix. Initialize caches before the compiled region. `torch.export` and `dynamo` are the supported APIs; torchscript and torch.fx are gone.

No `torch.float64` in modeling code: MPS, NPU and similar backends error or fall back silently. Grep your diff for `float64` / `.double()`.

## 11. Backward compatibility

- Public APIs evolve additively. New config fields default to the existing behavior: with all new flags off, the model is bit-identical to before (test it). Gate new logic on `feature is not None`; an opt-in feature is bit-inert when unset.
- A renamed weight or changed key layout gets a conversion rule so old checkpoints load, in both directions (section 7). No incidental rename or weight-structure change rides an unrelated diff; a decorator migration does not touch weights.
- A breaking change gets 🚨 in the PR title and its own PR.
- Removed kwargs break `Trainer` column passing and downstream callers; check callers before touching a public signature. A `labels` kwarg that only raises `NotImplementedError` still routes dataset columns.

## 12. Dead code and reachability

For any new model or substantial surface, trace how the code is reached from the entrypoints: `from_pretrained` → `forward` per task head, `generate` for generative models, the processor's `__call__`.

1. Follow every call from the entrypoint: which arguments are passed, which branches taken, which helpers invoked.
2. Check reachability under released configs. An `if self.config.use_foo:` where no published checkpoint sets `use_foo` is dead. A live branch carries `# CODEPATH: <checkpoint A> takes this side, <checkpoint B> the other`; a branch nobody can name a checkpoint for is deleted.
3. Flag unused weight: parameters never passed by a caller, private methods never called, layers built in `__init__` and unused in `forward` (loadable-but-dead weights pollute the checkpoint surface). Every class in the generated file is in `__all__` or used.
4. Qualify: "under the default config and the traced call path, this is unreachable." Name the config that exercises it if you know one; otherwise remove it.

Sweep for ephemeral context: `# per reviewer comment`, `# as discussed`, debug prints, parity harnesses with local paths, comparison scripts against the reference repo. Restate the reason so the comment stands alone, or delete it. Working artifacts stay on your machine.

## 13. Style consistency (what ruff cannot see)

`make style` formats. These are the things it does not check, and reviewers do:

- Names come from the repo vocabulary. Before keeping an identifier from the reference code, grep it under `src/transformers/models/`. Zero hits means rename to the existing term: `hidden_states` not `hidden_state` or `x`, `activation_fn` not `act_fn`, `vision_config` not `vit_config`, `crop_size` not `base_image_input_size`. Full words, no abbreviations you invented.
- Comments state an invariant flatly, only where the code cannot say it. No section headers, no slogans, no "as discussed", no comment that explains how the line came to be. Docstrings are one declarative sentence; `@auto_docstring` writes the argument tables.
- Imports at module top, never inside a function, never behind `try/except`. No empty `except`. No silent fallback to a second strategy when the first returns nothing: return nothing, or raise a precise error (`must be one of {ALLOWED} but got {value}`), never a bare `assert`.
- Set a flag or attribute once in `__init__` instead of `isinstance` checks in `forward`. Declare submodules in the order `forward` uses them. Type hints on public signatures stay, including the `tuple | ModelOutput` return hint under a decorator.
- The PR description is short prose a reader with no thread context can follow: what changed, why, how it was verified. No bullet walls, no bold lead-ins, no promises of follow-up work.

## 14. Docs and the mechanical gate

New or changed public behavior (a model, an argument, a default, a renamed API) gets matching updates in `docs/source/en/`, docstrings, and examples. New models: a docs page, a `docs/source/en/_toctree.yml` entry in the right modality section, auto-class registrations, a complete `__all__`.

Then run, in order, each exiting 0:

```bash
make fix-repo                    # ruff, copies, modular conversions, doc TOCs, docstrings
make typing                      # ty type checker + mlinter (structural rules from utils/rules.toml)
python utils/tests_fetcher.py    # writes the tests covering your diff against main to test_list.txt
pytest $(cat test_list.txt) -x
RUN_SLOW=1 pytest tests/models/<name>/test_modeling_<name>.py -k integration -x   # if you have the hardware
```

**mlinter** (`transformers-mlinter`, installed with `pip install -e ".[quality]"`) is the maintainers' structural review turned into rules: decorators on forwards, `post_init` placement, `_tied_weights_keys` form, `nn.Buffer`, `# CODEPATH:` notes, no `nn.Sequential`, no `einsum`, no `.item()` in forward, and so on. CI posts its findings as an advisory review on every PR, so a maintainer sees them before reading a line of your code. Read the rule behind each finding and fix it:

```bash
mlinter --changed-only --base-ref origin/main --rules-toml utils/rules.toml
mlinter --rule TRF041            # explain one rule
```

Files you added have no exemption. Files you edited may carry findings grandfathered by the model's release date; fix the ones on lines you touched. Never silence a rule with `# noqa` (that is itself a rule).

## 15. Report

End the self-review with this report and paste it into the PR description. One idea per sentence, plain words, no rule ids in the prose, and every finding names the fix as an action on the code.

```text
--- Self-review: <branch> ---
POLICY: issue <link>, coordination <link>, AI assistance: <yes/no + tools>
IMPACT: <the user-visible defect, requested model, or removed duplication this PR delivers>
TRIGGER (bugfix PRs): <user report / failing test / MRE on a released checkpoint>
REUSE: <parents inherited, helpers used; or "none applicable" with the grep that showed it>
CHECKS RUN: fix-repo | typing (mlinter: <0 findings | N, fixed>) | fast tests | slow tests <run/not run + why> | compile <break count vs main>
PARITY: <max abs diff at fp32 / argmax agreement / not applicable + why>

BLOCKING (fixed before submitting):
1. <title> — <file.py:line> — <what was wrong, rule cited, how fixed>

NON-BLOCKING (left for the reviewer):
1. <title> — <file.py:line> — <the judgment call and why you did not decide it alone>

DEAD CODE:
<path:line> | likely-dead / used | <reason, qualified per section 12>

KNOWN LIMITATIONS: <anything intentionally out of scope, stated plainly>
VERDICT: READY | NEEDS CHANGES
```

Two calibration rules. Fix every blocking finding before submitting, but leave genuine judgment calls for the reviewer: a non-blocking finding you are not sure about is raised in the report, not "fixed" by guessing. Report outcomes faithfully: if a test fails, say so with the output; if a step was skipped, say that and why. A finding you fix yourself costs nothing; the same finding found by a reviewer costs a round-trip week.
