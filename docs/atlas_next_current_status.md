# Atlas Next Current Status

Updated after PR #1396.

## Completed in latest UI track
- #1390 builds `web/atlas-next` during Docker image build.
- #1391 embeds `/atlas-next/` as the Atlas mode child view while keeping `ui.html` as the root default.
- #1392 renames the Vue start surface from duplicate Create Plan wording to Start Atlas.
- #1393 adds display-only workflow stages to the right progress rail.
- #1394 adds display-only Plan Review / Approval Review / Execute Preview board.
- #1395 adds a display-only Patch Review panel.
- #1396 adds backend-owned `patch_transaction_metadata` to the read-only workflow state and normalizes it into Vue as `patchTransaction`.

## Current safety boundaries
- `ui.html` remains the default root UI.
- Vue remains non-authoritative for workflow eligibility.
- Vue execution, autonomous execution, patch generation, patch apply, safe apply, verification, rollback, retry, auto-continue, execute-all, and remote git operations remain disabled.
- Atlas Next uses safe GET workflow state metadata plus the explicit PlanPool create endpoint only.

## Next narrow PR
- Wire real backend patch transaction preview data into `patch_transaction_metadata` where the existing Level-1 patch proposal and transaction foundations can provide it.
- Keep the surface display-only; do not add patch diff generation, apply, safe_apply, verification execution, rollback execution, or autonomous continuation.
