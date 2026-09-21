# Review dimension matrix (mined July 2026)

Ground truth for skill coverage: review dimensions extracted from the inline review comments (and, for domain engineers, authored-PR standards) of nine maintainers — molbap, ArthurZucker, vasqu, qubvel, Cyrilvallez, zucchini-nlp, hmellor (vLLM interop), 3outeille (parallelism), remi-or (continuous batching) — across ~300 huggingface/transformers PRs. A dimension earns a row when a reviewer checks it recurringly, not once. This file is normative: `review_deep.md` mandates a `DIMENSIONS:` coverage line per row id (`D1`–`D41`).

`Status` grades the skill as of the July 2026 audit, BEFORE the same-month restructure; every row is now encoded in its owning reference (mapping below). The column stays as the historical baseline for the maintenance loop.

Reviewer key: M = molbap, A = ArthurZucker, V = vasqu, Q = qubvel, C = Cyrilvallez, Z = zucchini-nlp, H = hmellor, O = 3outeille, R = remi-or.

## Owning references

- `review_deep.md` (process + new-model standard + torch.compile): D1 (with modular_review.md), D2, D4
- `references/modular_review.md`: D1 (converter, decorators, backbones)
- `references/mechanisms_review.md`: D19, D31, D38, D39
- `references/modeling_conventions_review.md`: D3, D6, D7, D8, D9, D13, D14, D15, D16, D17, D18, D24, D25, D26, D27, D29, D33, D34, D36, D40, D41
- `references/fidelity_review.md`: D5, D20, D21
- `references/tests_bc_review.md`: D10, D11, D12, D30, D32
- `references/processing_review.md`: D22, D23, D35, D37
- `references/new_model_review.md`: D28

| # | Dimension | Reviewers | Status | What the check is |
|---|---|---|---|---|
| 1 | Modular reuse / inheritance over duplication | M A V Q Z H | COVERED | nearest parent named per new module, inheritance floor, no cross-model imports |
| 2 | Decorator stack / modern output API | M A Q C Z R | COVERED | no legacy `output_*`/`return_dict`, `_can_record_outputs`/`OutputRecorder`, `@can_return_tuple`, typed internal calls |
| 3 | Attention interface + canonical QKV pattern | M V Z H | PARTIAL | dispatch covered (mechanisms); the llama-standard `hidden_shape`/view/transpose forward shape is not stated |
| 4 | torch.compile safety | M Q C | COVERED | data-dependent branching, `.item()`/`.tolist()`, device/dtype at tensor creation |
| 5 | Faithfulness to reference + parity provenance | M V Q H | MISSING | where expected test values come from; logits match original at 1e-3/1e-4; run the snippet; `model_debugging_utils.py`; reimplementation diverging from upstream needs numeric justification |
| 6 | Dead branches vs released checkpoints | M A V Q Z H O | MISSING | every config flag/branch must be exercised by a released checkpoint; unreachable `else` deleted; no BC shims in new models |
| 7 | Config discipline | M A V Q C Z R O | PARTIAL | config-driven init covered; missing: standard attr names + `attribute_map`, `rope_parameters` format, derived values in config not `__init__` math, no duplicate attrs |
| 8 | Layer-type taxonomy | V H (M) | MISSING | per-layer behavior via `config.layer_types` with distinct explicit names; no layer-index branching; no conflating mechanisms under one type |
| 9 | Signature stability + kwargs contract | V | MISSING | public signatures append-only; new inputs via `**kwargs`; `position_ids` never declared in layer/attention signatures (padding-free FA) |
| 10 | BC / deprecation cycle / 🚨 | V Q A Z H R | PARTIAL | tenet 7 exists; missing: deprecation-cycle mechanics, 🚨 title requirement, split-PR for breaking defaults |
| 11 | Cross-model blast radius | V A C Z H | MISSING | a fix to a shared/copied pattern enumerates sibling models (mamba2 family, MLA head dims, VLM tying) and verifies there; family slow tests |
| 12 | Test standards (extended) | M A V Q C Z R O | PARTIAL | numerical tests + skip justification covered; missing: repro-as-test for every bugfix, standard tester classes, mixin placement for generic behavior, `self.assertX`/`assert_close` over bare `assert`, e2e `generate()` for generative models, parametrized edge-case tables, pipeline tests enabled |
| 13 | Naming pass | M A V Q C Z R O | PARTIAL | full words in tenet 3; missing as mandated check: uniform `<Model>` prefix on every class, casing, no abbreviations, rename suggestions concrete |
| 14 | Minimal surface / good defaults / fail loudly | A V Q C Z H R O | PARTIAL | tenet 6 exists; missing: no `logger.warning` where a default suffices, raise-on-init for unsupported options, version gates on optional deps |
| 15 | Algorithmic directness / anti-premature-generalization | A V M C Z H R | PARTIAL | trivial-helper rule in memory only; missing: single pass over data, no one-consumer shared abstraction, inline stdlib |
| 16 | Loading/saving-path discipline | A Q C Z R O | MISSING | no `from_pretrained` overrides; meta-device init; single checkpoint scan; `load_backbone` for backbones; distributed branches extracted to the distributed module |
| 17 | State and hoisting | A V Q O | MISSING | no module attrs written in forward; config-derived constants hoisted to `__init__`; image processors stateless |
| 18 | `_init_weights` placement and completeness | Q M A C | MISSING | init arithmetic out of modeling code; heads covered for fine-tuning; checkpoint-aware `init.*`; family-appropriate scheme |
| 19 | Weight tying via `tied_weight_keys` | A C H | PARTIAL | dict-form flag covered; missing: loading/distributed code must consult declared keys, never tie twice |
| 20 | dtype/cast provenance | V Q M Z O | PARTIAL | einsum/numerics covered; missing: every added/removed cast in sensitive code cites reference or parity evidence |
| 21 | Conversion scripts + hub checkpoint strategy | M V Q C Z | PARTIAL | registry covered; missing: mapping-dict script format (mllama/dinov3_vit style), converted checkpoints pushed to hub (org PRs, `refs/pr/N`), `verify_logits` in conversion |
| 22 | Vision post-processing API consistency | Q Z | MISSING | `target_sizes` optional, `boxes` key names/formats match DETR/SAM family, no deprecated `post_process`, batch-first |
| 23 | Optional-backend gating | Q M Z H R O | MISSING | `requires_backends` + `is_*_available`, string-protected type hints, prefer torch/numpy rewrite over new dep |
| 24 | Module container discipline | Q | MISSING | `nn.ModuleList` over `getattr`/`setattr`; conditional layers as `nn.Identity` at init, not `if` in forward |
| 25 | Explicit path-pattern plans over introspection | A O | MISSING | tp_plan-style glob dicts instead of `named_modules()` walking; joined regex with group capture |
| 26 | Return-type honesty | M Q Z H | PARTIAL | annotation must match actual return; `ModelOutput` over multi-tensor tuples internally |
| 27 | Code-comment hygiene | V M R | PARTIAL | unexplained magic constant needs one line; boilerplate comments deleted; non-obvious numerics commented so they aren't "fixed" as typos |
| 28 | Docs/metadata coherence | M Q A Z R O | PARTIAL | registration checklist exists; missing: directory = `model_type` = class prefix = doc title, toctree, copyright year, runnable usage snippet, license header |
| 29 | Design-level Occam with measurement | M A R | PARTIAL | codepath count exists; missing: "does this subsystem need to exist" pass with quantified justification (allocation math, fragmentation numbers) |
| 30 | Escalation and refactor coordination | V M Z | MISSING | collision with in-flight refactors checked; domain-owner routing surfaced in output (tokenizer → tokenizer owner, etc.) |
| 31 | Framework mechanisms (kernels/integrations/fusion/registry/flags/EmbeddingAccessMixin) | M Z R (all implicitly) | COVERED | added July 2026, `references/mechanisms_review.md` |
| 32 | Feature isolation and incidental-rename guard | C Z | MISSING | opt-in feature bit-inert when unset; no user/checkpoint-visible rename or weight-structure change riding an unrelated diff |
| 33 | Hybrid cache/mask layer-type coverage | C Z R | MISSING | new cache/mask/generation logic verified for sliding-window, chunked, linear/recurrent layers; positions use `kv_offset`; layer-type names in sync across cache/mask/config |
| 34 | Mask-input plumbing via masking_utils | C Z | MISSING | new mask-affecting kwargs padded once at entry, composed via `or_masks`/`and_masks`, `allow_is_causal_skip` set, forwarded by `prepare_inputs_for_generation` |
| 35 | Tokenizer standards | V M H | MISSING | `TokenizersBackend`, `SLOW_TO_FAST_CONVERTERS` provenance for tokenizer.json, normalizer interface for casing, explicit `padding_side`, no redundant guards |
| 36 | VLM composition and multimodal feature API | Z | MISSING | llava class layout (`Model` + `ForConditionalGeneration`), towers named `vision_tower`/`language_model`, `get_image_features`/`get_placeholder_mask` + `masked_scatter`, pixel layout owned by the processor, mrope/position-id pipeline in the modeling file with one rope path |
| 37 | Video-processor base-class contract | Z | MISSING | only `sample_frames` (+ `_preprocess` internals) overridden; base owns decode (torchvision/torchcodec only), metadata, kwargs, batching; temporal-patch frame padding verified |
| 38 | Downstream consumability (vLLM et al.) | H | MISSING | replaceable computation in named methods not inline forward; truthful `_supports_attention_backend`; canonical weight names or conversion entry; text-only processor calls; config-discoverable topology; dependents smoke test |
| 39 | External extension points | H | MISSING | registration APIs append-only in accepted input shapes; registered local class beats `trust_remote_code`; defensive config mutation (write-on-change, tolerate read-only properties); legacy remap on config-vocabulary renames; hub-override tables family-complete |
| 40 | Continuous-batching runtime contracts | R | MISSING | no dense masks over ragged batches; slot read/write disjointness; request snapshots not live aliases; capability gating before worker launch; locked single-owner cross-thread state; per-request params need the logits processor |
| 41 | Distributed plan/runtime contract | O | MISSING | `ParallelStyle` registry over rank/mesh conditionals; plan-matrix completeness (`_tp/_sp/_tp_ep/_sp_ep`); shard-on-read loading; TP/EP loss-reduction semantics; topology round-trip e2e |

## Sources

- molbap: PRs 46886, 46861, 46836, 46662, 46374, 46347, 46344, 46376, 46262, 46244, 46219, 46163, 46130, 46041, 45919, 45497, 44160, 44125, 44030, 43486, 43451, 43420, 43279, 43263, 43228, 43166, 43137, 43098, 43018, 42978, 42964, 42956, 42896, 42795, 42513, 42507
- ArthurZucker: PRs 46425, 46332, 46565, 46520, 46707, 46603, 46197, 46406, 46622, 46667, 46339, 46818, 46446, 46229, 46440, 46442, 46865, 46842, 46705, 46434, 46386, 46384, 46372, 46765, 46712, 46395, 46407
- vasqu: PRs 46713, 46600, 46738, 46977, 46911, 46862, 46819, 46839, 46914, 46960, 46963, 47019, 46957, 46818, 46992, 46556, 46674, 46543, 46681, 46741
- qubvel: PRs 40859, 40800, 40786, 40651, 40436, 40377, 40342, 40329, 40185, 40141, 40096, 40023, 39970, 40802, 40339, 35550, 34900, 39895, 37357, 37460, 35769, 35627, 35476
- Cyrilvallez: PRs 45979, 46134, 46738, 45477, 45421, 46446, 45661, 45745, 46220, 46207, 45492, 46881, 46634, 44174, 44300, 43590, 43924, 43778, 44988, 44614, 43917, 43768, 45153, 43556, 45046, 44696, 44627, 44940, 44171, 43847, 43706, 45031, 44873
- Delta round (all five maintainers, registry-aware dedup): long PRs 43838, 41621, 43067, 44339 (519 comments, ~93% already covered); short PRs 46990, 46920, 46955; plus the PR 46347 vasqu re-review (~70 comments, source of D35)
- hmellor (registry-aware delta round, July 2026; source of D38/D39; reviews + authored-PR standards): reviewed 47483, 46456, 46023, 45741, 45318, 45094, 44984, 44971, 44953, 44943, 44926, 44903, 44897, 44865, 44851, 44634, 44629, 44582, 44475, 44468; authored 47460, 47451, 47435, 47384, 47296, 47245, 47198, 47174, 47148, 46605, 46524, 46500, 46383, 46087, 45739
- 3outeille (registry-aware delta round, July 2026; source of D41): reviewed 47481, 47253, 46818, 46246, 46189, 46141, 46103, 45994, 45862, 45675, 45483, 45155, 44768, 44640, 44613, 44612, 44608, 44540, 44507, 44506; authored 47357, 47352, 47244, 47237, 46717, 46707, 46705, 46679, 46394, 46292, 46290, 46102, 45409, 45408, 45028
- remi-or (registry-aware delta round, July 2026; source of D40): reviewed 47451, 47185, 47158, 47154, 47118, 46925, 46676, 46670, 46473, 46397, 46278, 46205, 46019, 45974, 45899, 45898, 45660, 45587, 45582, 45553, 45351, 45188, 45063, 44896, 44675, 44455, 44436, 44256, 43750, 43552; authored 47330, 47318, 47311, 47291, 47126, 47117, 47100, 47097, 46765, 46712
- zucchini-nlp (registry-aware delta round, July 2026; source of D36/D37): PR 43451 deep pass (184 inline comments) + 50 most recent merged reviewed PRs 47499, 47449, 47403, 47395, 47315, 47291, 47233, 47181, 47172, 47170, 47151, 47142, 47141, 47112, 47107, 47079, 47074, 47069, 47005, 46974, 46933, 46904, 46903, 46898, 46850, 46841, 46830, 46827, 46790, 46748, 46737, 46732, 46727, 46724, 46695, 46669, 46624, 46573, 46572, 46568, 46544, 46540, 46528, 46514, 46500, 46496, 46495, 46483, 46422, 46417 (~340 comments total; also the source of the functional-processor-refactor rules — #45493/#46258/#46556 contract encoded in `processing_review.md`)
- zucchini-nlp API-drift pass, August 2026 (June 14 – August 14 merged PRs, vision/VLM/preprocessing): #46556 + #47608 processor contract migration, #47614 replacement offsets backfilled, #46374 tester-mixin special tokens, #47573 qwen-format `resize`/`patchify` modularization, #47850 torchvision `read_video` removal, #46405 `get_image_features` output contract, #47737 auto-docstring kwargs unpacking, #47517 `PermuteForRope` direction flip. Updates landed in `processing_review.md`, `modeling_conventions_review.md` (D36), `fidelity_review.md` (D21). No dimension gained or lost scope, so the matrix rows and `execution_graph.js` detectors are unchanged.

## Maintenance loop (offline only — never during a review)

This file is read-only input to a review run. It is updated only on an explicit user request, outside any review: when a maintainer hand-reviews a PR the skill also reviewed, diff their comments against the skill's output — every comment the skill would not have generated is either a new dimension row or a new rule under an existing row. Update this matrix and the owning reference file together. Re-mining reviewer histories is an occasional curation task (last run July 2026), not a per-review step.
