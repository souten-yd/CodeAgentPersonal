# Atlas Next Current Status

Updated after the PR-ATLAS-SCALE-135 backend-only manually approved draft PR update helper.

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
- PR-ATLAS-SCALE-130 adds a backend-only `apply_patch_transaction_one_action` helper for a single low-risk patch transaction.
- PR-ATLAS-SCALE-131 adds a backend-only `create_local_branch_proposal` helper for writing a proposal artifact after an approved patch transaction apply.
- PR-ATLAS-SCALE-132 adds a backend-only `create_approved_local_branch` helper that creates a local branch ref from a proposal artifact after explicit approval and exact `CREATE LOCAL BRANCH` confirmation.
- PR-ATLAS-SCALE-133 adds backend-only `create_draft_pr_policy_metadata`, producing policy metadata for a created local branch while keeping PR creation disabled.
- PR-ATLAS-SCALE-134 adds backend-only `create_manually_approved_draft_pr`, using an injected draft PR client after explicit approval and exact `CREATE DRAFT PR` confirmation.
- PR-ATLAS-SCALE-135 adds backend-only `create_manually_approved_pr_update`, using an injected update client after explicit approval and exact `UPDATE DRAFT PR` confirmation.

## Current safety boundaries
- `ui.html` remains the default root UI.
- Vue remains non-authoritative for workflow eligibility.
- Vue execution, autonomous execution, automatic patch generation, automatic patch apply, safe apply controls, verification execution, rollback execution, retry, auto-continue, execute-all, and remote git push operations remain disabled.
- Draft PR creation and PR update are backend-only, manually approved, confirmation-gated, and require injected clients; no network library, public route, Vue control, push, or autonomous update path is introduced by SCALE-135.
- Atlas Next uses safe GET workflow state metadata plus the explicit PlanPool create endpoint only.
- Patch Review, Guarded Execution Preparation, right-rail diagnostics, conversation requirement summary, guided flow grouping, plan lifecycle strip, and PlanPool item summary are display-only and do not expose patch generation, apply, safe_apply, verification execution, rollback execution, retry, autonomous continuation, approval, dry-run, branch creation, draft PR, or PR update controls.
- SCALE-135 does not add a public route, add a Vue control, push a branch, add autonomous continuation, or change runtime level; it only records a manually approved draft PR update result through an injected backend client.

## Next narrow PR
- PR-ATLAS-SCALE-136: add bounded loop policy v1 for the next automation phase.
- Keep it policy-first and backend-authoritative; do not add Vue execution controls, autonomous continuation, runtime escalation, default UI changes, or remote git push operations.
