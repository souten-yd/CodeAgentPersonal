# Codex Prompt — Portal Forge Hardening

```text
Read AGENTS.md first.

Continue the Atlas Portal + Model Forge Hardening track in KasaneCore.

Use these files:
- docs/atlas_portal_forge_current_status.md
- docs/atlas_portal_forge_hardening_current_status.md
- docs/atlas_portal_forge_hardening_plan.md
- docs/atlas_portal_forge_hardening_test_plan.md
- docs/atlas_portal_forge_hardening_agent_entrypoint.md

Start from the current package in docs/atlas_portal_forge_hardening_current_status.md.

Current package is PFH-1 unless the status file says otherwise.

Do not restart Portal or Forge from scratch.
Do not delete legacy model execution.
Do not enable external providers by default.
Do not apply Arena candidates directly.
Do not mark unavailable as passed.

Implement each PFH package as a coherent PR-sized slice.
After each package, update docs/atlas_portal_forge_hardening_current_status.md with exact evidence.

Important first fix:
PFH-1 must fix benchmark preset identity and execution semantics:
- Forge UI must use real backend preset IDs or backend-provided family aliases.
- Tests must use real preset_listing() data.
- Multi-selected presets must be included in request payload or visibly unsupported.
- Depth must be implemented or visibly unavailable.
```
