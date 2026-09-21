---
name: huggingface-transformers-review-pr
license: MIT
description: Review Hugging Face Transformers pull requests and local branches in fast or deep mode, covering general bug fixes, refactors, and model additions. Use when asked to review or self-review a contribution to huggingface/transformers before opening a PR or during a review round. Defaults to fast; deep provides a more thorough maintainer-style review at significantly higher token cost.
---

# Transformers PR review

Review a `huggingface/transformers` PR or local branch. Both modes cover general PRs as well as model additions; apply architecture-specific checks only when relevant to the diff.

## Choose the review mode

The user chooses `fast` or `deep`, either in ordinary language or with `MODE=fast|deep`. If no mode is specified, **default to fast** and announce that choice without delaying the review for confirmation. If the user asks for help choosing, explain the tradeoff below and let them choose.

| Mode | Use | Instructions to load |
| --- | --- | --- |
| **fast** (default) | Contributor self-review: policy and impact, reuse, API conformance, lint/type/test gates, dead code, and numerical parity where applicable. | [references/review_fast.md](references/review_fast.md) |
| **deep** | Thorough maintainer-style review: systemic analysis, reviewer-comment and symbol ledgers, two-pass verification, and coverage of 41 review dimensions. **Requires significantly more tokens but results in a higher-quality PR by identifying and verifying more issues.** | [references/deep/review_deep.md](references/deep/review_deep.md), then the supporting resources it routes to |

Load only the selected mode's instructions. Do not load the deep registry, graphs, or specialist guides during fast mode. Never automatically escalate a fast review to deep.

Examples:

```text
Use huggingface-transformers-review-pr to review my current branch.
Use huggingface-transformers-review-pr MODE=fast PR_NUMBER=45123.
Use huggingface-transformers-review-pr MODE=deep BRANCH=my-bugfix.
```

Infer the target from the request or current checkout; ask only when the target is ambiguous. A PR URL or number selects that PR. A named branch selects that branch, even if another branch is checked out. Use the PR's actual base branch, or `main` for local branches unless the user specifies otherwise. Capture the reviewed base and head commits in the report. If the user includes uncommitted changes, review those explicitly in addition to the committed diff.

## Shared execution rules

These integration rules take precedence over the mode-specific instructions where they differ:

- Read the reviewed checkout's current `AGENTS.md`, `CONTRIBUTING.md`, and PR template. Apply its actual contribution policy; do not assume contributor history or repeat a historical ban warning without verifying that it applies. Never write a human's review attestation for them.
- The review is report-only. Report fixes as recommendations; perform fixes only if the user requested them, after completing the review. Do not post comments, update PR descriptions, submit reviews, commit, or push as part of reviewing. The fast guide's instruction to paste the report means prepare text for the user.
- Preserve the user's working tree. Inspect branch/status first and use an isolated worktree when the target differs. Run mutating checks such as `make fix-repo`, `make style`, modular regeneration, and test-list generation in a disposable copy of the reviewed state. Compare generated changes as evidence; do not let an auto-fix conceal an issue in the original diff. Use check-only alternatives where the checkout provides them.
- Confirm Python imports resolve to the reviewed checkout; use `PYTHONPATH=<reviewed-tree>/src` for Python and test commands. Adapt commands and framework conventions to that checkout, verifying symbols before citing them.
- Paths such as `src/transformers/`, `docs/source/en/`, `utils/`, `CONTRIBUTING.md`, and `MIGRATION_GUIDE_V5.md` refer to the reviewed Transformers checkout. Deep resource paths (`references/`, `REVIEW_DIMENSIONS.md`, and execution graphs) resolve relative to `references/deep/review_deep.md`; they are bundled skill resources.
- Mark checks as passed, failed, not run (with reason), or not applicable (with evidence). Missing hardware, credentials, or dependencies are coverage gaps, not proof of a code defect. Do not claim READY or Approve while required validation remains incomplete.
- Distinguish review depth from PR classification. In the deep guide, `MODE=auto|new_model|generic` means **classification**, not the user's fast/deep selection; `model_refactor` is also supported. Infer classification from the diff by default, or accept `PR_KIND=auto|new_model|model_refactor|generic`.
- Deep ledger fan-out may use the host's available subagent tools when delegation is permitted. The `Workflow` tool is not a dependency. If delegation is unavailable, process the same batches sequentially and retain every ledger row and verification step. Do not relax coverage requirements.
- Write only local review reports and temporary verification artifacts. Deep mode writes the `AUTOREVIEW_PR_<NUMBER>.md` or `AUTOREVIEW_BRANCH_<branch>.md` report in the reviewed repository root; replace branch-name `/` and other filename-unsafe characters with `-`. Report access limitations and complete independent checks when possible; ask for missing information only when it blocks further review.

## Finish the review

Use the selected mode's report format. Include actual check outcomes, unresolved findings with current file/line evidence, and validation limitations. For fast reviews, use “blocking findings” and “recommended fix” rather than claiming findings were already fixed.

**At the end of every fast review**, including a blocked or incomplete one, tell the user:

> A deep review is also available with `MODE=deep`. It uses significantly more tokens but provides a more thorough review to help produce a higher-quality PR.
