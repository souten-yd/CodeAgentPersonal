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

## PR-73〜PR-82 Autonomous Development Roadmap

- **PR-73: Workspace Snapshot & Restore Foundation**
  - 実行前snapshot
  - changed files manifest
  - restore point作成
  - full rollback API
  - no auto restore yet
- **PR-74: Patch Transaction Manager**
  - patch apply transaction
  - before/after hash保存
  - partial failure検出
  - rollback candidate生成
- **PR-75: Autonomous Execution Policy v1**
  - auto-run可能範囲をpolicy化
  - safe / medium / high risk分類
  - low-riskのみ連続実行許可
- **PR-76: Auto Verification Loop**
  - suggested testsを自動実行
  - failed test解析
  - retry plan生成
  - patch再生成はまだ人間承認
- **PR-77: Auto Patch Regen Loop**
  - failed verificationからpatch再生成
  - dry-run
  - diff review
  - policy内なら再適用
- **PR-78: Full Task Autopilot v1**
  - goal → plan → implement → test → fix loop
  - max iteration / max files / max risk制限
  - restore point必須
- **PR-79: Self-Improvement Guardrails**
  - CodeAgentPersonal自身の改修専用policy
  - core files変更時は厳格gate
  - launcher / Docker / UI / API変更の安全分類
- **PR-80: Self-Improving CodeAgent Platform v1**
  - AtlasでCodeAgentPersonal自身を改修
  - snapshot → implement → test → rollback/commit candidate
  - PR生成候補まで
- **PR-81: GitHub Branch / Draft PR Automation**
  - branch作成
  - commit candidate
  - draft PR作成
  - CI monitor
  - 失敗時修正loop
- **PR-82: Autonomous Development Milestone**
  - 大規模repo一気通貫評価
  - recovery / rollback検証
  - self-improvement検証

## 9. Final Vision: Autonomous Development Platform

- Atlasの最終像
  - large repo coding agent
  - goal → research → plan → implement → test → fix → PR
  - self-improving CodeAgentPersonal/KasaneCore platform
- 完全自動化の前提条件
  - workspace snapshot
  - restore point
  - patch transaction
  - before/after hash
  - test/CI artifact
  - rollback verified
  - human policy gates
- 安全境界
  - low-riskのみ自動化
  - medium/high-riskはapproval必須
  - core/runtime/Docker/launcher変更はstrict gate
  - self-modificationは専用policy

## Milestones (Extended)

- Milestone G: Transactional Development Foundation
  - Target: PR-73〜75
- Milestone H: Autonomous Verification / Fix Loop
  - Target: PR-76〜78
- Milestone I: Self-Improving Platform
  - Target: PR-79〜82

## Atlas Constitution / Checklist Reference Update

- docs/atlas_development_constitution.md
- docs/atlas_preflight_checklist.md
- docs/atlas_postflight_checklist.md
- docs/atlas_pr_template.md
- docs/atlas_self_development_rules.md

Current PR:
- PR-ATLAS-DOCS-CONSTITUTION-01

Next PR:
- PR-ATLAS-SCALE-64: Use repo context for verification planning and CI/test selection hints without auto execution

Known Current Code Facts:
- Atlas development must follow constitution/preflight/postflight docs.
- Future self-development requires snapshot/restore foundation before autonomous modification.



## PR-ATLAS-SCALE-64
- Completed: PR-ATLAS-SCALE-64
- Current PR: PR-ATLAS-SCALE-66B
- Next PR: PR-ATLAS-SCALE-68: Verification Recommendation UI using Planner Packaging v2
- Verification planning is advisory-only.
- Suggested commands are never executed.
- CI/test selection hints are local metadata only.
- Missing Repo Index remains non-blocking.
- No GitHub CI fetching or GitHub write operations are introduced.


## PR-ATLAS-DOCS-QUALITY-GATE-01

- Adds runtime-chain contract-test quality rules.
- Requires adversarial self-review for all future Atlas PRs.
- Prohibits string-only tests as sufficient completion evidence.
- Requires UI runtime-chain checks for DOM/API/binding/endpoint/unwrap/render/cache-bust.
- Requires backend runtime-chain checks for router/endpoint/data_root/service/response/safety flags.
- Next PR: PR-ATLAS-SCALE-68: Verification Recommendation UI using Planner Packaging v2.

- Historical marker: PR-ATLAS-SCALE-65B

- Historical completed item: PR-ATLAS-SCALE-66: Context Refresh v2 using PlanItem Impact Map.

- Next PR: PR-ATLAS-SCALE-68: Verification Recommendation UI using Planner Packaging v2


## PR-ATLAS-SCALE-67B
- Completed PR: PR-ATLAS-SCALE-67B
- Current PR: PR-ATLAS-SCALE-67B
- Next PR: PR-ATLAS-SCALE-68: Verification Recommendation UI using Planner Packaging v2
- Planner Packaging v2 remains advisory-only and manual-only.
- Planner Packaging v2 uses Context Refresh v2 and PlanItem Impact Map.
- No execution semantics added.
