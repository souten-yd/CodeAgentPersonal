# Codex 指示書 — PR3「Apply/各フェーズの詳細を status と UI に展開」

> 全体像は `docs/atlas_codex_pr_split_quality_visibility_plan.md`。**依存: PR2**（progress 基盤）。

## ゴール
item ごとに「どのサブ工程まで進み・何をしたか・修復を何回したか」を status と UI に展開し、
途中停止時の状態を判読可能にする。

## 現状（確認済みアンカー）
- item 結果 `AtlasAutopilotItemResult`（`agent/atlas_multi_item_autopilot_schema.py:64-77`）は
  `safe_apply_result`/`verification_result`/`metadata`/`warnings` を持つが、**時系列のサブ工程配列が無い**。
- 集約は `AtlasMultiItemAutopilotService.run()`（`agent/atlas_multi_item_autopilot_service.py:48-279`）。
  サブ工程の発生箇所: context_refresh(`:90-93`) / safe_apply(`:98-100`) / verification(`:118-120`) /
  repair(`:136-170`)。
- `_normalized_status`（`app/api/atlas_autonomous_codegen.py:113-197`）が UI 向けに整形。
  `_verification_summary`(`:311-317`) / `_repair_summary`(`:320-333`) が item_results を集計。
- ダッシュボード描画は `web/js/atlas_dashboard.js`。`badge()` ヘルパ(`:144-146`)、
  plan カード描画 `renderPlanList`(`:297-319`)。

## 実装タスク
1. **スキーマ**: `AtlasAutopilotItemResult`（`atlas_multi_item_autopilot_schema.py:64-77`）に
   `sub_phases: list[dict] = Field(default_factory=list)` を追加。各要素
   `{name, status, started_at, ended_at, detail}`。

2. **集約**: `atlas_multi_item_autopilot_service.py:48-279` の各サブ工程境界で
   `result.sub_phases.append({...})` を記録:
   - `safe_apply`（`:98-100` 後）: `detail = {changed_files, diff_line_count, backup_present}`
     （`result.safe_apply_result` から抽出）。
   - `verify`（`:118-120` / `:131-133` 後）: `detail = {command, exit_code, output_summary}`
     （`vr.model_dump()` から）。
   - `repair`（`:136-170`）: `detail = {attempt_count, attempts:[{status}]}`
     （`bounded_retry_result` / `self_correction_result` から）。
   started_at/ended_at は `datetime.now(timezone.utc).isoformat()`。

3. **status 素通し**: `_normalized_status`（`atlas_autonomous_codegen.py:159-193` の
   `evidence_summary`）に per-item `sub_phases` を含める。`_verification_summary`/`_repair_summary`
   は維持しつつ、`evidence_summary["item_sub_phases"] = [{item_id, status, sub_phases} for item in item_results]`
   を追加。

4. **UI**: `web/js/atlas_dashboard.js` に per-item 折りたたみタイムラインを描画。`badge()`(`:144`) を
   再利用し、apply→verify→(repair)→done を時系列カードで表示。データ源は status の
   `evidence_summary.item_sub_phases`。

## 制約
- 既存 `item_results` のキー削除・改名禁止（`sub_phases` は追加のみ）。
- status の既存キー互換を維持（PR2 の progress 整形とも互換）。

## 受け入れ条件
- 1 item の実行で apply→verify→(repair)→done のサブ工程が時系列で UI に出る。
- `pytest -q tests/test_atlas_multi_item_autopilot_service.py tests/test_atlas_autonomous_codegen_api.py`
  ＋ sub_phases 集約の新規テストが緑。

## 成果物
コード変更一式＋テスト。`claude/confident-cannon-SH4sV` にコミット。
