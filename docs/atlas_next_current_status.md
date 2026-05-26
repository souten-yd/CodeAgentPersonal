# Atlas Next Current Status

Updated after the read-only plan lifecycle strip PR.

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
- The read-only plan lifecycle strip PR ties Start Atlas, Plan Review, Approval Review, Execute Preview, and Patch Review into one visible sequence.

## Current safety boundaries
- `ui.html` remains the default root UI.
- Vue remains non-authoritative for workflow eligibility.
- Vue execution, autonomous execution, patch generation, patch apply, safe apply, verification, rollback, retry, auto-continue, execute-all, and remote git operations remain disabled.
- Atlas Next uses safe GET workflow state metadata plus the explicit PlanPool create endpoint only.
- Patch Review, Guarded Execution Preparation, right-rail diagnostics, conversation requirement summary, guided flow grouping, and plan lifecycle strip are display-only and do not expose patch generation, apply, safe_apply, verification execution, rollback execution, retry, autonomous continuation, approval, dry-run, or execute controls.

## Next narrow PR
- Add a read-only PlanPool item summary in the main pane so generated plan candidates are easier to scan before approval review.
- Keep the surface display-only except for the existing explicit PlanPool create endpoint; do not expose execute, approve, dry-run, safe_apply, verification execution, rollback execution, retry, or autonomous continuation controls.
