# Atlas Autopilot Current Status (PR-ATLAS-PIPE-42B)

## Completed

- PR-ATLAS-PIPE-0〜42
- PR-SEARXNG-SECRET-SYNC-01

## Current

- PR-ATLAS-PIPE-42B

## Next

- PR-ATLAS-PIPE-43: Nexus Context Refresh for implementation/debug/evaluation

## Known Current Code Facts

- PR-42 adds read-only code intelligence tools.
- PR-42B hardens Code Intel tools for large repositories.
- Code Intel supports single-file relative_path, safe per-file read failures, dependency resolution metadata, and safe related test verification hints.
- PR-42B does not add arbitrary command execution, remote git operations, auto rollback, or Task/Agent APIs.

## Compatibility Markers
- PR-ATLAS-PIPE-0〜41
- PR-ATLAS-PIPE-41B
- PR-ATLAS-PIPE-42

## PR-ATLAS-PIPE-43 Context Refresh
- Adds bounded local-first Nexus Context Refresh bundles.
- Web/Deep Research require explicit manual policy and budget.
- No side effects: no safe_apply/verification/debug/patch/restore/rollback.
- Next: PR-ATLAS-PIPE-44 LLM Evaluator uses context bundle + diff/tests.


- PR-ATLAS-PIPE-43B hardens Context Refresh before LLM Evaluator: Nexus sources in bundle, changed_files metadata resolution, audit events, collector partial failure, and bundle API path-traversal safety.
\n## PR-ATLAS-PIPE-44B\n- Hardened evaluator: path safety, input packet resolution, diff_summary extraction, prompt contract, strict policy validation, no-side-effect guarantees.\n- Evaluator remains decision-only; PR-45 consumes evaluator results for multi-item guarded autopilot.
