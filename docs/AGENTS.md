# KasaneCore Agent Instructions

This file is an agent-facing entrypoint for implementation tasks under `docs/`.

## Current priority task

Start from:

- `docs/weak_llm_large_file_edit_hardening_plan.md`

This plan contains the implementation instructions for weak LLM large-file edit hardening.

## Core rule

Do not ask a weak model to rewrite large existing files. Force it to return small edits or SEARCH/REPLACE blocks, then let Atlas apply, validate, and gate the edit deterministically.

## Main files

- `agent/atlas_patch_proposal_service.py`
- `agent/model_forge/weak_large_file_edit_policy.py`
- `agent/atlas_edit_format.py`
- `agent/atlas_file_safe_apply_executor.py`
- `tests/test_atlas_weak_large_file_edit_policy_contract.py`
- `tests/test_atlas_focused_patch_extraction.py`
- `tests/test_atlas_edit_format_contract.py`

## Live validation

The user may provide a weak OpenAI-compatible LLM on:

```text
http://127.0.0.1:8080/v1
```

After implementing the plan, run at least one live weak-LLM large existing-file modify scenario and confirm bounded behavior: small edit success or clear bounded rejection, not full-file token runaway.
