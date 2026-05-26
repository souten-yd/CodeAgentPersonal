# Atlas Next Current Status

Updated after the PR-ATLAS-SCALE-138 explicit Level-2 guarded bounded loop checkpoint helper.

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
- PR-ATLAS-SCALE-138 adds backend-only `create_level2_runtime_transition_checkpoint`, authorizing Level-2 only when bounded loop policy, retry recovery metadata, stop gate, verification allowlist, artifact capture, and explicit approval are present.

## Current safety boundaries
- `ui.html` remains the default root UI.
- Vue remains non-authoritative for workflow eligibility.
- Current runtime level is `level_2_guarded_bounded_loop` only through the explicit checkpoint; autonomous execution remains disabled.
- Level-2 is bounded, backend-authoritative, low-risk, dry-run-first, explicit-approval-per-iteration, stop-gated, verification-allowlisted, and artifact-captured.
- Vue execution, autonomous execution, automatic patch generation, automatic patch apply, automatic verification, automatic rollback, auto-continue, execute-all, direct merge, self-modification, and remote git push operations remain disabled.
- Draft PR creation and PR update are backend-only, manually approved, confirmation-gated, and require injected clients; no network library, public route, Vue control, push, or autonomous update path is introduced by SCALE-138.
- Atlas Next uses safe GET workflow state metadata plus the explicit PlanPool create endpoint only.
- Patch Review, Guarded Execution Preparation, right-rail diagnostics, conversation requirement summary, guided flow grouping, plan lifecycle strip, and PlanPool item summary are display-only and do not expose patch generation, apply, safe_apply, verification execution, rollback execution, retry, autonomous continuation, approval, dry-run, branch creation, draft PR, or PR update controls.
- SCALE-138 does not add a public route, add a Vue control, push a branch, add autonomous continuation, execute retries, or perform execution; it only records and validates the Level-2 transition checkpoint.

## Next narrow PR
- PR-ATLAS-SCALE-139: Level-3 autonomous implementation loop candidate.
- Keep it candidate-gated and draft-PR-only; do not add direct merge, self-modification, Vue authority, default UI promotion, or unbounded autonomous execution.
