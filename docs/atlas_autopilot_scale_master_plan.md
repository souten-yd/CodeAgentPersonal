# Atlas Autopilot Scale Master Plan (PR-ATLAS-PIPE-41B)

## Current Completed Baseline

- PR-40: auto verification failure stop + manual restore suggestion
- PR-41: Dev Tooling Pack 1 read-only local repo inspection tools
- PR-SEARXNG-SECRET-SYNC-01: Windows SearXNG secret_key sync fix

## Goal

- 中〜大規模プロジェクトの guarded autopilot
- local-first
- GitHub optional
- 認証なしでも local repo で修正/検証/restore 可能
- GitHub auth is only needed for remote operations (clone/pull/push/PR/Actions 取得)

## Roadmap

- PR-41B: design docs reconciliation
- PR-42: Dev Tooling Pack 2 - symbol index, dependency graph, related tests
- PR-43: Nexus Context Refresh for implementation/debug/evaluation
- PR-44: LLM Evaluator using diff/tests/dev tools/Nexus context
- PR-45: multi-item guarded autopilot
- PR-46: bounded retry loop
- PR-47: supervised patch regeneration
- PR-48: large project module graph / impact analysis
- PR-49: optional GitHub remote integration
- PR-50: Autopilot dashboard / run recovery


### PR-42 Update
- `symbol_index`, `dependency_graph`, `related_tests` are local-first and GitHub optional.
- GitHub auth is only needed for remote operations.
- Next milestone: PR-43 Nexus Context Refresh for implementation/debug/evaluation.

## PR-ATLAS-PIPE-43 Context Refresh
- Adds bounded local-first Nexus Context Refresh bundles.
- Web/Deep Research require explicit manual policy and budget.
- No side effects: no safe_apply/verification/debug/patch/restore/rollback.
- Next: PR-ATLAS-PIPE-44 LLM Evaluator uses context bundle + diff/tests.


- PR-ATLAS-PIPE-43B hardens Context Refresh before LLM Evaluator: Nexus sources in bundle, changed_files metadata resolution, audit events, collector partial failure, and bundle API path-traversal safety.
