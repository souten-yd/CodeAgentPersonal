# Codex 実装指示書: プラン生成のウォッチドッグ / stall 検知（固定タイムアウト撤廃）

## 目的（なぜやるか）

大規模なプランを要求すると「モデルが混雑しています（タイムアウト）」が出る。原因は **クライアントが固定 8 分のウォールクロックでポーリングを打ち切る**ためで、**実際には LLM がトークンを順調に生成していても総経過時間が予算を超えただけ**で失敗扱いになっている。

正しいシグナルは *経過時間* ではなく **進捗の停止（stall）**。本指示は「サーバ側でトークン生成をリアルタイム監視し、**生成が実際に止まったときだけ** stall とみなす」仕組みを実装する。固定タイムアウトは撤廃し、代わりに **stall 検知（主トリガ）＋ 寛大な絶対上限（バックストップ）** にする。

既存の **Nexus ディープリサーチの heartbeat / stall 検知**（`app/nexus/research_api.py` `_build_research_job_health`、`app/nexus/jobs.py` `append_job_heartbeat`、env `NEXUS_STALLED_AFTER_SEC`）と同じ思想を Atlas プラン生成へ移植する。実装時はこの前例を参照すること。

---

## 現状アーキテクチャ（変更対象、file:line）

1. **プラン作成エンドポイント / 背景ジョブ** — `app/api/atlas_pipeline.py`
   - `create_plan_pool()` @ `673`：`?sync=0`（既定）で背景デーモンスレッド `_runner` を起動し即 `{"pool_id","status":"queued"}` を返す。
   - `_runner` @ `693`：ジョブ状態ファイル `ca_data/atlas/plan_pool_jobs/{pool_id}.json` を `queued → running → ready|failed` と書き換える（`_write_plan_pool_job` @ `665`）。
   - 状態フィールド：`pool_id, status, created_at, finished_at, error, error_kind`。
   - `_create_plan_pool_core()` @ `727`：実際の生成本体。`forced_pool_id=pool_id` で同じ id に束ねる。
   - `GET /plan-pools/{pool_id}/status` @ `715`：状態ファイルの中身をそのまま返す（無ければ 404、読めなければ `{"pool_id","status":"running"}`）。

2. **LLM アダプタ（コア LLM 経路、全機能が使用）** — `agent/atlas_llm_json_adapter.py`
   - `AtlasLLMJsonAdapter.__init__(..., timeout_seconds=120)` @ `54`。
   - `_post_chat()` @ `287`：`POST {base_url}/v1/chat/completions`。**非ストリーミングの単発ブロッキング**：`urllib_request.urlopen(req, timeout=timeout_sec)` @ `320` で完成まで一括待ち、`resp.read()` を一括 parse。**トークン単位の進捗観測は皆無**。
   - `generate_json()` @ `72`：`backend_fn` 経路（テスト用）と `call_openai_compatible`（HTTP 経路）の分岐。構造化出力の strict→json_object フォールバックと一発リトライあり（壊さないこと）。

3. **プランナ経路（逐次 LLM 呼び出し）**
   - `_create_plan_pool_core` → `AtlasPlannerBridge`（`agent/atlas_planner_bridge.py`）。`run_real_planner()` @ `97` が `TaskPlanningRunner(...).run(...)` @ `100-117` を呼ぶ。`llm_json_fn` に `AtlasLLMJsonAdapter` が渡る。
   - `TaskPlanningRunner.run()`（`agent/task_planning_runner.py`）が **最大 ~7 回の逐次 LLM 呼び出し**：requirement_analysis → research_conductor →（deep_planner）→ plan build → adversarial_critique → revision×最大2。各呼び出しが `llm_json_fn` 経由。

4. **クライアント ポーラ** — `web/js/atlas_pipeline_api.js`
   - `pollPlanPoolUntilReady(poolId, ws, maxWaitMs=480000, intervalMs=1500)` @ `116`：**8 分固定キャップ**。超えると `plan_pool_timeout`「プラン作成がタイムアウトしました。モデルが混雑しています。」@ `138-142`。
   - `getPlanPoolStatus` @ `111`、`atlasFetch` は AbortController + `DEFAULT_TIMEOUT_MS=120000` @ `56`、5xx を `gatewayMessage` で丸める @ `7`。

---

## ゴール / 非ゴール

**ゴール**
- トークンが流れている限り、何分かかっても**誤タイムアウトしない**。
- 生成が**実際に止まった**（一定時間トークン無進捗）ときだけ stall として明示し、現フェーズ・経過秒・推奨アクションを返す。
- 絶対上限（バックストップ）で真のハング/暴走を確実に止める。
- 既存の非ストリーミング呼び出し・`backend_fn` 経路・構造化出力・`?sync=1` を壊さない。

**非ゴール**
- プランナのアルゴリズム自体は変えない（呼び出し回数・順序はそのまま）。
- llama.cpp 以外のバックエンド対応は対象外（ただし streaming 非対応バックエンドは env で無効化して従来動作にフォールバックできること）。

---

## 設計

### 共通: 進捗シンク（heartbeat writer）

ジョブ状態ファイルに進捗を追記する単一の関数を新設する。`app/api/atlas_pipeline.py` に追加（`_write_plan_pool_job` の隣）。

```python
def _merge_plan_pool_job(ca_data_root: Path, pool_id: str, patch: dict) -> None:
    """状態ファイルを read-modify-write でマージ更新（status を上書きしない用途）。"""
    path = _plan_pool_jobs_dir(ca_data_root) / f"{pool_id}.json"
    try:
        cur = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        cur = {}
    cur.update(patch)
    _write_plan_pool_job(ca_data_root, pool_id, cur)
```

**進捗コールバック**を `_runner` 内で生成し、本体へ渡す。最低限のフィールド：

```jsonc
{
  "phase": "adversarial_critique",      // 現フェーズ名
  "phase_index": 4, "phase_total": 7,    // 任意（分かる範囲で）
  "tokens_generated": 1234,              // 累積トークン（Phase 2 で更新）
  "last_progress_at": "2026-06-05T12:34:56.789Z", // 最後に「何か進んだ」時刻
  "last_token_at": "2026-06-05T12:34:56.700Z"     // 最後にトークンが来た時刻（Phase 2）
}
```

**スロットリング必須**：ディスク書き込みは最低でも 1.0〜1.5 秒に 1 回までに間引く（トークン毎に書かない）。コールバック側で `last_write_monotonic` を持ち、間隔未満ならメモリ更新のみ・ファイル書き込みはスキップ。ただし「フェーズ遷移」と「初トークン」は即時 flush する。

### Phase 1 — フェーズ単位 heartbeat（streaming 不要）

1. `create_plan_pool._runner`（`app/api/atlas_pipeline.py:693`）で進捗コールバック `heartbeat(phase, **details)` を作り、`_create_plan_pool_core(req, app_ref, forced_pool_id=pool_id, progress_cb=heartbeat)` に渡す。`running` 書き込み時点で `last_progress_at=now` を入れる。
2. `_create_plan_pool_core`（`727`）に `progress_cb: Callable | None = None` 引数を追加し、`AtlasPlannerBridge` 構築〜`TaskPlanningRunner` まで透過的に伝播させる。
   - `AtlasPlannerBridge.__init__` / `run_real_planner`（`agent/atlas_planner_bridge.py:97-117`）に `progress_cb` を通し、`planning_runner_factory(... , progress_cb=progress_cb)` と `runner.run(..., progress_cb=progress_cb)` へ渡す。
   - `TaskPlanningRunner`（`agent/task_planning_runner.py`）：各フェーズ開始直前に `progress_cb(phase="requirement_analysis", phase_index=1, phase_total=N)` のように呼ぶ。**既存の引数が増えるだけ**で、`progress_cb=None` のときは何もしない（後方互換）。
3. **状態エンドポイント**（`get_plan_pool_status` @ `715`）に stall 判定を追加して返す。`status` がファイルに無いフィールドは計算して付与：

```python
STALL_AFTER_SEC = float(os.environ.get("ATLAS_PLAN_STALL_AFTER_SEC", "120") or "120")
data = json.loads(...)              # 既存
status = data.get("status")
hb = data.get("last_progress_at") or data.get("created_at")
sec_since = _seconds_since_iso(hb)  # ヘルパ新設（Nexus の同等処理を参照）
is_terminal = status in {"ready", "failed"}
data["seconds_since_progress"] = sec_since
data["is_stalled"] = bool(status in {"running"} and not is_terminal and sec_since is not None and sec_since > STALL_AFTER_SEC)
data["current_phase"] = data.get("phase") or ("running" if status == "running" else status)
if data["is_stalled"]:
    data["stalled_reason"] = f"LLM生成のheartbeatが{int(sec_since)}秒更新されていません（フェーズ: {data['current_phase']}）。"
    data["suggested_action"] = "モデルが応答停止の可能性があります。少し待つか、再実行してください。"
return data
```

   - これだけで「進行中（フェーズが進んでいる）プラン」は stall 判定されない。`queued` は stall 対象外。

4. **クライアント**（`web/js/atlas_pipeline_api.js`）`pollPlanPoolUntilReady` を改修：
   - **8 分固定キャップを撤廃**。代わりに `ABSOLUTE_MAX_MS = Number(...) || 2700000`（45 分・バックストップ）。
   - ループ条件：`status` が `ready`/`failed` になるまで継続。`is_stalled === true` を受けたら**即座に**「停止の可能性」結果を返す（現フェーズ・経過秒を message に含める）。タイムアウト文言「混雑しています」は **stall 確定時のみ**。
   - 進行中は `current_phase` / `tokens_generated` を UI 状態へ反映（呼び出し側がフェーズ表示できるよう、polling 中の中間状態を渡せる薄いコールバック or 戻り値経由）。
   - `is_stalled=false` で進捗が動いている限り `ABSOLUTE_MAX_MS` まで待つ。`ABSOLUTE_MAX_MS` 到達時のみ最終バックストップとして失敗を返す。

### Phase 2 — トークン・ウォッチドッグ（streaming 化）

**狙い**：単一 LLM 呼び出しの**内部**で「トークン50/1000で固まった」を検知する。フェーズ境界だけでは 1 呼び出し内のハングを見逃すため。

1. **アダプタの streaming 経路を追加** — `agent/atlas_llm_json_adapter.py`
   - `AtlasLLMJsonRequest` に `stream: bool = False`、`AtlasLLMJsonAdapter.__init__` に `on_progress: Callable[[dict], None] | None = None`（または `generate_json` の引数）を追加。
   - 新メソッド `_post_chat_stream(request, *, structured) -> str`：`payload["stream"] = True` を付けて POST。レスポンスを**行単位**で読む（urllib の `HTTPResponse` は反復可能。`for raw in resp:` で `data: {json}` 行が得られる）。
     - `data: [DONE]` で終了。各行 `choices[0].delta.content` を連結。
     - チャンク受信ごとに、トークン数を増分して `on_progress({"tokens_generated": n, "last_token_at": now})` を呼ぶ（呼び先＝Phase1 の heartbeat。スロットリングは heartbeat 側で実施）。
     - **完全な content を組み立て終えたら、既存の parse / strict リトライ / フォールバック経路へ流す**（streaming はトランスポートのみ変更、パースは不変）。
   - `generate_json` で、`base_url` 経路かつ `stream=True` かつ streaming 有効時に `_post_chat_stream` を使い、それ以外は従来の `_post_chat`。
   - 構造化出力（`response_format`/`grammar`）は stream と併用してよい（llama.cpp 対応）。万一 4xx で拒否されたら従来同様 `_post_chat(..., structured=False)` フォールバック。

2. **「無進捗 = タイムアウト」を urllib のソケットタイムアウトで実現**
   - streaming 時、`urlopen(req, timeout=READ_INACTIVITY_SEC)` の `timeout` は**各ソケット read に効く**ため、**チャンクが来ない時間が `READ_INACTIVITY_SEC` を超えると `socket.timeout` が上がる**＝実質「無進捗タイムアウト」。健全なストリームは毎チャンクでリセットされるので、遅くても生きていれば落ちない。
   - `READ_INACTIVITY_SEC = ATLAS_PLAN_STALL_AFTER_SEC`（既定 120）に揃える。
   - **初トークンまでの待ち（prefill / スロット待ち）は別枠**：llama.cpp は単一スロットで、長いプロンプト評価や順番待ちの間トークンが出ない。初トークン前は `READ_INACTIVITY_SEC` ではなく `ATLAS_PLAN_FIRST_TOKEN_SEC`（既定 300）を使う（接続後〜初 delta までは長めに許容）。初トークン到着後は inter-token の `READ_INACTIVITY_SEC` に切替。実装は「初 delta を受けるまではタイムアウトを first-token 値、以降は inactivity 値」。urllib で read 毎にタイムアウトを変えにくい場合は、`http.client`/socket で `settimeout` を read ループ内で動的に設定するか、`fp` の socket に `settimeout` する。
   - `socket.timeout` を捕捉したら `AtlasLLMJsonResult(ok=False, error="llm_stalled", ...)` を返す（`llm_timeout` と区別）。

3. **フェーズ＋トークンの両方を heartbeat へ**：Phase1 のフェーズ heartbeat に加え、Phase2 のトークン heartbeat が `last_token_at` / `tokens_generated` を更新。状態エンドポイントの stall 判定は `last_progress_at = max(last_token_at, phase進捗時刻)` を基準にする（どちらかが動いていれば stall でない）。

### 設定（env）

| 変数 | 既定 | 意味 |
|---|---|---|
| `ATLAS_PLAN_STALL_AFTER_SEC` | `120` | 無進捗がこの秒数を超えたら stall（Nexus の 120 に合わせる） |
| `ATLAS_PLAN_FIRST_TOKEN_SEC` | `300` | 接続後〜初トークンまでの許容秒（prefill/スロット待ち） |
| `ATLAS_PLAN_ABSOLUTE_MAX_SEC` | `2700` | 絶対上限（バックストップ、45 分） |
| `ATLAS_LLM_STREAMING` | `1` | `0` で streaming を無効化し従来のブロッキングへフォールバック |

クライアント側の絶対上限はサーバ env を `/status` レスポンス等で渡すか、JS 定数 `ABSOLUTE_MAX_MS` を同値（2700000）にする。

---

## エッジケース / 必須の配慮

1. **後方互換**：`progress_cb=None` / `on_progress=None` / `stream=False` のとき、挙動は現状と完全に同一であること。`backend_fn` 経路（テスト）は streaming 対象外。
2. **構造化出力**：streaming でも delta を全部連結してから既存パーサに渡す。strict→json_object の一発リトライ・フォールバックを維持。
3. **`?sync=1`**：同期パスは progress_cb 無しでよい（テスト互換）。
4. **単一スロット待ち**：`queued` は stall 対象外。初トークン前は first-token タイムアウト。区別できるよう `phase` に `waiting_model_slot` / `generating` 等を入れてもよい。
5. **ディスク書き込み**：トークン毎に書かない（スロットリング 1〜1.5s）。フェーズ遷移と初トークンは即 flush。書き込み失敗は握りつぶす（生成を止めない）。
6. **terminal の安定**：`ready`/`failed` 後は `is_stalled=false` 固定。`finished_at` がある状態を stall にしない。
7. **stall 後も生成は継続させない**：stall 確定（socket.timeout / 絶対上限）時は当該 LLM 呼び出しを中断し、ジョブを `failed`（`error_kind="llm_stalled"` 等）にする。半端な接続を残さない。
8. **既定タイムアウト 120 を他用途で壊さない**：プラン生成以外の `AtlasLLMJsonAdapter` 利用箇所の挙動は不変（streaming はプラン経路でのみ有効化、または `on_progress` が渡ったときのみ）。

---

## テスト（必須・pytest）

`tests/` に新規追加。既存スイート（`test_atlas_llm_json_adapter.py`, `test_atlas_planner_bridge.py`, `test_atlas_api_pipeline.py`, `test_ui_nexus_deep_heartbeat.py` 等）を壊さないこと。

1. **アダプタ streaming 単体**（`test_atlas_llm_json_streaming.py`）
   - フェイクの SSE レスポンス（`data: {...delta...}` 複数 → `data: [DONE]`）を urlopen にモックし、(a) content が正しく連結される、(b) `on_progress` がチャンク毎に呼ばれ `tokens_generated` が増える、(c) 連結後に既存パーサで JSON が取れる。
   - 無進捗（チャンクが来ない）を `socket.timeout` でシミュレートし、`error="llm_stalled"` が返る。
   - 初トークン前タイムアウトは `ATLAS_PLAN_FIRST_TOKEN_SEC`、以降は `ATLAS_PLAN_STALL_AFTER_SEC` が使われることを検証。
2. **heartbeat マージ / 状態エンドポイント**（`test_atlas_plan_pool_watchdog.py`）
   - `last_progress_at` が新しい→ `is_stalled=false`。古い（> STALL_AFTER）→ `is_stalled=true` かつ `stalled_reason`/`current_phase` を含む。`ready`/`failed`/`queued` は stall にならない。
   - `_merge_plan_pool_job` が status を壊さずフィールドを足す。
3. **progress_cb 透過**（`test_atlas_planner_bridge.py` に追記）：`progress_cb` がフェーズ毎に呼ばれる（フェイク llm_json_fn 使用）。`progress_cb=None` で従来通り動く。
4. **クライアント契約**（`tests/test_atlas_plan_pool_poller_contract.py`、JS をテキスト検査する既存スタイルに合わせる）：`atlas_pipeline_api.js` が `maxWaitMs=480000` の固定キャップに依存せず `is_stalled` を参照し、`ABSOLUTE_MAX_MS` バックストップを持つことをアサート。
5. **後方互換**：`stream=False` / `backend_fn` 経路で出力が現状と一致。

---

## 受け入れ基準（Acceptance）

- [ ] トークンが流れ続ける大規模プラン（>8 分）が**誤タイムアウトせず完了**する。
- [ ] 生成が `ATLAS_PLAN_STALL_AFTER_SEC` を超えて無進捗のとき、`/status` が `is_stalled=true` と現フェーズ・経過秒を返し、UI が「混雑/停止の可能性」を**stall 確定時のみ**表示する。
- [ ] `ATLAS_PLAN_ABSOLUTE_MAX_SEC` 到達でバックストップ失敗する。
- [ ] `ATLAS_LLM_STREAMING=0` で従来のブロッキング動作に戻る。
- [ ] 既存テスト緑、追加テスト緑。`ruff`/型チェック（あれば）通過。
- [ ] プラン生成以外の LLM 利用箇所の挙動・既定 120s が不変。

---

## 実装順序（推奨）

1. Phase 1：`_merge_plan_pool_job` + `progress_cb` 透過（pipeline→bridge→runner）+ 状態エンドポイントの `is_stalled` + クライアント poller 改修 + テスト2,3,4。**ここまでで誤タイムアウトは解消**。
2. Phase 2：アダプタ streaming + inactivity/first-token タイムアウト + トークン heartbeat + テスト1,5。**1 呼び出し内ハングまで検知**。

各 Phase 毎にコミットを分け、メッセージに対象と理由を明記すること。**PR 作成・マージはユーザー指示があるまで行わない。**
