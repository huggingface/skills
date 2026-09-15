# Transformers Deep Review

Use this skill to review `huggingface/transformers` PRs or local branches against `main`. Output findings only. No filler.

Warn at the start of the review: breaching the repository agent contribution guidelines can result in automatic banning.

## Inputs

Accepted invocation forms:

```text
PR_NUMBER=45123
BRANCH=my-local-branch
MODE=auto|new_model|generic
```

Default to `MODE=auto`. If no input is explicit, infer the target from the user request.

## Read-Only Rule

Review work is read-only. You may inspect files, diffs, issues, PRs, and run read-only checks. Do not create comments, reviews, commits, pushes, merges, rebases, or formatting/codegen commands that rewrite files.

If a human action is required, write `[HUMAN ACTION NEEDED]` and stop.

## Fetch Context

### Workspace isolation (first)

`gh pr checkout` and `git checkout` switch the user's working tree. Before fetching anything, run `git branch --show-current` and `git status --short`. If the tree already sits on the PR branch, review in place. If it is on another branch or dirty, do not switch it — fetch the ref and review from a worktree:

```bash
git fetch origin pull/"$PR_NUMBER"/head:review-pr-"$PR_NUMBER"
git worktree add /tmp/review-pr-"$PR_NUMBER" review-pr-"$PR_NUMBER"
```

Leave worktree removal to the user (`[HUMAN ACTION NEEDED]` if cleanup matters).

### Environment preflight (before any python check)

`python -c "import transformers; print(transformers.__file__)"` must print a path under the reviewed tree. Dev machines carry several transformers worktrees; the active env may resolve imports to a different one, and every converter check, pytest run, and MRE then executes against the wrong code. If the path differs, prefix every command with `PYTHONPATH=<reviewed-tree>/src`. The false-drift signature this prevents is documented in `references/modular_review.md` (Workspace and environment preflight).

### Fetch

For a PR, read files directly from the checked-out tree — do not inspect through `gh pr diff` round-trips:

```bash
gh pr checkout "$PR_NUMBER" --repo huggingface/transformers   # only when the user's tree is clean and not parked on other work; otherwise use the worktree above
gh pr view "$PR_NUMBER" --repo huggingface/transformers --json title,body,author,url,baseRefName,comments
git diff --name-only "$(gh pr view "$PR_NUMBER" --repo huggingface/transformers --json baseRefName -q .baseRefName)...HEAD"
git diff "$(gh pr view "$PR_NUMBER" --repo huggingface/transformers --json baseRefName -q .baseRefName)...HEAD"
```

Note: `gh pr diff --stat` is not a valid flag. If you want stats, use `git diff --stat <base>...HEAD` after checkout.

For a branch:

```bash
git diff --name-only main...HEAD
git diff --stat main...HEAD
git diff main...HEAD
```

Read the full diff for every substantive changed file, then read nearby current source via the `Read` tool on the checked-out tree. Do not review from hunk headers alone.

## Reviewer Comments

Pull the existing reviewer discussion before drafting findings. Two goals: confirm each reviewer remark is addressed in the current head, and do not re-raise a point a reviewer already made. The valuable artifact is the remark content paired with the code it points at. Resolution flags are a weak secondary signal, not the mechanism for deciding "addressed".

**On a re-review, refetch.** New review rounds land between sessions (observed: 22 comments → 39 on PR #46266 between two reviews). Never seed the ledger from a previous `AUTOREVIEW_*.md` — its counts and dispositions describe a stale head and a stale comment set. The existing file is overwritten, not extended.

Two sources, both read-only:

```bash
# 1. Review summaries: overall body + state (APPROVED / CHANGES_REQUESTED / COMMENTED). Remarks not tied to a line.
gh pr view "$PR_NUMBER" --repo huggingface/transformers --json reviews \
  -q '.reviews[] | {author: .author.login, state, body}'

# 2. Inline review comments: each anchored to path + line, so the remark arrives with the code it references.
gh api repos/huggingface/transformers/pulls/"$PR_NUMBER"/comments --paginate \
  -q '.[] | {user: .user.login, path, line, original_line, diff_hunk, in_reply_to: .in_reply_to_id, body}'
```

`diff_hunk` carries the code the reviewer highlighted. `in_reply_to_id` links a reply to its parent; an author reply is a *claim* to verify against the head, not an acceptance criterion (see the disposition rules below). `gh pr view --json comments` returns only conversation-tab top-level comments, not inline review comments — it is not a substitute for source 2.

Optional hint: GraphQL `reviewThreads { isResolved isOutdated }` adds a resolved/outdated flag. Use it only as a tie-breaker; the binding test is reading the remark against the current code, not the checkbox.

### Reviewer-comment ledger (mandatory, complete)

Before drafting any finding, build a ledger with **one row per reviewer comment** returned by source 2 (after excluding bot authors and the PR author's own submissions; an author reply on a thread is evidence, not a row to drop the original). Assign each row a stable id `R1, R2, …`. The ledger is the unit of accountability: a comment that never enters the ledger is a comment that gets silently dropped, which is the failure this section exists to prevent.

Do not summarize, cluster, or pre-filter the raw comment list before it becomes ledger rows. Five comments that look like "the same double-decorator point" are five rows. A one-word comment ("Maybe also not needed", "Double decorator") is a row. A question ("Should X be required?", "Are the decorators still needed?") is a row. If `gh api` returned N non-bot, non-author comments, the ledger has exactly N rows. State the count: "Ledger: N reviewer comments (R1–RN)."

For each row, record `id`, `path`, `original_line`, the verbatim remark body, and the `diff_hunk` code. Apply a content-based addressed test:

- Locate the highlighted code in the current head. The stored `line` may have shifted. Re-locate by the `diff_hunk` content with `grep -n`, not by trusting `line`.
- Current code no longer exhibits what the remark describes → addressed. Drop from findings, but the ledger row stays and is marked `addressed`.
- Current code still exhibits it → outstanding. Record in the reviewer-comment audit. Do not emit it again as a new finding.
- A thread marked resolved whose code still matches is still outstanding.
- A question-form comment is `addressed` only when the current code or an author reply answers it; "the answer is obvious to me" is not a disposition — verify it like any other finding (Pass 2 applies to ledger rows, not only to diff-derived candidates).
- **An author reply claiming a pushed fix is verified by finding the fix on the head**, not by the reply. Commits land on the wrong branch (a literal "woops, wrong PR" commit has occurred). Grep the head for the described change; absent → the row is `outstanding` with "author reply claims a push not present on the head".
- **A reviewer self-withdrawal closes the row.** A reviewer replying to their own comment with a retraction ("I was wrong, the backbone forces keeping this") dispositions the row `addressed`; quote the withdrawal as evidence.
- **Disposition against the head, never against a reply's description of the code.** On a PR that reverted its own design mid-review, an author reply describing an intermediate state ("decorators remain on the Model") can contradict the final head (decorators on the Encoder). The reply being stale does not make the row outstanding if the head is coherent — verify the head and say so.
- A question that the codebase answers by convention (e.g. "why is `pixel_values` optional?" when the inherited root model has the identical signature) stays `outstanding` if no author reply exists — record the verified answer in the row so the author can reply with it, but do not mark it addressed on the reviewer's behalf.

Exclude bot authors and the PR author's own submissions from the remarks-to-address set; author replies are evidence to verify, per the rules above.

If `gh api` is unavailable, write `[HUMAN ACTION NEEDED] gh api access required to fetch inline review comments` and continue with source 1 only.

## Symbol Coverage Ledger (mandatory, complete)

Every class, method, and function touched by the diff gets exactly one row, and every row ends with one statement about that symbol. This is a coverage mechanism: a symbol with no row is a symbol that went unreviewed, which is the failure this section prevents. It runs before Pass 1 and feeds it.

Enumerate the symbols from the diff, not from memory. For each changed file, list every `class`, `def` (method or function) whose body the diff adds or modifies:

```bash
base="$(gh pr view "$PR_NUMBER" --repo huggingface/transformers --json baseRefName -q .baseRefName)"  # or main for a branch
for f in $(git diff --name-only "$base"...HEAD -- '*.py'); do
  echo "=== $f ==="
  git diff "$base"...HEAD -- "$f" | grep -nE '^\+.*\b(class|def) ' 
done
```

Assign each symbol a stable id `S1, S2, …`. State the count: "Symbol ledger: N symbols (S1–SN)." Do not cluster or skip symbols because they look trivial. A one-line property, a renamed method, an `__init__` that only calls `super()` — each is a row.

**Generated-file exception (the only permitted clustering).** Symbols in a generated file (`modeling_*.py` / `configuration_*.py` with a `modular_*.py` source) get one collective row per file, dispositioned by a clean `PYTHONPATH=src python utils/check_modular_conversion.py --files <all touched modulars>` run in this conversation (see `references/modular_review.md`, Generated files). The modular-file symbols still get individual rows — they are the source under review. If the converter check fails (after the environment preflight passed), there is no collective disposition: the failure itself is a `warning` finding and the generated symbols revert to individual rows.

For each row, record `id`, `path`, the symbol name, and exactly one statement. The statement is one of:

- A finding (becomes a Pass 1 candidate, carries its evidence forward). In the final output, the row cites the finding's `F<k>` id from the `FINDINGS:` block, the `Fsys<k>` id when a file-wide systemic finding touches the symbol (per the Review pipeline; a neutral disposition is invalid in that case), or the `R<n>` id when the point is an outstanding reviewer remark rather than a new finding.
- A neutral disposition when there is nothing to flag — e.g. "aligned with the rest of the codebase", "standard generic-head signature", "unchanged logic, rename only".

Every statement must be provable in this conversation, neutral dispositions included. "Aligned with the rest of the codebase" is a claim under the Verification rules: back it with a `grep -n` showing the same pattern in ≥1 sibling model, or a file:line to the convention it matches. An unprovable "looks fine" is not a valid disposition — either prove it or convert it to a finding. A neutral disposition with no evidence is the same failure as a finding with no file:line.

Before the output block, emit the coverage line: "Symbol ledger covered S1–SN: F findings, D neutral dispositions (F+D = N)." If F+D ≠ N, a symbol was dropped.

## Scaling the ledgers (subagent fan-out)

The reviewer-comment ledger and the symbol ledger are per-row, grep-verified-in-conversation accounting. On a large PR (a new model, a broad refactor) the counts make a single-context pass blow the budget: the failure mode is silently relaxing the mandate — clustering comments instead of one row each, skipping the symbol ledger, omitting the Pass 2 coverage lines. The fix is to fan the row work out to subagents, not to relax the mandate. Fan out when the comment count or the changed-symbol count exceeds ~40; below that, do it inline.

Orchestration runs through the `Workflow` tool (requires explicit user opt-in per its rules; a review request that names a high-volume PR and asks for the ledgers is the opt-in). The orchestrator does the work the subagents cannot: stage the data, partition it, and independently verify the assembled result.

**Stage the raw data to files first (orchestrator).** Subagents read these; do not inline them in prompts.
- Reviewer comments: `gh api .../comments --paginate -q '.[] | {id, user: .user.login, path, line, original_line, in_reply_to: .in_reply_to_id, diff_hunk, body}'` as JSONL. Filter bot + PR-author rows into the ledger set, keep author replies as an `author_reply` field keyed by `in_reply_to == id`, assign stable `rid` `R1..RN`, write `_ledger_rows.json`. State N.
- Symbols: run the Symbol Coverage Ledger enumeration loop, assign `S1..SM`, mark each `generated` (the generated `modeling_*.py` / `configuration_*.py` and any other converter output). Write `_symbols.json`. Generated-file symbols do not go to subagents — they collapse to one collective row per file dispositioned by the converter check (a failing check is the finding; see Symbol Coverage Ledger, generated-file exception).

**Fan out (one batch per agent, ~10 rows each).** Each agent reads its slice from the staged file, operates against the reviewed tree (pass the worktree path and `PYTHONPATH=<tree>/src`), and returns structured rows (use a `schema`). The agent prompt carries the disposition rules verbatim: re-locate by `diff_hunk` content not by stored line; an `author_reply` is a claim to verify by grep on the head, never acceptance; a question-form remark is addressed only when the head or a reply answers it; evidence is a concrete file:line or "code absent: <grep that returned nothing>". Symbol agents get the existing-findings list (`F1..Fk`) so a row can reference a finding instead of re-deriving it, and the new-model standard so legacy idioms in new code stay findings.

**Compliance audit (orchestrator by default; meta-agent optional).** After the fan-out returns, audit the assembled ledgers against the draft: coverage (every `R`/`S` id present once; emit the two coverage lines with real numbers), consistency (every outstanding reviewer row and every symbol finding the draft omitted from `REVIEWER REMARKS:` / `FINDINGS:`; any draft finding contradicting a ledger disposition; any finding with stale evidence), and disposition quality (any row whose evidence does not prove its disposition). The coverage arithmetic and the omission cross-check are cheap — the orchestrator does them directly. Delegating this audit to a separate meta-review agent is **optional** and expensive: a meta-agent must be handed the full assembled ledger JSON in its prompt, which is a large token cost on top of the fan-out. Spend it only when the ledgers are very large, the draft has many findings, or the stakes warrant a second independent reading. The audit itself is not optional — only its delegation is. Skipping the meta-agent does not skip the orchestrator's own verification below.

**The orchestrator independently verifies the fan-out and the meta-review before publishing — they propagate errors.** A subagent dispositioning a comment from the comment text alone, and a meta-review trusting that disposition, is the documented failure: on PR #43451 two `tarekziade` scope-leak rows were marked `outstanding` from the remark body, but the named files were absent from `git diff main...HEAD` — addressed, not outstanding. The orchestrator's diff-scope grep caught it. Treat every subagent and meta-review disposition as a claim under the Verification rules: spot-verify the highest-severity new findings with your own grep, and re-check any disposition that rests on "still present" / "absent" against the actual diff. The published review is the orchestrator's, not a paste of the agents' output.

## Classify

Use the deepest relevant mode:

- `new_model`: new `src/transformers/models/<name>/` surface, registrations, processors, image/video processing, tokenizers, tests, docs, or conversion mapping.
- `model_refactor`: modularization, generated files, `# Copied from`, modeling utilities, output capture, generic layers, loading, conversion, or processing backend migration.
- `generic`: everything else.

For `new_model` or `model_refactor`, read `references/new_model_review.md`.

For `model_refactor` diffs touching `modular_*.py`, decorator stacks (`@capture_outputs`, `@can_return_tuple`, `@merge_with_config_defaults`, `@filter_output_hidden_states`), backbones, or `conversion_mapping.py`, also read `references/modular_review.md` — it carries the converter's auto-derivation rules, the exact decorator semantics, the two valid backbone layouts, and the conversion-mapping coverage hole. Do not review a decorator stack from the decorator names alone.

For processor or image/video processing changes, read `references/processing_review.md`.

For any diff that adds or edits a normalization/activation/rotary/MoE-expert module, attention dispatch, a load-time module swap, checkpoint renames, or any `PreTrainedModel` subclass, read `references/mechanisms_review.md` — it carries the trigger table for hub kernels, `integrations/`, fusion mapping, monkey patching, the conversion-mapping registry, the `PreTrainedModel` flags audit, and `EmbeddingAccessMixin`. Every `new_model` and `model_refactor` review reads it.

Every `new_model` and `model_refactor` review also reads `references/modeling_conventions_review.md` (code-level conventions: attention shape pattern, dead branches, layer types, signatures, naming, state, `_init_weights`, containers, return types), `references/fidelity_review.md` (faithfulness to the reference implementation, cast provenance, conversion scripts, hub strategy), and `references/tests_bc_review.md` (test standards, BC/🚨, cross-model blast radius). For `generic` diffs, read the one whose dimensions the diff triggers.

For `generic`, keep the review short unless the diff touches shared modeling, loading, conversion, processing, attention, or test infrastructure. Short never skips the quick-review minimum (mined from maintainer behavior on small diffs): warning triage on any `logger.warning` in the hunk (D14), placement/isolation of branches added to core generic methods (D16/D32), provenance and failure-legibility of any test delta (D5/D12), and version floors on optional-dependency adaptations (D23).

## Dimension coverage (mandatory)

`REVIEW_DIMENSIONS.md` (repository of this skill) is the registry of review dimensions, ids `D1–D41`, each owned by a reference file. It was mined from ~300 PRs of maintainer review comments (molbap, ArthurZucker, vasqu, qubvel, Cyrilvallez, zucchini-nlp, hmellor, 3outeille, remi-or) and is the definition of "thorough"; a review that covers only what the diff makes obvious is the failure this section prevents.

**Route with the execution graph, not by re-reading everything.** `execution_graph.js` (repository of this skill) is the rule base for the sweep: run its detectors — cheap greps of `match` patterns over the diff — then read only the reference sections owned by the dimensions whose detectors fired. A silent detector is itself the evidence: its pattern and zero hits become the `not triggered` line, no reference read needed. Three parts are never gated by detectors: the `always_on` dimensions (run on every PR class), the `absence_checks` (mandatory on `new_model`/`model_refactor` — they catch reimplementation-by-absence, which no positive grep can see), and the DIMENSIONS block itself (all 41 ids, always). The graph narrows where you read, never what you cover. `graph.html` next to it renders the routing for humans.

**After a finding, consult the flow graph.** `execution_graph_full.js` is the unrolled companion: directed edges mined from real review trajectories (13 PRs), where an edge `X -> Y` means a finding on dimension X led maintainers to check Y next (weights = occurrence counts, each edge carries its rationale and source PRs). When a dimension produces a finding, walk its out-edges before closing the sweep — they are the consequent checks human reviewers ran in the same situation (e.g. a D1 duplicate-module finding opens the D21 rename-instead question; any D11 sibling enumeration closes only via family-scoped `run-slow`). Its `notes` array records flow shapes edges cannot express (re-review loops, SPLIT_PR vs CONSOLIDATE_PR, placement-as-precondition). `flowgraph.html` renders it.

Before the output block, sweep the registry once and emit a `DIMENSIONS:` block — one line per dimension:

- `D<k> <slug> — findings: F3, Fsys1` (the dimension produced findings), or
- `D<k> <slug> — clean: <one-line evidence>` (checked, nothing found; the evidence is a grep/command from this conversation, same standard as a neutral symbol disposition), or
- `D<k> <slug> — not triggered: <reason>` (nothing in the diff activates it; the reason names what is absent, e.g. "no processor files in diff").

Not-triggered lines may be collapsed into a single line listing the ids (`Not triggered: D8, D22, D23 (no layer_types / post-processing / new deps in diff)`). Clean and finding lines are never collapsed. A dimension with no line is an unreviewed dimension — the same coverage failure as a dropped ledger row.

The registry is static input at review time. A review never mines reviewer histories, never fetches anything beyond the PR under review, and never edits this skill's files. The dimension sweep costs greps against the diff, nothing more. Updating the registry (adding rules from a hand review the skill missed) happens only on an explicit user request outside any review run, by editing the owning reference file and `REVIEW_DIMENSIONS.md` together.

## Core Review Priorities

Review in this order:

1. **Tests.** Reject unjustified skips. Integration tests must compare numerical outputs, not shapes. Shape-only forward or preprocessing tests do not constitute coverage.
2. **Decorators, output capture, flags.** Check `@can_return_tuple`, `@merge_with_config_defaults`, `@capture_outputs`, `_can_record_outputs`, `OutputRecorder`. Every new or edited `PreTrainedModel` subclass gets the flags audit and the `EmbeddingAccessMixin` check (`references/mechanisms_review.md`): `_supports_*` flags match the actual dispatch, `_tied_weights_keys` is a dict, `_can_compile_fullgraph` is honest, no getter/setter override the mixin already resolves.
3. **Generic layers.** Use `GenericForSequenceClassification`, `GenericForTokenClassification`, `GenericForQuestionAnswering`, `GradientCheckpointingLayer` when applicable.
4. **Conversion mappings.** `src/transformers/conversion_mapping.py` controls checkpoint name compatibility. One `WeightRenaming` rule or one `_MODEL_TO_CONVERSION_PATTERN` alias line can replace a duplicated parent architecture.
5. **Processing interfaces.** Image processors use the backend interfaces. Multimodal processors use the generic `ProcessorMixin` flow (`docs/source/en/multimodal_processing.md` is the contract).
6. **Framework mechanisms.** Hub kernels (`@use_kernel_forward_from_hub`, `@use_kernel_func_from_hub`), `integrations/` backends, `ExpertsInterface`, fusion mapping, monkey patching. A mechanism is in scope when the diff **reimplements what it owns**, not only when the diff touches its files — vendored kernels, legacy attention-dispatch dicts, `if config.fuse_x` load-time swaps, hand-rolled expert loops are findings by absence of the mechanism. See `references/mechanisms_review.md`.
7. **Modularity.** A short `modular_<name>.py` inheriting from the closest existing model replaces copied modeling code.
8. **Tenets.** The eight design principles of the library. A diff that violates one is a finding. See `## Tenets` below for the full list and how to apply each in review.

## Tenets

The eight tenets from the `transformers-community/Transformers-tenets` blog (October 2025). They are written-down software interfaces that emerged over time and were then recognized as load-bearing. They are the source of truth for the review priorities above; a diff that violates a tenet is a finding, and the tenet is the `NOTE`'s justification.

Apply them against the current framework state, not the blog's snapshot. Several tenets are now enforced by machinery the blog predates or only gestures at: the decorator stack (`@can_return_tuple`, `@capture_outputs`, `@merge_with_config_defaults`), `_can_record_outputs` / `OutputRecorder`, modular files, and `conversion_mapping.py`. When a diff regresses one of those mechanisms, cite both the tenet and the mechanism.

1. **Source of truth.** Model implementations are reliable, reproducible, and faithful to the original performances. Review hook: integration tests compare numerical outputs against the reference, not shapes; a new model without a numerical parity test violates this tenet.
2. **One model, one file.** All inference and training core logic is visible top-to-bottom in one file, to maximize hackability. Review hook: model-specific logic pulled into a shared util that the reader must leave the file to understand is a violation. This does not conflict with modular — modular's generated `modeling_*.py` is still one self-contained file; the `modular_*.py` is the authoring source.
3. **Code is the product.** Optimize for reading, diffing, and tweaking; users are power users. Review hook: explicit, full-word variable names; readability regressions (terse names, dead params, collapsed control flow that hides a branch) are findings even when behavior is unchanged.
4. **Standardize, don't abstract.** If it is model behavior, keep it in the file; abstractions are only for generic infra. Review hook: a new abstraction layer wrapping behavior that differs per model is a violation; conversely, re-implementing generic infra (a task head, a mask creation, output capture) inline instead of using the standardized helper is the same tenet pointing the other way (see Core Review Priorities 3 and 5).
5. **DRY\* (do repeat yourself).** Copy when it helps users; keep successors in sync without centralizing behavior. Review hook: duplication is acceptable when it keeps a model file readable, but it must be kept in sync — a `# Copied from` block edited without updating its source, or a near-duplicate parent architecture that a `WeightRenaming` rule or a `modular_*.py` would collapse, is a violation. Modular and `# Copied from` are the sanctioned sync mechanisms.
6. **Minimal user API.** Config, model, preprocessing; `from_pretrained`, `save_pretrained`, `push_to_hub`; the least number of codepaths. Review hook: a new public method, constructor arg, or codepath that duplicates an existing entrypoint, or that the user must learn to use the model, is a violation. Prefer extending the standard flow over adding a parallel one.
7. **Backwards compatibility.** Evolve by additive standardization, never break public APIs. Any artifact that once worked stays usable indefinitely. Review hook: a removed/renamed public kwarg, a changed return-shape convention, or a renamed buffer/weight without `_keys_to_ignore_on_load_unexpected` or a `conversion_mapping.py` rule is a violation. Removing `output_attentions` / `output_hidden_states` / `return_dict` from a signature is allowed only when the decorator stack restores the same public behavior.
8. **Consistent public surface.** Same argument names, same outputs across models; hidden states and attentions exposed; enforced by tests. Review hook: this is what `_can_record_outputs`, `@capture_outputs`, and `@can_return_tuple` enforce mechanically. A model whose `hidden_states` / `attentions` come back empty (wrong `_can_record_outputs` class, double-decorated call chain, capture on the wrong level), or whose argument names diverge from sibling models, violates this tenet. See `references/modular_review.md` for the decorator semantics.

## New-model standard: novelty is not a waiver

A new model file (`new_model` mode, or any newly added `modular_*.py` / `modeling_*.py`) is held to the **current** framework standard, not to what legacy models happen to contain. "This architecture is novel / not like any other model in the codebase" is the single most common justification a review wrongly accepts; it raises the bar for *how* a convention is applied, never *whether* it applies. When a draft finding's disposition is about to read "acceptable because the model is novel" or "justified given the architecture," that is the signal to write the finding, not to drop it — let the author supply the specific reason no standard alternative exists. The reviewer does not pre-grant that reason.

This is a coverage mechanism for the systemic issues that per-symbol review misses. A high symbol count tempts the reviewer to disposition each module "neutral; novel block" and move on; that is the failure this section prevents. Check each item against the whole new model, file-wide, not symbol-by-symbol:

1. **Legacy ("v4") idioms in new code.** Each of these is a finding in a new model even though it exists in older models, and it is **not** graded against legacy prevalence (see Verification, "new code vs legacy prevalence"):
   - `return_dict` / `output_hidden_states` / `output_attentions` in a forward signature, or manual resolution (`x = x if x is not None else self.config.x`); the decorator stack (`@can_return_tuple`, `@auto_docstring`, `_can_record_outputs` / `@capture_outputs`) owns these.
   - Returning a `ModelOutput`/dict with no tuple path, or hand-assembling an intermediate tuple/“return intermediate” plumbing, instead of the decorator-provided BC.
   - Bespoke output dataclasses that duplicate a generic one (`MaskedLMOutput`, `TokenClassifierOutput`) to add one field.
   Severity `warning`: the new model is the place to set the current standard, and a port that ships pre-v5 plumbing has not been ported.

2. **Modules must take `config`.** An `nn.Module` constructed from loose scalar dims (`SomeBlock(d_model=2560, d_z=256, num_layers=80)`) instead of receiving the `config` object is a finding. Values derivable from config but recomputed at `__init__` from loose args are the same finding. The convention is `__init__(self, config)`; architecture-defining knobs live in the config, not as constructor defaults or call-site literals. `warning` when a released checkpoint variant cannot be expressed because the knob is not a config field.

3. **Sampling / generation parameters belong in a generation config.** A `sample()` / `generate()` / inference method that takes `num_steps`, `noise_scale`, `step_scale`, `max_sigma`, `temperature`, etc. as method arguments instead of reading them from a `GenerationConfig` is a finding. Hyperparameters as method defaults are config fields in disguise.

4. **Forward size and arity.** A `forward` longer than ~100 LOC is a decomposition finding — the body belongs in named submodules the reader can follow (tenets 2, 3). A `forward` with a large positional-argument count (≳10, especially a long run of same-typed tensors) is a finding — bundle related inputs (a features dict, a dataclass, or config) and split the model into submodules that each own their slice. A 200-line forward and a 20-argument forward are each a finding on their own, before any per-line review.

5. **Codepath proliferation (tenet 6).** Count the distinct codepaths a new model adds: chunked vs unchunked, varlen vs dense, cache vs no-cache, multiple public inference entrypoints, bespoke setup/toggle methods (a per-instance compile switch, a chunk-size setter, a custom inference helper) that the standard flow does not require. Each parallel path the user must learn or the maintainer must keep alive is a finding; prefer one path through the standard flow. A method that mutates global or process state (a framework's global compile/threading config) as an instance side effect is a `warning`.

6. **Hardcoded tables/constants belong in the config on the hub.** A large hardcoded numeric table (reference coordinates, vocabularies, lookup tables) baked into a modeling or util file is a finding; the fix is to store it in the checkpoint config on the hub and load it through `from_pretrained`, not to "add a source comment." Data in Python source is data outside the model's load contract.

7. **Cross-model imports in the generated modeling file.** The generated `modeling_*.py` must be self-contained — the converter inlines parents. An `from ..other_model.modeling_other import X` surviving in the *generated* file is a finding (tenet 2). The `modular_*.py` may import from other models (that is the authoring source); the generated file may not.

**Modular inheritance floor.** A `modular_*.py` that is almost entirely bare `nn.Module` definitions with near-zero inheritance is itself a file-level finding, not a neutral observation. The modular mechanism exists to inherit; a novel architecture raises the bar for the per-module reuse analysis (`references/modular_review.md`, "Read the root before judging the leaf") but does not remove it. For each new `nn.Module`, state the nearest existing implementation and the count of what survives inheritance; if the file inherits from almost nothing, say so as a file-level finding and require the author to justify each bare module — do not justify the file on the author's behalf.

**Verdict and ordering.** When a new-model PR exhibits a cluster of the above (no inheritance + config-less modules + giant forward + legacy idioms + sampling params as args), lead the review with the systemic assessment and set the verdict to `Request changes` at minimum. Do not let a high symbol count or a "novel architecture" framing dilute a cluster of systemic findings into a list of `discussion` items. A model that needs structural rework is `Request changes`, stated plainly, however individually defensible each line is.

## Verification

**Every claim in a review must be backed by evidence in this conversation.** A claim is anything of the form: "X is broken", "Y is missing", "Z is equivalent to W", "A is replaceable by B", "C is an antipattern", "D defaults to E". If you cannot point to a file:line, a tool output, or a numeric trace that supports the claim, leave the claim out.

Specific traps:

- **Docstring drift without checking the rendering pipeline.** `auto_docstring` rebuilds the `, defaults to X` segment from `getattr(cls, name)` at render time (`src/transformers/utils/auto_docstring.py:4319-4321,4342`). Literal "defaults to X" text in the source is a no-op for rendered docs. Before flagging "doc says A, field is B", grep the docstring decorator path and confirm the text is user-facing.
- **"Drop-in batched" without reading the shape contract.** Before claiming `f(N-batched-array)` replaces a loop, read the function: do the shape annotations, index arithmetic, and strides support a leading batch dim? If the flat-index calc lacks an `N`-stride, the function is N=1-only and needs rewriting.
- **Torch/torchvision "equivalent" without checking signatures.** `tvF.affine` is not `cv2.warpAffine` — the former takes decomposed `(angle, translate, scale, shear)` with uniform scale, the latter takes an arbitrary 2×3 matrix. Before claiming an equivalent, check parameter shapes, interpolation modes, output-size handling, and border handling.
- **"This is an antipattern" without grepping the codebase.** Patterns that look wrong in isolation are often established idioms. Example: `labels=...` + `raise NotImplementedError` is used in 11+ models for dense-prediction heads where training is not implemented (depth_anything, depth_pro, zoedepth, dpt, vitmatte, vilt, swin2sr, perceiver, omdet_turbo, prompt_depth_anything, bark). Keeping `labels` in the signature is required for `Trainer._remove_unused_columns` to pass the dataset column through. Before flagging an idiom, `grep -rn "<pattern>" src/transformers/models/` and count the hits.
- **New code graded against legacy prevalence.** The "established idiom — grep ≥3 models" rule protects *existing* code under edit from churn; it does **not** license a *new* model file to adopt a legacy idiom. `torch.einsum`, `return_dict` in signatures, manual `output_*` resolution, bespoke output dataclasses, and config-less modules appear in dozens of older models and are still findings when introduced in new code. A high grep count across legacy models is the modal *historical* practice, not the current standard. Before downgrading a new-model finding because the pattern is common, check whether the file is new (`git diff --name-status main...HEAD` → `A`); if it is, hold it to the current convention and keep the finding. This is the inverse error to the one above: the antipattern-grep protects legacy edits, it does not absolve new files.
- **"Refactor X into Y" without proving equivalence.** When suggesting reuse of an existing helper (e.g., "import vitpose's `box_to_center_and_scale` with `normalize_factor=1.0`"), produce a case-by-case proof: for each branch of the current code, show the equivalent branch in the replacement produces the same output (centers, scales, boundary cases, numeric spot-check on one concrete input). "They look similar" is not a proof.
- **"This breaks Z" without showing the failure.** When flagging behavioral risk (autograd, `torch.compile`, in-place mutation, view aliasing), produce a minimal repro that triggers the failure. If the failure is conditional, state the exact conditions under which it triggers and the conditions under which it does not.
- **Performance claims without naming the regime.** State the regime: "O(N_persons) Python iterations dominate the GPU forward when N_persons ≥ K". Otherwise drop the finding.
- **API improvement suggestions without thinking through compute cost.** A `flip: bool` shortcut that internally runs two forwards has the same compute cost as a user calling two forwards. The arguments against forward-side TTA are semantic (which `hidden_states`/`attentions` end up in the single `ModelOutput`), not compute cost.
- **Findings based on commit messages, PR titles, or branch names.** PRs to `huggingface/transformers` are squash-merged: the branch becomes one commit on `main` and individual commit messages disappear. Never ground a finding on a mismatch between a commit message and the code it shipped (e.g. "commit titled 'Inherit from X' but the class doesn't inherit from X"). The code is the only durable artifact. If the code is not actionable on its own, drop the finding.
- **Citing framework symbols without grepping them.** Before naming an API entrypoint (`_autoset_attn_implementation`, `ALL_ATTENTION_FUNCTIONS[...]`, `.dispatch(...)`, `register_for_auto_class`) in a review or recommendation, grep for the exact symbol and read the current call sites. Framework internals change: `_autoset_attn_implementation` → `_check_and_adjust_attn_implementation`; `ALL_ATTENTION_FUNCTIONS[impl]` → `ALL_ATTENTION_FUNCTIONS.get_interface(impl, default_fn)`; `if impl != "eager": ...` removed, default is a parameter. Run `grep -rn "<symbol>" src/transformers/` and quote a current call site before naming any registry, mixin, decorator, or resolver method. Current attention dispatch pattern: `ALL_ATTENTION_FUNCTIONS.get_interface(self.config._attn_implementation, eager_attention_forward)` — re-locate with `grep -n "get_interface" src/transformers/models/dinov3_vit/modeling_dinov3_vit.py`. Anchor citations by symbol, not by line number: line numbers in this skill and its references drift across branches; a `grep -n` for the symbol is the durable pointer.
- **Unresolved referent in the user prompt.** When the user names a source — a reviewer ("comments of X on the other review"), a file path, a PR number, a thread — and two read-only lookups against the obvious locations (the named PR's `reviews` / `comments` endpoints, `git log --grep`, `ls`/`grep` on the local filesystem) return nothing, stop and ask the user before widening the search. A misread or hallucinated referent burns tool calls and pollutes the context window with negative results. One AskUserQuestion beats five broader greps.
- **Tool output produced against the wrong tree.** Before reporting any converter-check failure, pytest result, or MRE outcome, confirm the Environment preflight (Fetch Context) ran. A drift report where the generated side resembles the *base ref* means the converter resolved a parent model from another worktree, not that the PR is out of sync. Re-run with `PYTHONPATH=<reviewed-tree>/src` before writing the finding.
- **"Redundant declaration" without the converter's derivation rules.** A class attribute in a modular file (`base_model_prefix`, `_no_split_modules`, `_can_record_outputs`) that equals the parent's value renamed is removable — but only the auto-derivation proof makes that a finding: cite a sibling modular that omits the attribute and whose generated file carries it correctly (ijepa is the reference pair for the ViT family). Without that pair, the claim is unverified. See `references/modular_review.md`.
- **Fast-suite green read as conversion-mapping coverage.** `test_reverse_loading_mapping` skips when any class in `all_model_classes` lacks an entry ("No conversion found for `<X>Backbone`"); a green run with skips validates nothing about a new mapping entry. Report pass/skip per model and route validation to the slow integration test. See `references/modular_review.md` (Conversion mapping).

## Review pipeline (order of operations)

The ledgers, the new-model checks, and the two passes are not parallel checklists — they run in a fixed order, and the order is load-bearing. The symbol ledger is a leniency pump: every symbol viewed alone looks locally defensible, so a per-symbol sweep run first disposes away the file-wide problems (no inheritance, oversized forward, codepath sprawl) that live in no single row. Run breadth before depth.

1. **Reviewer-comment ledger** (`R1–RN`) — build it first; it bounds what is already said.
2. **Systemic pass (breadth), file-wide.** Before enumerating symbols, run the `New-model standard` checks (new models), the mechanism-coverage pass (`references/mechanisms_review.md`, trigger table — all modes), and the relevant tenets across the whole diff. Emit file-level findings with ids `Fsys1, Fsys2, …`. The inputs are cheap greps: `forward` LOC and positional-arg counts, `class .* nn.Module` with no base class, `torch.einsum` count, whether each `nn.Module.__init__` takes `config`, legacy `return_dict`/`output_*` in signatures, hardcoded numeric tables, cross-model imports in generated files, `*_ATTENTION_CLASSES` dicts, undecorated norm/rotary modules whose family parent is decorated, `PreTrainedModel` flags set vs dispatch, `get_input_embeddings` overrides. Emit the line **"Systemic checks run: M/M; Fsys count = K"** where M counts new-model checks plus fired mechanism triggers — this comes *before* the symbol ledger in the working notes, which forces the ordering. A mechanism trigger that fires and produces no finding gets a one-line provable disposition in the working notes, like any neutral symbol row.
3. **Symbol pass (depth), seeded by the systemic findings.** Now build the symbol ledger. Each row resolves *against* the `Fsys*` set: it either cites the systemic finding that touches it (`S122 → Fsys3`) or is genuinely neutral. **Invariant: a "neutral" disposition is invalid for any symbol a systemic finding touches.** A neutral row that overlaps an `Fsys*` is a coverage error, not a disposition — grep the `Fsys*` file:lines against the symbol's span to check. This is the constraint that stops "neutral; novel block" from burying the structural findings.
4. **Pass 2 verification, over both sets.** Hard-find + scope-check every `Fsys*`, every diff-derived `F*`, and every `R*` ledger row. The new-code-vs-legacy carve-out applies: an `Fsys*` is not downgraded because the idiom is common in older models.
5. **Verdict consumes the systemic set.** A cluster of `Fsys*` is `Request changes` led with the systemic assessment (per `New-model standard`), regardless of how defensible each individual line is.

These steps are enforced by **verifiable artifacts**, not exhortation: the "Systemic checks run" count, the "Symbol ledger covered S1–SN: F+D = N" count, and the neutral-overlap invariant are each grep-checkable. A count that does not add up is the signal a pass was skipped.

## Two-Pass Review Process

Two passes. The second pass is **mandatory and non-skippable**. The review is not allowed to reach `## Output Format` until Pass 2 has run over (a) every Pass 1 candidate finding and (b) every reviewer-comment ledger row. There is no "small diff" or "obvious" exemption. If you find yourself writing the output block without a completed Pass 2 ledger, stop and run Pass 2 first.

Pass 2 has two distinct subjects, and **both** must be processed — missing either is the documented failure mode of this skill:

1. **Candidate findings** from Pass 1 (the diff-derived list).
2. **Reviewer-comment ledger rows** (R1–RN from the Reviewer-comment ledger section). Each row gets the same hard-find verification as a candidate. A row is never dropped by omission — it ends Pass 2 with an explicit disposition (`addressed` / `outstanding`) backed by a grep against the current head. A question-form row ("why is this needed?", "should X be required?") is dispositioned by verifying the answer, not by asserting one.

Before the output block, emit the ledger coverage line: "Pass 2 covered R1–RN: K addressed, M outstanding (K+M = N)." If K+M ≠ N, a row was dropped — Pass 2 is incomplete.

Greps, `Read`s, parameter-shape lookups, and repro snippets go in the same batch of tool calls as the draft. Do not write a finding before its verification has returned.

**Pass 1.** Generate candidate findings against the diff. For each candidate, attach the evidence (file:line, grep output, parameter shape, repro output). Working draft, not shown to the user.

**Pass 2.** For each candidate finding AND each reviewer-comment ledger row:

1. **Hard-find verification (required).** Before writing the finding, run a `grep -n` (or `rg -n`) for the exact code text the finding cites, scoped to the file path the finding targets. The grep must return a non-empty match. Paste the grep command and the matched line into the verification batch. If the grep returns nothing, the line number or the quoted code is wrong — re-read the file and fix both, or drop the finding. The `CODE:` field of the finding must be the verbatim grep match, not a paraphrase.

   **Scope check (required).** After the file-level grep passes, run a second grep against the base ref: `git show <base>:<file> | grep -n "<code>"`. If the line is present on the base ref, the issue is pre-existing and the PR does not introduce it — drop the finding. A PR review is for what the PR changes, not for a tour of the file. Exception: a finding may stay if the surrounding edit creates a new failure mode for a line that existed before (e.g. a flag was removed elsewhere that used to make the line safe); in that case the NOTE must state the specific delta on this branch that activates the failure.

   Example:
   ```
   $ grep -n "batch_logits, batch_boxes = batch\[1\], batch\[2\]" docs/source/en/tasks/object_detection.md
   269:...         batch_logits, batch_boxes = batch[1], batch[2]
   ```
   `CODE:` then quotes exactly `batch_logits, batch_boxes = batch[1], batch[2]` and `LINE` is `269`.

2. **Verified?** Point to file:line, tool output, or numeric trace in the conversation. Otherwise drop.
3. **Established idiom?** Grep the codebase. If the pattern appears in ≥3 unrelated models or is documented in a `references/` file, do not flag — **but only for existing code under edit.** A new model file is held to the current standard regardless of legacy prevalence (see Verification, "new code vs legacy prevalence", and "New-model standard: novelty is not a waiver"). Do not downgrade or drop a new-model finding because legacy models share the idiom.
4. **Proposed alternative equivalent?** Write the equivalence proof or numeric trace. If absent, downgrade from "do this instead" to "consider whether X applies."
5. **Conflated concepts?** Shorter-edge resize vs aspect-expand crop; `tvF.affine` (decomposed) vs `cv2.warpAffine` (matrix); `gaussian_blur` border handling; uniform vs non-uniform scale; `interpolate(antialias=True)` vs `INTER_AREA`.
6. **User-visible contract preserved?** Removing a kwarg breaks `Trainer` column passing. Changing a return-shape convention breaks downstream callers. Renaming a buffer breaks old checkpoints unless the diff includes `_keys_to_ignore_on_load_unexpected`.
7. **Severity calibrated?** `warning` = correctness or policy violation. `discussion` = design choice with tradeoffs. `nit` = cosmetic.
8. **Already raised?** Match the candidate against the reviewer remarks by `path` and the highlighted code. If a reviewer already states the point, do not emit a duplicate finding. Record it in the reviewer-comment audit. Use the same hard-find `grep -n` to confirm the highlighted code still exists in the current head.

Cut candidates that fail any pass-2 check.

## Implementation conventions (apply before recommending rewrites)

Codebase-wide conventions. A rewrite that violates them is not an improvement.

### No `numpy` in image / video / audio processing paths

Processing code (`_preprocess`, `post_process_*`, image / video / audio processor methods) stays on `torch.Tensor` end-to-end. The torchvision backend (`TorchvisionBackend`, `torchvision.transforms.v2.functional`) is the convention for spatial ops: `resize`, `pad`, `gaussian_blur`, `crop`, `affine`, `normalize`.

- Numpy paths force a CPU round-trip; `.cpu().numpy()` ↔ `torch.from_numpy()` boundary cost.
- `disable_grouping` / shape-grouping batch optimizations in `image_transforms.py` require tensor inputs.
- `torch.compile` and AMP autocast do not compose with numpy.

Numpy is allowed for pure-Python orchestration that does not touch per-pixel arrays (e.g. building `center` and `scale` from a bbox, computing a 2×3 warp matrix to hand to `cv2`). Per-pixel math is torch.

Convert numpy in a proposed rewrite before including it: `np.pad(..., mode="edge")` → `F.pad(..., mode="replicate")`; `np.clip` → `.clamp`; `np.log` → `.log_()`; `np.linalg.inv` → `torch.linalg.inv`; `np.einsum` → below.

### Avoid `einsum` in modeling and processing hot paths

`torch.einsum` produces different floating-point results across backends (CUDA vs CPU vs MPS, FP16/BF16 vs FP32). Contraction order and intermediate buffer placement vary by implementation; accumulation differences exceed integration-test tolerances. Use explicit `@` / `bmm` / broadcasting:

| `einsum` form | explicit equivalent |
|---|---|
| `einsum("nkij,nkj->nki", A, b)` | `(A @ b.unsqueeze(-1)).squeeze(-1)` |
| `einsum("nij,njk->nik", A, B)` | `A @ B` |
| `einsum("bnd,bnd->bn", x, y)` | `(x * y).sum(-1)` |
| `einsum("bhqd,bhkd->bhqk", q, k)` | `q @ k.transpose(-1, -2)` |
| `einsum("nij->nji", A)` | `A.transpose(-1, -2)` |

Translate any `einsum` in a proposed rewrite to the explicit form before including it.

## torch.compile compatibility

Forward-pass ops that break the dynamo graph disable compile in user code. When the diff touches a `forward` method, verify compile-friendliness.

### Grep-level break risks

- `.tolist()` / `.item()` / `.cpu()` / `.numpy()` — force materialization.
- `if tensor.shape[i] == constant:` — specialization; recompile on shape change.
- `if tensor.is_cuda:` — device-dependent branch.
- `int(tensor.X)` / `bool(tensor.X)` — data-dependent control flow; breaks `fullgraph=True`.
- `getattr(torch, str_var)` — string→dtype lookup. Safe in `__init__`, breaks in `forward`.
- `for x in tensor:` / `for x in tensor.tolist():` — data-dependent loop; breaks `fullgraph=True`.
- `isinstance(submodule, SomeNNType)` — specialized at trace; verify if the submodule swaps based on input.
- `with torch.autocast(...)` / `maybe_autocast(...)` — context supported; inner ops still need to be compile-friendly; dtype change triggers recompile.

### Python `if` on a tensor expression

Each of the following produces `Unsupported: Data-dependent branching` (`generic_jump TensorVariable()` in `explain` output) at the `if` line, before dynamo reaches any later materialization:

- `if tensor_a != int_literal:` — `tensor != int` returns a 0-d bool tensor; Python `if` calls `.item()` implicitly. No `.item()` text in the source.
- `if tensor_a != tensor_b:` — same.
- `if tensor_a != int_literal and tensor_a % int_literal == 0:` — Python `and` / `or` over tensor comparisons evaluates each operand as a Python bool; both operands break.
- `if tensor.sum() > 0:`
- `if (input_ids == token_id).any():`

Reference: `modular_molmo2.py:1539` (generated `modeling_molmo2.py:1032`). `if total_image_tokens != image_features.shape[0] and total_image_tokens % image_features.shape[0] == 0:` fails `fullgraph=True` with `Unsupported: Data-dependent branching` at the `if`, before reaching the `.tolist()` two lines below. Grep tensor-valued names on either side of `if` / `and` / `or` / ternary `if … else …`.

### Hidden materializations

- `range(tensor_scalar)` — `range()` requires a Python int; calls `.item()`. Triggered by `num_beams = total_tensor // shape_int` (still 0-d) followed by `for _ in range(num_beams)`.
- `int(tensor_scalar)` / `float(tensor_scalar)` — same.
- `tensor[::tensor_scalar]` — slice `step` requires a Python int; 0-d tensor step is `.item()`-ed. Dynamo emits `Graph break from Tensor.item()` at the slice line.
- `list(tensor)` — iterates; `.item()` per element.
- `[int(x) for x in tensor.tolist()]` — `tolist()` materializes; `int(...)` is where dynamo prints the break.
- `tensor.size()` returns `torch.Size` (Python tuple); safe. Distinct from a 0-d tensor compared with `tensor.shape[i]`.

### Compiled-region scope

- `.cpu().numpy()` in `post_process_*`: not compiled; safe.
- Same op in `Model.forward`: graph break.

### dynamic=True

Vision models with arbitrary resolution and sequence models with arbitrary length: compile may pass with `dynamic=False` and fail with `dynamic=True`. Verify both.

### Verification recipe

```python
import torch, torch._dynamo as dynamo

def suspect(...):
    # paste the function or the smallest enclosing forward fragment here.
    ...

# inputs that take the flagged branch
input_ids = torch.zeros(B * num_beams, S, dtype=torch.long); input_ids[..., :K] = image_token_id
image_features = torch.randn(B * K, D)

dynamo.reset()
explained = dynamo.explain(suspect)(input_ids, image_features, image_token_id)
print(explained.graph_break_count, [r.reason for r in explained.break_reasons])

# backend="eager" skips inductor codegen; failure is the dynamo trace error
dynamo.reset()
torch.compile(suspect, fullgraph=True, backend="eager")(input_ids, image_features, image_token_id)
```

Quote `break_reasons[i].reason` or the `Unsupported: ...` line in the finding with file:line.

### Dynamo error → cause

- `Unsupported: Data-dependent branching` → Python `if` on a tensor expression. Fix: restructure control flow (`torch.where`, masking, or hoist the branch out of the compiled region).
- `Graph break from Tensor.item()` → explicit or implicit `.item()`. Dynamo prints the use site (`range(...)`, slice with tensor step), not the `.item()` call.
- `generic_jump TensorVariable()` → data-dependent branching, `explain`-output form.
- `Unsupported: call_function BuiltinVariable(range) [TensorVariable()]` → `range(tensor)`.
- `Unsupported: dynamic shape operator` → `nonzero()` / `unique()` in `forward`.

### Severity

- Forward-pass graph break under `fullgraph=True`: **warning**. Compile is disabled in user code.
- Forward-pass break with `fullgraph=False`: **discussion**. Compile runs slower than it should.
- `dynamo.explain` reports `graph_break_count > 0` under the default config: **warning**. Compile produces multiple recompiled fragments; slower than the uncompiled baseline.
- Post-processing graph break: **info**. Only flag if the post-processor is documented as a compile target.
- Risky idiom present but not on any compiled path: drop.

### Existing tests in transformers that catch compile breaks

Read CI before claiming a test gap.

- `tests/models/<name>/test_modeling_<name>.py::<Model>ModelTest::test_torch_export` — runs `torch.export`. Data-dependent branching surfaces as `torch.fx.experimental.symbolic_shapes.GuardOnDataDependentSymNode: Could not guard on data-dependent expression Eq(uN, M)`. Failure on a PR is direct evidence of a compile/export break in `forward`.
- `tests/models/<name>/test_image_processing_<name>.py::*::test_can_compile_fast_image_processor` and `tests/models/<name>/test_video_processing_<name>.py::*::test_can_compile_fast_video_processor` — run `torch.compile` on the fast processor path. `AssertionError: Tensor-likes are not close!` indicates an op behaves differently under compile (quantization, fused kernel, resize/interpolation tolerance mismatch).

Molmo2, May 2026: `Molmo2ModelTest::test_torch_export` failed with `Could not guard on data-dependent expression Eq(u1, 1)`. Source: `if total_image_tokens != image_features.shape[0]` at `modular_molmo2.py:1539`.

### Known patterns

- `flip_pairs.tolist()` in a TTA path inside `forward`: data-dependent integer indexing; breaks `fullgraph=True`. Keep `flip_pairs` as a tensor and use `torch.gather` / advanced indexing, or move the flip out of the compiled region.
- `if input_ids.shape[1] > self.config.max_position_embeddings:` — specialization; recompiles on every new length. Use `torch._dynamo.mark_dynamic` or restructure.
- `embed_tokens(input_ids).to(dtype)` where `dtype` is `torch.get_default_dtype()` inside forward: recompile on dtype change.
- Writing a mutable global (registry, config singleton) on a path that runs under compile: gate the write on `is_torchdynamo_compiling()` being false or hoist it out of the compiled region.
- Cache initialization inside the compiled region: the first call must initialize the cache before compile captures it — run the first chunk/step uncompiled, then compile steady-state.
- Beam-search image-feature re-expansion via token-count divisibility (Molmo2, May 2026). Pattern: `if (input_ids == img_id).sum() != image_features.shape[0] and ... % ... == 0:` followed by `image_token_counts[::num_beams]`, `range(num_beams)`, `original_image_token_counts.tolist()`. Three breaks: data-dependent branching at the `if`; `.item()` at the slice step; `range(tensor)`. Measurements: `dynamo.explain` reports `graph_break_count=1` under default config; `fullgraph=True` fails with `Unsupported: Data-dependent branching`; `test_torch_export` fails with `Could not guard on data-dependent expression Eq(u1, 1)`. Compile-clean rewrite: stash `expand_size` and per-sample image-token counts as Python `int` / `list[int]` on `model_kwargs` inside `_expand_inputs_for_generation`; in `forward`, use `image_features.split(counts)` (Python list of ints) and `torch.cat([chunk for chunk in split_result for _ in range(expand_size)], dim=0)`.

## Tone

The review is a technical document, not prose. Write factually and monotonously. Findings describe what the code does, what the diff changes, and what fails. Nothing else.

Hard rules:

- No rhetorical flourishes, metaphors, idioms, jokes, or judgments of style. "The comment is folklore", "this is a footgun", "this is canonical X", "smells like Y", "reads as Z" are all banned. State the mechanical fact instead: "The comment references a workaround whose trigger condition is not stated. Document the trigger or remove the workaround."
- No varied vocabulary for its own sake. Pick one word for one concept and reuse it across the review. If "unused parameter" is the term in the codebase, use "unused parameter" every time — not "orphan grad", "dangling param", "stranded weight".
- No softeners or intensifiers: "clearly", "obviously", "frankly", "arguably", "interesting", "neat", "elegant", "ugly", "messy", "brittle" (unless paired with the concrete brittleness condition), "footgun", "gotcha", "trap".
- No second-person address ("you'll want to", "you can"). Use imperative or declarative: "Use X.", "X returns Y."
- No filler openers: "Note that", "It's worth noting", "As written", "In practice", "Effectively", "Essentially", "Basically".
- One claim per sentence. Short declarative sentences. Subject-verb-object. No semicolon-chained clauses that smuggle in a second claim.
- Findings are written in the same shape every time: `<symbol> at <file:line> does <X>. Under <condition> this produces <Y>. Replace with <Z>.` Do not vary the structure to keep the reader entertained.

If a sentence could appear in a blog post, rewrite it.

## Minimal Reproducible Example (MRE)

When a finding describes a situation in which the code can break, do not explain the situation in prose. Provide a Python snippet that triggers the failure.

The MRE replaces the prose. It does not accompany the prose.

Shape:

```
NOTE: <one sentence stating the failure mode and where it triggers>

MRE:
```python
# self-contained snippet; runs against the current tree; prints or asserts the failure
```
```

Rules:

- The snippet imports from the current `transformers` tree, not from a hypothetical fixed version.
- The snippet ends in a `print(...)` or `assert ...` that materializes the failure (wrong index, shifted tuple, shape mismatch, raised exception). The reader runs it and sees the bug.
- No narration inside the snippet. Comments only for non-obvious setup.
- If the failure requires a specific call site (e.g. `Trainer.prediction_step`), import the real symbol and call it. Do not paraphrase it.
- If the snippet is longer than ~25 lines, the finding is probably two findings — split it.
- No hub downloads, no full model loads, no real datasets. Construct the failing object directly: instantiate the `ModelOutput` dataclass with zero tensors, build a `datasets.Dataset.from_dict` with a handful of rows, call the failing helper with synthetic inputs. The reader must be able to run the MRE on a laptop with no network and no GPU. If a checkpoint is genuinely required, the finding is not an MRE candidate — describe the test command instead.

When prose alone is enough (a missing arg in a doc, a typo, a dead branch), no MRE is needed. MRE is required for "breaks under <condition>", "shifts silently", "wrong tensor selected", "race condition", "wrong device", "dtype overflow".

## Pre-Output Checklist

- [ ] Every "doesn't work" / "is broken" claim names the failure mode (which test, which dtype path, which device).
- [ ] Every "should use existing helper" claim lists the helper's signature and a case-by-case equivalence (or "verified by grep" for a literal drop-in).
- [ ] Every "antipattern" claim has been grep-checked against `src/transformers/models/`.
- [ ] Every performance claim names the loop bound (N persons, K keypoints, batch size) and the operation cost.
- [ ] User retractions are recorded inline (struck through or in a "Dropped findings" subsection).
- [ ] Severity: `warning` = correctness / policy violation; `discussion` = design choice with tradeoffs; `nit` = cosmetic.
- [ ] Output is in reading order: diff-derived findings, outstanding reviewer remarks, and symbol rows sorted by (path alphabetical, line ascending); `Fsys*` lead the block; `F*` ids assigned after sorting; highest-severity ids named in `SUMMARY:` and `REASON:`.
- [ ] If the diff touches a forward method, `torch.compile(fn, fullgraph=True)` was run on the new code path. Otherwise state the reason for skipping.
- [ ] No finding rests on a commit message, PR title, or branch name.
- [ ] Every finding's `LINE` and `CODE:` were hard-verified with a `grep -n` against the cited file. The `CODE:` value is the verbatim grep match.
- [ ] Every finding's `CODE:` was checked against the base ref with `git show <base>:<file> | grep -n`. Pre-existing lines were dropped unless this PR's edits make them newly broken (NOTE states the delta).
- [ ] No rhetorical phrasing, metaphors, idioms, or aesthetic judgments. No "folklore", "footgun", "canonical", "smells", "reads as", "elegant", "ugly". One word per concept, reused.
- [ ] No second-person address, no filler openers ("Note that", "As written", "In practice"), no softeners ("clearly", "arguably").
- [ ] Every "breaks under <condition>" / "shifts silently" / "wrong tensor selected" finding has a runnable MRE under it. Prose explanations of breakage without an MRE are not allowed.
- [ ] Workspace isolation respected: the user's checkout was not switched; a worktree was used if the tree was dirty or on other work.
- [ ] Environment preflight ran: `import transformers` resolves to the reviewed tree, or every python command carried `PYTHONPATH=<tree>/src`.
- [ ] If the diff touches any `modular_*.py`, `check_modular_conversion` ran (post-preflight) over all touched modulars and its result is stated.
- [ ] If the diff touches `conversion_mapping.py`, `test_reverse_loading_mapping` ran per affected model and skips are reported as coverage gaps, not passes.
- [ ] On a re-review, reviewer comments were refetched; no count or disposition was carried over from a previous `AUTOREVIEW_*.md`.
- [ ] The reviewer-comment ledger has exactly one row per non-bot, non-author comment from source 2, and the stated row count N matches the number `gh api` returned.
- [ ] Pass 2 ran over every ledger row R1–RN, not only the diff-derived candidates. The "Pass 2 covered R1–RN: K addressed, M outstanding" line is present and K+M = N.
- [ ] On a high-volume PR (comment or symbol count > ~40) the ledgers were fanned out to subagents per "Scaling the ledgers", the compliance audit ran (orchestrator-direct by default; meta-agent optional), and every subagent disposition — and the meta-agent's, if one was used — was independently verified by the orchestrator (highest-severity findings re-grepped; "present"/"absent" dispositions re-checked against the actual diff). The ledger mandate was not relaxed.
- [ ] Every reviewer remark is accounted for as addressed or outstanding, with the addressed test run against the current head. Question-form remarks are dispositioned by a verified answer, not an asserted one.
- [ ] No candidate finding duplicates an existing reviewer remark.
- [ ] The Review pipeline order was followed: systemic pass (breadth) ran before the symbol ledger (depth), the "Systemic checks run: M/M; Fsys count = K" line is present, and `Fsys*` findings are listed first in the output.
- [ ] Neutral-overlap invariant holds: no symbol-ledger row is dispositioned "neutral" while an `Fsys*` finding touches its span.
- [ ] For a new model, "New-model standard: novelty is not a waiver" was applied file-wide: legacy idioms, config-less modules, sampling params as args, forward size/arity, codepath proliferation, hardcoded tables, cross-model imports, and the modular inheritance floor were each checked, not only per-symbol.
- [ ] No finding was downgraded to `discussion` or dropped solely because the architecture is "novel" or because the idiom is common in legacy models. Every "acceptable given the architecture" disposition names the specific reason no standard alternative exists.
- [ ] The mechanism-coverage pass ran over the whole diff (`references/mechanisms_review.md` trigger table): hub kernels, `integrations/` backends, `ExpertsInterface`, fusion mapping, monkey patching, conversion-registry aliases. Reimplementation-by-absence was checked, not only files the diff touches; each fired trigger has a finding or a provable disposition.
- [ ] Every new or edited `PreTrainedModel` subclass got a flags audit against the class body of `PreTrainedModel` (not a remembered list) and the `EmbeddingAccessMixin` override check.
- [ ] For each changed mechanism, the matching contract doc under `docs/source/en/` was read; doc-vs-code divergence was reported on whichever side is stale.
- [ ] The `DIMENSIONS:` block covers D1–D41 from `REVIEW_DIMENSIONS.md` with no missing id; every `clean` line carries in-conversation evidence; `not triggered` reasons name what is absent from the diff.

## Common Findings

- Generated `modeling_*.py`, `configuration_*.py`, processor, or image processing files edited while a `modular_*.py` source exists.
- `# Copied from` block changed without updating the source or breaking the copy link.
- Task head reimplemented when a generic head in `modeling_layers.py` applies.
- `_can_record_outputs` points to the wrong module class, omits `OutputRecorder`, or captures the wrong tuple index.
- `@capture_outputs` or `@can_return_tuple` missing from a forward that returns a `ModelOutput` and supports BC tuple behavior.
- New model duplicates a parent architecture because conversion names do not match, when `WeightRenaming` would align them.
- Modular declares class attributes the converter derives from the parent (`base_model_prefix`, `_no_split_modules`, `_can_record_outputs`) — removable when equal to the parent's value renamed (`references/modular_review.md`).
- `@capture_outputs` stacked with `@can_return_tuple` on one forward — capture pops `return_dict` itself; one of the two is dead.
- `@capture_outputs` on two levels of one call chain (Encoder and Model) — the ContextVar collector shadows; the outer level's captures come back empty.
- `@filter_output_hidden_states` below a Backbone-level `@capture_outputs` whose body never sets `hidden_states` — the filter has nothing to strip; dead decorator.
- `get_input_embeddings` override returning what the inherited `_input_embed_layer` already resolves; vestigial attributes (`self.pooler = None`) absent on the base ref with no reader.
- A public forward newly accepts or forwards `attention_mask` without `create_bidirectional_mask` conversion on one of its paths (Model converts, Backbone passes raw).
- Image preprocessing uses ad hoc PIL/NumPy when `TorchvisionBackend` or `PilBackend` applies.
- Processor expands placeholder tokens without the matching `replace_*_token` method.
- Integration tests assert only `.shape`, skip without a concrete blocker, or omit numerical slices / logits / task outputs.
- New model written to a pre-v5 standard: `return_dict`/`output_*` in signatures, manual flag resolution, dict/intermediate-tuple output without decorator BC, bespoke output dataclasses (see "New-model standard").
- `nn.Module` taking loose scalar dims instead of `config`; architecture knobs as constructor defaults or call-site literals rather than config fields.
- Sampling / inference hyperparameters (`num_steps`, `noise_scale`, `max_sigma`) as method arguments instead of a `GenerationConfig`.
- A `forward` over ~100 LOC or with ≳10 positional args, undecomposed into submodules.
- A `modular_*.py` with near-zero inheritance (bare `nn.Module` definitions throughout) — file-level finding, not a neutral "novel architecture" disposition.
- Hardcoded numeric tables/constants in a modeling or util file that belong in the checkpoint config on the hub.
- Bespoke public methods that add a parallel codepath or mutate global/process state as an instance side effect; cross-model imports surviving in the generated `modeling_*.py`.
- New/edited norm, activation, or rotary module matching a hub-kernel layer name without `@use_kernel_forward_from_hub` / `@use_kernel_func_from_hub`, or a modular override dropping the parent's kernel decorator (check the generated file).
- Vendored kernel source or inline `import triton` in a model directory instead of the kernels hub (`_HUB_KERNEL_MAPPING` + `lazy_load_kernel`).
- Legacy `*_ATTENTION_CLASSES` dispatch dict or inline `if self.config._attn_implementation == ...:` branching in new code; per-model attention wrapper duplicating `integrations/{flash,sdpa,flex}_attention.py`.
- MoE experts hand-rolled as a Python loop instead of an `Experts` module under `@use_experts_implementation` (`integrations/moe.py`).
- Load-time module swap via config flag + `__init__` branch instead of a `ModuleFusionSpec` (`fusion_mapping.py`) or `register_patch_mapping` (`monkey_patching.py`); a fused layout without reverse `make_transforms` (breaks `save_pretrained` round-trip).
- New conversion block duplicating a pattern reachable by one `_MODEL_TO_CONVERSION_PATTERN` alias line; a `convert_*_to_hf.py` script doing pure renames the registry expresses.
- `_supports_sdpa`/`_supports_flash_attn`/`_supports_flex_attn`/`_supports_attention_backend` asserted without interface dispatch, or left `False` over standard dispatch; `_tied_weights_keys` as a list; `_can_compile_fullgraph = True` with data-dependent branching in forward.
- `get_input_embeddings`/`set_input_embeddings` override that the `EmbeddingAccessMixin` resolution order already covers; a getter override with no matching setter (breaks `resize_token_embeddings`).
- Mechanism behavior changed without updating its contract doc (`kernels.md`, `fusion_mapping.md`, `multimodal_processing.md`, `attention_interface.md`, `monkey_patching.md`, `weightconverter.md`).

## Test Standard

- Skips require a concrete blocker.
- New models require modeling, processor / image processor, loading / conversion, and integration tests.
- Preprocessing tests compare representative numerical `pixel_values` or equivalent outputs with tolerances.
- Forward tests compare logits, hidden states, masks, boxes, decoded text, or task outputs.
- Slow tests may be marked slow but must be runnable with `RUN_SLOW=1`.
- Targeted check example: `RUN_SLOW=1 pytest tests/models/<name>/test_modeling_<name>.py -xvs`.

## Output Format

Findings only. Do not list passing items.

```text
--- Deep Review: PR #<number> ---

SUMMARY:
<2-4 sentences: what changed and the overall risk>

DIMENSIONS:
- D<k> <slug> — findings: F<i>, ... | clean: <evidence> | (collapsed) Not triggered: D<i>, D<j> (<reason>)

REVIEWER REMARKS:
- <path:line> <reviewer> — <one-line remark> — STATUS: addressed | outstanding

FINDINGS:
FINDING F<k>
FILE <path> LINE <n or hunk>
SEVERITY: error|warning|discussion
CATEGORY: tests|decorators|flags|generic-layers|conversion|processing|modular|kernels|integrations|fusion|docs|logic|policy
CODE: `<exact line from the file, copied verbatim>`
NOTE: <one precise sentence>

SUGGESTED CHECKS:
- <only commands that materially validate the risk>

VERDICT: Approve|Request changes|Needs discussion|Blocked by policy
REASON: <one sentence>
```

Present the results in reading order — the order a reviewer scrolling the GitHub *Files changed* tab encounters the code: sort the diff-derived `F*` findings by file path (alphabetical, as GitHub orders changed files), then by line number within a file. Assign the stable ids `F1, F2, …` after sorting, so `F1` is the first finding met while scrolling. Severity does not drive ordering — it stays on each finding, and the `SUMMARY:` and `REASON:` lines name the highest-severity ids so they are not lost mid-list. Order outstanding `REVIEWER REMARKS:` rows and symbol-ledger rows by the same path+line key. File-wide systemic findings from the Review pipeline keep their `Fsys<k>` ids in the same `FINDINGS:` block and are listed first, before the diff-derived `F*`, so the systemic assessment leads; they carry no line anchor and are exempt from the sort. Every cross-reference to a finding — from a `REVIEWER REMARKS:` row ("See FINDINGS F4"), from a symbol-ledger row, or from the summary — uses the `F<k>` id, never a prose description ("the attention finding") or an unanchored number. An id referenced anywhere must exist in the `FINDINGS:` block; an unreferenced id is fine.

For local branches, use `--- Deep Review: BRANCH <name> ---`. A local branch has no reviewer remarks; omit the `REVIEWER REMARKS:` block.

List only outstanding remarks in `REVIEWER REMARKS:`, plus a one-line count of addressed ones. An outstanding remark the review independently confirms also gets a normal `FINDINGS` entry referencing the reviewer.

If there are no findings, state that. Mention residual test risk only if real.

## Output File

Write the review to a file at the repository root, never to stdout only.

- For a PR: `AUTOREVIEW_PR_<NUMBER>.md` (e.g. `AUTOREVIEW_PR_45919.md`).
- For a local branch: `AUTOREVIEW_BRANCH_<branch-name>.md` (e.g. `AUTOREVIEW_BRANCH_update-docs.md`).

Do not append author, model, or date suffixes. Do not version with `_v2`. Overwrite the file on re-review.
