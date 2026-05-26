# Atlas Next Current Status

Updated after the PR-ATLAS-SCALE-159 self-improvement autonomous candidate loop.

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
- PR-ATLAS-SCALE-130 through PR-ATLAS-SCALE-146 build the guarded patch, branch, draft PR, bounded loop, Level-3, self-improvement, and Level-4 checkpoint chain.
- PR-ATLAS-SCALE-147 through PR-ATLAS-SCALE-156 add automation safety profile, external recovery, candidate workspace, boot diagnosis, conversational shell, candidate apply, verification, promotion readiness, and automatic failure recovery plan metadata.
- PR-ATLAS-SCALE-157 adds backend-only autonomous loop execution v1 session metadata, bounded by allowlisted loop actions, maximum iterations, stop-on-failure, and recovery plan requirements.
- PR-ATLAS-SCALE-158 adds backend-only full automation mode checkpoint metadata from a ready SCALE-157 session while keeping arbitrary command execution, stable runtime mutation, self-apply, direct merge, remote push, pointer switching, default UI promotion, and Vue authority disabled.
- PR-ATLAS-SCALE-159 adds backend-only self-improvement autonomous candidate loop metadata from a ready SCALE-158 checkpoint. It enables candidate-workspace-only autonomous loop readiness for patch preview, verification-gate request, promotion-gate request, recovery-plan request, and progress reporting while keeping stable runtime mutation, self-apply, direct merge, remote push, pointer switching, default UI promotion, and Vue authority disabled.

## Current safety boundaries
- `ui.html` remains the default root UI.
- Vue remains non-authoritative for workflow eligibility.
- Current runtime level is `level_7_self_improvement_autonomous_candidate_loop`.
- Self-improvement autonomous candidate loop is backend-authoritative and candidate-workspace-only.
- Candidate loop actions are bounded to allowlisted candidate actions, at most three iterations, stop-on-gate-failure, and recovery-plan-before-promotion.
- Candidate apply may mutate the candidate root after all gates, but it must not mutate the stable target repo, self-apply to the running runtime, promote candidates, push branches, merge, or enable Vue authority.
- External recovery supervisor use remains application-runtime-independent and bounded to manifest validation and plan-only recovery metadata.
- Work target mode selection can distinguish ordinary software development/repair from platform self-improvement intent, but it does not authorize self-apply, direct merge, stable runtime mutation, or Vue authority without backend gates.
- Arbitrary command execution, automatic rollback execution, execute-all, direct merge, self-modification, self-apply, remote git push, pointer switching, promotion execution, default UI promotion, Vue authority, and stable runtime mutation remain disabled.
- SCALE-159 does not add a public route, add a Vue control, push a branch, create a branch, run verification commands, run boot probes, update PRs, self-apply, self-modify, direct merge, perform command execution, perform recovery execution, switch release pointers, promote a candidate, mutate stable runtime, or require npm/Vite build for the default shell.

## Later UI/UX planning note
- Later conversational/FastUI work must expose a backend-owned work target mode selector for ordinary software development/repair versus platform self-improvement.
- That selector is a UI intent control only; it must not authorize self-apply, direct merge, stable runtime mutation, or Vue authority without the backend profile, scope, checkpoint, candidate workspace, verification, and recovery gates.

## Next narrow PR
- PR-ATLAS-SCALE-160: fully autonomous code agent milestone.
- Keep it dependent on SCALE-159 candidate-loop metadata and do not add direct merge, stable runtime mutation, self-apply, remote push, default UI promotion, arbitrary command execution, or Vue authority unless the milestone helper explicitly proves every gate and keeps a rollback path.
