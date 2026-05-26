# Atlas Next Current Status

Updated after the PR-ATLAS-SCALE-156 automatic failure recovery helper.

## Completed in latest UI track
- #1390 builds `web/atlas-next` during Docker image build.
- #1391 embeds `/atlas-next/` as the Atlas mode child view while keeping `ui.html` as the root default.
- #1392 renames the Vue start surface from duplicate Create Plan wording to Start Atlas.
- #1393 adds display-only workflow stages to the right progress rail.
- #1394 adds display-only Plan Review / Approval Review / Execute Preview board.
- #1395 adds a display-only Patch Review panel.
- #1396, #1398, #1399, and #1400 carry backend-owned patch transaction preview metadata into Atlas Next display.
- #1402 through #1408 connect guarded execution preparation, gate readiness, provenance, and Start Atlas conversation flow as display-only UI.
- The read-only PlanPool item summary PR makes generated plan candidates easier to scan inside the Start Atlas result review panel.

## Completed in latest automation roadmap track
- PR-ATLAS-SCALE-129 remains planned and records patch transaction preview with rollback metadata required and no apply.
- PR-ATLAS-SCALE-130 through PR-ATLAS-SCALE-135 add the human-approved patch apply, local branch, draft PR, and PR update metadata chain without enabling autonomous execution.
- PR-ATLAS-SCALE-136 through PR-ATLAS-SCALE-139 add bounded loop policy, retry metadata, Level-2 checkpoint, and Level-3 candidate gates.
- PR-ATLAS-SCALE-140 through PR-ATLAS-SCALE-146 add the self-improvement proposal, risk, preview, dry-run, approved candidate patch apply, draft PR, and Level-4 checkpoint chain.
- PR-ATLAS-SCALE-147 adds backend-only automation safety profile metadata without enabling execution.
- PR-ATLAS-SCALE-148 adds the external `recovery/` supervisor foundation that can validate recovery manifests, read release pointers, hash files, and plan pointer switches without importing target runtime modules or executing recovery.
- PR-ATLAS-SCALE-149 adds backend-only candidate workspace planning without creating worktrees, copying files, applying patches, verifying, promoting, mutating stable runtime, pushing branches, or merging.
- PR-ATLAS-SCALE-150 adds boot self-diagnosis checkpoint metadata without running probes, importing app runtime, mutating stable runtime, creating candidate workspaces, promoting, pushing, or merging.
- PR-ATLAS-SCALE-151 and PR-ATLAS-SCALE-152 add the buildless conversational Atlas shell contract/model with backend-owned work target mode selector while keeping authority and execution disabled.
- PR-ATLAS-SCALE-153 adds backend-only candidate-workspace patch apply after strict gates; stable runtime mutation remains disabled.
- PR-ATLAS-SCALE-154 adds backend-only candidate verification gate metadata from allowlisted evidence; command execution and fabricated verification remain disabled.
- PR-ATLAS-SCALE-155 adds backend-only candidate promotion gate metadata that prepares rollback-ready release pointer switch readiness; pointer switching and stable runtime mutation remain disabled.
- PR-ATLAS-SCALE-156 adds backend-only automatic failure recovery plan metadata from a ready promotion gate and external recovery manifest; recovery execution, pointer switch execution, command execution, LLM-dependent recovery, stable runtime mutation, push, merge, self-apply, and Vue authority remain disabled.

## Current safety boundaries
- `ui.html` remains the default root UI.
- Vue remains non-authoritative for workflow eligibility.
- Current runtime level remains `level_4_self_improvement_platform`; autonomous execution remains disabled until the dedicated full automation execution PRs.
- Candidate apply is candidate-workspace-only. It may mutate the candidate root after all gates, but it must not mutate the stable target repo, self-apply to the running runtime, promote candidates, push branches, merge, or enable Vue authority.
- Candidate verification, promotion, and automatic failure recovery are backend-only metadata helpers. They may mark verification, promotion readiness, and bounded recovery-plan readiness only from prior gated artifacts and evidence, but they must not execute commands, fabricate verification, switch pointers, run recovery, or mutate stable runtime.
- External recovery supervisor use remains application-runtime-independent and bounded to manifest validation and plan-only recovery metadata.
- Work target mode selection can distinguish ordinary software development/repair from platform self-improvement intent, but it does not authorize self-improvement, self-apply, execution, direct merge, or Vue authority without later backend gates.
- Vue execution, autonomous loop execution, autonomous execution, command execution, automatic patch generation, automatic verification, automatic rollback execution, auto-continue, execute-all, direct merge, self-modification, self-apply, branch creation, remote git push, pointer switching, promotion execution, and stable runtime mutation remain disabled.
- SCALE-156 does not add a public route, add a Vue control, push a branch, create a branch, add autonomous continuation, execute retries, run verification commands, run boot probes, generate patches, update PRs, self-apply, self-modify, direct merge, perform command execution, perform recovery execution, switch release pointers, promote a candidate, mutate stable runtime, or require npm/Vite build for the default shell.

## Later UI/UX planning note
- Later conversational/FastUI work must expose a backend-owned work target mode selector for ordinary software development/repair versus platform self-improvement.
- That selector is a UI intent control only; it must not authorize self-improvement, self-apply, execution, direct merge, or Vue authority without the backend profile, scope, checkpoint, candidate workspace, verification, and recovery gates.

## Next narrow PR
- PR-ATLAS-SCALE-157: autonomous loop execution v1.
- Keep it bounded by the existing recovery, candidate workspace, verification, promotion, and safety profile metadata; do not add Vue authority, default UI promotion, unbounded execution, self-apply, remote push, arbitrary command execution, or LLM-dependent recovery outside the gated backend contract.
