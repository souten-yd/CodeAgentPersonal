# Atlas Next Current Status

Updated after the PR-ATLAS-SCALE-157 autonomous loop execution v1 contract.

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
- PR-ATLAS-SCALE-147 adds backend-only automation safety profile metadata without enabling direct merge or stable runtime mutation.
- PR-ATLAS-SCALE-148 adds the external `recovery/` supervisor foundation that can validate recovery manifests, read release pointers, hash files, and plan pointer switches without importing target runtime modules or executing recovery.
- PR-ATLAS-SCALE-149 through PR-ATLAS-SCALE-152 add candidate workspace, boot diagnosis, and buildless conversational shell foundations while keeping `ui.html` default and Vue non-authoritative.
- PR-ATLAS-SCALE-153 through PR-ATLAS-SCALE-156 add candidate apply, verification, promotion readiness, and automatic failure recovery plan metadata while keeping stable runtime mutation, pointer switching, recovery execution, push, merge, self-apply, and Vue authority disabled.
- PR-ATLAS-SCALE-157 adds backend-only autonomous loop execution v1 session metadata. It authorizes a bounded autonomous loop session only from an active autonomous safety profile plus a ready automatic failure recovery plan, while still forbidding arbitrary command execution, stable runtime mutation, self-apply, direct merge, remote push, pointer switching, default UI promotion, and Vue authority.

## Current safety boundaries
- `ui.html` remains the default root UI.
- Vue remains non-authoritative for workflow eligibility.
- Current runtime level is `level_5_autonomous_loop_execution_v1`.
- Autonomous loop execution v1 is backend-authoritative and bounded to allowlisted loop actions, at most three iterations, stop-on-failure, and a recovery plan requirement before each iteration.
- Candidate apply is candidate-workspace-only. It may mutate the candidate root after all gates, but it must not mutate the stable target repo, self-apply to the running runtime, promote candidates, push branches, merge, or enable Vue authority.
- Candidate verification, promotion, and automatic failure recovery are backend-only metadata helpers. They may mark verification, promotion readiness, and bounded recovery-plan readiness only from prior gated artifacts and evidence, but they must not execute commands, fabricate verification, switch pointers, run recovery, or mutate stable runtime.
- External recovery supervisor use remains application-runtime-independent and bounded to manifest validation and plan-only recovery metadata.
- Work target mode selection can distinguish ordinary software development/repair from platform self-improvement intent, but it does not authorize self-improvement, self-apply, direct merge, stable runtime mutation, or Vue authority without backend gates.
- Arbitrary command execution, automatic rollback execution, execute-all, direct merge, self-modification, self-apply, remote git push, pointer switching, promotion execution, default UI promotion, Vue authority, and stable runtime mutation remain disabled.
- SCALE-157 does not add a public route, add a Vue control, push a branch, create a branch, run verification commands, run boot probes, generate patches, update PRs, self-apply, self-modify, direct merge, perform command execution, perform recovery execution, switch release pointers, promote a candidate, mutate stable runtime, or require npm/Vite build for the default shell.

## Later UI/UX planning note
- Later conversational/FastUI work must expose a backend-owned work target mode selector for ordinary software development/repair versus platform self-improvement.
- That selector is a UI intent control only; it must not authorize self-improvement, self-apply, direct merge, stable runtime mutation, or Vue authority without the backend profile, scope, checkpoint, candidate workspace, verification, and recovery gates.

## Next narrow PR
- PR-ATLAS-SCALE-158: full automation mode checkpoint.
- Keep it dependent on SCALE-157 session metadata and do not add direct merge, stable runtime mutation, self-apply, remote push, default UI promotion, arbitrary command execution, or Vue authority in the checkpoint PR.
