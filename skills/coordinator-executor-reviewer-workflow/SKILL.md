---
name: coordinator-executor-reviewer-workflow
description: Coordinate tasks through a coordinator, executor, and reviewer across any domain. Use when the user explicitly requests this role framework, independent review, or complex delegated work that needs sustained coordination and acceptance decisions. Apply to technical and nontechnical work; adapt verification to the task. Do not trigger a multi-agent workflow merely because an ordinary task has several steps.
---

# Coordinator Executor Reviewer Workflow

## Purpose and Scope

Use three distinct responsibilities to carry an authorized task to a verified outcome:

- **Coordinator:** owns the overall objective, scope, dependencies, monitoring, user communication, and continuation decisions.
- **Executor:** produces the assigned deliverable and evidence that it meets its requirements.
- **Reviewer:** independently checks the deliverable against those requirements, reports findings, and recommends next work.

This framework is domain-neutral. It applies to writing, analysis, planning, design, administrative work, software, and other tasks. It does not prescribe a particular project, roadmap, technology, experiment, or downstream deliverable. Domain instructions come from the actual task and applicable specialist skills.

Scale the ceremony to the task. A short assignment can use one deliverable and a concise review; a complex objective may need several phases. Applying the framework does not require a repository, shell process, unit tests, or a separate document for every step. Follow the user's choice of agents, people, or self-execution; distinguish self-review from independent review honestly.

### Choose the smallest sufficient execution mode

- **Lightweight:** for a short, low-risk task with no independent-approval requirement, one worker may execute and perform an explicitly labelled self-review. Use a compact task record rather than separate phase documents.
- **Independent review:** retain a separate reviewer when the user or acceptance contract requires independence, or when the consequence of an unnoticed error justifies it.
- **Parallel execution:** add workers only for bounded work that can proceed independently with clear ownership. Do not create three agents merely to mirror three responsibilities.

The mode is a coordination choice, not permission to weaken acceptance criteria. If independence is required but unavailable, preserve that gap and follow the authorized fallback; never relabel self-review as independent approval.

## Establish the Task Contract

Identify the user's intended outcome, existing authorization, constraints, inputs, and definition of done. Read applicable briefs, plans, standards, prior decisions, and evidence. Do not demand unrelated policies or invent missing approval gates.

For substantial work, maintain a compact coordinator-owned plan in an appropriate durable location. If no storage is available, keep an explicit task record in the conversation and state its persistence limits. The plan should contain:

1. Objective and non-goals.
2. Authoritative instructions and input references.
3. Known facts, assumptions, and unresolved questions.
4. Deliverables, dependencies, owners, and acceptance criteria.
5. Suitable verification methods and evidence requirements.
6. Authorization boundaries and conditions for pausing.
7. Remaining authorized work and closure criteria.

An existing roadmap or mainline may serve as this plan, but one is not a prerequisite for every task. Record its exact reference and precedence when applicable; do not guess authority from filenames.

No role may invent a new route or expand the objective beyond existing authorization. Resolve routine implementation choices within scope. When a material requirement is unclear, pause only dependent work and ask the coordinator to resolve it from the existing instructions before requesting user input.

## Role Responsibilities

### Coordinator

- Define bounded outcomes with enough scope to deliver something verifiable.
- Assign the executor the relevant inputs, constraints, ownership, acceptance criteria, and expected evidence.
- Give the reviewer the same task contract and a clear review brief.
- Confirm assignments were accepted; retain ownership through execution, review, repair, and closure.
- Monitor actual task state and keep the user informed without pressuring workers for premature conclusions.
- Inspect delivered evidence, assess review conditions, and decide to continue, repair, pause, or close.
- Preserve the whole authorized objective. Finishing a subtask does not cancel remaining required work; equally, do not invent additional work after the user's objective is met.

### Executor

- Understand the assigned outcome and relevant requirements before acting.
- Work within the assignment, avoid unrelated changes, and preserve others' work.
- Collect suitable evidence and perform the required verification.
- Report what is complete, incomplete, changed, uncertain, or blocked.
- Raise material uncertainty promptly while continuing unaffected authorized work.
- Do not substitute a plan or limitation note for a requested deliverable, or shorten verification to satisfy a coordinator message deadline.

### Reviewer

- Inspect the actual deliverable and supporting evidence, not just the executor's summary.
- Check requirements, completeness, correctness, boundary cases, and the limits of the evidence as appropriate to the task.
- Tie findings to the reviewed deliverable version and the method used to check it.
- Classify blocking and nonblocking findings; state missing evidence and recommended repairs.
- Return a verdict with its exact scope and conditions. The coordinator owns routing decisions.
- Retain independent judgment; do not soften findings merely to accelerate progress.
- Do not change the deliverable being reviewed and then call approval of those changes independent.

## Phase Size and Completion

A useful phase has one primary outcome, defined ownership, explicit requirements, a deliverable, and a reviewable acceptance decision. It may cover a document section, a reconciled dataset, a design decision, a working feature, or another task-appropriate unit.

Avoid both vague assignments such as “finish everything” and artificial micro-phases that only rename or document unfinished work. Keep unresolved criteria within the current phase until fulfilled or explicitly revised within authorization.

Interpret service states such as `completed` according to the host's documented semantics. A terminal service state alone does not establish that the task's acceptance criteria were met. A preliminary analysis or passing narrow check proves only the scope it actually covers.

## Monitoring Without Deadline Pressure

Read [Monitoring and decision examples](references/monitoring-and-decisions.md) when managing a live task or recovering stalled work.

Agree on evidence milestones and a reasonable silence window at dispatch. A milestone is a natural deliverable or checkpoint, not a demand to finish in the next message. Completion depends on acceptance criteria, not a coordinator reply deadline. Context pressure calls for a truthful handoff, not omitted verification.

Separate three cadences:

- **User updates:** provide concise commentary at the host's required interval (normally within 60 seconds during active work) and on material events. Explain verified progress, uncertainty, current judgment, and the next decision. Updating the user does not require another message to a worker.
- **Passive monitoring:** use available status, mailbox, deliverables, logs, and resource information when relevant. Wait between checks; avoid busy polling. Use bounded waits so the user can steer ongoing work.
- **Worker contact:** send new evidence, user steering, a scope correction, a genuine dependency, or one targeted liveness inquiry after an agreed checkpoint is missed. Do not repeatedly demand final reports, reduced verification, or a quick PASS.

Quiet output is not proof of a hang. Reasoning, reading, and editing may produce no visible process or new file. Conversely, a PID, `running` label, timestamp, or unrelated successful check does not prove substantive progress. Correlate status with relevant evidence over time. Do not start irrelevant activity merely to display progress.

When an inquiry is pending, allow a reasonable response window and do useful independent work. Intervene immediately for user steering, a verified safety/resource problem, unauthorized scope drift, or conflicting work. Document the reason. Resource limits protect the working environment; they are not delivery deadlines.

## Dispatch-to-Closure Loop

### Coordinator session lifetime

Treat the coordinator session as open for the entire authorized objective. A worker's `PASS`, `PASS_WITH_CONDITIONS`, `HOLD`, `FAIL_NEEDS_REPAIR`, `STOP`, `complete`, or `idle` message is an event about that worker or reviewed version; it is never, by itself, an instruction to end the coordinator session. Translate the event into a decision, update the phase record, and inspect the remaining acceptance checklist.

After every worker or reviewer event, perform this continuation check:

1. Is the assigned deliverable present and reviewed at a named version?
2. Which mandatory criteria, dependencies, repairs, and reviews remain open?
3. Is there an active worker, a resumable process, a safe reassignment, or an authorized self-review path for the next item?
4. Is the overall objective complete, or is there a genuine external/user decision boundary?

If required work remains executable, continue monitoring and dispatch the next action in the same turn. If a worker says `STOP`, determine whether it means “stop this attempt,” “stop this phase,” or “stop the whole objective”; only the last can close the objective, and only when it is authorized and evidenced. End the coordinator session only after the Closure conditions below are satisfied, or when the Unexpected Events section requires yielding to the user. Do not emit a final completion report merely because the latest event says `PASS` or `HOLD`.

Keep a compact phase record: objective, current owner, state, last observation time, evidence references, open findings, and next action. Update it at meaningful transitions; routine polls need not generate new documents.

Use explicit states such as `ready`, `executing`, `awaiting_review`, `reviewing`, `repair_required`, `verified`, `awaiting_user`, `blocked_external`, and `closed`. These states differ from service status and review verdicts.

1. Dispatch a bounded outcome and confirm acceptance. Do not report rejected work as running.
2. Monitor, communicate, and incorporate user steering during execution. If no relevant worker exists, resume/reassign work or use authorized fallback; do not wait for nonexistent future output.
3. On completion, inspect deliverables against acceptance criteria and retain unmet items.
4. Review a stable version. The reviewer may prepare while execution proceeds but cannot approve unseen later work. Avoid conflicting edits and re-review affected evidence after changes.
5. Route by finding and dependency: `FAIL_NEEDS_REPAIR` means correct the defect; `HOLD` requires identifying whether the need is repair, missing verification, external input, or a user decision; `PASS_WITH_CONDITIONS` requires assessing each condition; `PASS` permits the next authorized dependency. Do not redo correct work while waiting for an external approval. None automatically closes the overall objective.
6. Continue while required work remains executable. When continuation is authorized, dispatches and phase results belong in progress messages, not premature final answers.

Before a final answer, reconcile the whole authorized scope with verified evidence and outstanding tasks. End on completion, explicit user pause/handoff, a material unexpected event requiring user judgment, or a genuine confirmation/authorization/external dependency. Attempt routine authorized repairs and alternatives first.

If the host actually forces interruption, preserve a truthful handoff. Do not invent a time-window limit or promise monitoring after the turn ends without a verified persistent monitor.

### Agent Lifecycle and Fallback

Use only capabilities the host actually exposes. If it has no agents, progress channel, wait operation, or persistent execution, use the available equivalent and state the limitation. Do not invent tool names or promise unattended monitoring. Host and user instructions take precedence over example cadences in this skill.

When agents are used, prefer reusing suitable existing workers through a tool that actually starts a new turn. A plain message may not resume an idle agent. `interrupt` stops activity; it does not imply thread deletion or slot reclamation. Use close/release only if available and verify the result.

A thread-limit error does not establish why resources were not reclaimed. Try reuse rather than repeatedly spawning or interrupting completed agents. If it also fails, apply the user's authorized fallback or report the actual external dependency while continuing independent work. Do not spin on unchanged errors.

Label author-reviewed work **self-review**, never “independent self-review.” Changing role names or making a second pass does not satisfy independent approval. Any final acceptance or external use follows the task's actual requirements; this skill invents no domain-specific eligibility rules.

## Context and Token Economy

Reduce repeated transmission and redundant work, not necessary evidence or verification:

- Dispatch a **minimum sufficient task packet**: outcome, authorization/constraints, acceptance criteria, input versions and references, owned scope, open findings, expected deliverable and checkpoint. Do not fork the full conversation by default.
- Keep one authoritative task/phase record. After the first packet, send only changed facts, new evidence and unresolved findings. Preserve access to original sources; a summary is not a substitute for review evidence.
- Read references and specialist instructions only when relevant to the current role. Reuse already-read, unchanged instructions; re-read when their version or applicability changes.
- Prefer event notifications and targeted status checks. Limit tool output to the evidence needed for the current decision, while preserving complete logs in durable storage when required.
- Re-review changed work, previous blocking findings and affected dependencies. Expand the review when shared inputs, interfaces, assumptions or uncertain impact invalidate prior evidence. Do not blindly repeat all checks, and do not use “diff only” to skip cross-cutting requirements.
- Track available token/call/time usage at meaningful checkpoints when cost matters. Treat a worsening budget trend as a reason to reassess duplication, task split or approach. If completion requires a new budget or scope decision, consult the user; never silently drop acceptance criteria or manufacture completion.

Do not impose fixed short report limits that hide uncertainty, eliminate required independent review, or cap repair attempts merely to save tokens. Actual savings and quality must be measured together; byte or word counts are not exact billing-token counts.

## Evidence Integrity

Acceptance criteria are requirements to verify, not obstacles to disable. Investigate failed checks using actual inputs and outputs. Do not remove required checks, insert unsupported defaults, hide errors, or relabel incomplete deliverables merely to obtain a positive verdict. A genuinely incorrect requirement needs a justified correction within authorization and evidence that the new check distinguishes valid from invalid outcomes.

Choose verification that fits the work: source checking for factual claims, reconciliation for calculations, coverage and consistency checks for documents, feasibility checks for plans, functional tests for software, or other relevant methods. Do not require code tests for non-code tasks. A tool's successful exit or an executor's confidence is not sufficient evidence on its own.

The evidence must match the claim's scope and conditions. Do not generalize a narrow sample or isolated component result into complete success. Distinguish observations from assumptions, estimates from measurements, and verified findings from recommendations. Record meaningful limitations.

If later findings invalidate earlier acceptance claims, mark affected evidence superseded/invalid in the task record and inform the user. Preserve provenance; do not silently reuse stale proof.

## Repeated Repairs and Alignment Review

Repeated repairs are a signal to reassess the diagnosis and direction, not a reason to pressure workers, weaken acceptance criteria, or automatically abandon the task. Count substantive repair attempts against the same outcome, not messages or minor edits. Renaming a phase does not reset its unresolved findings.

Unless the task specifies different checkpoints, reassess when the same blocking finding survives two completed repair-and-review cycles, or a phase reaches three substantive repair cycles. These are default diagnostic triggers, not delivery deadlines or a maximum number of attempts. Reassess sooner if new evidence contradicts the plan; explain a different cadence when the task calls for it.

Before another repair, compare the current outcome and approach with the authoritative task plan. Check:

- Does the work still serve the user's objective and stay within authorized scope?
- Is the root cause supported by evidence, or are repairs only addressing symptoms?
- Are requirements and review findings consistent, or has the acceptance target been moving?
- Do successive attempts show measurable progress, or repeat the same failure?
- Is the phase poorly bounded, missing a dependency, or affected by conflicting work?
- Are further changes increasing cost, complexity, or risk beyond the agreed limits?

Record the diagnosis, evidence, revised next action, and next verification checkpoint in the phase record; share the material conclusion with the user. For an in-scope correction with a credible path forward, adjust the approach or assignment and continue without asking for redundant authorization. Useful progress can justify further repair cycles.

If reassessment finds a material departure from the agreed objective, requires new authorization or changed constraints/commitments, or repeated evidence leaves no credible in-scope path, safely pause affected work and yield for user judgment under the next section. Explain what has been tried, what was learned, the unresolved assumption, and the choices requiring a decision. Do not ask merely because a counter reached a threshold, and do not keep repeating an ineffective repair to avoid admitting a dead end.

## Unexpected Events and User Decisions

When a material unexpected event falls outside the agreed repair/risk envelope, or a next action genuinely needs user confirmation or authorization, pause dependent work. Examples include possible loss of important information, conflicting authoritative instructions, new costs or commitments beyond agreed bounds, or findings requiring a substantive change of objective or approach.

Ordinary verification failures, anticipated repair cycles, normal worker silence, and complexity alone are not reasons to seek renewed permission.

1. Bring affected work to a safe pause using the supported mechanisms. Preserve evidence and recoverable state. Verify and report what is paused or still active; state any inability to pause safely.
2. Complete safe preparation needed for a concrete, reviewable proposal. Do not perform the dependent action first or rush workers to finish because a pause is required.
3. Yield the turn with what happened, verified impact and uncertainty, a recommended next action, material alternatives, and the exact confirmation needed. Identify the restriction or explain why the event exceeds the agreed envelope.
4. Wait for the user's explicit reply before resuming dependent actions. Time, silence, and default options are not approval. Existing authorization and preferences remain valid; do not ask again for covered actions.
5. Record the user's decision and resume from the preserved state.

At this boundary, ending the turn to consult the user is correct. Continuous execution does not authorize bypassing decisions the user must make.

## Lightweight Report Templates

Adapt length and medium to the task. Small tasks may combine these fields in short paragraphs; use a durable report for complex or long-running work. Do not create empty sections or additional approval gates just to fill a template.

### Execution report

- Assignment, requirements, and input references.
- Deliverable and what changed.
- Verification performed, evidence references, and reviewed version.
- Acceptance criteria met and still unmet.
- Issues, assumptions, deviations, and recommendation for review.

### Review and next-work recommendation

- Verdict: `PASS`, `PASS_WITH_CONDITIONS`, `HOLD`, `FAIL_NEEDS_REPAIR`, or `STOP`.
- Reason and next action: defect repair, missing verification, external dependency, user decision, or next authorized work.
- Reviewed scope/version and evidence checked.
- Findings with severity, missing evidence, and limitations.
- For each condition: owner, required verification, and whether it blocks dependent work.
- Recommended repair or next authorized step; an actual user decision if necessary.

A failing review should yield actionable findings, not a vague instruction to “try again.” Keep those findings in the existing phase record where practical.

## Closure and Handoff

Close only when all mandatory criteria have verified evidence, blocking findings are resolved (or the user explicitly narrows the objective), and no required task or review remains unaccounted for. Nonblocking deferrals need a rationale, owner, and verification plan; they cannot hide unmet mandatory requirements.

The final report states completed work, evidence, remaining limitations or authorized deferrals, and any actual follow-up within the agreed scope. Do not turn optional suggestions into new mandatory tasks.

For handoff, record authoritative task references, remaining deliverables, accepted authorization, verified facts versus unverified claims, active workers and their last observed state, evidence versions, open findings, and the next executable action. On resumption, inspect the current state before acting; other workers may have changed it.

## Interaction With Domain Skills

Use this skill for coordination and an appropriate specialist skill for substance when helpful. Let the task determine standards, tools, verification, and deliverables. This framework does not dictate those choices or a fixed downstream workflow.
