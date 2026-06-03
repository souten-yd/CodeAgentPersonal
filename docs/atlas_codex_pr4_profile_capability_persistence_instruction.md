# Codex 指示書 — PR4「Profile / Capability preferences のサーバ永続化＋既定 Profile 4」

> 全体像は `docs/atlas_codex_pr_split_quality_visibility_plan.md`。**依存: なし。**

## ゴール
選択プロファイルと capability preferences をサーバ保存し、再起動・再接続後も復元する。
既定選択を完全自動（Profile 4 = `autonomous_bounded_dev`）にする（**実行可否はゲート/envelope を維持**）。

## 現状（確認済みアンカー）
- automation-features ストア `agent/atlas_automation_features.py` は **string 3 キーのみ**:
  `critical_handling`/`clarification_mode`/`quality_gate_enforcement`（`:28-36`）。
  `normalize_features`（`:51-58`）は値を `str().lower()` 正規化するため **dict 値は扱えない**。
  保存先 `{ca_data_root}/atlas/automation_features.json`（`:44,61-62`）。
- API `app/api/atlas_automation_features.py`: `GET ""`(`:20-23`) は
  `{features, defaults}` を返す、`POST ""`(`:26-30`) は `payload.features` を保存。
- capability スキーマは別ファイル `agent/atlas_capability_preference_schema.py`:
  `ALL_CAPABILITY_KEYS`(`:11-17`)、`get_default_preferences()`(`:66-68`、全 True)、
  `normalize_ui_preferences()`(`:52-63`、UI id↔backend key)、`apply_preferences()`(`:71-77`)。
- UI `web/js/atlas_claude_panel.js`: `state.selectedPresetId = 'review_only'`（`:30`）、
  preset ラジオ変更ハンドラ（`:239-246`）、presets ロード `refreshPolicies`（`:307-320`）。
- API ラッパ `web/js/atlas_pipeline_api.js`: `getAutomationFeatures`(`:186-188`) /
  `setAutomationFeatures`(`:189-191`)。

## 実装タスク
1. **ストア拡張（`agent/atlas_automation_features.py`）**: 保存構造を後方互換で拡張する。
   `automation_features.json` を
   ```json
   {"features": {...3キー...},
    "selected_preset_id": "autonomous_bounded_dev",
    "capability_preferences": {<ALL_CAPABILITY_KEYS>: bool}}
   ```
   に拡張。新規ヘルパ:
   - `load_full_automation_state(ca_data_root) -> {features, selected_preset_id, capability_preferences}`
   - `save_full_automation_state(ca_data_root, *, features, selected_preset_id, capability_preferences)`
   `selected_preset_id` は文字列正規化、`capability_preferences` は
   `agent/atlas_capability_preference_schema.normalize_ui_preferences` ＋ `get_default_preferences()`
   で検証（**`normalize_features` の str 正規化は通さない別ルート**）。
   既存 `load_automation_features`/`save_automation_features`/`resolve_features` は **シグネチャ維持**
   （旧形式 JSON も読めるよう、`features` キーが無ければ全体を features とみなすフォールバック）。
   既定 `selected_preset_id = "autonomous_bounded_dev"`。

2. **API 拡張（`app/api/atlas_automation_features.py`）**:
   - `GET ""`(`:20-23`) の戻りに `selected_preset_id` と `capability_preferences` を追加。
   - `AtlasAutomationFeaturesUpdate`(`:16-17`) に `selected_preset_id: str | None = None` と
     `capability_preferences: dict | None = None` を追加。`POST ""`(`:26-30`) で両方を受理・保存し、
     保存後の全状態を返す。後方互換: 旧 `{features:{...}}` のみの POST も従来どおり動く。

3. **UI 復元/保存（`web/js/atlas_claude_panel.js` / `atlas_pipeline_api.js`）**:
   - init/activate（`atlas_claude_panel.js:266-285` 周辺）で `getAutomationFeatures()` を呼び、
     `state.selectedPresetId` と 5 つの capability チェック（`cap-command-execution` 等、
     `atlas_capability_preference_schema.UI_ID_TO_KEY` のキー）を **サーバ値から復元**。
   - preset ラジオ変更（`:239-246`）と capability チェック変更時に `setAutomationFeatures(...)` で
     **POST 保存**。
   - localStorage は単なるキャッシュに降格（source of truth はサーバ）。
   - 既定表示は Profile 4（`autonomous_bounded_dev`）。
   - 「既定選択」と「自動実行可否」を分離: envelope 未起動/未確認なら従来どおり mutation を
     ブロックし、その旨を UI に明示（`updateSelectButtonState` のロジックは維持）。

## 制約
- 既存 3 キーの GET/POST 後方互換を壊さない（旧クライアント・旧 JSON が動くこと）。
- 「既定が Profile 4」と「envelope 無しで自動実行が走る」は**別物**。実行ゲート/envelope の緩和は禁止。

## 受け入れ条件
- Features 変更 → リロード → 値が保持される。
- 初期状態が Profile 4（`autonomous_bounded_dev`）。
- envelope 無しでは mutation がブロックされる（UI に明示）。
- `pytest -q tests/test_atlas_automation_features.py` ＋ 新規キー GET/POST 往復テストが緑。

## 成果物
コード変更一式＋テスト。`claude/confident-cannon-SH4sV` にコミット。
