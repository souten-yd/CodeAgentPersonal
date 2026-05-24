# Atlas Automation Master Plan

## Canonical status

This file is the single human-readable source of truth for Atlas automation planning.

- Completed automation PR: PR-ATLAS-SCALE-114
- Current automation track: PR-ATLAS-SCALE-115
- Next automation track after this correction: PR-ATLAS-SCALE-115
- Current runtime level: level_0_manual_only
- Target runtime level: level_1_guarded_single_step
- Final goal: fully_autonomous_code_agent
- Self-improvement goal: self_improving_codeagentpersonal_kasanecore
- Backend workflow_state remains authoritative.
- Vue remains display-only and non-authoritative.
- Atlas Next defaultization is complete, but defaultization is not execution enablement.

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

## Completed phase: Readiness Metadata Review Phase

SCALE-100 through SCALE-112 are complete and are now closed as the Readiness Metadata Review Phase.

This phase delivered local-only, display-only operator review capabilities: snapshot comparison, local history, import/export, diff view, filtering/grouping, export/copy, annotations, bookmarks, labels, label filtering, label export/import, and label conflict resolution.

This phase intentionally did not add execution capability. Runtime remains level_0_manual_only, Level-1/autonomous execution remain disabled, and Vue remains non-authoritative.

## Current phase: Level-1 Advancement Preparation

SCALE-113 starts the Level-1 Advancement Preparation phase. The purpose of this phase is to move away from more local-only review UX and toward the evidence generation needed for guarded single-step automation.

### Direction lock

- SCALE-114 completed: advisory readiness rollup and gate evidence summary captured (advisory-only, no execution enablement).
Next PRs must advance Level-1 readiness evidence or the roadmap/validator itself.

They must not add another local-only diff label/bookmark/annotation UX unless explicitly approved as a PR-B drift repair or a user-requested exception.

Allowed PR-B additions:

- PR-B is allowed only when a required implementation is incomplete, broken, or unsafe.
- PR-B must keep the same phase and goal as its parent PR.
- PR-B must not introduce a new feature family that delays Level-1 advancement.
- PR-B must explicitly state which parent PR acceptance criteria it fixes.

Disallowed drift:

- new local-only metadata decoration as the mainline next work
- Vue becoming authoritative
- execution endpoint exposure before the explicit Level-1 transition PR
- mutation, patch apply, git operations, autonomous loop, or PR creation before their planned PRs
- changing runtime level before the explicit transition checkpoint

## Level roadmap

- Level 0: Manual only. Current state. No autonomous execution.
- Level 1: Guarded single-step automation. One low-risk, allowlisted action at a time. Dry-run first. Explicit approval token required. No auto-continue.
- Level 2: Guarded bounded loop. Limited low-risk sequence. Hard bounds. Stop gate. Allowlisted verification. Captured artifacts.
- Level 3: Autonomous implementation loop. Plan, patch, dry-run, apply, verify, bounded fix loop, draft PR only. No direct merge.
- Level 4: Self-improvement platform. Atlas may improve CodeAgentPersonal / KasaneCore itself under strict self-modification gates, draft PR only, no direct merge.

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
| PR-ATLAS-SCALE-134 | Draft PR creation | remote git limited | draft only, no merge |
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

## Required checks for every future confirmation

When checking a PR, verify all of the following against this master plan and the actual codebase:

- Scope matches the planned PR row.
- Any PR-B only repairs the parent PR criteria.
- No deleted duplicate plan docs are recreated.
- No local-only metadata UX is added as mainline work after SCALE-113 unless explicitly approved.
- Runtime level remains unchanged unless the planned transition PR explicitly allows it.
- Backend workflow_state remains authoritative.
- Vue remains non-authoritative.
- No execution, mutation, patch apply, git, autonomous loop, or self-modification is added before its scheduled PR.
- Tests cover the planned acceptance criteria and drift checks.

## Safety invariants

Until the explicit transition PR says otherwise:

- runtime_level remains level_0_manual_only
- Level-1 execution remains disabled
- autonomous execution remains disabled
- automatic verification remains disabled
- automatic patch generation remains disabled
- automatic patch apply remains disabled
- automatic rollback remains disabled
- automatic retry remains disabled
- execute-all remains disabled
- auto-continue remains disabled
- direct merge remains forbidden
- draft PR creation remains forbidden until the draft PR policy and creation PRs
