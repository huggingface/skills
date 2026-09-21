# Processing Review

Reference for image processors, video processors, multimodal processors, and processor tests.

Contract doc: `docs/source/en/multimodal_processing.md` states the intended `ProcessorMixin` API (`valid_processor_kwargs`, `replace_<modality>_token`, `prepare_inputs_layout`, `validate_inputs`). Read it before reviewing a processor; a processor diverging from the doc, or a doc lagging a shipped processor change, is a finding.

The API above is the result of the functional decomposition of `ProcessorMixin` (#45493): `__call__` is generic and split into small override points, and a simple model overrides exactly one method (`replace_image_token`). Third-party consumers (vLLM) call these pieces separately — see "vLLM decoupling" below. Review new processors against this contract, not against the pre-refactor models that still carry full `__call__` overrides.

#46556 (breaking, merged July 2026) migrated the bulk of the multimodal processors onto that contract and extended it. It deleted the per-model private text builders (`_expand_image_tokens`, `_insert_media_placeholders`, `expand_text_with_image_tokens`, `_build_prompt_with_target_shape`, `_get_num_multimodal_tokens`, `_is_url`, …) across the library. A new processor reintroducing a private placeholder-expansion or prompt-building helper is a finding: the expansion string comes from `replace_<modality>_token`, the prompt scaffolding from `prepare_inputs_layout`. What #46556 added:

- `replace_<modality>_token` now takes `**kwargs`, and `_process_<modality>` forwards the merged modality kwargs into it, so per-call kwargs reach token expansion.
- `unused_input_names` (property) drops subprocessor outputs that exist only to compute token counts.
- Overriding `_process_<modality>` is the sanctioned way to thread per-item state into `replace_<modality>_token`.

When `processing_utils.py` and `multimodal_processing.md` disagree, the code wins and the doc gap is the finding — the doc still shows `replace_image_token` without `**kwargs`.

## Image Processing Backends

Interface: `src/transformers/image_processing_backends.py`.

- Main processor inherits `TorchvisionBackend` for fast tensor processing.
- PIL-compatible counterpart inherits `PilBackend` for exact PIL/NumPy behavior or fallback compatibility.
- Backend-specific code respects `backend`, not the deprecated `is_fast`.
- `process_image` normalizes PIL, NumPy, and torch inputs into the backend's expected channel-first representation.
- `SizeDict` for resize, crop, and pad sizes.
- `disable_grouping`, batched shape grouping, and `reorder_images` preserve input order.
- `return_tensors`, device, dtype, channel format, padding masks, and nested image batches are handled explicitly.
- Torchvision limitations: LANCZOS fallback, tensor interpolation differences.

Backend methods own resize, pad, rescale, normalize, crop, and fetch. Do not reimplement them in new code.

The base owns input normalization and kwarg defaulting. Sanctioned override points, in the order the base calls them:

- `_standardize_kwargs` (base at `src/transformers/image_processing_utils.py:314`) — converts `size`/`crop_size`/`pad_size` to `SizeDict` and normalizes mean/std. A model overrides it to map its own aliases onto the canonical keys (`min_pixels`/`max_pixels` → `SizeDict(shortest_edge, longest_edge)`) and then calls `super()`.
- `resize` — dynamic per-image sizing (the `smart_resize` family). It computes the target height/width and delegates the actual resize to `super().resize(...)`.
- `patchify` — flattens an image into `(seq_len, patch_dim)` and returns `(flatten_patches, grid_h, grid_w)`.
- `_preprocess` — receives a ready list of CHW tensors; owns whatever is left after the hooks above.
- `get_number_of_image_patches(height, width, images_kwargs=None)` — required so the processor can predict token counts without running preprocessing. It reads `images_kwargs` when given and falls back to `self.<attr>` only when it is `None`.

A `preprocess` override is a finding **unless** it is a pass-through whose only body is `return super().preprocess(images, **kwargs)`, carrying `@auto_docstring` and the `Unpack[<Model>ImagesKwargs]` annotation. That shape is the sanctioned way to attach rendered docs (56 image processors carry it) and is not duplicated logic. Any statement other than the `super()` call in a `preprocess` body is a finding.

- Processor classes use `@auto_docstring` with kwargs typed `Unpack[<Model>ImagesKwargs]`, not hand-written docstrings. Since #47737 `auto_docstring` explicitly unpacks kwargs into the rendered docstring and covers video processors too, so a hand-written kwargs block is dead text.
- #47573 modularized the qwen-format processors around `resize`/`patchify`. A new qwen-format image or video processor inherits from the nearest sibling (`Qwen2VLImageProcessor`, `Glm4vImageProcessor`, and their `Pil` counterparts) and overrides only the hook that differs. A new file re-deriving the whole patch layout from `TorchvisionBackend`/`PilBackend` when a sibling exists is a finding.
- Per-sample pixel layout (splitting, unpadding, nesting as `list[list[image]]`, `pixel_attention_mask`) is owned by the image/video processor; modeling code re-deriving it from `input_ids` or example ids is a finding (see D36 in `modeling_conventions_review.md`).

## Post-processing API consistency (D22)

`post_process_*` methods match the repo conventions, not the original repo's:

- `target_sizes` optional; batch-first outputs; one dict per image.
- Output key names match the task family: `boxes` (not `bboxes`), `scores`, `labels`, `masks`; box formats are the documented corner/center conventions of the DETR/SAM family.
- The deprecated bare `post_process` method never appears in a new model.
- Processors are stateless: `self.<attr> =` inside `preprocess`/`_preprocess`/`post_process_*` is a finding — preprocess-many-then-postprocess batching breaks on carried state.

## Optional-backend gating (D23)

- A new heavy/optional dependency (cv2, scipy, extra torchvision features) in a processing path first gets the rewrite question: can torch/numpy express it? If not, the import is gated with `is_*_available` + `requires_backends(self, ["cv2"])`, type hints referencing the optional type are string-protected, and the error message names the missing package.
- An unconditional top-level import of an optional backend in a model or processing file is a finding.
- When a diff adapts code to a new API of an optional dependency, the matching `is_*_available` check (and its `require_*` test decorator) is bound to the minimum version; an availability check that passes on an older, incompatible version is a finding. Importing a new symbol from an optional dep bumps the floor in `setup.py` + `dependency_versions_table.py`.
- The inverse also fires: a stale availability guard around a hard dependency (torchvision in the fast-processor path) is itself a finding — the guard implies an untested fallback path that no longer exists.
- Availability is probed with capability checks (`is_*_available()`, `hasattr`, version predicates like `is_torch_greater_or_equal("2.5")`), never `try/except ImportError` — and with exactly one predicate, no redundant fallback branch. A new near-duplicate availability function is a finding when an existing checker can grow a kwarg.
- Optional-kernel/JIT load paths fail (and fall back) at load time, not at first runtime call; a fallback `except` clause covers the failure types the probe can actually raise (`AssertionError`/JIT errors, not only `ImportError`). Note `functools.cache` does not cache exceptions — a cached loader that raises retries the expensive failure forever.
- Toolchain version gating checks consistency, not just minimums: components can each be "recent enough" yet mismatched (CUDA 12.9 in one part of the toolkit, 13.1 in another).

## Tokenizer standards (D35)

- New tokenizers use `TokenizersBackend`; a legacy slow/fast pair in a new model is a finding.
- The `tokenizer.json` shipped with the checkpoint has a stated provenance: converted via a `SLOW_TO_FAST_CONVERTERS` entry (`convert_slow_tokenizer.py`) or taken from the original release. A hand-produced tokenizer file with no conversion path is a finding — "how did we get to this version?" must have an answer, and adding the converter entry is preferred so others can reproduce it.
- Behavior modifiers go through the backend interface: casing via the normalizer sequence (`normalizers.Lowercase()` prepended, the Siglip2 idiom), not string-lowering in `__call__`.
- `padding_side` and similar defaults are set explicitly on the tokenizer class when the model depends on them.
- No re-guarding of properties the backend already guarantees; no dead constructor kwargs.
- Hub-override tables (`MODEL_IDS_TO_TOKENIZERS_BACKEND`, `MODELS_WITH_INCORRECT_HUB_TOKENIZER_CLASS`) are family-complete — see `mechanisms_review.md`, External extension points (D39).
- Route deep tokenizer-internals questions to the tokenizer owner rather than adjudicating (D30).

## Video-processor contract (D37)

`BaseVideoProcessor`'s generic flow owns video loading/decoding (torchvision or torchcodec only — by design, no decord or bespoke wrappers), metadata resolution, kwarg standardization, and batching before `_preprocess` is reached. A model defines at most `sample_frames` (plus the `resize`/`patchify`/`_preprocess` hooks above) and class attrs like `num_frames`/`temporal_patch_size`.

`torchvision.io.read_video` was deprecated in torchvision 0.22 and removed in torchvision 0.26, which ships with torch 2.11 (#47850). The repo pins `torch>2.5`, so the torchvision decode path is version-gated at runtime. New code calling `read_video` without that guard is a finding; torchcodec is the unguarded path.

Findings in a new `video_processing_<model>.py`:

- A decode/load function or wrapper (the base loads the video before `_preprocess`).
- An override of `__call__`/`preprocess` or other base methods.
- A numpy conversion path.
- A bespoke sampling function reducible to the base uniform sampling (call `super()` instead).
- Docs/tests manually decoding frames and passing `video_metadata` when the processor loads from a URL itself.

Gotcha (from memory, verified): `do_sample_frames=False` bypasses `sample_frames`, so `VideoMetadata.fps`/`.frames_indices` may stay `None` — downstream consumers keep fallbacks.

Recurring bug to verify on every new video processor: frame count must be padded to a multiple of `temporal_patch_size` by repeating the last frame — this exact miss has recurred across models ("why do we keep getting this bug?").

## Preprocessing Tests

Preprocessing tests validate values, not shapes.

Required (one or more):

- Representative `pixel_values` slices with tight tolerance.
- Padding mask values.
- Image grid or patch count values.
- Order preservation for grouped images of different sizes.
- PIL and Torchvision backend parity when both exist.
- Device and `return_tensors="pt"` behavior when supported.

Shape-only tests are smoke tests. They do not constitute integration coverage.

## ProcessorMixin Flow

Reference: `src/transformers/processing_utils.py`.

- Inherits `ProcessorMixin`.
- `valid_processor_kwargs` uses a model-specific `ProcessingKwargs` subclass when kwargs differ from defaults; per-call defaults live in the subclass `_defaults` dict, not in `__call__` bodies.
- `super().__init__(...)` receives the right components.
- Uses `prepare_inputs_layout`, `validate_inputs`, `_process_images`, `_process_videos`, `_process_audio`, `get_text_with_replacements` instead of custom rewrites. Input re-nesting belongs in a `prepare_inputs_layout` override (calling `super()` first); model-specific validation belongs in a `validate_inputs` override, not inline in `__call__`.
- Subprocessor outputs that the model's `forward` never consumes (`num_patches`, `grids`, `aspect_ratios`, `image_sizes`, `image_rows`/`image_cols`) are declared in the `unused_input_names` property. The base `__call__` filters them out of the `BatchFeature` and the base `model_input_names` subtracts them. A processor that instead pops those keys by hand, or overrides `model_input_names` to hide them, is a finding.
- `decode` and `batch_decode` are implemented on the base and forward to the tokenizer. Re-declaring them on a model processor is a finding.
- Per-call kwargs win over instance attributes: a `_preprocess` body (or helper it calls) reading `self.<attr>` when the resolved kwargs dict carries the same key silently ignores user overrides — every `self.` read with a matching processor kwarg is a finding.
- Conversation dicts keep the standard schema: extra knobs go through `processing_kwargs` and must be consumed by the image/video processor classes, never smuggled as custom conversation keys.
- Multimodal chat templating routes through the processor: code or tests calling `tokenizer.apply_chat_template` on a VLM is a finding — only the processor can load/decode images and video; tokenizers are fully separated from processors in v5.
- A preprocessing refactor must be generation-output-invariant against `main`: op-level divergences (PIL resize vs tensor resize) are investigated, not papered over by swapping ops — especially when the model team reports eval sensitivity.
- **A full `__call__` override is a finding.** The test is what the method ends with: a `__call__` that ends in `self.tokenizer(...)` + `BatchFeature(...)` re-implements the generic flow and must be removed. A `__call__` that ends in `super().__call__(...)` is acceptable when it only pre-merges kwargs or attaches a model-specific extra to the returned `BatchFeature` (`Emu3Processor` is the reference shape).
- After #46556, "the hook signature cannot carry my per-item state" is no longer a valid reason to keep a full `__call__`. The route is: override `_process_<modality>` to compute the state, call `self.replace_<modality>_token(processed, idx, **extra)` with it, and read it from `**kwargs` in the replacement method. `GotOcr2Processor` is the reference: `_process_images` computes `num_pages_per_batch` and `patch_indices`, `replace_image_token` consumes them, `unused_input_names` drops `num_patches`. Verify any claimed exception against `processing_utils.py`, do not accept it from the PR description.
- Gotcha, kwargs shape in `prepare_inputs_layout`: the base calls it *before* `_merge_kwargs`, so it normally receives flat kwargs. A processor whose `__call__` pre-merges and splats `super().__call__(**merged_kwargs)` makes it receive the structured form instead (`kwargs["images_kwargs"]`). An override that reads the wrong shape silently loses the option — check the shape against the processor's own `__call__`, and check that keys the override consumes are popped so they do not reach the subprocessor.
- `image_token`, `video_token`, `audio_token` match the exact token in user text; a model with no placeholder repetition leaves `image_token` unset and the base class skips replacement.
- Token ids match tokenizer attributes or `convert_tokens_to_ids`. Since #46556 the standard form is an instance attribute set in `__init__` (`self.image_token_id = tokenizer.encode(self.image_token, add_special_tokens=False)[0]`) — 67 processors do this, 9 keep a property, both are accepted. It is not written to the processor config: `to_dict` keeps only attributes whose name is an `__init__` signature parameter or a declared sub-processor attribute, and `image_token_id` is neither. Flagging the instance-attribute form is a false finding. What is still a finding is a token id that does not come from the tokenizer (a hard-coded integer).
- The plural `image_token_ids`/`video_token_ids`/`audio_token_ids` are base-class properties backing `create_mm_token_type_ids`. They default to `[self.<modality>_token_id]`; a model using extra BOI/EOI/row/col tokens sets the list through the setter instead of overriding the property.
- **v5 boilerplate purge:** `tokenizer_class`/`image_processor_class`/`video_processor_class` class attributes were dropped in v5 — their presence in a new processor is a finding. Per-modality kwargs classes are redundant when the sub-processor declares `cls.valid_kwargs`. Multimodal token type ids come from `self.create_mm_token_type_ids`, not manual numpy comparison against token-id arrays. Placeholder expansion is built in the string domain, not via numpy arrays of token ids.
- **vLLM decoupling (#46258):** vLLM encodes text and mm-data separately, so a processor call with placeholder tokens in text but no associated mm-data must not crash — replacement is skipped when there are no replacements to apply. A new processor whose text path assumes paired mm inputs (indexes into `images` because `image_token` is present) is a finding. Do not accept new code that makes text/mm coupling tighter.
- **Replacement offsets shipped** (#46556, backfilled to the remaining old-format processors by #47614 to unblock vLLM PR 50107). It is no longer a forward-looking API. The base `get_text_with_replacements` returns `(text, batch_replacement_offsets)`, `return_text_replacement_offsets` is a real text kwarg that the base `__call__` pops and turns into a `text_replacement_offsets` output key, and `ProcessorMixin.skip_tensor_conversion = ["video_metadata", "text_replacement_offsets"]` keeps it out of tensor conversion. A new processor gets this for free: it declares `"return_text_replacement_offsets": False` in its `ProcessingKwargs._defaults["text_kwargs"]` alongside `return_mm_token_type_ids`, and nothing else. A processor that computes offsets itself, or omits the default, is a finding.

Placeholder token expansion requires the matching method:

- `replace_image_token(self, image_inputs: dict, image_idx: int, **kwargs) -> str`
- `replace_video_token(self, video_inputs: dict, video_idx: int, **kwargs) -> str`
- `replace_audio_token(self, audio_inputs: dict, audio_idx: int, **kwargs) -> str`

The replacement string matches the model's expected number and layout of placeholder tokens for that input item. The `**kwargs` is the merged modality kwargs dict, forwarded by `_process_<modality>`: a replacement method whose token count depends on a per-call option (`num_image_tokens`, patch counts) reads it from there. Reading `self.<attr>` for a value the kwargs carry is the same finding as in `_preprocess` — the user override is silently dropped. A signature missing `**kwargs` breaks the base forwarding and is a finding.

## Multimodal Token Counts

Check across processor and model:

- Placeholder count from `replace_*_token`.
- Processor output: grids, masks, metadata, patch counts, multimodal token type ids.
- Model-side placeholder masks and feature insertion.
- Image / video / audio token ids in config and tokenizer.
- Batch behavior for multiple images, videos, or audio clips per prompt.
- Text replacement order across a batch.

Failure mode: processor expands placeholders with one patch / merge formula, model computes features with another.

## Processor Tests

- Text-only, modality-only, multimodal inputs when supported.
- Single and multiple images / videos / audio items.
- Placeholder replacement counts and ordering.
- `return_mm_token_type_ids` when used.
- Returned model input names.
- Chat-template integration if the processor owns multimodal prompt formatting.
- Numerical output, not shapes.

`ProcessorTesterMixin` covers the above generically; a test class re-implementing a mixin test is a finding. Fit the model to the mixin through its declared hooks, not through overridden test bodies:

- Class attributes for naming and sizing: `videos_input_name`, `images_input_name`, `tiny_model_id`, and the `*_max_length` knobs (`image_unstructured_max_length`, `image_text_kwargs_max_length`, …). A model whose token expansion is large raises those numbers instead of overriding the test case.
- `_setup_from_pretrained` for component fixups the checkpoint lacks (a tokenizer with no `pad_token_id`).
- `_setup_test_attributes` no longer needs to be overridden to set the special tokens: since #46374 the base loops over `image_token`/`video_token`/`audio_token` and copies whichever the processor exposes onto the test class. That PR's point was that a tester silently missing a token was never testing placeholder replacement for that modality — so an override that *drops* a token the processor has is a finding, not a convenience. The remaining valid reason to override is unwrapping (`cls.image_token = processor.image_token.content` when the processor stores an `AddedToken`, as in BLIP-2 and InstructBLIP).
- `test_processor_text_has_no_visual` is the mixed-batch test: samples with and without vision in one call (issue #40263, same contract as vLLM decoupling above). Skipping it needs an architectural reason that every sample must carry an image (BLIP-2, Florence-2), stated in the skip message. A skip because the processor crashes is a finding against the processor, not a valid skip.

Skips require a concrete blocker. Missing assets are not a blocker: use a synthetic image, generated tensor, or fixture.
