# Codex 指示書 — フォローアップ（OpenCode 同等以上 / PR6+ 候補）

> 全体像は `docs/atlas_codex_pr_split_quality_visibility_plan.md` の「フォローアップ」節。
> PR1〜PR5 とは独立。優先度・依存を明記。各項目は単独 PR 化推奨。

## F1. 段階的 codegen ＋セルフレビュー（依存: PR1）
**現状:** 提案→適用は一発。verify 失敗時のみ `self_correction`（`agent/atlas_multi_item_autopilot_service.py:148-170`）。
**狙い:** 1 step を「生成→自己レビュー(lint/型/要件適合)→修正」まで **適用前**に閉じる内ループ化。
**実装の足場:** `AtlasPatchProposalService.propose_for_item`（`agent/atlas_patch_proposal_service.py`）の
生成直後に、生成内容に対する軽量セルフレビュー（lint/型/要件キーフレーズ照合）を 1 パス挿入し、
不合格なら同 item を再生成（最大 N 回）。`include_self_correction` 系の既存設定値を流用。
**受け入れ:** 明白な lint/型エラーや要件キーフレーズ欠落が適用前に1回は是正される。

## F2. 要件カバレッジ検証（依存: PR1）
**現状:** done_definition 達成は弱検証で trivially pass しがち（`compute_run_quality_rollup`
＝`agent/atlas_run_quality_rollup.py`、`atlas_multi_item_autopilot_service.py:256-276`）。
**狙い:** `done_definition` / `acceptance_criteria` を LLM か assertion で **実測**
（例「Hello World 文言が DOM に出る/色がアニメする」）。
**実装の足場:** `AtlasAutoVerificationService`（`agent/atlas_auto_verification_service.py`）に
acceptance_criteria を入力する検証パスを追加し、結果を `verification_result.metadata.requirement_coverage`
（既存キー、`atlas_multi_item_autopilot_service.py:425` が参照）へ書く。
**受け入れ:** acceptance を満たさない成果物が `completed` にならず `partial`/`needs_revision` になる。

## F3. MCP / Git 連携（依存: PR2 推奨）
**現状:** Draft PR は artifact 生成止まり（orchestrator `_prepare_draft_pr_artifact`
＝`agent/atlas_autonomous_codegen_orchestrator_service.py:258-280`、push/PR は手動）。
**狙い:** ブランチ作成〜push〜Draft PR を **envelope 内で安全に**閉じる。
**制約:** リモート mutation は capability/envelope ゲート必須。デフォルト OFF、明示許可時のみ。
**受け入れ:** envelope 有効時のみ push/PR が走り、無効時は従来どおり artifact 止まり。

## F4. リポジトリ全体コンテキスト（独立）
**現状:** `repo_context` は scope_summary 中心（`app/api/atlas_repo_index.py`、
`agent/atlas_code_intel_service.py`）。
**狙い:** `atlas_repo_index` をシンボル/依存グラフベースの関連ファイル抽出に強化し、
planner/patch generator に渡す関連ファイルの精度を上げる。
**受け入れ:** ある goal に対し、変更対象に隣接するシンボル/依存ファイルが上位に抽出される。

## F5. 巨大単一ファイルのモジュール分割（独立・低リスク先行可）
**現状:** `main.py`(778KB) / `ui.html`(853KB) が単一巨大ファイル → 自己改善時の安全編集を阻害。
**狙い:** ルート/機能単位に段階分割（`app/api/*` への移譲は既に進行中＝`docs/refactor_*` 群参照）。
**制約:** 1 PR=1 領域、各分割でエンドポイント契約を不変に保ち回帰テストで担保。
**受け入れ:** 分割後も既存 API/UI 契約テストが緑、ファイル行数が有意に低下。

## 進め方
F1/F2 は PR1 完了後に着手すると効果が高い（goal/acceptance が前提）。F5 は独立・低リスクで随時。
