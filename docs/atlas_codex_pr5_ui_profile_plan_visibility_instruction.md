# Codex 指示書 — PR5「UI：Profile 3/4 の差を明示＋戦略プランの視認性向上」

> 全体像は `docs/atlas_codex_pr_split_quality_visibility_plan.md`。**依存: PR1**（step の goal/acceptance_criteria）。

## ゴール
プリセットの機能差を一目で分かるようにし、戦略プランを構造化表示する。

## 現状（確認済みアンカー）
- ダッシュボード `web/js/atlas_dashboard.js`:
  - `badge(label, status)` ヘルパ（`:144-146`）。
  - `renderPlanList`（`:297-319`）は各 item を title＋`item_type`/`status`/`risk_level` バッジ＋
    `description`＋`depends_on`/`target_files` 件数だけ表示。**goal / acceptance_criteria /
    verification / rollback / test は出していない。**
  - `renderCurrentItem`（`:331-344`）も description/goal のみ。
- パネル `web/js/atlas_claude_panel.js`:
  - `state.presets`（`:28`、`refreshPolicies` `:307-320` で `automation_profile_presets` をロード）。
  - preset ラジオ（name=`atlas-claude-preset`、`:239-246`）。
  - `renderPresetSummary()`（preset 概要描画。grep で確認して該当関数に追記）。
- CSS `web/css/app.css`（バッジ等のスタイル定義先、`.atlas-badge*`）。

## 実装タスク
1. **プリセット badge（`atlas_claude_panel.js` の `renderPresetSummary` ＋ `app.css`）**:
   各 preset に `enables_full_automation`（ON/OFF）と `envelope`（none/bounded_dev）の badge を表示
   （`badge()` 相当 or 新規 span）。ラベルを差が読める文言に:
   - 「3: Autonomous（毎回 bounds 指定・完全自動 OFF）」
   - 「4: Autonomous（envelope 内で完全自動・★完全自動コード生成）」
   preset データのどのキーが full_automation/envelope を表すかは `state.presets` の各要素を
   `console`/テストで確認して対応付ける（`automation_profile_presets` の項目）。

2. **戦略プランのカード化（`atlas_dashboard.js:renderPlanList` `:297-319`）**:
   item カードに **PR1 で追加した `goal` と `acceptance_criteria`** を加え、
   ゴール / アプローチ / step（各: 目標・対象ファイル・受け入れ条件・検証・ロールバック・risk の
   ラベル付き）/ リスク / テスト / 完了条件 に分割表示する。
   - `item.goal`、`arr(item.acceptance_criteria || item.done_definition)`、`item.verification`、
     `item.rollback_plan`、`item.risk_level` をラベル付きで描画。
   - レビュー・敵対的批評は「未解決のみ強調＋解決済みは畳む」。
   - 生プラン（plan JSON）は `<details>` collapsible にする。
   `esc()` でのエスケープを維持し、XSS を作らないこと。

3. **CSS（`web/css/app.css`）**: 新規バッジ/カード/タイムライン/`<details>` のスタイルを
   既存 `.atlas-badge` 系の規約に合わせて追加。

## 制約
- 表示のみ。実行ロジック・API・ゲートには触れない。
- 既存 `renderPlanList`/`renderPresetSummary` の他の描画を壊さない。
- PR1 未マージ環境でも壊れないよう、`goal`/`acceptance_criteria` は欠損時フォールバック
  （`item.goal || item.description`、空配列）を入れる。

## 受け入れ条件
- Profile 3 と 4 の差が説明なしで分かる（badge＋文言）。
- プランがゴール/step（目標・対象ファイル・受け入れ条件・検証・ロールバック・risk）/リスク/テスト/
  完了条件に整理表示される。生プランは折りたたみ。
- `pytest -q tests/` のうち UI 契約テスト（例 `tests/test_atlas_autopilot_ui_contract.py`）が緑。

## 成果物
コード変更一式＋（あれば）UI 契約テスト更新。`claude/confident-cannon-SH4sV` にコミット。
