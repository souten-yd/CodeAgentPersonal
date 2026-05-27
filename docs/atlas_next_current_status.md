# Atlas Next Current Status

Updated after POST-SCALE-160 FastUI shell MVP progress.

## Completed in latest UI track
- #1390 builds `web/atlas-next` during Docker image build.
- #1391 embeds `/atlas-next/` as the Atlas mode child view while preserving legacy `/ui/` fallback access.
- #1392 renames the Vue start surface from duplicate Create Plan wording to Start Atlas.
- #1393 adds display-only workflow stages to the right progress rail.
- #1394 adds display-only Plan Review / Approval Review / Execute Preview board.
- #1395 adds a display-only Patch Review panel.
- #1396, #1398, #1399, and #1400 carry backend-owned patch transaction preview metadata into Atlas Next display.
- #1402 through #1408 connect guarded execution preparation, gate readiness, provenance, and Start Atlas conversation flow as display-only UI.
- The read-only PlanPool item summary PR makes generated plan candidates easier to scan inside the Start Atlas result review panel.
- POST-SCALE-160-VUE-DEFAULT-PROMOTION-GATE adds a backend-only readiness gate for promoting `/atlas-next/` as the default route.
- POST-SCALE-160-VUE-DEFAULT-PROMOTION-APPLY aligns docs, manifest, and route contracts with the existing guarded `/` default behavior.
- POST-SCALE-160-UI-DEFAULT-RECONFIRM records that the current guarded Atlas Next root default stays active for now while buildless ThinUX / FastUI remains the preferred future default direction.
- POST-SCALE-160-FASTUI-SHELL-MVP mounts the first conversation-first Atlas shell above the older detailed panels, including a backend-owned work target intent selector, current phase, next action, safety badge, changed files, verification, recovery, one Start Atlas CTA, and a collapsed settings drawer.

## Completed in latest automation roadmap track
- PR-ATLAS-SCALE-129 remains planned and records patch transaction preview with rollback metadata required and no apply.
- PR-ATLAS-SCALE-130 through PR-ATLAS-SCALE-160 reach the backend fully autonomous code agent milestone.
- POST-SCALE-160-VUE-DEFAULT-PROMOTION-GATE prepared Vue default promotion readiness after the backend milestone.
- POST-SCALE-160-VUE-DEFAULT-PROMOTION-APPLY records the guarded Vue default route as applied without expanding Vue authority or runtime mutation.
- POST-SCALE-160-STABLE-RUNTIME-MUTATION-GATE adds a backend-only gate for future stable runtime mutation or release pointer behavior.
- POST-SCALE-160-UI-DEFAULT-RECONFIRM completes the UI default checkpoint required before stable runtime mutation apply.
- POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY adds a strict, record-only stable runtime mutation apply helper that consumes a ready gate and exact approval.
- POST-SCALE-160-PRACTICAL-AUTOMATION-PLAN adds the practical full-automation experience plan and marks practical completion flags incomplete until evidence exists.

## Current safety boundaries
- `/` selects Atlas Next only through `can_serve_atlas_next_default()` after `validate_atlas_next_dist()` passes.
- `/ui/` remains the legacy UI fallback route and root fails closed to legacy UI if the prebuilt Vue dist is missing or invalid.
- Buildless ThinUX / FastUI conversational shell is the preferred future normal Atlas experience, but it is not switched to the default route in this checkpoint.
- Practical full automation is not complete at backend-milestone-only state; FastUI usability, bounded developer loop, self-improvement loop, draft PR experience, and checkpoint evidence remain tracked separately.
- Vue remains non-authoritative for workflow eligibility and approval; backend workflow state remains authoritative.
- Current runtime level is `level_8_fully_autonomous_code_agent` for the backend automation milestone.
- Stable runtime mutation apply remains tightly gated: ready gate, verified candidate workspace, stable snapshot, rollback evidence, recovery evidence, strict approval, and exact confirmation are required.
- Direct merge, remote push, self-apply, pointer switching, execute-all, Vue authority, and recovery execution remain disabled unless a later dedicated PR proves the needed evidence and rollback path.
- The FastUI shell MVP does not serve raw Vue source, run npm at server startup, add Vue authority, or enable Vue execution controls.

## Later UI/UX planning note
- Later conversational/FastUI work must expose a backend-owned work target mode selector for ordinary software development/repair versus platform self-improvement.
- That selector is a UI intent control only; it must not authorize self-apply, direct merge, stable runtime mutation, or Vue authority without the backend profile, scope, checkpoint, candidate workspace, verification, and recovery gates.

## Next narrow work
- POST-SCALE-160-PRACTICAL-AUTONOMOUS-DEV-LOOP: connect the FastUI shell to bounded backend loop summaries and recovery/draft-PR progress artifacts while keeping direct merge, self-apply, remote push, arbitrary command execution, and Vue authority separate gated changes.