# Atlas Scale Master Roadmap

## Atlasの最終目標

- 中〜大規模リポジトリでも安全に運用できる Atlas guarded autopilot を確立する。
- 実行系は常に human-in-the-loop を維持し、提案と実行を明確に分離する。
- local-first を維持しつつ、必要時のみ GitHub/CI 連携を段階的に有効化する。

## 現在の完成度

- Guarded loop の基盤（PR-ATLAS-PIPE-0〜60D）は完了。
- Repo context / planner packaging の初期段階（PR-ATLAS-SCALE-61〜63B）は完了。
- 次フェーズは verification planning と CI/GitHub read-only 連携の強化。

## Completed PRs

- PR-ATLAS-PIPE-0〜60D: completed
- PR-ATLAS-SCALE-61〜63B: completed
- PR-SEARXNG-SECRET-SYNC-01: completed

## Current Architecture

- PlanPool / Context Refresh / Evaluator / Supervised loop は分離された責務で構成。
- Repo Index は advisory 情報を提供し、実行を直接トリガーしない。
- Impacted tests は recommendation のみであり、自動実行はしない。
- Operator Loop は dry_run-first + one-action confirmation を維持。

## Remaining Roadmap

- verification planning の精度向上（repo context, changed files, dependency graph 利用）。
- PlanItem ごとの影響範囲可視化と説明可能性の向上。
- Context Refresh の安定化（大規模repo/部分失敗/キャッシュ整合性）。
- Planner Packaging v2 による入力品質向上。
- Verification recommendation UI と CI 失敗マッピング強化。
- GitHub read-only / Draft PR ワークフロー統合。

## PR-64〜PR-72計画

- **PR-ATLAS-SCALE-64**: Use repo context for verification planning and CI/test selection hints without auto execution。
- **PR-ATLAS-SCALE-65**: PlanItem Impact Map。
- **PR-ATLAS-SCALE-66**: Context Refresh v2。
- **PR-ATLAS-SCALE-67**: Planner Packaging v2。
- **PR-ATLAS-SCALE-68**: Verification Recommendation UI。
- **PR-ATLAS-SCALE-69**: CI Failure Mapping。
- **PR-ATLAS-SCALE-70**: GitHub Read-only Integration。
- **PR-ATLAS-SCALE-71**: Draft PR Workflow。
- **PR-ATLAS-SCALE-72**: Large Repo Readiness Milestone。

## Safety Policy

### 禁止事項

- execute all
- auto continue
- shell=True
- remote git
- automatic safe_apply
- automatic verification
- automatic retry
- automatic patch generation
- automatic test execution

### 許可事項

- read-only analysis
- recommendations
- metadata generation
- small-step execution
- human approval

## Milestones

- M1: PR-64〜66 で verification planning / context refresh の基盤を安定化。
- M2: PR-67〜69 で planner/verification/CI 提案品質を向上。
- M3: PR-70〜72 で GitHub read-only と Draft PR 運用を接続し、大規模repo readiness を達成。

## Future候補

- Repo scale profiling dashboard。
- Evidence traceability for recommendation rationale。
- Optional policy templates per repository size/team。
- Risk-tiered verification suggestion presets。
