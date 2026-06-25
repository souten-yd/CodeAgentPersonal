# Generic Weak LLM App Hardening Plan

## Purpose

This plan continues the weak-LLM large-file edit work after the completed P0/P1 packages in `docs/weak_llm_large_file_edit_hardening_plan.md`.

The earlier work made weak/standard large-file modification bounded by forcing small edits, SEARCH/REPLACE, output caps, and raw `proposed_content` rejection. The next step is to make the same safety model useful beyond the game/WebGL reproduction case.

Atlas must support game projects, ordinary Web apps, and business applications. Therefore, future hardening must be generic:

```text
weak model chooses or describes a small edit
Atlas normalizes it
Atlas dry-runs the edit in memory
generic contracts validate the post-apply state
optional domain recipes repair known violation classes deterministically
Safe Apply remains the only authority that changes files
```

## Non-goals

- Do not add more game-only fixes as top-level special cases.
- Do not let repair recipes bypass Proposal, Safe Apply, Verification, or rollback.
- Do not let weak models rewrite large existing files.
- Do not treat mock output, UI rendering, or inferred facts as runtime proof.

---

# Read order for Codex / agents

Start from root `AGENTS.md`, then read:

1. `docs/generic_weak_llm_app_hardening_plan.md` — this plan.
2. `docs/weak_llm_large_file_edit_hardening_plan.md` — completed P0/P1 safety base and evidence.
3. Current implementation files listed below.

Primary implementation files:

- `agent/atlas_patch_proposal_service.py`
- `agent/atlas_file_safe_apply_executor.py`
- `agent/atlas_edit_format.py`
- `agent/atlas_repair_recipes.py`
- `agent/model_forge/weak_large_file_edit_policy.py`

Likely new modules:

- `agent/atlas_post_apply_preview.py`
- `agent/atlas_contracts.py`
- `agent/atlas_contract_registry.py`
- `agent/atlas_repair_recipe_registry.py`
- `agent/atlas_edit_primitives.py`

Tests should be added beside the existing Atlas patch / edit / repair tests.

---

# Package GA1 — Post-Apply Preview for generic validation

## Goal

Create a reusable in-memory post-apply preview layer. Validators must inspect the file state after edits are applied, not raw LLM output fragments.

## Problem

`proposed_content`, `file_changes`, and `metadata.edits` are currently interpreted by different parts of the pipeline. Some validators may see fragments rather than the final post-apply file state.

For Web apps and business apps, validation must run against the final in-memory state:

- React/Vue/Svelte import and prop usage
- API route and client mismatch
- DB schema/query mismatch
- JSON/YAML/env/config key changes
- auth/permission guard consistency
- form field / validation schema consistency

## Required implementation

Add a preview layer that converts a proposal into:

```python
{
    "applied": bool,
    "post_apply_content_by_path": dict[str, str],
    "applied_changes": list[dict],
    "blocked_changes": list[dict],
    "warnings": list[str],
    "reasons": list[str],
}
```

The preview must:

1. Start from current file contents.
2. Apply `content_mode="edits"` edits in memory using the same matching rules as Safe Apply where possible.
3. Apply full `content` only when the file is new or policy allows full content.
4. Reject slice-derived content as full file content.
5. Never write to disk.

## Acceptance criteria

- Existing edit-only proposals produce a full `post_apply_content_by_path` for validators.
- Edits are not represented as joined `new_string` fragments.
- Slice markers or slice-only content cannot become post-apply full file content.
- Tests cover Python, JS/TS, JSON, YAML-like text, and ordinary text files.

## Suggested tests

- `tests/test_atlas_post_apply_preview.py`
- Apply one exact edit to a large JS file and assert final content has the edit and unchanged surrounding content.
- Attempt to preview a sliced full-content replacement and assert it is blocked.
- Preview multiple files and ensure unrelated files remain unchanged.

---

# Package GA2 — Harden sliced-content salvage

## Goal

Make full-content-to-edits salvage safe when `current_file_content_sliced=True`.

## Problem

`_full_content_to_edits()` can convert raw full content into surgical edits. This is useful for small accidental rewrites. But when the current content is a slice, the diff base is not the real file.

## Required implementation

When edit-only policy is active and `current_file_content_sliced=True`:

- Prefer structured edits and SEARCH/REPLACE only.
- Do not run full-content salvage against the slice unless a future span-map proves the exact original region.
- Reject edits that contain slice omission markers or placeholder ellipses in `old_string` / `new_string`.

Add a clear warning/reason:

```text
full_content_salvage_forbidden_on_sliced_content
slice_marker_forbidden_in_edit
```

## Acceptance criteria

- Sliced current content plus raw `proposed_content` becomes bounded rejection, not converted edits.
- Non-sliced large file can still convert small full-content rewrite to edits.
- SEARCH/REPLACE with exact old_string still works on sliced payload if it does not include slice markers.

---

# Package GA3 — Generic Contract Registry

## Goal

Move from a WebGL-specific resource contract mindset to generic application contracts that can support games, Web apps, and business apps.

## Contract families

Implement lightweight DTOs / dictionaries first. Avoid overbuilding.

```text
ProjectContract
├─ ResourceContract
│  ├─ DOM id / root element / canvas / asset path
│  ├─ env var / config key
│  └─ file path / external resource handle
├─ InterfaceContract
│  ├─ exported functions/classes
│  ├─ component props
│  ├─ API endpoints
│  └─ event names
├─ DataContract
│  ├─ DB schema
│  ├─ JSON shape
│  ├─ form fields
│  └─ validation rules
├─ StateContract
│  ├─ store shape
│  ├─ session/auth state
│  └─ workflow state
└─ BusinessRuleContract
   ├─ permissions
   ├─ invariants
   ├─ calculations
   └─ approval flows
```

## Required implementation

Create a registry that can receive post-apply content and produce violations:

```python
{
    "violations": [
        {
            "code": "api_route_missing_handler",
            "contract_type": "interface",
            "path": "...",
            "severity": "error",
            "evidence": {...},
        }
    ],
    "warnings": [],
}
```

Start with generic extractors that are cheap and deterministic:

- JS/TS import/export symbols
- React/Vue/Svelte component prop-like identifiers where easy
- API route path strings
- env/config key strings
- JSON object keys
- SQL-like table/column references using conservative heuristics

## Acceptance criteria

- WebGL/canvas contract can be represented as a ResourceContract, not as the only hard-coded pattern.
- At least three non-game contract examples have tests:
  - API endpoint mismatch
  - config/env key mismatch
  - JSON/YAML form field mismatch or schema mismatch
- Contract checks consume `post_apply_content_by_path`, not raw LLM output.

---

# Package GA4 — Repair Recipe Registry

## Goal

Move existing WebGL repair into a registry of deterministic recipes. The recipe engine should be generic; WebGL should be one recipe.

## Required interface

```python
class RepairRecipe:
    id: str
    violation_code: str
    contract_type: str
    applies_to: list[str]

    def options(self, violation, context) -> list[dict]: ...
    def apply_selected(self, option_id, violation, context) -> dict: ...
```

A plain-function registry is acceptable for MVP if tests prove the same behavior.

## Required behavior

- Register the existing WebGL/2D conflict recipe under a generic registry.
- Keep explicit option selection; never guess a used-context repair.
- Return bounded `selected_option_not_implemented` for unsupported options.
- Allow future recipes for Web/business apps without modifying the main patch proposal service.

## Candidate generic recipes for future packages

- `api_route_missing_handler`
- `client_api_path_mismatch`
- `missing_import_for_used_symbol`
- `env_key_mismatch`
- `json_schema_field_missing`
- `form_validation_field_mismatch`
- `auth_guard_missing_for_protected_route`

## Acceptance criteria

- Existing WebGL repair tests pass through the registry.
- Direct calls to legacy WebGL repair can remain for compatibility but should be routed or wrapped by the registry.
- Main service code does not grow new app-specific branches.

---

# Package GA5 — File-type-aware edit policy and primitives

## Goal

Extend weak-model edit constraints beyond generic line/char thresholds. Business and Web apps have file types where full rewrites are dangerous even when files are not huge.

## File-type policy examples

```text
.ts/.tsx/.jsx/.vue/.svelte: edit-only above smaller threshold; prefer symbol/component primitive
.py service/domain files: edit-only above normal threshold; prefer function/class primitive
.sql/schema.prisma/migrations: edit-only by default; validate schema/query impact
.json/.yaml/.yml: path/key primitive by default
.env/.env.example: key primitive only
openapi.yaml/swagger.json: path/schema primitive only
```

## Required primitives

Add a primitive vocabulary that weak models can choose from:

```text
replace_exact
search_replace
replace_symbol
insert_import
replace_object_property
replace_json_pointer
replace_yaml_path
replace_sql_statement
replace_route_handler
replace_component_prop
```

Do not implement every primitive fully in the first PR. Define the schema and implement at least:

- `replace_exact` / existing edits compatibility
- `replace_json_pointer`
- `insert_import` for JS/TS/Python or a safe conservative subset

## Acceptance criteria

- Weak models can be instructed to choose a primitive rather than emit raw content.
- Unsupported primitive returns bounded rejection, not fallback to full content.
- JSON path replacement test passes.
- Import insertion test passes or is truthfully marked unavailable if parser support is missing.

---

# Package GA6 — Generic validators after preview

## Goal

Run deterministic validators against post-apply preview output.

## Initial validators

- `import_export_validator`
- `json_shape_validator`
- `config_env_key_validator`
- `api_route_reference_validator`
- `forbidden_full_content_validator`
- `slice_marker_validator`

## Acceptance criteria

- Validators take `post_apply_content_by_path` as input.
- Validators return structured violations with codes.
- Existing WebGL validator can be represented as a resource validator.
- Tests include at least one Web app case and one business/config case.

---

# Package GA7 — 8080 weak-model generic live checks

## Goal

Prove the safety model outside the game/WebGL case.

The user may provide an OpenAI-compatible weak LLM at:

```text
http://127.0.0.1:8080/v1
```

## Required scenarios

Run at least two temporary-workspace live scenarios:

1. Web app scenario:
   - React/TS or plain JS app
   - large existing component/service file
   - requested small UI/API modification
   - expected output: edits or bounded rejection

2. Business/config scenario:
   - JSON/YAML config, form schema, or API route file
   - small requested change
   - expected output: path/key edit, edits, or bounded rejection

## Required evidence

Record:

- model name/provider
- endpoint
- target file sizes
- edit policy verdict
- output cap
- output mode
- post-apply preview result
- contract violations
- safe apply dry-run result
- unavailable checks

## Acceptance criteria

- No full-file token runaway.
- No slice fragment applied as full file.
- No raw `proposed_content` accepted under edit-only.
- At least one non-game scenario reaches post-apply preview.

---

# Package GA8 — Documentation and agent workflow update

## Goal

Keep root `AGENTS.md` and `docs/AGENTS.md` as useful entrypoints.

## Required updates

- Link this plan from root `AGENTS.md`.
- Link this plan from `docs/AGENTS.md`.
- Keep `docs/weak_llm_large_file_edit_hardening_plan.md` as the completed base-plan reference.
- Record completion evidence after each package in this file.

## Evidence template

Each completed package must append:

```text
Completed package:
Status:
Changed modules/files:
Behavior implemented:
Focused tests:
Affected tests:
Syntax checks:
8080 live model evidence:
Post-apply preview evidence:
Contract validation evidence:
Unavailable checks:
Safety invariants:
Remaining gaps:
Next package:
Blocker:
Proof level:
```

---

# Completion evidence

## GA1 — Post-Apply Preview for generic validation (completed 2026-06-25)

Completed package: GA1 `codex/generic-post-apply-preview`
Status: completed; ready for item PR publication and merge
Changed modules/files: `agent/atlas_post_apply_preview.py`, `tests/test_atlas_post_apply_preview.py`, this plan
Behavior implemented: added a reusable in-memory post-apply preview layer that resolves Atlas plan item file changes to `post_apply_content_by_path` without writing to disk. The preview reuses Safe Apply content resolution for edits/append/full-content/diff paths, expands `content_mode="edits"` into final file content, carries unchanged target files into the preview map, reports applied/blocked changes, and blocks slice-derived full-content replacements.
Focused tests: `pytest -q tests/test_atlas_post_apply_preview.py` -> 10 passed
Affected tests: `pytest -q tests/test_atlas_file_safe_apply_executor.py` -> 24 passed
Syntax checks: `py_compile agent/atlas_post_apply_preview.py tests/test_atlas_post_apply_preview.py` -> passed
8080 live model evidence: not required for GA1; this package is deterministic preview plumbing and makes no LLM call
Post-apply preview evidence: tests cover JS/TS exact edit preview, Python, JSON, YAML-like text, ordinary text, multi-file unchanged target retention, new-file full content preview, policy-gated existing full content, and slice full-content rejection
Contract validation evidence: unavailable; generic contract validators are GA3/GA6
Unavailable checks: no browser/UI evidence; no live model evidence required for this slice
Safety invariants: no disk write; Safe Apply remains the only authority that changes files; slice markers are not promoted to full file content; `unavailable` is not treated as passed
Remaining gaps: GA2 sliced-content salvage hardening, GA3 contract registry, GA4 repair recipe registry, GA5 edit primitives, GA6 validators, GA7 live 8080 generic checks, GA8 entrypoint docs
Next package: GA2 — Harden sliced-content salvage
Blocker: none
Proof level: `post_apply_preview_component_complete`

---

## GA2 — Harden sliced-content salvage (completed 2026-06-25)

Completed package: GA2 `codex/harden-sliced-content-salvage`
Status: completed; ready for item PR publication and merge
Changed modules/files: `agent/atlas_patch_proposal_service.py`, `tests/test_atlas_patch_output_minimization.py`, this plan
Behavior implemented: edit-only generation for sliced existing files now forbids full-content-to-edits salvage instead of diffing against a slice. The proposal records `full_content_salvage_forbidden_on_sliced_content` and drops raw `proposed_content`. Exact SEARCH/REPLACE edits still parse and remain allowed on sliced payloads. Surgical edits containing omitted/rest-unchanged slice markers are rejected during normalization with `slice_marker_forbidden_in_edit`.
Focused tests: `pytest -q tests/test_atlas_patch_output_minimization.py` -> 13 passed
Affected tests: `pytest -q tests/test_atlas_edit_format_contract.py tests/test_atlas_weak_large_file_edit_policy_contract.py tests/test_atlas_focused_patch_extraction.py tests/test_atlas_post_apply_preview.py` -> 48 passed
Syntax checks: `py_compile agent/atlas_patch_proposal_service.py tests/test_atlas_patch_output_minimization.py` -> passed
8080 live model evidence: not required for GA2; this package hardens deterministic proposal normalization after model output
Post-apply preview evidence: GA1 preview tests remain green and cover slice full-content rejection
Contract validation evidence: unavailable; generic contract validators are GA3/GA6
Unavailable checks: no live model evidence required for this deterministic slice
Safety invariants: sliced content is never used as a full-file diff base; SEARCH/REPLACE remains bounded exact-edit input; Safe Apply authority unchanged; no direct workspace apply
Remaining gaps: GA3 contract registry, GA4 repair recipe registry, GA5 edit primitives, GA6 validators, GA7 live 8080 generic checks, GA8 entrypoint docs
Next package: GA3 — Generic Contract Registry
Blocker: none
Proof level: `sliced_salvage_hardened`

---

## GA3 — Generic Contract Registry (completed 2026-06-25)

Completed package: GA3 `codex/generic-contract-registry`
Status: completed; ready for item PR publication and merge
Changed modules/files: `agent/atlas_contracts.py`, `agent/atlas_contract_registry.py`, `tests/test_atlas_contract_registry.py`, this plan
Behavior implemented: added lightweight generic contract DTOs and a deterministic registry that consumes `post_apply_content_by_path`. The registry returns structured `violations` plus discovered contracts for shared app resources, API routes, env/config keys, JSON schema fields, and YAML form fields. Existing WebGL/canvas checks are represented as a resource contract violation instead of a game-only top-level pattern.
Focused tests: `pytest -q tests/test_atlas_contract_registry.py` -> 5 passed
Affected tests: `pytest -q tests/test_atlas_contract_registry.py tests/test_atlas_contract_adherence.py tests/test_atlas_post_apply_preview.py` -> 20 passed; `pytest -q tests/test_atlas_patch_proposal_codegen_contract.py tests/test_atlas_patch_output_minimization.py` -> 27 passed
Syntax checks: `py_compile agent/atlas_contracts.py agent/atlas_contract_registry.py tests/test_atlas_contract_registry.py` -> passed
8080 live model evidence: not required for GA3; this package is deterministic contract extraction/validation over post-apply preview content
Post-apply preview evidence: API endpoint mismatch test consumes GA1 preview output, not raw model fragments
Contract validation evidence: non-game examples covered API endpoint mismatch, env/config key mismatch, and JSON/YAML form/schema mismatch; WebGL conflict is surfaced as `resource:shared_app_surface`
Unavailable checks: no live model evidence required; no repair recipe application yet
Safety invariants: registry is read-only; no Proposal / Safe Apply / Verification bypass; violations are evidence, not direct apply authority
Remaining gaps: GA4 repair recipe registry, GA5 edit primitives, GA6 validators, GA7 live 8080 generic checks, GA8 entrypoint docs
Next package: GA4 — Repair Recipe Registry
Blocker: none
Proof level: `generic_contract_registry_component_complete`

---

## GA4 — Repair Recipe Registry (completed 2026-06-25)

Completed package: GA4 `codex/repair-recipe-registry`
Status: completed; ready for item PR publication and merge
Changed modules/files: `agent/atlas_repair_recipe_registry.py`, `agent/atlas_repair_recipes.py`, `tests/test_atlas_repair_recipe_registry.py`, this plan
Behavior implemented: added a generic repair recipe registry with `RepairRecipe` protocol, option lookup, selected-option application, and a registered `webgl_canvas_2d_context_conflict` recipe. Existing `apply_known_bug_repairs` remains compatible but now dispatches through the registry. Unsupported selected options return bounded `selected_option_not_implemented`; unknown violations return `no_recipe`.
Focused tests: `pytest -q tests/test_atlas_repair_recipe_registry.py` -> 4 passed
Affected tests: `pytest -q tests/test_atlas_repair_recipes_contract.py tests/test_atlas_contract_registry.py` -> 14 passed; `pytest -q tests/test_atlas_patch_proposal_codegen_contract.py tests/test_atlas_patch_output_minimization.py` -> 27 passed
Syntax checks: `py_compile agent/atlas_repair_recipe_registry.py agent/atlas_repair_recipes.py tests/test_atlas_repair_recipe_registry.py` -> passed
8080 live model evidence: not required for GA4; repairs are deterministic recipe dispatch after explicit violation evidence
Post-apply preview evidence: GA3 registry still produces the WebGL resource violation consumed by the repair registry
Contract validation evidence: WebGL conflict repair is now keyed by `resource` contract type and `webgl_canvas_2d_context_conflict` violation code
Unavailable checks: generic non-WebGL recipes are not implemented yet and return `no_recipe` or `selected_option_not_implemented`
Safety invariants: repair recipes do not guess semantic intent; registry returns bounded options/results; no Safe Apply bypass; no direct workspace apply
Remaining gaps: GA5 edit primitives, GA6 validators, GA7 live 8080 generic checks, GA8 entrypoint docs
Next package: GA5 — File-type-aware edit policy and primitives
Blocker: none
Proof level: `repair_recipe_registry_component_complete`

---

## GA5 — File-type-aware edit policy and primitives (completed 2026-06-25)

Completed package: GA5 `codex/filetype-edit-primitives`
Status: completed; ready for item PR publication and merge
Changed modules/files: `agent/atlas_edit_primitives.py`, `agent/atlas_file_safe_apply_executor.py`, `agent/atlas_plan_item_file_changes.py`, `agent/atlas_patch_proposal_service.py`, `agent/atlas_llm_schemas.py`, `agent/atlas_post_apply_preview.py`, `tests/test_atlas_edit_primitives.py`, this plan
Behavior implemented: added a file-type-aware edit policy and a bounded edit primitive vocabulary for weak models. Safe Apply now accepts `content_mode="edit_primitives"` / `edit_primitives` through proposal metadata and file changes, applies implemented primitives against current file content, and blocks unsupported primitives without falling back to raw full content. Implemented primitives cover exact replacement compatibility, JSON Pointer replacement, and conservative Python/JS/TS import insertion.
Focused tests: `pytest -q tests/test_atlas_edit_primitives.py` -> 22 passed
Affected tests: `pytest -q tests/test_atlas_file_safe_apply_executor.py tests/test_atlas_post_apply_preview.py` -> 34 passed; `pytest -q tests/test_atlas_patch_proposal_codegen_contract.py tests/test_atlas_patch_output_minimization.py` -> 27 passed
Syntax checks: `py_compile agent/atlas_edit_primitives.py agent/atlas_file_safe_apply_executor.py agent/atlas_plan_item_file_changes.py agent/atlas_patch_proposal_service.py agent/atlas_llm_schemas.py tests/test_atlas_edit_primitives.py` -> passed
8080 live model evidence: not required for GA5; this package defines deterministic schema, normalization, and Safe Apply behavior after model output. Live 8080 generic checks remain GA7.
Post-apply preview evidence: preview now passes `file_path` into Safe Apply content resolution so edit primitives can be resolved consistently in dry-run preview paths.
Contract validation evidence: unavailable for this slice; GA6 adds deterministic validators over post-apply preview output.
Unavailable checks: no live model evidence required; unsupported primitives beyond `replace_exact`, `search_replace`, `replace_json_pointer`, and `insert_import` are intentionally bounded rejections.
Safety invariants: unsupported primitives return `unsupported_edit_primitive`; missing existing target returns `edit_primitives_require_existing_file`; no fallback to full content when a primitive is present; Safe Apply remains the only disk-write authority.
Remaining gaps: GA6 validators, GA7 live 8080 generic checks, GA8 entrypoint docs
Next package: GA6 — Generic validators after preview
Blocker: none
Proof level: `file_type_edit_primitives_component_complete`

---

## GA6 — Generic validators after preview (completed 2026-06-25)

Completed package: GA6 `codex/generic-preview-validators`
Status: completed; ready for item PR publication and merge
Changed modules/files: `agent/atlas_post_apply_validators.py`, `tests/test_atlas_post_apply_validators.py`, this plan
Behavior implemented: added deterministic post-apply validators that consume `post_apply_content_by_path` and return structured violations plus per-validator status. Initial validators cover import/export mismatches, invalid JSON and JSON/form field mismatches, env/config key mismatches, API route reference mismatches, WebGL shared resource conflicts as resource violations, forbidden full-content preview metadata, and slice marker leakage.
Focused tests: `pytest -q tests/test_atlas_post_apply_validators.py` -> 7 passed
Affected tests: `pytest -q tests/test_atlas_post_apply_validators.py tests/test_atlas_contract_registry.py tests/test_atlas_post_apply_preview.py` -> 22 passed; `pytest -q tests/test_atlas_repair_recipe_registry.py tests/test_atlas_edit_primitives.py` -> 26 passed
Syntax checks: `py_compile agent/atlas_post_apply_validators.py tests/test_atlas_post_apply_validators.py` -> passed
8080 live model evidence: not required for GA6; validators are deterministic post-apply evidence checks. Live 8080 generic scenarios remain GA7.
Post-apply preview evidence: validators accept a `post_apply_content_by_path` map and optional preview metadata for full-content policy checks.
Contract validation evidence: Web app tests cover missing named export and missing API route handler; business/config tests cover env mismatch and invalid JSON; WebGL conflict is represented through the resource validator.
Unavailable checks: no live model evidence required for this deterministic slice
Safety invariants: validators are read-only; they do not apply repairs or write files; structured violations remain evidence for Proposal / Safe Apply / Verification rather than execution authority.
Remaining gaps: GA7 live 8080 generic checks, GA8 entrypoint docs
Next package: GA7 — 8080 weak-model generic live checks
Blocker: none
Proof level: `generic_post_apply_validators_component_complete`

---

## GA7 — 8080 weak-model generic live checks (completed 2026-06-25)

Completed package: GA7 `codex/generic-weak-llm-live-checks`
Status: completed; ready for item PR publication and merge
Changed modules/files: `tests/test_atlas_generic_weak_llm_live.py`, this plan
Behavior implemented: added a `real_model`-gated live evidence test that drives two temporary-workspace Atlas patch proposal scenarios through the local OpenAI-compatible 8080 model, then runs post-apply preview and generic validators without applying files to the repository workspace.
Focused tests: `pytest -q tests/test_atlas_generic_weak_llm_live.py -m real_model -s` -> 1 passed in 74.06s using localhost 8080
Affected tests: live GA7 test exercises `AtlasPatchProposalService`, `AtlasLLMJsonAdapter`, weak large-file edit policy, file-type edit policy, post-apply preview, and generic post-apply validators
Syntax checks: covered by pytest collection for `tests/test_atlas_generic_weak_llm_live.py`
8080 live model evidence: `GET http://127.0.0.1:8080/v1/models` returned `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`. Web app scenario `src/App.tsx` had 4334 chars / 152 lines, `large_existing_file` edit-only policy, output cap 1800, output mode `edits`, output tokens 42, preview `applied=true`, validator violations `[]`, no full-content acceptance. Business/config scenario `config/settings.json` had 63 chars / 2 lines, JSON file-type policy `json_pointer_required`, output cap 1800, output mode `edits`, output tokens 376, preview `applied=true`, validator violations `[]`, no full-content acceptance.
Post-apply preview evidence: both live scenarios reached preview with one applied change and zero blocked changes
Contract validation evidence: all generic validators passed for both post-apply maps; no contract violations were recorded
Unavailable checks: none for this run; 8080 was reachable and returned model/usage evidence
Safety invariants: no full-file token runaway; no slice fragment applied as full file; no raw `proposed_content` accepted under edit-only; tests run in temporary workspaces and use preview as the dry-run evidence path
Remaining gaps: GA8 entrypoint docs
Next package: GA8 — Documentation and agent workflow update
Blocker: none
Proof level: `generic_weak_llm_live_evidence_complete`

---

## GA8 — Documentation and agent workflow update (completed 2026-06-25)

Completed package: GA8 `codex/generic-agent-docs-update`
Status: completed; ready for item PR publication and merge
Changed modules/files: `AGENTS.md`, `Agent.md`, `docs/AGENTS.md`, this plan
Behavior implemented: aligned the root and docs agent entrypoints on the Generic Weak LLM App Hardening track, linked this active plan and the completed weak-LLM large-file base plan, marked GA1-GA7 complete, and kept the per-item PR workflow plus 8080 evidence requirement explicit.
Focused tests: documentation-only package; no product code path changed
Affected tests: `pytest -q tests/test_atlas_generic_weak_llm_live.py -m real_model -s` remained the GA7 live evidence gate before GA8; no additional runtime test required for doc-only changes
Syntax checks: markdown text inspection and `rg -n "generic_weak_llm_app_hardening_plan|weak_llm_large_file_edit_hardening_plan|GA8" AGENTS.md Agent.md docs/AGENTS.md docs/generic_weak_llm_app_hardening_plan.md`
8080 live model evidence: not required for GA8; GA7 recorded live 8080 model evidence with `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`
Post-apply preview evidence: unchanged from GA7
Contract validation evidence: unchanged from GA7
Unavailable checks: no live model evidence required for this documentation-only slice
Safety invariants: documentation preserves Proposal / Safe Apply / Verification authority, edit-only weak model constraints, truthful unavailable handling, and one-package-per-PR workflow
Remaining gaps: none for the Generic Weak LLM App Hardening package sequence
Next package: none for this track; choose a new active plan before continuing
Blocker: none
Proof level: `generic_agent_workflow_docs_complete`

---

# Global safety invariants

- `unavailable` is not `passed`.
- Mock output is not live model evidence.
- UI rendering is not runtime evidence.
- No code path may bypass Proposal / Safe Apply / Verification.
- Weak/standard large existing-file modify must remain edit-only.
- Raw full content is forbidden under edit-only unless converted into bounded surgical edits against non-sliced full content.
- Sliced content must never be promoted to full file content.
- Repair recipes must not guess semantic intent; they may apply only explicit, deterministic, locally provable transforms.
- Domain-specific repairs must live under registry-style extension points, not scattered top-level branches.
