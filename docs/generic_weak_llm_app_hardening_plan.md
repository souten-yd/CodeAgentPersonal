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
