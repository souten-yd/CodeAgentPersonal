# Atlas Next Current Status

Updated after the PR-ATLAS-SCALE-155 self-improvement candidate promotion gate helper.

## Completed in latest UI track
- #1390 builds `web/atlas-next` during Docker image build.
- #1391 embeds `/atlas-next/` as the Atlas mode child view while keeping `ui.html` as the root default.
- #1392 renames the Vue start surface from duplicate Create Plan wording to Start Atlas.
- #1393 adds display-only workflow stages to the right progress rail.
- #1394 adds display-only Plan Review / Approval Review / Execute Preview board.
- #1395 adds a display-only Patch Review panel.
- #1396 adds backend-owned `patch_transaction_metadata` to the read-only workflow state and normalizes it into Vue as `patchTransaction`.
- #1398 adds a read-only backend helper for latest patch transaction workflow metadata.
- #1399 wires patch transaction preview metadata into `/api/atlas/workflow-state/read-only` through a dedicated router registered before the legacy pipeline route.
- #1400 carries patch preview status, risk class, rollback readiness, and warnings into Atlas Next Patch Review display.
- #1402 adds a display-only Guarded Execution Preparation panel.
- #1403 exposes backend-owned guarded execution review metadata through the read-only workflow state contract.
- #1404 summarizes gate readiness, endpoint contract status, missing gates, and blocked reasons in the right rail.
- #1405 shows whether Atlas Next is rendering safe backend workflow_state metadata or placeholder fallback data.
- #1406 summarizes selected plan mode, operation mode, questions, and detailed definition in the main pane.
- #1407 visually connects Start Atlas input and the conversation summary before review panels.
- #1408 ties Start Atlas, Plan Review, Approval Review, Execute Preview, and Patch Review into one visible sequence.
- The read-only PlanPool item summary PR makes generated plan candidates easier to scan inside the Start Atlas result review panel.

## Completed in latest automation roadmap track
- PR-ATLAS-SCALE-129 adds patch transaction preview with rollback metadata required and no apply.
- PR-ATLAS-SCALE-130 adds a backend-only `apply_patch_transaction_one_action` helper for a single low-risk patch transaction.
- PR-ATLAS-SCALE-131 adds a backend-only `create_local_branch_proposal` helper for writing a proposal artifact after an approved patch transaction apply.
- PR-ATLAS-SCALE-132 adds a backend-only `create_approved_local_branch` helper that creates a local branch ref from a proposal artifact after explicit approval and exact `CREATE LOCAL BRANCH` confirmation.
- PR-ATLAS-SCALE-133 adds backend-only `create_draft_pr_policy_metadata`, producing policy metadata for a created local branch while keeping PR creation disabled.
- PR-ATLAS-SCALE-134 adds backend-only `create_manually_approved_draft_pr`, using an injected draft PR client after explicit approval and exact `CREATE DRAFT PR` confirmation.
- PR-ATLAS-SCALE-135 adds backend-only `create_manually_approved_pr_update`, using an injected update client after explicit approval and exact `UPDATE DRAFT PR` confirmation.
- PR-ATLAS-SCALE-136 adds backend-only `create_bounded_loop_policy_v1`, producing a policy-only bounded loop artifact while keeping loop execution disabled.
- PR-ATLAS-SCALE-137 adds backend-only `create_bounded_retry_recovery_metadata`, producing metadata-only bounded retry and failure recovery policy while keeping retry execution disabled.
- PR-ATLAS-SCALE-138 adds backend-only `create_level2_runtime_transition_checkpoint`, authorizing Level-2 only when bounded policy, retry metadata, stop gate, verification allowlist, artifact capture, and explicit approval are present.
- PR-ATLAS-SCALE-139 adds backend-only `create_level3_autonomous_loop_candidate`, authorizing a Level-3 candidate only from an approved Level-2 checkpoint while keeping execution disabled.
- PR-ATLAS-SCALE-140 adds backend-only `create_self_improvement_proposal`, recording proposal-only self-improvement intent for CodeAgentPersonal / KasaneCore while keeping self-apply disabled.
- PR-ATLAS-SCALE-141 adds backend-only `classify_self_modification_risk`, recording classification-only strict self-modification risk metadata while keeping patch preview disabled.
- PR-ATLAS-SCALE-142 adds backend-only `create_self_improvement_patch_preview`, recording preview-only changed-path metadata from an approved risk classification while keeping patch generation and apply disabled.
- PR-ATLAS-SCALE-143 adds backend-only `create_self_improvement_dry_run_verification`, recording allowlist-classified verification metadata from an approved patch preview while keeping command execution disabled.
- PR-ATLAS-SCALE-144 adds backend-only `apply_self_improvement_patch_one_action`, allowing one manually approved self-improvement patch apply after SCALE-143 verification, snapshot, rollback, strict gate, explicit approval, and exact confirmation text.
- PR-ATLAS-SCALE-145 adds backend-only `create_self_improvement_draft_pr_one_action`, using an injected draft PR client after a validated SCALE-144 apply artifact, branch readiness, strict gate approval, explicit approval, and exact confirmation text.
- PR-ATLAS-SCALE-146 adds backend-only `create_level4_self_improvement_checkpoint`, authorizing the Level-4 self-improvement platform checkpoint only after Level-3 candidate and SCALE-145 draft PR evidence, strict self-improvement gates, explicit approval, and exact confirmation text.
- PR-ATLAS-SCALE-147 adds backend-only `create_automation_safety_profile`, defining review_only, guarded_single_action, supervised_bounded_auto, and autonomous_dev_agent profile metadata plus a separate gated self-improvement axis without enabling execution.
- PR-ATLAS-SCALE-148 adds an external `recovery/` supervisor foundation that can validate recovery manifests, read release pointers, hash files, and plan pointer switches without importing target runtime modules or executing recovery.
- PR-ATLAS-SCALE-149 adds backend-only `create_candidate_workspace_plan`, defining target repo, candidate root, path bounds, checkpoint references, recovery references, and safety limits without creating worktrees, copying files, applying patches, verifying, promoting, mutating stable runtime, pushing branches, or merging.
- PR-ATLAS-SCALE-150 adds backend-only `create_boot_self_diagnosis_checkpoint`, recording stable release metadata, boot health check evidence, artifact hashes, recovery manifest reference, and candidate workspace plan reference without running probes, importing app runtime, mutating stable runtime, creating candidate workspaces, promoting, pushing, or merging.
- PR-ATLAS-SCALE-151 adds backend-only `create_conversational_shell_contract`, defining the buildless conversational shell regions and backend-owned work target mode selector without requiring npm/Vite/Vue runtime, promoting Atlas Next, executing commands, applying candidates, self-applying, self-modifying, pushing, or merging.
- PR-ATLAS-SCALE-152 adds backend-only `create_conversational_shell_model`, turning the SCALE-151 contract into a buildless display/supervision model with transcript, goal input, phase, next action, safety profile, work target selector, changed files, verification, recovery, and one primary CTA while keeping authority and execution disabled.
- PR-ATLAS-SCALE-153 adds backend-only `apply_self_improvement_candidate_patch_one_action`, allowing one manually approved patch apply inside the candidate workspace root only after candidate plan, dry-run verification, rollback, strict gate, explicit approval, and exact candidate confirmation text.
- PR-ATLAS-SCALE-154 adds backend-only `create_self_improvement_candidate_verification_gate`, requiring an applied candidate result, allowlisted verification commands, and evidence references while keeping command execution, fabricated verification, promotion, stable runtime mutation, push, merge, self-apply, and Vue authority disabled.
- PR-ATLAS-SCALE-155 adds backend-only `create_self_improvement_candidate_promotion_gate`, preparing a rollback-ready release pointer switch gate from a ready candidate verification gate while keeping pointer switching, promotion execution, stable runtime mutation, push, merge, self-apply, and Vue authority disabled.

## Current safety boundaries
- `ui.html` remains the default root UI.
- Vue remains non-authoritative for workflow eligibility.
- Current runtime level remains `level_4_self_improvement_platform`; autonomous execution remains disabled.
- Candidate apply is candidate-workspace-only. It may mutate the candidate root after all gates, but it must not mutate the stable target repo, self-apply to the running runtime, promote candidates, push branches, merge, or enable Vue authority.
- Candidate verification gate is backend-only and metadata-only. It may mark candidate verification ready only from an applied candidate result, allowlisted commands, and relative evidence references, but it must not execute commands or fabricate verification results.
- Candidate promotion gate is backend-only and metadata-only. It may mark release pointer switching ready only from a ready candidate verification gate, rollback pointer path, stable checkpoint ref, recovery manifest ref, strict approval, and exact confirmation text, but it must not switch pointers or mutate the stable runtime.
- Work target mode selection can distinguish ordinary software development/repair from platform self-improvement intent, but it does not authorize self-improvement, self-apply, execution, direct merge, or Vue authority without later backend gates.
- Vue execution, autonomous loop execution, autonomous execution, command execution, automatic patch generation, automatic verification, automatic rollback, auto-continue, execute-all, direct merge, self-modification, self-apply, branch creation, remote git push, pointer switching, promotion execution, and stable runtime mutation remain disabled.
- SCALE-155 does not add a public route, add a Vue control, push a branch, create a branch, add autonomous continuation, execute retries, run verification commands, run boot probes, generate patches, update PRs, self-apply, self-modify, direct merge, perform command execution, perform recovery execution, switch release pointers, promote a candidate, mutate stable runtime, or require npm/Vite build for the default shell.

## Later UI/UX planning note
- Later conversational/FastUI work must expose a backend-owned work target mode selector for ordinary software development/repair versus platform self-improvement.
- That selector is a UI intent control only; it must not authorize self-improvement, self-apply, execution, direct merge, or Vue authority without the backend profile, scope, checkpoint, candidate workspace, verification, and recovery gates.

## Next narrow PR
- PR-ATLAS-SCALE-156: automatic failure recovery v1.
- Keep it external-recovery-supervisor bounded and independent from app runtime; do not add direct merge, Vue authority, default UI promotion, unbounded autonomous execution, self-apply, remote push, arbitrary command execution, or LLM-dependent recovery.
