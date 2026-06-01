# Atlas Autonomous Execution Readiness Policy

## Canonical relationship

This file is the canonical safety and level-advancement policy for Atlas automation.

The canonical implementation roadmap is `docs/atlas_scale_master_roadmap.md`.
The machine-readable phase contract is `docs/atlas_automation_phase_manifest.json`.

Do not duplicate active/current/next PR pointers in additional planning files. Any future handoff or UI migration note must link to the master roadmap instead of copying its PR table.

## Profile-dependent runtime model

Atlas runtime level is profile-dependent: it is resolved from the selected automation profile rather than pinned to a single fixed level (see `runtime_level_by_profile` in the phase manifest and the roadmap section of the same name). Defaults sit on the safe end (`review_only` → level 0, `guarded_single_action` → level 1, `supervised_bounded_auto` → level_2_to_level4 band). The `autonomous_dev_agent` profile reaches level_8_fully_autonomous_code_agent, but Level 8 full automation is bounded and only activated by an active pre-authorized envelope — selecting a profile alone never starts a loop. Even at Level 8 the prohibitions in this policy remain in force: direct merge, remote git push, self-apply, stable runtime mutation, Vue authority, arbitrary unbounded command execution, and self-modification without the self-improvement gate are all forbidden. The historical level/boundary notes below are retained as the baseline record.

## Current execution boundary

- Completed automation PR: POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY
- Current automation track: POST-SCALE-160-FASTUI-SHELL-MVP
- Next automation track: POST-SCALE-160-PRACTICAL-FULL-AUTOMATION-CHECKPOINT
- Runtime level model: profile-dependent; effective runtime level is resolved from the selected backend automation profile and envelope.
- Current level semantics: maximum backend milestone reached, not one always-on active runtime.
- Default runtime level: level_4_self_improvement_platform
- Max runtime level: level_8_fully_autonomous_code_agent
- Next level advancement checkpoint: POST-SCALE-160-PRACTICAL-FULL-AUTOMATION-CHECKPOINT
- Final goal: fully autonomous code agent
- Self-improvement goal: self-improving CodeAgentPersonal / KasaneCore platform

The current active boundary is the manifest state above. Profile selection alone never starts an autonomous loop. Bounded autonomous execution requires an active pre-authorized envelope and still preserves direct-merge, remote-push, self-apply, stable-runtime-mutation, Vue-authority, and arbitrary-unbounded-command prohibitions.

## Historical baseline after PR-ATLAS-SCALE-152

PR-ATLAS-SCALE-152 adds a buildless conversational Atlas shell model. It can turn the SCALE-151 contract into backend-owned display/supervision regions for transcript, goal input, current phase, next action, safety profile, work target selector, changed files, verification, recovery, and one primary CTA.

The conversational shell model is intentionally metadata-only and buildless. It does not require npm, Vite, Vue runtime, or Atlas Next dist assets; does not promote Atlas Next as the default root UI; and does not approve, execute, apply, verify, recover, create candidate workspaces, promote candidates, mutate the stable runtime, push branches, update PRs, merge, auto-continue, execute-all, self-apply, self-modify, or enable Vue authority.

PR-ATLAS-SCALE-128 through PR-ATLAS-SCALE-152 completed the patch proposal, patch transaction preview, approved single patch apply, local branch artifact, local branch creation, draft PR policy, manually approved draft PR creation, manually approved PR update, bounded loop policy, bounded retry/failure metadata, explicit Level-2 checkpoint, Level-3 candidate contract, self-improvement proposal mode, strict self-modification risk classifier, self-improvement patch preview, self-improvement dry-run verification planning, self-improvement approved patch apply, self-improvement draft PR creation, explicit Level-4 self-improvement checkpoint, automation safety profile framework, external recovery supervisor foundation, candidate workspace manager foundation, boot self-diagnosis/stable checkpoint foundation, buildless conversational shell contract, and buildless conversational shell model. These steps do not enable unbounded autonomous execution, execute-all, direct merge, Vue authority, automatic self-modification, self-apply to the stable runtime, branch push, or remote git push.

Self-improvement candidate apply, boot probe execution, verification execution, candidate workspace creation, autonomous loop execution, automatic recovery execution, and full automation remain disabled after PR-ATLAS-SCALE-152.

## Contract Phrase Lock

This policy does not enable unbounded autonomous execution. The historical SCALE-152 baseline was a Level 4 self-improvement platform checkpoint with proposal-only self-improvement metadata, classification-only self-modification risk metadata, preview-only self-improvement patch metadata, verification-plan-only self-improvement dry-run metadata, manually approved one-action self-improvement patch apply, manually approved injected-client self-improvement draft PR creation, checkpoint-only Level-4 authorization, backend-owned automation safety profile metadata, external recovery supervisor metadata, candidate workspace plan metadata, boot self-diagnosis checkpoint metadata, buildless conversational shell contract metadata, and buildless conversational shell model metadata. The current runtime model is profile-dependent and envelope-bounded; future PRs must explicitly move execution authority.

- Backend workflow state is authoritative.
- ThinUI remains supervision layer.
- CLI should use the same backend workflow contract.
- allowlist does not execute commands.
- recommended commands remain suggestions only.
- no arbitrary command execution.
- explicit approval is mandatory for medium/high/strict risk.
- EXECUTE ONE ACTION remains required for single-step actions.
- strict_gate always requires explicit approval.
- gate readiness does not execute automatically.
- restore plan is required and must be valid.
- restore remains manual-only.
- external recovery supervisor remains application-runtime independent.
- external recovery supervisor may produce metadata and plans only.
- candidate workspace manager may produce metadata and plans only.
- candidate workspace manager must not create worktrees, copy files, apply patches, verify, promote, or mutate stable runtime until later explicit PRs.
- boot self-diagnosis checkpoint may record stable release metadata, required check evidence, artifact hashes, recovery manifest references, and candidate workspace plan references only.
- boot self-diagnosis checkpoint must not run probes, import app runtime, execute commands, create candidate workspaces, apply patches, verify, promote, or mutate stable runtime until later explicit PRs.
- conversational shell contract and shell model may record UI/UX metadata, visible regions, conversation state, selected safety profile label, work target mode intent, and display/supervision summaries only.
- conversational shell contract and shell model must not require npm/Vite/Vue runtime, promote Atlas Next as default, approve, execute, apply, verify, recover, self-apply, self-modify, push, merge, or become authoritative.
- automatic recovery execution requires a future explicit policy PR.
- automatic rollback requires a future explicit policy PR.
- plan / intent summary, patch transaction manifest, dry-run result, execution result, verification plan, verification result, warnings and recovery instructions, and resolved data_root are required evidence classes.
- artifact capture does not create fake execution results.
- artifact capture does not create fake verification results.
- missing references are recorded explicitly.
- stop state must be visible in ThinUI/CLI.
- stop metadata does not stop real jobs or kill processes.
- self-improvement proposal, risk classifier, patch preview, dry-run verification, approved apply, draft PR creation, Level-4 checkpoint, automation safety profile, external recovery supervisor, candidate workspace manager, boot self-diagnosis checkpoint, and conversational shell modes remain backend-gated; automatic self-improvement remains disabled; automatic self-modification remains disabled; self-modification is strict-gate by default.
- Level 1: Guarded single-step automation.
- Level 2: Guarded bounded loop.
- Level 3: Autonomous implementation loop candidate.
- Level 4: Self-improvement platform checkpoint.
- execute all remains forbidden.
- auto continue remains forbidden.
- automatic safe_apply, automatic verification, automatic retry, automatic rollback, automatic recovery execution, boot probe execution, candidate workspace creation, candidate apply, promotion, and automatic patch generation remain disabled.
- no git push, no git pull, no git clone, no git fetch, no git remote, no direct merge, and no automatic PR creation.
- draft PR creation and PR update remain manually gated through dedicated backend helpers; automatic PR creation, automatic PR update, and direct merge remain forbidden.
- automation safety profiles are metadata/policy only until later execution PRs explicitly consume them.
- max actions per loop, max retries, max runtime, max files changed, and max risk level are mandatory.
- No unbounded autonomous loop.
- Auto-continue remains disabled.
- Execute-all remains forbidden.

## Non-Negotiable Safety Invariants

Current active invariants:

- backend workflow state is authoritative
- ThinUI remains supervision/display only
- direct merge remains disabled
- remote git push remains disabled
- self-apply remains disabled
- stable runtime mutation remains disabled unless a separate strict gate explicitly records evidence; the current practical track does not perform it
- Vue authority remains disabled
- arbitrary unbounded command execution remains disabled
- verification results must not be fabricated
- critical events always require user judgment, including full_auto/autonomous modes
- profile selection alone never starts an autonomous loop
- active envelopes remain bounded by max actions, max retries, max runtime, max files, max risk, allowed paths, blocked paths, and allowlisted commands

## Historical Non-Negotiable Safety Invariants After PR-ATLAS-SCALE-152

After PR-ATLAS-SCALE-152:

- runtime remains level_4_self_improvement_platform
- autonomous execution remains disabled
- external recovery supervisor foundation is metadata/plan-only
- candidate workspace manager foundation is metadata/plan-only
- boot self-diagnosis checkpoint foundation is artifact-only
- conversational shell contract and shell model are metadata-only and buildless
- conversational shell model does not require npm/Vite/Vue runtime, promote Atlas Next as default, approve, execute, apply, verify, recover, create candidate workspaces, promote candidates, mutate stable runtime, self-apply, self-modify, push, or merge
- work target mode selection does not authorize platform self-improvement without backend gates
- boot self-diagnosis checkpoint does not run probes, import app runtime, execute commands, start services, create candidate workspaces, apply patches, verify candidates, promote candidates, or mutate stable runtime
- candidate workspace manager does not create worktrees, copy workspaces, execute commands, apply patches, verify candidates, promote candidates, or mutate stable runtime
- automation safety profile selection is backend-owned metadata only
- self-improvement profile activation requires Level-4 checkpoint evidence and strict gate approval
- self-improvement platform work remains draft-PR-only until candidate execution PRs explicitly change it
- stable runtime mutation remains disabled
- self-improvement draft PR creation remains one-action and manually approved
- draft PR creation uses an injected client only
- branch creation and remote push remain disabled
- command execution remains disabled
- verification commands are not executed by the safety profile helper, recovery supervisor, candidate workspace manager, boot self-diagnosis checkpoint, or conversational shell model
- verification results are not fabricated
- automatic patch generation remains disabled
- automatic patch apply remains disabled
- self-modification remains disabled
- self-apply remains disabled
- autonomous loop execution remains disabled
- backend workflow_state remains authoritative
- Vue remains non-authoritative and display-only
- suggested commands are not executed automatically
- safe_apply remains manually gated
- automatic verification remains disabled
- automatic retry remains disabled
- automatic rollback remains disabled
- automatic recovery execution remains disabled
- candidate workspace creation remains disabled
- candidate apply remains disabled
- candidate promotion remains disabled
- execute-all remains forbidden
- auto-continue remains forbidden
- git push/pull/clone remains forbidden
- direct merge remains forbidden
- automatic PR creation and automatic PR update remain forbidden

## Completed Readiness Metadata Review Phase

SCALE-100 through SCALE-112 completed the local-only readiness metadata review phase. That phase is now closed.

Those PRs may remain as operator review tools, but they are not the mainline path to complete automation. Future mainline work must advance the canonical automation track unless the user explicitly authorizes a PR-B repair or a narrowly scoped exception.

## Readiness Gates Before Autonomous Execution

Autonomous execution remains forbidden until the relevant gates pass.

1. Snapshot / Restore Gate
   - workspace snapshot exists before mutation
   - restore is validated
   - restore proof is captured
   - snapshot manifest is stored under resolved data_root
   - no direct Path("ca_data") writes

2. Patch Transaction Gate
   - proposed changes are represented as patch transactions
   - transaction has file list, diff summary, risk class, and rollback metadata
   - transaction can be dry-run validated before apply
   - transaction artifacts are captured

3. Risk Classification Gate
   - each action has explicit risk classification
   - unknown risk is not low risk
   - runtime, launcher, Docker, execution APIs, data_root, safety docs, UI workflow state, and self-modification are strict-gate by default

4. Verification Allowlist Gate
   - verification commands must be selected from an allowlist
   - allowlist resolution alone does not execute commands
   - no broad shell, arbitrary command execution, shell metacharacters, remote git, package install, or destructive commands

5. Dry-run and Approval Gate
   - dry-run-first is mandatory
   - explicit approval token is mandatory before guarded execution
   - human approval is mandatory for medium/high/strict risk
   - self-modification requires stricter gates than ordinary repo work

6. Rollback Readiness Gate
   - rollback plan exists
   - restore plan is valid
   - snapshot manifest and rollback metadata are required
   - rollback readiness verification does not execute rollback unless a later explicit PR allows it

7. Artifact Capture Gate
   - plan, snapshot, patch transaction, rollback metadata, risk classification, verification allowlist, dry-run approval, and rollback readiness records are captured
   - dry-run, execution, verification plan, and verification result references are tracked when available
   - missing evidence is recorded explicitly and not fabricated

8. Stop / Kill Switch Gate
   - stop state is visible
   - no auto-continue after stop
   - stop blocks continuation

9. Loop Bound Gate
   - max actions, retries, runtime, files changed, risk level, verification attempts, failures, and patch transactions are bounded
   - no unbounded autonomous loop

10. Remote Git Gate
   - no git push/pull/clone before a dedicated policy and implementation gate
   - no direct merge
   - draft PR creation and PR update remain manually gated until later automation levels explicitly expand them

11. Self-Improvement Gate
   - CodeAgentPersonal / KasaneCore self-modification is stricter than ordinary repo work
   - launcher, Docker, runtime, UI, execution APIs, data_root, and policy docs are strict-gate by default
   - UI work target mode selection must not authorize self-improvement without backend profile, scope, checkpoint, candidate workspace, verification, and recovery gates

12. External Recovery Supervisor Gate
   - recovery supervisor must remain outside app runtime dependencies
   - recovery supervisor must not import app runtime, web runtime, model providers, or process execution helpers
   - recovery supervisor may only read manifests, validate metadata/hashes, and produce recovery plans until a later explicit recovery execution PR
   - pointer switches, file restores, file copies, command execution, network access, and automatic recovery remain disabled

13. Candidate Workspace Gate
   - candidate workspace manager must declare target repo, candidate root, allowed paths, blocked paths, max files, and max risk level before any candidate mutation PR
   - stable checkpoint, recovery manifest, and safety profile references are required metadata
   - candidate root must not be inside the stable target repo
   - worktree creation, copy fallback, candidate patch apply, verification, promotion, and stable runtime mutation remain disabled until later explicit PRs

14. Boot Self-Diagnosis / Stable Checkpoint Gate
   - boot self-diagnosis checkpoint must record stable release id, source commit, release pointer, artifact hashes, required check evidence, recovery manifest reference, and candidate workspace plan reference before later startup/recovery execution PRs consume it
   - boot checks are evidence references only until a future execution PR explicitly permits probe execution
   - boot self-diagnosis checkpoint must not import app runtime, start services, run commands, execute probes, create candidate workspaces, apply patches, promote candidates, switch release pointers, or mutate stable runtime

15. Conversational Shell Gate
   - conversational shell must use backend workflow_state as source of truth
   - work target mode selection is intent metadata only until future backend gates explicitly authorize more
   - default conversational shell must not require npm install, Vite build, Vue compilation, or Atlas Next dist assets
   - conversational shell must not approve, execute, apply, verify, rollback, retry, continue, authorize platform self-improvement, self-apply, direct merge, or become authoritative

## Readiness Levels

### Level 0: Manual Only

Historical baseline. No autonomous execution.

### Level 1: Guarded Single-Step Automation

One low-risk, allowlisted action at a time. Dry-run first. Explicit approval token required. No auto-continue.

### Level 2: Guarded Bounded Loop

Limited low-risk sequence with hard loop bounds, captured artifacts, allowlisted verification, stop gate, and human approval for each iteration.

### Level 3: Autonomous Implementation Loop Candidate

Candidate metadata can describe plan, patch proposal, dry-run request, artifact evaluation, draft PR update metadata, human approval requests, self-improvement proposals, self-modification risk classification, self-improvement patch preview, self-improvement dry-run verification planning, one manually approved self-improvement patch apply, one manually approved self-improvement draft PR creation through an injected client, and candidate workspace planning. It cannot execute commands, generate patches, run verification commands, retry, update PRs, push branches, merge, self-apply, self-modify, create candidate workspaces, or let Vue authorize workflow state.

### Level 4: Self-Improvement Platform Checkpoint

Current state. Atlas may prepare CodeAgentPersonal / KasaneCore self-improvement work under stricter self-modification gates, draft-PR-only boundaries, automation safety profile metadata, external recovery supervisor metadata, candidate workspace plan metadata, boot self-diagnosis checkpoint metadata, and conversational shell model metadata. It cannot directly merge, mutate the stable runtime, push branches, self-apply, self-modify, execute boot probes, execute recovery, create candidate workspaces, or enable Vue authority.

## Anti-Drift Requirements

Every future automation PR must prove the following:

- It matches the PR row in `docs/atlas_scale_master_roadmap.md`.
- It does not add another local-only readiness decoration as mainline work after SCALE-113.
- It does not recreate deleted duplicate planning files.
- It does not change runtime level before the planned transition PR.
- It does not add execution, mutation, patch apply, remote git push, autonomous loop execution, automatic PR creation, direct merge, recovery execution, boot probe execution, candidate workspace creation, candidate apply, candidate promotion, stable checkpoint promotion, or self-modification before the scheduled PR.
- PR-B changes are repair-only and point back to the parent PR acceptance criteria.

## Confirmation Checklist

When verifying a PR, report:

- implemented
- missing
- implementation defects
- over-implementation / forbidden changes
- safety
- next required instruction

This checklist must be based on actual main-branch files, manifest, tests, runtime contract, and PR diff when needed, not only the PR body.
