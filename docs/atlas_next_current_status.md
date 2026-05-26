# Atlas Next Current Status

Updated after the POST-SCALE-160 Vue default promotion readiness gate.

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
- POST-SCALE-160-VUE-DEFAULT-PROMOTION-GATE adds a backend-only readiness gate for promoting `/atlas-next/` as the default route in a later apply PR.

## Completed in latest automation roadmap track
- PR-ATLAS-SCALE-129 remains planned and records patch transaction preview with rollback metadata required and no apply.
- PR-ATLAS-SCALE-130 through PR-ATLAS-SCALE-160 reach the backend fully autonomous code agent milestone.
- POST-SCALE-160-VUE-DEFAULT-PROMOTION-GATE prepares Vue default promotion readiness after the backend milestone while keeping the actual default route unchanged.

## Current safety boundaries
- `ui.html` remains the default root UI until a separate default-promotion apply PR.
- Vue remains non-authoritative for workflow eligibility; default Vue promotion still requires a separate apply PR.
- Current runtime level is `level_8_fully_autonomous_code_agent`.
- Fully autonomous code agent milestone remains backend-authoritative and requires a ready SCALE-159 candidate loop, milestone evidence, rollback evidence, strict gate approval, and exact confirmation text.
- Vue default promotion readiness requires a valid prebuilt dist, `/atlas-next/` smoke evidence, legacy UI route availability, fail-closed verification, rollback evidence, strict gate approval, and exact confirmation text.
- Stable runtime mutation, direct merge, remote push, self-apply, pointer switching, execute-all, default UI promotion, Vue authority, and recovery execution remain disabled unless a later dedicated gate proves the needed evidence and rollback path.
- POST-SCALE-160-VUE-DEFAULT-PROMOTION-GATE does not change the default route, add a redirect, bypass fallback behavior, serve raw Vue source, run npm at server startup, add Vue authority, or enable Vue execution controls.

## Later UI/UX planning note
- Later conversational/FastUI work must expose a backend-owned work target mode selector for ordinary software development/repair versus platform self-improvement.
- That selector is a UI intent control only; it must not authorize self-apply, direct merge, stable runtime mutation, or Vue authority without the backend profile, scope, checkpoint, candidate workspace, verification, and recovery gates.

## Next narrow work
- POST-SCALE-160-VUE-DEFAULT-PROMOTION-APPLY: apply the default route switch only if the readiness gate output, valid dist, smoke evidence, legacy route, fail-closed behavior, and rollback plan are all present.
- Direct merge, stable runtime mutation, self-apply, remote push, arbitrary command execution, and Vue authority must remain separate gated changes.
