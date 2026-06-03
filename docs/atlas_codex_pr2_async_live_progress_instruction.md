# Codex 指示書 — PR2「実行の非同期化とライブ進捗」

> 全体像と背景は `docs/atlas_codex_pr_split_quality_visibility_plan.md` を参照。依存: なし（PR3 の土台）。

## ゴール
完全自動コード生成を即時リターンのバックグラウンドジョブにし、実行中も `/status` から
「現在 item / 全件 / サブ工程 / 修復試行 / 経過・モデル待ち」を取得できるようにする。
**新規 API は作らない。** 既存 journal イベント＋`progress.json` 集約で実装する。

## 現状（確認済みアンカー）
- `POST /api/atlas/autonomous-codegen/start`（`app/api/atlas_autonomous_codegen.py:92-94`）は
  単に同期 `run()` を呼ぶだけ（即時化されていない）。
- `GET .../status/{pool}/{run}`（`:107-110`）は `read_result`（`:97-104`）に委譲。結果 JSON が無い実行中は
  **404**。
- `POST .../stop`（`:209-224`）は `stop_requested.json` を書くが、オーケストレータが読まない（no-op）。
- オーケストレータ `agent/atlas_autonomous_codegen_orchestrator_service.py`:
  - `run()`（`:53-284`）はフェーズを `out.phase` に直書きしつつ進める:
    understanding_goal(`:67`) → adversarial_review(`:96`) → candidate_generation(`:114`) →
    candidate_apply(`:193`） → final_summary(`:222`)。
  - 各境界で `self._emit(...)`（`:64,83,91,109,161,188,282`、定義 `:1511-1525`）が
    `journal.append_event(pool_id, run_id, {...})` する。
  - 結果は `save_result`（`:1527-1532`）が
    `{data_root}/atlas/autonomous_codegen/{pool_id}/{orchestrator_run_id}.json` と `latest.json` に書く。
  - フェーズ一覧定数 `_AUTONOMOUS_PHASES`（`:28-35`）。
- Phase 3 の item ループは `AtlasMultiItemAutopilotService.run()`
  （`agent/atlas_multi_item_autopilot_service.py:48-279`）。サブ工程と emit:
  context_refresh(`:90-93`) / safe_apply(`:98-100`) / verification(`:118-120`) /
  repair=bounded_retry・self_correction(`:136-170`)。`emit()` は `:371-374`。
- LLM 呼び出しは `AtlasLLMJsonAdapter`（`app/api/atlas_pipeline.py:401-409`、
  `app.state.atlas_llm_json_fn`）。

## 実装タスク
1. **progress ヘルパ（新規 `agent/atlas_codegen_progress.py`）**: `write_progress(data_root, pool_id, run_id, patch: dict)` /
   `read_progress(...)` / `request_stop(...)` / `is_stop_requested(...)` を実装。保存先は
   `{data_root}/atlas/autonomous_codegen/{pool_id}/{orchestrator_run_id}.progress.json`。
   スキーマ: `{phase, current_item_index, total_items, sub_phase, attempt, started_at,
   heartbeat_at, last_event, waiting_on_model_seconds, stop_requested}`。原子的書込（temp→rename）。

2. **即時化**: `app/api/atlas_autonomous_codegen.py` の `/start`（`:92-94`）を、`BackgroundTasks` を
   引数に取り、`orchestrator_run_id` を**事前生成**して即返すように変更。実体は
   `background_tasks.add_task(_orchestrator_service(...).run, payload_with_fixed_run_id)`。
   `run_id`/`orchestrator_run_id` を呼び出し前に確定させるため、`AtlasAutonomousCodegenRequest` に
   `orchestrator_run_id` を渡せるようにするか、`run()` を `orchestrator_run_id` 受け取り可能にする
   （`:55` の生成をオプション引数に）。`/run`（`:41-89`）は同期版として温存。
   返却: `{pool_id, run_id, orchestrator_run_id, phase:"understanding_goal", status:"running"}`。

3. **進捗 emit**: オーケストレータ `run()` の各フェーズ境界（`:67,96,114,193,222`）と Phase3 の
   item ループ（`atlas_multi_item_autopilot_service.py` の context_refresh/safe_apply/verification/repair
   境界）で `write_progress(...)` を呼び、`current_item_index`/`total_items`/`sub_phase`/`attempt`/
   `heartbeat_at`/`last_event` を更新する。`total_items=len(apply_item_ids)`。
   既存 `_emit`/`emit` 直後に progress 更新を**追記**する（イベント発火は壊さない）。

4. **/status の二段読み**: `app/api/atlas_autonomous_codegen.py:107-110` を、
   「最終結果 JSON（`{run}.json`）があれば従来どおり `_normalized_status`、無ければ
   `{run}.progress.json` を読み、`_normalized_status` とキー互換（`status`/`current_phase`/
   `plan_summary`(processed/total)/`next_action`/`controls`）に整形して返す」に変更。
   実行中 404 を解消。`read_result`（`:97-104`）はそのまま（結果専用）残す。

5. **モデルタイムアウト/ハートビート**: LLM json fn にタイムアウト（既定 180s、env
   `ATLAS_LLM_CALL_TIMEOUT_SECONDS` で可変）を入れる。`AtlasLLMJsonAdapter`
   （`app/api/atlas_pipeline.py:401-409`）呼び出しをラップし、待機中に `waiting_on_model_seconds` を
   progress に更新、超過時は当該呼び出しを例外/None で返して当該 attempt を `model_call_timeout`
   失敗扱いにし、既存の修復/停止判定（`atlas_multi_item_autopilot_service.py:212-223` の except）へ
   流す。**安全ゲートは変更しない。**

6. **協調停止**: `/stop`（`:209-224`）が `stop_requested.json` に加え `{run}.progress.json` の
   `stop_requested=true` も立てる。オーケストレータ `run()` のフェーズ境界・item ループ先頭で
   `is_stop_requested(...)` を確認し、`out.status="stopped"` / `out.stop_reason="user_stop_requested"`
   で安全に中断して `save_result`。

7. **(任意)** llama-server usage が取れる場合は `generated_tokens` / `ctx_used` / `ctx_max` を
   progress に転記。取れなければ経過秒＋ハートビートのみで可。

## 制約
- 新規 API ルート追加禁止（既存 `/start`/`/status`/`/stop` の挙動拡張のみ）。
- 安全ゲート（preflight/critique/full_auto 判定）の緩和禁止。
- 既存同期 `/run` の戻り値スキーマを壊さない。

## 受け入れ条件
- `/start` が即返る（`orchestrator_run_id` を含む）。
- 実行中 `/status` が `current_phase` と `plan_summary`(processed/total) と sub_phase 相当を返し 404 にならない。
- モデル無応答で `model_call_timeout` に遷移し、`/stop` が効いて `stopped` で終わる。
- `pytest -q tests/test_atlas_autonomous_codegen_api.py tests/test_atlas_multi_item_autopilot_api.py`
  ＋進捗/停止の新規テスト（`tests/test_atlas_codegen_progress.py`）が緑。

## 成果物
コード変更一式＋新規 progress ヘルパ＋テスト。`claude/confident-cannon-SH4sV` にコミット。
