# Atlas Next Current Status

Updated after the PR-ATLAS-SCALE-131 backend-only local branch proposal artifact.

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
- Branch proposal artifacts are stored under `data_root/atlas/branch_proposals/<proposal_id>/manifest.json` and keep branch creation, git mutation, draft PR creation, and autonomous execution disabled.

## Current safety boundaries
- `ui.html` remains the default root UI.
- Vue remains non-authoritative for workflow eligibility.
- Vue execution, autonomous execution, automatic patch generation, automatic patch apply, safe apply controls, verification execution, rollback execution, retry, auto-continue, execute-all, branch creation, draft PR creation, and remote git operations remain disabled.
- Atlas Next uses safe GET workflow state metadata plus the explicit PlanPool create endpoint only.
- Patch Review, Guarded Execution Preparation, right-rail diagnostics, conversation requirement summary, guided flow grouping, plan lifecycle strip, and PlanPool item summary are display-only and do not expose patch generation, apply, safe_apply, verification execution, rollback execution, retry, autonomous continuation, approval, dry-run, branch creation, or draft PR controls.
- SCALE-131 does not create a branch and does not add a public route or Vue control; it only writes a backend proposal artifact after explicit approval and an applied patch transaction.

## Next narrow PR
- PR-ATLAS-SCALE-132: add approved local branch creation from a local branch proposal artifact.
- Keep it manually gated and backend-only; do not add draft PR creation, PR update, Vue execution controls, autonomous continuation, runtime escalation, or default UI changes.
