# Codex 指示書 — PR1「ゴール機能」自律コード生成の品質根本改修

> このファイルは Codex にそのまま渡せる単一ゴールの指示。詳細な根拠と他PRは
> `docs/atlas_codex_pr_split_quality_visibility_plan.md` を参照。

---

## ゴール
Atlas の自律コード生成（“ゴール機能”）の出力品質を、プラン step の `goal` と `acceptance_criteria` を
一級データとしてコード生成プロンプトまで確実に伝播させることで根本から底上げする。あわせて敵対的批評を
実際にプランへ反映し、未解決の high リスクが無検証で実行へ流れないようにする。

## なぜこれが効くか（データフロー）
コード生成プロンプトは `AtlasPatchProposalService` が `item.goal` と `item.done_definition` から組み立てる
（`agent/atlas_patch_proposal_service.py:235-236, 253`）。しかし現状、step の goal は途中で痩せる:
`PLAN_GENERATION_PROMPT`(`agent/agent_prompts.py:44`) が goal/acceptance を要求せず、
`ImplementationStep`(`agent/plan_schema.py:18-26`) にフィールドが無く、`PlannerPhase1`
(`agent/planner_phase1.py:148-159`) が LLM の goal を pydantic で破棄し、`AtlasPlanPoolBuilder`
(`agent/atlas_plan_pool_builder.py:212,249-251`) が description へフォールバックする。ここを通す。

## 実装タスク（順に実施）

1. **スキーマ**: `agent/plan_schema.py` の `ImplementationStep`(18-26) に
   `goal: str = ""` と `acceptance_criteria: list[str] = Field(default_factory=list)` を追加。

2. **プランナー取り込み**: `agent/planner_phase1.py:148-159` の `ImplementationStep(...)` 構築に
   `goal=str(item.get("goal") or item.get("description","")),` と
   `acceptance_criteria=_as_str_list(item.get("acceptance_criteria")),` を追加。
   フォールバック skeleton step(165-189) にも goal/acceptance_criteria を明示。

3. **pool 伝播**: `agent/atlas_plan_pool_builder.py:249-251` の `done_definition` の優先順を
   `step.get("acceptance_criteria")` を先頭に変更（acceptance → done_definition → verification → plan done）。

4. **プロンプト**: `agent/agent_prompts.py` の `PLAN_GENERATION_PROMPT`(27-67) を改訂。
   implementation_steps の要素に `goal` と `acceptance_criteria` を必須化(44)。Rules に
   「各 step は goal（要件のどの部分を満たすか1文）と 1件以上の観測可能な acceptance_criteria と
   具体的 verification を必ず出力」「ユーザー要件のキーフレーズ（表示文言・色・挙動）を該当 step の
   description に必ず織り込む」「空 description / 空 acceptance_criteria を出力禁止」を追記。

5. **改訂ループ**: `agent/task_planning_runner.py:343-360` の一度きり再生成を、最大2回まで再試行する
   ループへ変更。再生成が step を返さない／要件カバレッジ（requirement の functional_requirements・
   done_definition のキーフレーズが step description 群に出現する件数）が下がる場合は元プランを維持し
   warning `plan_revision_failed_kept_original` を立てる（無言フォールバック廃止）。全試行後も
   `critique.requires_revision` が残るなら後段の status 判定前に `plan.status="needs_revision"` を確定。

6. **リスクゲート**: `agent/task_planning_runner.py:371-376` を、`overall_risk in {"high","critical"}` かつ
   `review_result.blocking_findings` が非空なら autonomous でも `requires_user_confirmation=True` /
   `status="needs_confirmation"` にするよう強化（critical は従来どおり）。

7. **品質ゲート**: `agent/atlas_plan_quality_gate.py` の `apply_plan_quality_gate` に step 構造検査を追加。
   full_auto 時、空 description の step・空 acceptance_criteria の step・fallback のみの pool/test_plan を
   ブロッキング扱いにし `plan_revision_required=True` / `require_approval=True` を返す
   （`_finding_is_safety_sensitive` の安全判定には触れない）。

## 制約
- すべて後方互換（新フィールドはデフォルト付き）。既存スキーマのキー削除・改名禁止。
- 安全ゲート（critical / safety-sensitive 判定）の緩和は禁止。本PRは「より止める」方向のみ。
- UI・実行ランタイム・非同期化（PR2 以降）は対象外。
- 巨大ファイル(`main.py`/`ui.html`)は触らない。

## 受け入れ条件
- 入力「Hello World をレインボーで表示する HTML」で step が複数生成され、各 step が非空 description と
  1件以上 acceptance_criteria を持つ。
- 批評が high のとき改訂が反映される、または needs_revision でブロックされる。
- 新規テスト `tests/test_atlas_plan_goal_propagation.py` を追加: ImplementationStep の
  goal/acceptance_criteria が pool item の goal/done_definition に伝播することを検証。
- `pytest -q tests/test_atlas_plan_*.py tests/test_atlas_autopilot_task_plan_*.py tests/test_atlas_automation_features.py`
  および追加テストが緑。

## 成果物
- 上記コード変更一式 ＋ 新規テスト。
- 変更は `claude/confident-cannon-SH4sV` 上にコミット。コミットメッセージは目的を明記し、
  受け入れ条件のテスト結果を本文に記載すること。
