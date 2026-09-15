# Tests, Backwards Compatibility, and Blast Radius

Reference for dimensions D10, D11, D12, D30, D32 of `REVIEW_DIMENSIONS.md`. Extends the Test Standard in `../review_deep.md`; the rules here were mined from recurring maintainer review comments.

## D12 — Test standards (beyond "numerical, no unjustified skips")

- **Repro-as-test for every bugfix.** A PR that fixes behavior ships the failing case as a test that fails on unfixed CI. No test delta on a behavior fix is a finding ("can we add a test of what was broken?"). If the failure is device-specific, the test carries the device marker; if it genuinely cannot be tested, the code carries a comment stating the trigger.
- **Standard testers.** New models use the common tester classes (`CausalLMModelTester` and friends); a hand-rolled tester duplicating mixin machinery is a finding — name the sibling model whose tester to copy (qwen3_next-style pointer).
- **Mixin placement.** A test exercising framework-generic behavior (loading, tying, dispatch) written under `tests/models/<x>/` is a finding — it moves to the common/mixin suite so every model inherits it.
- **Assertion style.** No bare `assert` in tests: `self.assertEqual`/`assertTrue` for scalars, `torch.testing.assert_close` for tensors (bare asserts vanish under `-O` and give no diff on failure).
- **e2e generation.** Generative models get a full `model.generate()` integration test with decoded-output comparison, not only forward-logits.
- **Parametrized edge cases.** A set of related edge cases (backend selection, padding variants) is a table of `(case, expected)` driving one parametrized test, not scattered near-duplicate tests.
- **Flash/backend markers.** Attention-backend-dependent fixes get the corresponding marked test (`@require_flash_attn` etc.).
- **Pipeline tests.** New models in a pipeline-covered task enable the pipeline tests; check the model is not excluded from the pipeline test mapping.
- **Trim redundancy.** Tests that re-assert what a mixin already covers, or intermediate checks a stronger end-to-end assertion subsumes, are flagged for deletion — test files are read by humans rarely; shorter is safer.
- **No new test files where a suite exists.** A new `tests/.../test_*.py` for a subsystem that already has one (generation, caches, loading) is a finding — fold the tests into the existing file.
- **Composite-model verification.** Loading/tying/config-resolution claims are exercised on a composite model (main model + submodels with their own configs), not only a text-only one — `_tied_weights_keys` on the main model with `tie_word_embeddings` on the text config is the documented false-pass.
- **Tiny real-format checkpoints.** Loading and conversion tests run against tiny checkpoints in real-world formats (sharded, indexed, original key layout); synthetic state dicts miss what breaks in the wild.
- **Per-variant integration coverage.** A model with N released submodel/backbone variants gets at least one integration test per variant, not one for the family.
- **Hub-asset caching.** Test assets fetched from the hub go through `utils/fetch_hub_objects_for_ci.py` and cache-path access; raw per-test hub downloads are a finding.
- **Split percents over skips.** Failing accelerate/offload tests usually mean bad `model_split_percents` / `_no_split_modules` — tune the percents (e.g. `[0.5, 0.8, 0.9]`) and leave a FIXME rather than skipping.
- **Thread exception propagation.** A test running `generate()` or other assertion-relevant work in a `Thread` (streamer pattern) wraps the target so exceptions propagate to the main thread; otherwise an in-thread raise surfaces as an opaque output mismatch instead of the real traceback.
- **Targeted override over skip.** When a common test fails for one structural reason (a conversion-mapping clash, one incompatible field), override the test in the model's tester and neutralize only that piece (pop the offending mapping entry temporarily); a blanket `@unittest.skip` where a scoped override works is a finding.
- **`Expectations`, never fixture files.** Device-variant expected outputs go through `testing_utils.Expectations` keyed by device, not bare `EXPECTED_TEXT = "..."` literals; committed JSON/tensor fixtures of expected outputs are findings — assert an in-test slice of logits/codes plus mean/std instead.
- **Tiny deterministic checkpoints + size guards.** An integration test loading a full-size checkpoint gets the minified-hub-checkpoint suggestion (fewer layers, deterministic logits, garbage output OK, hosted in the testing org); heavy processors get a size-guard test in the style of `test_is_model_small`.
- **Common-test uniformity.** Common tests contain no `try/except` (it hides errors) and no per-model-type conditionals; per-model deviations live as `@unittest.skip` in that model's tester.
- **Version-gated branches both tested.** A diff branching on a dependency version needs both branches exercised — CI runners install the latest, so the legacy branch requires mocking the version check; an unmocked test silently covers one side only.
- **Lift the skips the fix enables.** When a PR removes the reason existing skips or tester flags were guarding (forced caching, `is_training = False`), flipping those flags and un-skipping is part of the same PR — grep sibling models for skips citing the same reason.
- **Placement by trigger cost.** A test added to a per-model-parametrized suite that never instantiates the model runs N times for nothing — move it to the utility/integration test class.
- **No cross-test state leakage.** A test setting process-global defaults (default dtype, mutated shared config) without teardown is a finding — the pollution surfaces as unrelated later failures.
- **Capability skips in the mixin.** A `_skip_if_*` helper repeated inside multiple test bodies of a mixin file hoists to the shared tester mixin.
- **Parallelism strategies ship their harness.** A new plan kind or `ParallelStyle` ships a dedicated `*TesterMixin`, CI job, and pytest markers; its e2e test is the topology round-trip — train, distributed save, reload under a different mesh, greedy generation verbatim.

## D10 — BC, deprecation cycles, 🚨

- Every deprecation shim/warning states the version at which it gets deleted; a version-less deprecation is a finding.
- Any rename/removal/move of an importable symbol, public kwarg, or attribute that a user could hold needs either a deprecation cycle (old name accepted with a versioned warning) or a 🚨 marker in the PR title. This includes private-by-underscore functions that are importable — "priv but still slightly breaking" gets the 🚨.
- Changed public-method signatures and changed default constants (mean/std, thresholds) are BC events: require the BC statement, and recommend splitting mechanical changes from breaking ones into separate PRs.
- Converting a public mutable attribute into a property is a BC break for hub custom-code models that set it directly: the conversion must ship a setter, and the getter must honor an explicitly set value before computing a derived one.
- The question to answer with evidence, not assertion: "did you check what is **actually** returned/loaded before and after?" — run both sides when feasible.
- New models need no BC shims (D6 in `modeling_conventions_review.md`); BC discipline protects existing surface only.

## D11 — Cross-model blast radius

A fix to a pattern that exists in multiple models is not done when one model is fixed.

- Enumerate the siblings: grep the fixed pattern across `src/transformers/models/` and list every model sharing it (the mamba2 family — bamba, falcon_h1, nemotron_h, zamba2 — is the canonical example). The fix either covers them (shared source, `# Copied from` propagation, modular regeneration) or the finding lists the still-broken siblings.
- One consolidated PR, not a trickle: a shared-pattern bug is fixed for all affected models in a single PR with one common test; per-model trickle PRs for the same bug are a review-cost multiplier and a coordination finding.
- Shape/attribute assumptions get checked against the known-divergent architectures before acceptance: MLA models (`qk_rope_head_dim`, `qk_head_dim` ≠ `hidden_size // num_heads`), VLMs (tying beyond `embed_tokens`, multiple towers), encoder-decoder.
- For a shared-infra change, ask for (or run) the family slow tests; a green single-model run does not validate the family.
- General loading logic and per-model conversion mappings do not change in one PR — the generic change and the mapping changes split, and every model whose mapping changed gets a `run-slow` on real checkpoints; a mapping edit can silently break all real-world weights while the fast suite stays green.

## D32 — Feature isolation and incidental-rename guard

- An opt-in feature is bit-inert when unset: every new code path gates on the feature (`x is not None` / flag), and the default path executes the same instructions as before the diff. Verify by reading the default branch, not the feature branch. A default-path behavior change riding an opt-in feature is a finding.
- A refactor or feature PR does not rename or restructure anything user- or checkpoint-visible in passing: module attribute names, weight paths, output keys, public class names. "Why change the name here?" has one acceptable answer — the rename is the point of the PR and carries its BC treatment (D10); otherwise revert the incidental rename.

## D30 — Escalation and coordination

- Check for in-flight refactors that touch the same area before endorsing a design (`gh pr list --search "<area>"`); a collision is reported as a coordination item with the PR number.
- The review output may route domain-specific items to their owner instead of adjudicating: tokenizer internals, quantization backends, continuous batching, modular converter internals. The routing line names the domain and the open question; it does not guess the answer. Use `[ROUTE TO DOMAIN OWNER: <domain> — <question>]` in the findings block.
