# AGENTS.md — KasaneCore 実装エージェント向け入口

このファイルは Codex / Claude などの実装エージェントが最初に読む入口です。タスクに着手する前に、対応する**正典の指示書（instruction doc）を必ず開いて、その手順・受け入れ基準・テストに従って**実装してください。

## 進行中の実装タスク（Active・次に着手）

| タスク | 正典の指示書（これに従う） | 優先 | 状態 |
|---|---|---|---|
| パッチ生成のストール対策（ウォッチドッグをパッチ生成経路へ展開） | [`docs/atlas_codex_patchgen_watchdog_instruction.md`](docs/atlas_codex_patchgen_watchdog_instruction.md) | P0 | 未着手 |
| 視覚テスト網羅 WP-8（将来パターン・任意） | [`docs/atlas_codex_visual_test_coverage_instruction.md`](docs/atlas_codex_visual_test_coverage_instruction.md) | P2 | 任意・未着手 |

> **実装ルール**: 着手時はまず該当指示書を全文読み、冒頭の「実装計画／チェックリスト」を作業の単一 source of truth とする。各タスク完了ごとにチェックボックスを更新してコミット。**PR 作成・マージはユーザーの明示指示があるまで行わない。** 安全ゲート（承認・ロールバック・remote push 無効化など）の意味を変えない。

## 完了済みゴール（main マージ済み・参考）

| ゴール / タスク | 正典 | 状態 |
|---|---|---|
| 視覚コントラクト false-negative 修正（色名 keyframes / motion 連動 / smoke 診断） | [`docs/atlas_codex_visual_contract_falsenegative_instruction.md`](docs/atlas_codex_visual_contract_falsenegative_instruction.md) | ✅ 完了（#1565/#1569） |
| プラン生成ウォッチドッグ / stall 検知（Phase1+2） | [`docs/atlas_codex_plan_watchdog_instruction.md`](docs/atlas_codex_plan_watchdog_instruction.md) | ✅ 完了（#1569） |
| 連続実装ゴール（視覚修正＋ウォッチドッグ） | [`docs/atlas_codex_goal_visual_and_watchdog.md`](docs/atlas_codex_goal_visual_and_watchdog.md) | ✅ 完了 |
| requirement coverage 回帰修正（視覚 pass を覆さない） | （#1573） | ✅ 完了（#1573） |
| ブラウザ/視覚検証の網羅テスト + 既存実装改良（WP-0〜7） | [`docs/atlas_codex_visual_test_coverage_instruction.md`](docs/atlas_codex_visual_test_coverage_instruction.md) | ✅ 完了（WP-8 のみ任意で残）|

## このリポジトリの指示書（instruction doc）規約

- 設計・実装の正典は `docs/atlas_codex_*_instruction.md` および `docs/atlas_*_plan.md`。記憶や推測ではなく、必ず該当ファイルの file:line と手順に従う。
- PR の流れ・採番は `docs/atlas_unified_autopilot_pr_backlog.md` を参照。
- 変更後は関連 `pytest` を実行し、既存テストを壊さないこと。安全ゲート（承認・ロールバック・remote push 無効化など）の意味を変えないこと。

## 完了タスク（参考リンク）

- 直近: `safe_apply_exception` クラッシュ修正 / Playwright ブラウザ self-healing / runtime-smoke による視覚検証 override（PR #1565、main マージ済み）。
