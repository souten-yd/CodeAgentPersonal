# AGENTS.md — KasaneCore 実装エージェント向け入口

このファイルは Codex / Claude などの実装エージェントが最初に読む入口です。タスクに着手する前に、対応する**正典の指示書（instruction doc）を必ず開いて、その手順・受け入れ基準・テストに従って**実装してください。

## 進行中の実装タスク（Active）

| タスク | 正典の指示書（これに従う） | 状態 |
|---|---|---|
| 視覚コントラクト false-negative 修正（色名 keyframes / motion 過剰必須） | [`docs/atlas_codex_visual_contract_falsenegative_instruction.md`](docs/atlas_codex_visual_contract_falsenegative_instruction.md) | 未着手 |
| プラン生成のウォッチドッグ / stall 検知（固定タイムアウト撤廃） | [`docs/atlas_codex_plan_watchdog_instruction.md`](docs/atlas_codex_plan_watchdog_instruction.md) | 未着手 |

> **実装ルール**: 上記タスクに着手するときは、まず該当の指示書を全文読み、冒頭の「実装計画（タスク・チェックリスト）」を作業の単一の source of truth とする。各タスク完了ごとにチェックボックスを更新してコミットすること。Phase / コミットは指示書の「実装順序」に従って分割する。**PR 作成・マージはユーザーの明示指示があるまで行わない。**

## このリポジトリの指示書（instruction doc）規約

- 設計・実装の正典は `docs/atlas_codex_*_instruction.md` および `docs/atlas_*_plan.md`。記憶や推測ではなく、必ず該当ファイルの file:line と手順に従う。
- PR の流れ・採番は `docs/atlas_unified_autopilot_pr_backlog.md` を参照。
- 変更後は関連 `pytest` を実行し、既存テストを壊さないこと。安全ゲート（承認・ロールバック・remote push 無効化など）の意味を変えないこと。

## 完了タスク（参考リンク）

- 直近: `safe_apply_exception` クラッシュ修正 / Playwright ブラウザ self-healing / runtime-smoke による視覚検証 override（PR #1565、main マージ済み）。
