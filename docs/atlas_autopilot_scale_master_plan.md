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
