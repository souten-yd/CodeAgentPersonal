# Atlas Code Generation Quality Gates

This document defines the quality gates, policies, and verification contracts
that Atlas applies during code generation, Safe Apply, and completion reporting.

---

## Verification Status Semantics

`applied_no_verification` is NOT a success status.

| Status | Meaning | Counted as success? |
|--------|---------|---------------------|
| `completed` | Applied + verification passed | Yes |
| `applied_no_verification` | Applied, no verification ran | No — `applied_no_verification_count` |
| `failed` | Apply failed or verification failed | No |
| `blocked` | Blocked before apply | No |

---

## Verify Level Taxonomy

Levels are ordered from lowest to highest confidence:

```
applied_only → static_checked → syntax_checked → runtime_smoke_checked → requirement_checked
```

- `runtime_smoke_checked` 未満 → 「実行確認済み」と表示しない (`is_execution_confirmed() = False`)
- `requirement_checked` 未満 → 「要件充足済み」と表示しない (`is_requirement_confirmed() = False`)

Implementation: `agent/atlas_verify_level_schema.py`

---

## Safe Apply Patchability Gate

Before a PlanItem reaches Safe Apply, `classify_plan_item_patchability()` checks:

| Condition | Reason |
|-----------|--------|
| item_type in {research, planning, verification, nexus_save} | `non_patch_plan_item` |
| clarification/inspect-like item_type strings | `non_patch_plan_item` |
| action_type = run_command | `run_command_clarification` |
| action_type = delete/execute/shell | `forbidden_action_type` |
| implementation with no target_files AND no file_changes | `no_concrete_target` |
| implementation with no patch content | `patch_content_missing` |

Implementation: `agent/atlas_plan_item_patchability.py`

---

## Multi-File Write-Time Rollback Policy

When a multi-file Safe Apply fails mid-write:

- Written files are rolled back in **reverse order**
- New files (did not exist before) → deleted
- Updated files (existed before) → restored to original content
- **Rollback success**: `partial_write_possible=False`, `changed_files=[]`
- **Rollback failure**: `partial_write_possible=True`, `unrestored_files=[...]`

Rollback metadata persisted in `item.metadata.safe_apply`:
- `rollback_attempted`, `rollback_succeeded`, `restored_files`, `unrestored_files`

Implementation: `agent/atlas_file_safe_apply_executor.py`, `agent/atlas_safe_apply_execution_service.py`

---

## High Critique Gate

`AtlasCritiqueGateService.evaluate()` blocks Patch/Apply when:

- Any finding has `severity = "high"` or `"critical"`
- `consensus_risk = "high"` or `"critical"`
- `requires_revision = True`

Override is allowed only with explicit `override_reason` (non-empty).
Override reason is recorded in the final summary.

Implementation: `agent/atlas_critique_gate_service.py`

---

## Risk / Evidence Gate

When high risk is detected:

**A. User clarification** — required when: design branches, scope decisions, UX decisions,
compatibility, safety/security judgments. Atlas presents options with merits/risks/recommendation.

**B. Evidence gathering** — resolve by checking: main branch files, docs, manifests, tests,
runtime implementation, PR diffs, existing issues. Resolved risks are recorded as downgraded.

**C. Blocked** — if neither A nor B resolves the risk. Blocked reason + unresolved risks
are included in the final summary.

---

## Clarification Gate

`AtlasClarificationGateService.evaluate()` requires user clarification when:

- Ambiguity signals are detected (unclear scope, multiple interpretations, etc.)
- Safety-sensitive ambiguity → **always requires clarification** (no safe default)

Safe, obvious defaults bypass clarification and are recorded as `explicit_assumptions`.

Implementation: `agent/atlas_clarification_gate_service.py`

---

## Requirement Trace

Each user request is decomposed into atomic requirements with:

```
requirement_id, description, planned_files, implementation_evidence,
verification_method, status
```

Status values: `planned → implemented → verified` (or `missing` / `partial`)

`missing` or `partial` requirements prevent `success_eligible=True`.

Implementation: `agent/atlas_requirement_tracer.py`

---

## Multi-File Integration Check

Generated files are checked for:

- Referenced from HTML entrypoint (script src / link href)
- Export/import consistency across JS/TS files
- Public methods/functions connected to user-facing behavior

Disconnected user-facing modules → `failed` / `degraded`
Disconnected non-user-facing modules → `warning`

Implementation: `agent/atlas_integration_checker.py`

---

## Placeholder Detection

The following are detected as warnings/blockers in generated implementation files:

- `# placeholder` / `# TODO` / `# in a real implementation`
- `// placeholder` / `// TODO` (JS)
- Empty `draw` / `update` / `check` / `render` function bodies (only `pass`)
- `console.log` with placeholder/stub/not-impl messages

Intentional placeholders in `docs/`, `tests/`, `spec/`, `fixture/` paths are excluded.

Implementation: `agent/atlas_placeholder_detector.py`

---

## Visual Artifact Static Contract Verification

HTML visual artifacts are NOT verified by file existence alone.

Checked signals for animation tasks:

| Signal | Examples |
|--------|----------|
| animation_signal | `requestAnimationFrame`, CSS `@keyframes` |
| color_mutation_signal | `hsl(`, `rgb(`, `style.color`, CSS variable, `hue-rotate` |
| motion_signal | `transform`, `translate`, canvas context |
| wave_phase_signal *(wave tasks)* | `Math.sin`, `phase`, `amplitude`, `frequency` |

For non-animation tasks, signals are advisory only.

Implementation: `agent/atlas_visual_artifact_verifier.py`

---

## Optional Playwright Visual Smoke Verification

When Playwright is available in the test/CI environment:

- Only opens `file://` URIs of local generated artifacts (no arbitrary URLs)
- Checks: JS errors, DOMContentLoaded, expected visible text, computed style changes over time
- Results: `browser_smoke_passed / browser_smoke_failed / browser_smoke_skipped`
- Playwright unavailable → `browser_smoke_skipped`, static contract is still primary

Implementation: `agent/atlas_playwright_smoke_verifier.py`

---

## Repair Prompt Prioritization

When a user message contains repair keywords ("not changing", "bug", "fix", "直ってない", etc.):

- `classify_repair_intent()` returns `primary_target_files = previous_changed_files`
- Planner prioritizes those files as the first implementation update target
- Test-only repair plans (`is_test_only_repair_plan()`) are warned/blocked

Implementation: `agent/atlas_repair_intent_classifier.py`

---

## Modular Vertical-Slice Policy

HTML/JS apps are generated as modular vertical slices, not God source:

- `index.html` → thin shell (DOM structure, canvas, script entrypoints only)
- Recommended layout: `js/main.js`, `js/state.js`, `js/input.js`, `js/renderer.js`, `css/style.css`

Every generated module must:
- Be imported or loaded by the entrypoint
- Have at least one public function called from the runtime path
- Contribute to user-visible behavior

God source detection (`check_god_source()`):
- HTML inline script > 80 lines → warning
- JS file > 600 lines → warning
- Disconnected module forest → warning/failed

Implementation: `agent/atlas_modular_slice_policy.py`

---

## No God Source Policy

- Do NOT put large application logic in HTML `<script>` blocks
- Do NOT make `main.js` an oversized God object
- If splitting into modules, ALL modules must be connected to the entrypoint

Both extremes are blocked:
- God source (all logic in one file)
- Disconnected module forest (split but not connected)

---

## Features Capability Preference UI Semantics

Capability checkboxes in the Features UI are **user preference metadata only**.

| Metadata key | Meaning |
|-------------|---------|
| `feature_preferences.X_requested = true` | User selected this capability |
| `runtime_capabilities.X_enabled = false` | Backend policy has not enabled it |
| `runtime_block_reason = level_0_manual_only` | Why it is currently blocked |

**Checked UI preference ≠ backend authorization.**
Backend/runtime policy remains authoritative over UI preference.

Implementation: `ui.html`, `web/js/atlas_claude_panel.js`, `agent/atlas_capability_preference_schema.py`

---

## Final Summary Requirements

The final summary must separately report:

1. Patch application status
2. Rollback status (rollback_attempted, rollback_succeeded, restored_files, unrestored_files)
3. Verification status (verify_level reached, levels not reached, reason)
4. Requirement coverage (by status, missing/partial count, success_eligible)
5. Unresolved critique findings
6. Resolved/downgraded risks + evidence sources
7. Unresolved risks
8. User decisions and assumptions
9. Integration warnings (disconnected modules)
10. Placeholder warnings
11. Feature preferences (selected + blocked capabilities)
12. User action required items

`完了 7 失敗 0` のような作業完了だけを success として見せない。

---

## Override Policy

Any gate can be overridden **only with an explicit `override_reason`** (non-empty string).

Override metadata saved in final summary:
- `override_reason`
- `approver` (if known)
- `residual_risk`
- `verification_gap`

---

## Safety-Sensitive Ambiguity Policy

Ambiguity involving any of the following topics **must not use safe defaults** —
always require explicit user clarification:

- execution capability / runtime policy
- external access / network / credentials
- security / permissions
- safety policy / sandboxing

---

## Safety Invariants (All PRs)

These invariants are never relaxed by quality gate code:

- `delete / run_command / execute / shell / external_fetch` are never enabled
- Absolute paths / parent traversal / `.git` / protected paths are never allowed
- Vue authority / `ui.html` default are never changed
- `backend authoritative` / `runtime level_0_manual_only` are maintained
- Autonomous execution capability is never added
- `npm install` / arbitrary browser automation are never added to startup
- Raw source serving / fallback / redirect are never added
