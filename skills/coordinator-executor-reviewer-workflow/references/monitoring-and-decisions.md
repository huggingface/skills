# Monitoring and decision examples

These examples apply across task domains. They illustrate coordination decisions, not a mandatory sequence of deliverables. Cadences are defaults, not deadlines for producing a result. User and host instructions take precedence.

## Dispatch an outcome

> Complete the assigned deliverable using the agreed inputs and constraints. Acceptance requires all requested elements, checked supporting evidence, and explicit unresolved assumptions. Own the specified part of the work; the reviewer will inspect a stable version. Report at natural milestones or when genuinely blocked. Take the time needed for correctness. If context becomes tight, preserve the current result, remaining criteria, and resume instructions. Do not substitute a progress note for the deliverable.

Agree on suitable checkpoints for the work. For multi-minute tasks, a checkpoint every 5–10 minutes can be reasonable when the worker can report safely. Existing progress indicators may be enough for long automated operations. Do not force minute-by-minute reports from a worker doing concentrated thinking. The coordinator can still update the user using passive evidence.

## Progress to the user

Include the current phase, actual owner/review state, verified changes, remaining uncertainty, coordinator judgment, and next decision. Give estimates only when supported.

Examples:

> 执行者已完成初稿，正在核查两处事实来源；审查者已准备验收清单，最终审查尚未开始。目前没有需要你决策的异常，我会等材料齐备后交审。

> 审查正在核对计算依据，自上次更新以来没有新的结论。任务状态仍显示运行中，尚未超过约定检查点，我继续等待证据。

> 本次通过仅覆盖需求清单，交付方案和可行性核查仍未完成。它们仍是当前目标的必做项，接下来继续推进。

A user update does not require a new request to the worker. Never claim background monitoring in a final answer unless a real persistent monitor exists and has been verified.

## Monitoring decisions

| Observation | Coordinator action |
|---|---|
| Worker active, evidence advancing | Monitor passively and update the user; leave the worker uninterrupted. |
| No visible process while a worker is thinking or editing | Allow work within the checkpoint window; lack of a PID is not proof of inactivity. |
| An agreed checkpoint passes with no relevant output | Check state and evidence, then send one targeted inquiry if needed. |
| An inquiry is pending within its response window | Wait or do independent work; do not repeat the inquiry. |
| Worker finishes with only a note instead of the assigned result | Record unmet criteria and resume or reassign the actual remaining work. |
| All workers idle while required work remains | Restore execution or use authorized fallback; do not wait for nonexistent future progress. |
| Verified threat to data or the working environment | Safely pause affected activity, preserve evidence, and explain the reason. |
| A required external input is unavailable | Finish safe independent preparation, identify the dependency, and ask only for what is needed. |
| Material unexpected conflict outside the agreed scope | Pause affected work, explain impact and options, and yield for user judgment. |
| Next action requires new authorization | Prepare a reviewable proposal, pause dependent actions, and await explicit approval. |

A targeted inquiry:

> 约定的检查点已过去，当前未观察到新进展。请在方便的工作边界说明正在做什么、是否有阻塞、下一份证据是什么；保持原验收要求，不必为回复提前收尾。

Avoid “马上给结论”, “这轮必须完成”, “快速 PASS”, or “时间不够就先交报告” merely because the coordinator wants progress. An actual user deadline may require discussing tradeoffs; it does not authorize hiding incomplete checks.

## Route findings, not verdict words

These labels are not session commands. The coordinator remains responsible for the whole objective after routing the finding. Append the routed action to the open work list and continue until that list is empty or a real decision boundary is reached.

- `PASS`: verify scope and version, then continue the next required dependency if one exists.
- `PASS_WITH_CONDITIONS`: assign each condition an owner and evidence requirement. Only continue work that does not rely on unresolved blocking conditions.
- `FAIL_NEEDS_REPAIR`: identify the unmet requirement, cause, and concrete correction.
- `HOLD`: identify the reason. Route a defect to repair, missing evidence to verification, an external dependency to a documented wait, and a needed user decision to safe pause and consultation. Do not rework a correct deliverable merely because approval has not arrived.
- `STOP`: determine what the coordinator can resolve within authorization and what actually requires user input.

For a reviewer message that ends with a verdict, use this response sequence before yielding: acknowledge the reviewed scope and version, record every condition or finding, assign the next owner, dispatch or resume the next executable action, and report the remaining checklist. A final answer is allowed only after this sequence finds no mandatory item left. “Reviewer returned PASS” is therefore progress evidence, not a completion reason.

A reviewer may disagree with the coordinator. Do not pressure them to soften findings. A verdict has no value without evidence matching the claimed scope.

## Repeated repairs

After repeated substantive repair cycles, compare the actual work with the authorized goal and inspect why findings persist. The default checkpoints in the main skill trigger a diagnosis, not a demand to finish immediately.

Example of continuing: two reviews find inconsistent totals. The coordinator discovers that workers used different input versions, freezes the correct shared input, and schedules reconciliation again. The goal and authorization remain intact; report the correction and continue.

Example of consulting the user: successive plan revisions show the requested scope cannot fit the agreed budget without removing a mandatory requirement. Preserve the analysis, pause dependent commitments, and ask the user to choose the scope/budget tradeoff. Do not silently redefine success.

Example of healthy iteration: each review resolves prior issues and reveals a narrower edge case; the result remains aligned with the goal and within agreed costs. Continue with evidence-based checkpoints rather than stopping merely because three cycles have occurred.

## Avoid nominal progress

Keep one acceptance checklist per meaningful phase. Revisions update it rather than disguising unfinished work under new phase numbers. Verification should fit the deliverable.

Examples of inadequate evidence across domains:

- A summary claims every requested topic is covered, but a required section is missing.
- A numerical conclusion has no traceable inputs or reconciliation.
- A plan lists milestones but omits a necessary dependency or exceeds the agreed budget.
- A design looks complete but has not been checked against the stated user requirements.
- A component test is used as proof that the complete software workflow works.
- A small, unrepresentative sample is used to support a universal conclusion.
- The author labels their own second pass as independent review.

These require targeted correction or qualification even if a superficial check passes. Do not mechanically require every type of evidence for every task.

## Handoff and resumption

Record the authoritative task references and their precedence, verified facts separately from earlier claims, current owners, last observed state, evidence versions, authorization, unresolved criteria, and next action.

On resumption, inspect current state: other workers may have changed the deliverable or plan. Preserve their work and do not rely on stale approval. Retain any remaining authorized deliverables in the work list; successful completion of one phase does not complete the entire objective. If the agreed objective is already met, do not invent a downstream workflow.
