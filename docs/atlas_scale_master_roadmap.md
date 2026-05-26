# Atlas Automation Master Plan

## Canonical status

This file is the single human-readable source of truth for Atlas automation planning.

- Completed automation PR: PR-ATLAS-SCALE-150
- Current automation track: PR-ATLAS-SCALE-151
- Next automation track: PR-ATLAS-SCALE-151
- Current runtime level: level_4_self_improvement_platform
- Target runtime level: level_4_self_improvement_platform
- Final goal: fully_autonomous_code_agent
- Self-improvement goal: self_improving_codeagentpersonal_kasanecore
- Backend workflow_state remains authoritative.
- Vue remains display-only and non-authoritative.
- `ui.html` remains the default root UI; Atlas Next is available as an embedded child view / explicit route, not the default root.
- Post-Level-4 full automation, self-recovery, and conversational UX plan: `docs/atlas_full_automation_self_recovery_ux_plan.md`.

Machine-readable phase and anti-drift rules are recorded in `docs/atlas_automation_phase_manifest.json`.
Execution readiness policy is recorded in `docs/atlas_autonomous_execution_readiness_policy.md`.

## Consolidation decision

The previous roadmap state duplicated active PR pointers across multiple files. This made code-agent tasks drift by updating several similar documents with slightly different current/next PR text.

Canonical planning is now consolidated as follows:

- `docs/atlas_scale_master_roadmap.md`: canonical human roadmap and PR-by-PR execution plan.
- `docs/atlas_autonomous_execution_readiness_policy.md`: canonical safety and level advancement policy.
- `docs/atlas_automation_phase_manifest.json`: machine-readable current phase, goals, forbidden drift classes, and PR plan.
- `docs/atlas_full_automation_self_recovery_ux_plan.md`: post-Level-4 extension plan for safety profiles, non-LLM recovery, candidate workspaces, and conversational Atlas UX.

The following redundant planning files are removed from the active docs set:

- `docs/atlas_development_handoff.md`
- `docs/atlas_thinui_readiness.md`
- `docs/atlas_vue_migration_plan.md`

Future PRs must not reintroduce duplicated active/current/next automation pointers in replacement files. If a handoff summary is required, it must reference this master plan instead of copying the PR table.

## Completed phase: Readiness Metadata Review Phase

SCALE-100 through SCALE-112 are complete and are now closed as the Readiness Metadata Review Phase.

This phase delivered local-only, display-only operator review capabilities: snapshot comparison, local history, import/export, diff view, filtering/grouping, export/copy, annotations, bookmarks, labels, label filtering, label export/import, and label conflict resolution.

This phase intentionally did not add execution capability. At that time runtime remained level_0_manual_only, Level-1/autonomous execution remained disabled, and Vue remained non-authoritative.

## Current phase: Conversational Atlas UX

SCALE-113 through SCALE-150 moved Atlas from Level-1 preparation through the patch, branch, draft PR, bounded-loop policy, bounded retry metadata, explicit Level-2 checkpoint, Level-3 autonomous implementation loop candidate, self-improvement proposal mode, strict self-modification risk classifier, self-improvement patch preview, self-improvement dry-run verification planning, one manually approved self-improvement patch apply, one manually approved self-improvement draft PR creation through an injected client, the explicit Level-4 self-improvement platform checkpoint, backend-owned automation safety profile framework, external recovery supervisor foundation, candidate workspace manager foundation, and boot self-diagnosis/stable checkpoint foundation. SCALE-151 is now the active next PR and must introduce only a buildless conversational Atlas shell contract with work target mode selector and no npm/Vite build dependency, autonomous loop, stable runtime mutation, execution authority, direct merge, remote push, self-apply, or Vue authority.

### Direction lock

- SCALE-114 completed: advisory readiness rollup and gate evidence summary captured (advisory-only, no execution enablement).
- SCALE-115 completed: dry-run artifact schema v1 added as schema-only metadata infrastructure, no execution enablement.
- SCALE-116 completed: verification allowlist resolver added as metadata-only resolver, no command execution.
- SCALE-117 completed: dry-run-only backend endpoint skeleton added as non-mutating metadata-only endpoint, no execution enablement.
- SCALE-118 completed: dry-run-only result artifact capture added under resolved data_root, no project mutation or execution enablement.
- SCALE-119 completed: approval token backend contract added as digest-only metadata, no execution or autonomous authorization.
- SCALE-120 completed: Vue dry-run result viewer added as display-only backend-owned metadata view, no dry-run start or execution capability.
- SCALE-121 completed: disabled single allowlisted command runner contract added as default-disabled metadata, no command execution.
- SCALE-122 completed: execution artifact capture v1 schema added as one-action metadata capture, no loop or execution enablement.
- SCALE-123 completed: stop / kill-switch runtime integration added as metadata-only continuation blocking, no process kill or execution enablement.
- SCALE-124 completed: rollback readiness verification added as verify-only metadata, no automatic rollback or restore.
- SCALE-125 completed: Level-1 guarded single-step endpoint contract added as dry-run and approval gated metadata.
- SCALE-126 completed: Vue guarded execution review panel added as display-only metadata review; Vue remains non-authoritative and cannot approve, execute, apply, verify, rollback, retry, or continue.
- SCALE-127 completed: explicit Level-1 runtime transition checkpoint added. Runtime policy became level_1_guarded_single_step for one low-risk allowlisted action after dry-run evidence and explicit approval; autonomous loop, rollback/restore automation, remote git push, and Vue authority remained disabled.
- SCALE-128 completed: metadata-only patch proposal generator added. It records proposed target files, rationale, questions, and acceptance criteria without generating diff text, creating patch transactions, applying patches, using safe_apply, running git, or enabling autonomous execution.
- SCALE-129 completed: patch transaction preview added with rollback metadata requirement and no apply.
- SCALE-130 completed: human-approved patch apply one action added for a single low-risk transaction with snapshot requirements.
- SCALE-131 completed: local branch proposal artifact added without git mutation.
- SCALE-132 completed: approved local branch creation added as local git ref creation only, with no remote push.
- SCALE-133 completed: draft PR policy metadata added without PR creation.
- SCALE-134 completed: manually approved draft PR creation result added through an injected client.
- SCALE-135 completed: manually approved draft PR update result added through an injected update client.
- SCALE-136 completed: bounded loop policy v1 added as a policy-only artifact; loop execution and retry execution remained disabled.
- SCALE-137 completed: bounded retry and failure recovery metadata added as metadata-only policy; retry execution remained disabled.
- SCALE-138 completed: explicit Level-2 guarded bounded loop checkpoint added. Runtime policy became level_2_guarded_bounded_loop only when bounded policy, retry metadata, stop gate, verification allowlist, artifact capture, and explicit approval are present.
- SCALE-139 completed: Level-3 autonomous implementation loop candidate added. It records a draft-PR-only, single-file, bounded, low-risk candidate contract from an approved Level-2 checkpoint while keeping autonomous loop execution, automatic patch generation, automatic apply, automatic verification, direct merge, remote git push, self-modification, and Vue authority disabled.
- SCALE-140 completed: self-improvement proposal mode added. It records proposal-only intent for CodeAgentPersonal / KasaneCore self-improvement while keeping self-apply, self-modification, patch generation, patch apply, verification execution, direct merge, remote git push, and Vue authority disabled.
- SCALE-141 completed: strict self-modification risk classifier added. It records classification-only risk metadata and required next gates while keeping patch preview, self-apply, self-modification, execution, direct merge, remote git push, and Vue authority disabled.
- SCALE-142 completed: self-improvement patch preview added. It records preview-only changed-path metadata from an approved risk classification while keeping patch generation, patch apply, verification execution, self-apply, direct merge, remote git push, and Vue authority disabled.
- SCALE-143 completed: self-improvement dry-run verification added. It records allowlist-classified verification metadata from an approved patch preview while keeping command execution, verification result creation, patch apply, self-apply, direct merge, remote git push, and Vue authority disabled.
- SCALE-144 completed: self-improvement approved patch apply added. It allows one manually approved create/modify patch from a validated transaction after SCALE-143 verification, snapshot reference, rollback readiness, dry-run gate, strict gate approval, explicit approval, and exact confirmation text while keeping command execution, automatic apply, self-apply, self-modification, direct merge, remote git push, and Vue authority disabled.
- SCALE-145 completed: self-improvement draft PR creation added. It allows one manually approved injected-client draft PR result after an applied SCALE-144 artifact, branch readiness, strict gate approval, explicit approval, and exact confirmation text while keeping command execution, branch creation, remote push, automatic PR creation, PR update, self-apply, self-modification, direct merge, and Vue authority disabled.
- SCALE-146 completed: explicit Level-4 self-improvement checkpoint added. It authorizes the self-improvement platform checkpoint only after Level-3 candidate evidence, SCALE-145 draft PR evidence, strict self-improvement gates, explicit approval, and exact confirmation text while keeping autonomous execution, automatic apply, stable runtime mutation, self-apply, direct merge, remote push, and Vue authority disabled.
- SCALE-147 completed: automation safety profile framework added. It records backend-owned review_only, guarded_single_action, supervised_bounded_auto, and autonomous_dev_agent profile metadata plus a separate gated self-improvement axis while keeping actual command execution, automatic apply, stable runtime mutation, self-apply, direct merge, remote push, and Vue authority disabled.
- SCALE-148 completed: external recovery supervisor foundation added under `recovery/`. It can validate recovery manifests, read release pointers, hash files, and plan pointer switches without importing target runtime modules or performing command execution, restore, file copy, pointer switch, stable runtime mutation, direct merge, remote push, self-apply, or Vue authority.
- SCALE-149 completed: candidate workspace manager foundation added. It records target repo, candidate root, allowed/blocked paths, checkpoint and recovery references, max files, max risk, and strategy metadata without creating worktrees, copying files, applying patches, running verification, promoting candidates, mutating stable runtime, direct merge, remote push, self-apply, or Vue authority.
- SCALE-150 completed: boot self-diagnosis and stable checkpoint foundation added. It records caller-supplied stable release metadata, required boot check evidence, artifact hashes, recovery manifest reference, and candidate workspace plan reference without executing boot probes, importing app runtime, creating candidate workspaces, promoting candidates, mutating stable runtime, direct merge, remote push, self-apply, or Vue authority.

Next PRs must advance the conversational Atlas UX foundation without bypassing backend authority, safety profiles, candidate workspace requirements, recovery supervisor boundaries, boot checkpoint evidence requirements, draft-PR-only constraints, direct merge restrictions, or stable runtime mutation restrictions.

Allowed PR-B additions:

- PR-B is allowed only when a required implementation is incomplete, broken, or unsafe.
- PR-B must keep the same phase and goal as its parent PR.
- PR-B must not introduce a new feature family that delays Level-4 or post-Level-4 advancement.
- PR-B must explicitly state which parent PR acceptance criteria it fixes.

Disallowed drift:

- new local-only metadata decoration as the mainline next work
- Vue becoming authoritative
- runtime level change outside an explicit transition checkpoint PR
- unbounded retry, auto-continue, execute-all, direct merge, or self-modification before their planned PRs
- remote git push before a dedicated policy and implementation gate
- conversational Atlas UX becoming the source of truth instead of backend workflow_state
- full automation before recovery supervisor, candidate workspace, checkpoint, and promotion gates exist
- work target mode selection enabling platform self-improvement without backend gates

## Level roadmap

- Level 0: Manual only. Historical baseline. No autonomous execution.
- Level 1: Guarded single-step automation. One low-risk, allowlisted action at a time. Dry-run first. Explicit approval token required. No auto-continue.
- Level 2: Guarded bounded loop. Limited low-risk sequence. Hard bounds. Stop gate. Allowlisted verification. Captured artifacts. Human approval remains required.
- Level 3: Autonomous implementation loop candidate. Candidate contract can plan, propose, request dry-run, evaluate artifacts, prepare draft PR update metadata, record self-improvement proposals, classify self-modification risk, preview self-improvement changed paths, plan dry-run verification, perform one manually approved self-improvement patch apply, and create one manually approved self-improvement draft PR through an injected client, but command execution, automatic patch generation, automatic apply, verification execution, retry, PR updates, direct merge, self-apply, self-modification, branch push, and remote git push remain disabled until future gated PRs.
- Level 4: Self-improvement platform. Current state. Atlas may improve CodeAgentPersonal / KasaneCore itself only under strict self-modification gates, candidate workspace planning, boot self-diagnosis checkpoint metadata, draft PR only, no direct merge, no stable runtime mutation, no remote push, and no Vue authority.
- Post-Level-4 Full Automation: future explicit phase. Atlas may progress toward Codex/Claude-like autonomous coding under user-selectable safety profiles, candidate workspaces, non-LLM recovery, and conversational supervision UX. Direct merge remains forbidden unless a future explicit policy changes it.

## Conversational Atlas UX target

Atlas should move toward a simple Codex-like conversation shell while keeping backend workflow_state authoritative.

Default visible UI should contain:

- conversation transcript
- goal input
- current phase card
- next action card
- safety profile badge
- work target mode badge / selector for software development/repair versus platform self-improvement
- changed files summary
- verification summary
- recovery status
- one primary CTA

Diagnostics, raw JSON, low-level IDs, direct subsystem controls, and internal manifests must remain hidden by default and available only through explicit diagnostics mode. Vue or Atlas Next may render the shell, but must not approve, execute, apply, verify, rollback, retry, continue, authorize platform self-improvement, or become the source of truth.

Primary conversational states:

- idle
- understanding_goal
- planning
- needs_scope_confirmation
- previewing_changes
- awaiting_approval
- running_dry_run
- applying_candidate
- verifying_candidate
- promoting_candidate
- draft_pr_ready
- blocked
- recoverable_failure
- recovered

## PR-by-PR implementation plan

### Phase 1: Level-1 readiness evidence generation

| PR | Required outcome | Runtime impact | Drift check |
| --- | --- | --- | --- |
| PR-ATLAS-SCALE-113 | Consolidate master plan, remove duplicate plan docs, add phase manifest and drift validator | no runtime change | canonical plan only |
| PR-ATLAS-SCALE-114 | Advisory readiness rollup and gate evidence summary | no execution | advisory-only, not eligibility |
| PR-ATLAS-SCALE-115 | Dry-run artifact schema v1 | no execution | schema only |
| PR-ATLAS-SCALE-116 | Verification allowlist resolver | no command execution | resolver only |
| PR-ATLAS-SCALE-117 | Dry-run-only backend endpoint skeleton | no mutation | no patch apply, no git |
| PR-ATLAS-SCALE-118 | Dry-run result artifact capture | no mutation | captures real dry-run output only |
| PR-ATLAS-SCALE-119 | Approval token backend contract | no execution | token does not authorize autonomous loop |
| PR-ATLAS-SCALE-120 | UI dry-run result viewer | Vue display-only | Vue remains non-authoritative |

### Phase 2: Level-1 guarded single-step enablement

| PR | Required outcome | Runtime impact | Drift check |
| --- | --- | --- | --- |
| PR-ATLAS-SCALE-121 | Disabled single allowlisted command runner | default disabled | allowlisted only |
| PR-ATLAS-SCALE-122 | Execution artifact capture v1 | no loop | one action only |
| PR-ATLAS-SCALE-123 | Stop / kill-switch runtime integration | no auto-continue | stop blocks continuation |
| PR-ATLAS-SCALE-124 | Rollback readiness verification | no automatic rollback | verify only |
| PR-ATLAS-SCALE-125 | Level-1 guarded single-step endpoint | limited execution | dry-run + approval required |
| PR-ATLAS-SCALE-126 | UI guarded execution review panel | Vue still non-authoritative | backend executes, Vue reviews |
| PR-ATLAS-SCALE-127 | Explicit Level-1 runtime transition checkpoint | runtime may become level_1_guarded_single_step | only if all gates pass |

### Phase 3: Patch, branch, and draft PR pipeline

| PR | Required outcome | Runtime impact | Drift check |
| --- | --- | --- | --- |
| PR-ATLAS-SCALE-128 | Patch proposal generator | no apply | proposal only |
| PR-ATLAS-SCALE-129 | Patch transaction preview | no apply | rollback metadata required |
| PR-ATLAS-SCALE-130 | Human-approved patch apply one action | single mutation | snapshot required |
| PR-ATLAS-SCALE-131 | Local branch proposal artifact | no git mutation | proposal only |
| PR-ATLAS-SCALE-132 | Approved local branch creation | local git only | no remote push |
| PR-ATLAS-SCALE-133 | Draft PR policy | no PR creation | policy only |
| PR-ATLAS-SCALE-134 | Draft PR creation | remote service via injected client | draft only, no merge |
| PR-ATLAS-SCALE-135 | PR update from approved patch transaction | draft PR update only | no direct merge |

### Phase 4: Bounded autonomous loop

| PR | Required outcome | Runtime impact | Drift check |
| --- | --- | --- | --- |
| PR-ATLAS-SCALE-136 | Bounded loop policy v1 | no loop yet | hard limits only |
| PR-ATLAS-SCALE-137 | Bounded retry and failure recovery | limited retry candidate | no unbounded retry |
| PR-ATLAS-SCALE-138 | Level-2 guarded bounded loop checkpoint | runtime may advance to Level 2 | explicit transition only |
| PR-ATLAS-SCALE-139 | Level-3 autonomous implementation loop candidate | autonomous candidate | draft PR only, no direct merge |

### Phase 5: Self-improving platform

| PR | Required outcome | Runtime impact | Drift check |
| --- | --- | --- | --- |
| PR-ATLAS-SCALE-140 | Self-improvement proposal mode | no self-apply | proposal only |
| PR-ATLAS-SCALE-141 | Strict self-modification risk classifier | no execution | strict by default |
| PR-ATLAS-SCALE-142 | Self-improvement patch preview | no apply | preview only |
| PR-ATLAS-SCALE-143 | Self-improvement dry-run verification | no apply | allowlisted verification only |
| PR-ATLAS-SCALE-144 | Self-improvement approved patch apply | single approved mutation | snapshot + rollback required |
| PR-ATLAS-SCALE-145 | Self-improvement draft PR creation | draft PR only | no direct merge |
| PR-ATLAS-SCALE-146 | Level-4 self-improvement checkpoint | explicit transition | all self gates required |

### Phase 6: Post-Level-4 full automation foundation

Detailed requirements are recorded in `docs/atlas_full_automation_self_recovery_ux_plan.md`.

| PR | Required outcome | Runtime impact | Drift check |
| --- | --- | --- | --- |
| PR-ATLAS-SCALE-147 | Automation safety profile framework | no new execution | profile selection only |
| PR-ATLAS-SCALE-148 | External recovery supervisor foundation | no app dependency | recovery must not import app/ |
| PR-ATLAS-SCALE-149 | Candidate workspace manager | no stable mutation | self-improvement uses candidate only |
| PR-ATLAS-SCALE-150 | Boot self-diagnosis and stable checkpoint | no autonomous loop | startup health artifact only |

### Phase 7: Conversational Atlas UX

| PR | Required outcome | Runtime impact | Drift check |
| --- | --- | --- | --- |
| PR-ATLAS-SCALE-151 | Conversational Atlas shell contract with work target mode selector | UI/UX only | backend workflow_state remains authoritative |
| PR-ATLAS-SCALE-152 | Conversational shell implementation with backend-owned mode selector | display/supervision only | one primary CTA, no authority shift |

### Phase 8: Self-improvement candidate execution and recovery

| PR | Required outcome | Runtime impact | Drift check |
| --- | --- | --- | --- |
| PR-ATLAS-SCALE-153 | Self-improvement candidate apply | candidate mutation only | stable runtime untouched |
| PR-ATLAS-SCALE-154 | Candidate verification gate | allowlisted verification only | no promote without evidence |
| PR-ATLAS-SCALE-155 | Promotion gate and release pointer switch | controlled promotion | rollback-ready pointer required |
| PR-ATLAS-SCALE-156 | Automatic failure recovery v1 | recovery automation | no LLM or app import required |

### Phase 9: Full automation execution

| PR | Required outcome | Runtime impact | Drift check |
| --- | --- | --- | --- |
| PR-ATLAS-SCALE-157 | Autonomous loop execution v1 | bounded execution | draft PR only, no direct merge |
| PR-ATLAS-SCALE-158 | Full automation mode checkpoint | explicit transition | Safety Profile 3 gates required |
| PR-ATLAS-SCALE-159 | Self-improvement autonomous candidate loop | candidate-only self automation | no direct stable mutation |
| PR-ATLAS-SCALE-160 | Fully autonomous code agent milestone | final checkpoint | goal to draft PR E2E, no direct merge |

## Required checks for every future confirmation

When checking a PR, verify all of the following against this master plan and the actual codebase:

- Scope matches the planned PR row.
- Any PR-B only repairs the parent PR criteria.
- No deleted duplicate plan docs are recreated.
- No local-only metadata UX is added as mainline work after SCALE-113 unless explicitly approved.
- Runtime level remains unchanged unless the planned transition PR explicitly allows it.
- Backend workflow_state remains authoritative.
- Vue remains non-authoritative.
- Conversational UI does not approve, execute, apply, verify, rollback, retry, continue, authorize platform self-improvement, or become authoritative unless a future explicit policy changes it.
- No execution, mutation, patch apply, git, autonomous loop execution, direct merge, or self-modification is added before its scheduled PR.
- No full automation mode is enabled before safety profiles, recovery supervisor, candidate workspace, boot checkpoints, and promotion gates exist.
- Tests cover the planned acceptance criteria and drift checks.
