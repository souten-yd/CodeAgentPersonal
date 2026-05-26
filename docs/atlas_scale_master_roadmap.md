# Atlas Automation Master Plan

## Canonical status

This file is the single human-readable source of truth for Atlas automation planning.

- Completed automation PR: PR-ATLAS-SCALE-141
- Current automation track: PR-ATLAS-SCALE-142
- Next automation track: PR-ATLAS-SCALE-142
- Current runtime level: level_3_autonomous_implementation_loop_candidate
- Target runtime level: level_3_autonomous_implementation_loop_candidate
- Final goal: fully_autonomous_code_agent
- Self-improvement goal: self_improving_codeagentpersonal_kasanecore
- Backend workflow_state remains authoritative.
- Vue remains display-only and non-authoritative.
- `ui.html` remains the default root UI; Atlas Next is available as an embedded child view / explicit route, not the default root.

Machine-readable phase and anti-drift rules are recorded in `docs/atlas_automation_phase_manifest.json`.
Execution readiness policy is recorded in `docs/atlas_autonomous_execution_readiness_policy.md`.

## Consolidation decision

The previous roadmap state duplicated active PR pointers across multiple files. This made code-agent tasks drift by updating several similar documents with slightly different current/next PR text.

Canonical planning is now consolidated as follows:

- `docs/atlas_scale_master_roadmap.md`: canonical human roadmap and PR-by-PR execution plan.
- `docs/atlas_autonomous_execution_readiness_policy.md`: canonical safety and level advancement policy.
- `docs/atlas_automation_phase_manifest.json`: machine-readable current phase, goals, forbidden drift classes, and PR plan.

The following redundant planning files are removed from the active docs set:

- `docs/atlas_development_handoff.md`
- `docs/atlas_thinui_readiness.md`
- `docs/atlas_vue_migration_plan.md`

Future PRs must not reintroduce duplicated active/current/next automation pointers in replacement files. If a handoff summary is required, it must reference this master plan instead of copying the PR table.

## Current phase: Self-Improving Platform Preparation

SCALE-113 through SCALE-141 moved Atlas from Level-1 preparation through patch/branch/draft PR policy, bounded-loop policy, Level-2 and Level-3 checkpoints, self-improvement proposal mode, and strict self-modification risk classification. SCALE-142 is now the active next PR and must introduce only self-improvement patch preview, with no apply, no self-apply, no direct merge, and no Vue authority.

### Direction lock

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
- SCALE-139 completed: Level-3 autonomous implementation loop candidate added. It records a draft-PR-only, single-file, bounded, low-risk candidate contract while keeping autonomous loop execution, automatic patch generation, automatic apply, automatic verification, direct merge, remote git push, self-modification, and Vue authority disabled.
- SCALE-140 completed: self-improvement proposal mode added. It records proposal-only intent while keeping self-apply, self-modification, patch generation, patch apply, verification execution, direct merge, remote git push, and Vue authority disabled.
- SCALE-141 completed: strict self-modification risk classifier added. It records classification-only risk metadata and required next gates while keeping patch preview, self-apply, self-modification, execution, direct merge, remote git push, and Vue authority disabled.

Next PRs must advance self-improvement patch preview without bypassing classification-only limits, proposal traceability, direct merge restrictions, or draft-PR-only constraints.

Allowed PR-B additions:

- PR-B is allowed only when a required implementation is incomplete, broken, or unsafe.
- PR-B must keep the same phase and goal as its parent PR.
- PR-B must not introduce a new feature family that delays Level-3 or Level-4 advancement.
- PR-B must explicitly state which parent PR acceptance criteria it fixes.

Disallowed drift:

- new local-only metadata decoration as the mainline next work
- Vue becoming authoritative
- runtime level change outside an explicit transition checkpoint PR
- unbounded retry, auto-continue, execute-all, direct merge, or self-modification before their planned PRs
- remote git push before a dedicated policy and implementation gate

## Level roadmap

- Level 0: Manual only. Historical baseline. No autonomous execution.
- Level 1: Guarded single-step automation. One low-risk, allowlisted action at a time. Dry-run first. Explicit approval token required. No auto-continue.
- Level 2: Guarded bounded loop. Limited low-risk sequence. Hard bounds. Stop gate. Allowlisted verification. Captured artifacts. Human approval remains required.
- Level 3: Autonomous implementation loop candidate. Current state. Candidate contract can plan, propose, request dry-run, evaluate artifacts, prepare draft PR update metadata, record self-improvement proposals, and classify self-modification risk. Execution, patch apply, verification, retry, PR updates, and direct merge remain disabled until future gated PRs.
- Level 4: Self-improvement platform. Atlas may improve CodeAgentPersonal / KasaneCore itself under strict self-modification gates, draft PR only, no direct merge.

## PR-by-PR implementation plan

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

## Required checks for every future confirmation

When checking a PR, verify all of the following against this master plan and the actual codebase:

- Scope matches the planned PR row.
- Any PR-B only repairs the parent PR criteria.
- No deleted duplicate plan docs are recreated.
- No local-only metadata UX is added as mainline work after SCALE-113 unless explicitly approved.
- Runtime level remains unchanged unless the planned transition PR explicitly allows it.
- Backend workflow_state remains authoritative.
- Vue remains non-authoritative.
- No execution, mutation, patch apply, git, autonomous loop execution, direct merge, or self-modification is added before its scheduled PR.
- Tests cover the planned acceptance criteria and drift checks.

## Safety invariants

After PR-ATLAS-SCALE-141:

- runtime_level remains level_3_autonomous_implementation_loop_candidate
- strict self-modification risk classifier is classification-only
- patch preview remains disabled until PR-ATLAS-SCALE-142
- self-modification remains disabled
- self-apply remains disabled
- automatic patch generation remains disabled
- automatic patch apply remains disabled
- automatic verification remains disabled
- autonomous loop execution remains disabled
- autonomous execution remains disabled
- execute-all remains disabled
- auto-continue remains disabled
- direct merge remains forbidden
- remote git push remains forbidden
- Vue remains non-authoritative
- draft PR creation and PR update remain manually gated through dedicated backend helpers; automatic PR creation, automatic PR update, and direct merge remain forbidden
