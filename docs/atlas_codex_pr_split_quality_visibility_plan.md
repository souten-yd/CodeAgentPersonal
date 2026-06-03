# Atlas Codex 改修計画 — 成果物品質と実行可視化（PR1〜PR5 ＋ フォローアップ）

> 目的: 自律コード生成（Atlas Autonomous Codegen / “ゴール機能”）を「生成しっぱなし」から脱却させ、
> (a) プラン品質を強制し批評を実際に反映する、(b) 実行を非同期化して進捗・ハングを可視化する、
> (c) プロファイル/設定をサーバ永続化し UI を判読可能にする。
>
> 本書は **Codex / Atlas が単独で実装着手できる参照可能計画** である。各 PR は対象ファイルの
> 現在の行番号・関数・データフローに紐づく。行番号は記載時点（`claude/confident-cannon-SH4sV`）の
> ものなので、着手時は関数名・シンボルで再確認すること。

### Codex 指示書インデックス（diff レベル・各 PR を Codex にそのまま渡せる）
| PR | 指示書 | 依存 |
|----|--------|------|
| PR1 | `docs/atlas_codex_pr1_goal_feature_instruction.md` | なし（最優先） |
| PR2 | `docs/atlas_codex_pr2_async_live_progress_instruction.md` | なし |
| PR3 | `docs/atlas_codex_pr3_subphase_detail_instruction.md` | PR2 |
| PR4 | `docs/atlas_codex_pr4_profile_capability_persistence_instruction.md` | なし |
| PR5 | `docs/atlas_codex_pr5_ui_profile_plan_visibility_instruction.md` | PR1 |
| F1〜F5 | `docs/atlas_codex_followups_opencode_parity_instruction.md` | 各記載 |

推奨着手順: **PR1 → PR2**（体感改善大）→ PR3/PR4/PR5 → フォローアップ。

---

## 0. 背景：goal/done_definition データフロー（PR1 の根拠）

自律コード生成のプロンプトは `AtlasPatchProposalService` が `item.goal` と `item.done_definition`
から組み立てる（`agent/atlas_patch_proposal_service.py:235-236`、`:253`）。つまり **プラン item の
`goal` と `done_definition` の品質が、そのまま生成コードの品質を決める。**

ところが現状のデータフローでは goal が痩せる：

1. `PLAN_GENERATION_PROMPT`（`agent/agent_prompts.py:44`）は step に
   `{title,description,target_files,action_type,risk_level,verification,rollback}` しか要求していない
   （`goal` も `acceptance_criteria` も無い）。
2. `ImplementationStep` スキーマ（`agent/plan_schema.py:18-26`）にも `goal` / `acceptance_criteria`
   フィールドが無い。pydantic v2 は未知キーを破棄するため、仮に LLM が `goal` を返しても
   `PlannerPhase1`（`agent/planner_phase1.py:148-159`）で `ImplementationStep` を組み立てる際に **捨てられる**。
3. `AtlasPlanPoolBuilder.build_from_plan_payload`（`agent/atlas_plan_pool_builder.py:212`）は
   `step.get("goal")` を読むが、上記により常に空 → `description or title or root_goal` にフォールバック。
   `done_definition` も `step.get("done_definition") or step.get("verification") or payload.get("done_definition")`
   （`:249-251`）に依存し、step 個別の受け入れ条件が無いと plan 全体の done_definition に薄まる。

**結論:** `goal` / `acceptance_criteria` を ImplementationStep の一級フィールドに昇格し、プロンプトで
必ず埋めさせ、pool item まで伝播させることが品質改善の根本。これが PR1。

---

## PR1 — プラン品質と批評反映の強制（最優先）

**Goal:** すべての実装 step が「要件に紐づく実装目標・受け入れ条件・具体的検証」を必ず持ち、敵対的批評を
実際にプランへ反映し、未解決の high リスクが無検証で実行へ流れないようにする。

**対象ファイル:**
- `agent/plan_schema.py`
- `agent/agent_prompts.py`（`PLAN_GENERATION_PROMPT`）
- `agent/planner_phase1.py`
- `agent/atlas_plan_pool_builder.py`
- `agent/task_planning_runner.py`
- `agent/atlas_plan_quality_gate.py`

### 変更点

**1. スキーマ拡張（`agent/plan_schema.py:18-26`）**
`ImplementationStep` に次を追加（後方互換のためデフォルト付き）:
```python
goal: str = ""
acceptance_criteria: list[str] = Field(default_factory=list)
```

**2. プランナーで取り込む（`agent/planner_phase1.py:148-159`）**
`ImplementationStep(...)` 構築時に下記を追加し、空なら description にフォールバック:
```python
goal=str(item.get("goal") or item.get("description", "")),
acceptance_criteria=_as_str_list(item.get("acceptance_criteria")),
```
フォールバックの skeleton step（`:165-189`）にも `goal` / `acceptance_criteria` を明示的に与える。

**3. pool への伝播（`agent/atlas_plan_pool_builder.py`）**
- `goal`（`:212`）はそのままで OK（step.goal が埋まるので機能する）。
- `done_definition`（`:249-251`）の優先順に **`step.get("acceptance_criteria")` を先頭に追加**:
  ```python
  done_definition=coerce_list(
      step.get("acceptance_criteria")
      or step.get("done_definition")
      or step.get("verification")
      or payload.get("done_definition")
  ),
  ```

**4. プロンプト改訂（`agent/agent_prompts.py:27-67` の `PLAN_GENERATION_PROMPT`）**
`implementation_steps` の要素スキーマを次に変更（`:44`）:
```
- implementation_steps: [{title, description, goal, target_files, action_type,
  risk_level, acceptance_criteria, verification, rollback}]
```
さらに Rules を追記:
- 各 step に **goal**（この step が要件のどの部分を満たすか1文）、**acceptance_criteria**
  （観測可能な合否条件の string[]、1件以上）、**verification**（具体コマンド or 観測項目）を必ず出力。
- ユーザー要件のキーフレーズ（表示文言・色・挙動など）を該当 step の description に必ず織り込む。
- 空 description / 空 acceptance_criteria の step を出力してはならない。

**5. 改訂ループの修正（`agent/task_planning_runner.py:343-360`）**
現状は批評が `requires_revision` のとき **一度だけ**再生成し、`revised.implementation_steps` が
空なら無言で元プランを使う。これを:
- 最大 **2回**まで再試行するループにする。
- 再生成プランが step を返さない／要件カバレッジが下がった場合は元プランを維持しつつ warning
  `plan_revision_failed_kept_original` を立てる（無言フォールバック廃止）。
- 全試行後も `critique.requires_revision` が残るなら、後段（`:371-376`）の status 判定の前に
  `plan.status = "needs_revision"` を確定させ、自律実行をブロックする。
  - 「要件カバレッジ」は簡易判定でよい: requirement の functional_requirements / done_definition の
    キーフレーズが plan の step description 群に何件出現するかの単純カウント。低下＝採用しない。

**6. リスクゲート強化（`agent/task_planning_runner.py:371-376`）**
現状は `overall_risk == "critical"` のみ status を変える。これを:
```python
unresolved_high = bool(review_result.blocking_findings) and review_result.overall_risk in {"high", "critical"}
if review_result.overall_risk == "critical":
    plan.status = "rejected" if review_result.recommended_next_action == "reject_plan" else "needs_revision"
elif unresolved_high:
    plan.requires_user_confirmation = True
    plan.status = "needs_confirmation"
elif review_result.requires_user_confirmation:
    plan.status = "needs_confirmation"
else:
    plan.status = "planned"
```
（high かつ未解決 blocking finding があるなら autonomous プロファイルでも確認を要求。`blocking_findings`
は `_merge_critique_into_review` が `agent/task_planning_runner.py:453-474` で adversarial 由来を追加済み。）

**7. 品質ゲート昇格（`agent/atlas_plan_quality_gate.py`）**
`apply_plan_quality_gate` に「step 構造検査」を追加する。自律実行（full_auto）時に次を **ブロッキング**扱い:
- 空 `description` の step が存在
- 空 `acceptance_criteria` の step が存在
- pool が fallback のみ（`metadata.fallback_plan_items_generated == True`）または test_plan が fallback のみ
判定結果は `plan_item_goal_missing` を従来の非ブロッキング warning から **blocking** へ昇格させ、
`plan_revision_required=True` / `require_approval=True` を返す。
（安全側 keyword 検査 `_finding_is_safety_sensitive` のロジックには触れない。）

### Acceptance
入力「Hello World をレインボーで表示する HTML」で:
- (a) step が複数生成され、各 step が非空 `description` と 1件以上の `acceptance_criteria` を持つ。
- (b) 批評が high のとき改訂が反映される、または `needs_revision` でブロックされる。
- (c) 既存テスト緑: `pytest -q tests/test_atlas_plan_*.py tests/test_atlas_autopilot_task_plan_*.py`
- (d) 新規テスト: ImplementationStep の goal/acceptance_criteria が pool item の goal/done_definition に
  伝播することを `tests/test_atlas_plan_goal_propagation.py`（新規）で検証。

### Out of scope
実行ランタイム・UI（PR2 以降）。

---

## PR2 — 実行の非同期化とライブ進捗

**Goal:** 完全自動実行を即時リターンのバックグラウンドジョブにし、実行中に
`現在の item / 全件 / サブ工程 / 修復試行 / 経過・モデル待ち` を `/status` から取得可能にする。
**追加 API は作らず**、既存 journal イベント＋`progress.json` 集約で実装する。

**対象ファイル:**
- `app/api/atlas_autonomous_codegen.py`
- `app/api/atlas_multi_item_autopilot.py`
- `agent/atlas_multi_item_autopilot_service.py`
- `agent/atlas_autonomous_codegen_orchestrator_service.py`
- LLM json fn ラッパ（`app/api/atlas_pipeline.py` の `register_atlas_llm_json_adapter` 周辺）

### 現状
- `/start`（`app/api/atlas_autonomous_codegen.py:92-94`）は単に `run()` を同期呼び出し（即時化されていない）。
- `/status`（`:107-110`）は結果 JSON を読むだけ。実行中はファイルが無く `read_result` が **404**（`:102-103`）。
- `/stop`（`:209-224`）は `stop_requested.json` を書くが、オーケストレータのループがそれを見ていない。

### 変更点
1. **即時化:** `/start` を `BackgroundTasks`（または `app/api/jobs.py` の既存ジョブ機構）で実行し、
   生成した `orchestrator_run_id` を即返す。`/run`（`:41-89`）は同期版として残す。
2. **progress.json:** 実行開始時に
   `ca_data/atlas/autonomous_codegen/{pool_id}/{orchestrator_run_id}.progress.json` を作成。
   各フェーズ完了 emit のたびに次を更新:
   ```json
   {"phase": "...", "current_item_index": 1, "total_items": 3,
    "sub_phase": "context_refresh|patch_proposal|safe_apply|verify|repair",
    "attempt": 1, "started_at": "...", "heartbeat_at": "...", "last_event": "...",
    "waiting_on_model_seconds": 0, "stop_requested": false}
   ```
   `AtlasMultiItemAutopilotService`（`agent/atlas_multi_item_autopilot_service.py`）の item ループと
   オーケストレータ（`agent/atlas_autonomous_codegen_orchestrator_service.py`）のフェーズ境界で更新する。
3. **/status の二段読み:** `app/api/atlas_autonomous_codegen.py:107-110` を
   「最終結果 JSON があればそれを `_normalized_status` で返す、無ければ `*.progress.json` を読んで
   進捗形に整形して返す（実行中 404 を解消）」へ変更。progress 整形は `_normalized_status` と
   キー互換（`status`/`current_phase`/`plan_summary`/`next_action`）を保つ。
4. **モデルタイムアウト/ハートビート:** LLM json fn ラッパに timeout（既定 180s、設定可）を入れ、
   待機中は `waiting_on_model_seconds` を更新。超過時は当該 attempt を `model_call_timeout` で失敗扱いにし、
   修復/停止判定へ回す。
5. **協調停止:** progress に `stop_requested` を持たせ、`/stop`（`:209-224`）が
   `{run}.progress.json` の `stop_requested=true` も立てるようにし、オーケストレータのループ先頭で確認して
   安全に中断する。
6. **(任意)** llama-server の usage が取れる場合は `generated_tokens` / `ctx_used` / `ctx_max` を
   progress に転記。取れなければ経過秒＋ハートビートのみで可。

### Acceptance
- `/start` が即返る（`orchestrator_run_id` を含む）。
- 実行中 `/status` が `current_item_index`/`total_items` と `sub_phase` を返す（404 にならない）。
- モデル無応答時に `model_call_timeout` で進捗が遷移し、`/stop` が効く。
- `pytest -q tests/test_atlas_autonomous_codegen_api.py tests/test_atlas_multi_item_autopilot_api.py` 緑。

**依存:** なし（PR3 の土台）。

---

## PR3 — Apply/各フェーズの詳細を status と UI に展開

**Goal:** item ごとに「どのサブ工程まで進み・何をしたか・修復を何回したか」を可視化し、途中停止時の
状態を判読可能にする。

**対象:** `app/api/atlas_autonomous_codegen.py`（`_normalized_status` `:113-197`）、
`agent/atlas_multi_item_autopilot_service.py`（`item_results` 集約）、
`web/js/atlas_dashboard.js`（進捗描画）。

### 変更点
- `item_results` 各要素に `sub_phases: [{name, status, started_at, ended_at, detail}]` を含める:
  - `safe_apply`: 書込ファイル / 差分行数 / バックアップ有無
  - `verify`: command / exit_code / 出力要約
  - `repair`: attempt 数と各結果
- `_normalized_status` の `evidence_summary`（`:159-193`）に per-item サブ工程を素通しする
  （既存 `_verification_summary` `:311-317` / `_repair_summary` `:320-333` を拡張）。
- `web/js/atlas_dashboard.js` に per-item の折りたたみタイムラインを描画（apply→verify→(repair)→done）。

### Acceptance
1 item の実行で apply→verify→(repair)→done のサブ工程が時系列で UI に出る。
**依存:** PR2。

---

## PR4 — Profile / Capability preferences のサーバ永続化＋既定 Profile 4

**Goal:** 選択プロファイルと capability preferences をサーバ保存し、再起動・再接続後も復元。
完全自動（Profile 4 = `autonomous_bounded_dev`）を既定選択にする（実行はゲート/envelope を維持）。

**対象:** `agent/atlas_automation_features.py` ＋ `app/api/atlas_automation_features.py`、
`web/js/atlas_claude_panel.js`、`web/js/atlas_pipeline_api.js`、
（参照）`agent/atlas_capability_preference_schema.py`。

### 現状
`agent/atlas_automation_features.py` のストアは **3 つの string キーのみ**
（`critical_handling`/`clarification_mode`/`quality_gate_enforcement`、`:32-36`）。
`normalize_features`（`:51-58`）は値を str に正規化するため、新規キーの型に注意。

### 変更点
1. **ストア拡張（`agent/atlas_automation_features.py`）:**
   - `selected_preset_id`（string、既定 `"autonomous_bounded_dev"`）を追加。
   - `capability_preferences`（dict）を追加。dict は `normalize_features` の str 正規化を通さず、
     `agent/atlas_capability_preference_schema.py` の正規化ヘルパで検証する別ルートにする
     （`DEFAULT_AUTOMATION_FEATURES` の構造を `{features: {...3キー...}, selected_preset_id, capability_preferences}`
     のように拡張するか、別キーで保存。後方互換を保つこと）。
2. **API 拡張（`app/api/atlas_automation_features.py:20-30`）:**
   GET は `selected_preset_id` と `capability_preferences` も返す。POST は両方を受理・保存。
3. **UI（`web/js/atlas_claude_panel.js` / `atlas_pipeline_api.js`）:**
   - `state.selectedPresetId` と 5 つの capability チェックを **init で GET から復元**、
     変更時に **POST 保存**。
   - localStorage は単なるキャッシュに降格（source of truth はサーバ）。
   - 既定 `selected_preset_id = "autonomous_bounded_dev"`（Profile 4）。
   - 「既定選択」と「自動実行可否」を分離: envelope 未起動/未確認なら従来どおり mutation をブロックし、
     その旨を UI に明示。

### Acceptance
Features 変更 → リロード → 値が保持される／初期状態が Profile 4／envelope 無しでは mutation がブロックされる。
`pytest -q tests/test_atlas_automation_features.py` 緑（新規キーの GET/POST 往復テストを追加）。

---

## PR5 — UI：Profile 3/4 の差を明示＋戦略プランの視認性向上

**Goal:** プリセットの機能差を一目で分かるようにし、戦略プランを構造化表示する。

**対象:** `web/js/atlas_dashboard.js` / `web/js/atlas_claude_panel.js`、`web/css/app.css`。

### 変更点
1. **プリセット badge:** `enables_full_automation`（ON/OFF）と `envelope`（none/bounded_dev）を表示。
   ラベルを差が読める文言に:
   - 「3: Autonomous（毎回 bounds 指定・完全自動 OFF）」
   - 「4: Autonomous（envelope 内で完全自動・★完全自動コード生成）」
2. **戦略プランのカード化:** ゴール / アプローチ / step（各: 目標・対象ファイル・受け入れ条件・検証・
   ロールバック・risk のラベル付き）/ リスク / テスト / 完了条件 に分割。
   PR1 で追加した step の `goal` / `acceptance_criteria` をここで表示する。
   レビュー・敵対的批評は「未解決のみ強調＋解決済みは畳む」。生プランは collapsible。

### Acceptance
3 と 4 の差が説明なしで分かる／プランが整理表示される。

---

## フォローアップ（別 PR 推奨 / OpenCode 同等以上）

- **段階的 codegen ＋セルフレビュー:** 1 step を「生成→自己レビュー(lint/型/要件適合)→修正」まで
  step 内ループに（現状は提案→適用が一発）。
- **要件カバレッジ検証:** `done_definition` 達成を LLM か assertion で実測
  （例: "Hello World 文言が DOM に出る/色がアニメする"）。弱検証は trivially pass する。
- **MCP / Git 連携:** ブランチ作成〜push〜Draft PR を envelope 内で安全に閉じる（現状は手動 `gh pr create` 止まり）。
- **リポジトリ全体コンテキスト:** `atlas_repo_index` をシンボル/依存グラフベースの関連ファイル抽出に強化。
- **巨大単一ファイル分割:** `main.py`(778KB) / `ui.html`(853KB) をモジュール分割し自己改善時の安全編集を担保。

---

## 進め方
**PR1（成果物が正しくなる根本）→ PR2（止まった時に見える・ハングしない）** を先行させると体感改善が大きい。
PR2 のライブ進捗は新規 API ではなく既存 journal イベント＋`progress.json` 集約で実装する方針（追加 API 不要）。
PR3 は PR2 に依存、PR5 は PR1 の step 拡張に依存。PR4 は独立。
