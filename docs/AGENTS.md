# KasaneCore Agent Instructions

This file is an agent-facing entrypoint for implementation tasks under `docs/`.

## Current priority task

Start from:

- `docs/generic_weak_llm_app_hardening_plan.md`

Then read the completed safety base:

- `docs/weak_llm_large_file_edit_hardening_plan.md`

The new generic plan continues the completed weak LLM large-file edit hardening work and generalizes it for games, Web apps, and business applications.

## Core rule

Do not ask a weak model to rewrite large existing files. Force it to return small edits or SEARCH/REPLACE blocks, then let Atlas normalize, preview, validate, and gate the edit deterministically.

The repair system must stay generic:

```text
weak model chooses or describes the smallest edit
Atlas dry-runs the post-apply content in memory
generic contracts validate the post-apply state
domain-specific repairs run only through a registry
Safe Apply remains the only authority that changes files
```

Do not add game-only special cases at the patch service top level. WebGL/Canvas repair is one domain recipe, not the framework.

## Current package order

Use `docs/generic_weak_llm_app_hardening_plan.md` and implement:

1. GA1 — Post-Apply Preview for generic validation
2. GA2 — Harden sliced-content salvage
3. GA3 — Generic Contract Registry
4. GA4 — Repair Recipe Registry
5. GA5 — File-type-aware edit policy and primitives
6. GA6 — Generic validators after preview
7. GA7 — 8080 weak-model generic live checks
8. GA8 — Documentation and agent workflow update

## Main files

- `agent/atlas_patch_proposal_service.py`
- `agent/atlas_file_safe_apply_executor.py`
- `agent/atlas_edit_format.py`
- `agent/atlas_repair_recipes.py`
- `agent/model_forge/weak_large_file_edit_policy.py`

Likely new files:

- `agent/atlas_post_apply_preview.py`
- `agent/atlas_contracts.py`
- `agent/atlas_contract_registry.py`
- `agent/atlas_repair_recipe_registry.py`
- `agent/atlas_edit_primitives.py`

## Live validation

The user may provide a weak OpenAI-compatible LLM on:

```text
http://127.0.0.1:8080/v1
```

After implementation, run live weak-LLM checks outside the game/WebGL case when available:

- one Web app scenario;
- one business/config scenario.

Success means bounded behavior: small edit success, post-apply preview validation, or clear bounded rejection. It does not require the weak model to be semantically perfect.

## Must preserve

- No code path may bypass Proposal / Safe Apply / Verification.
- Weak/standard large existing-file modify remains edit-only.
- Raw full content is forbidden under edit-only unless converted into bounded surgical edits against non-sliced full content.
- Sliced content must never become full file content.
- Domain-specific repairs must live under registry-style extension points.
- `unavailable` is not `passed`.
- Mock output is not live model evidence.
