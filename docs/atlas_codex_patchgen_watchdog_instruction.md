# Codex/Claude 指示書: パッチ生成のストール対策（ウォッチドッグをパッチ生成経路へ展開）

> 本書は **「不具合の確認(再現)手順」＋「根本修正の実装指示」** を兼ねる。プラン生成に入れた stall/streaming/heartbeat を**パッチ生成経路にも展開**し、「`Patch generation N/5` で固まる」を解消する。**PR 作成・マージはユーザーの明示指示まで禁止**。

## 不具合（症状）

autopilot のパッチ生成中、ステータスパネルが次の状態で**固まって見える**：

```
phase: patch_generation / status: running
items: 3/5, current item: 3. Validate HTML structure
message: Patch generation 3/5 / next action: wait, cancel
source: /api/atlas/patch-proposals/generate
```

進捗トークンの可視化が無いため「生成中で遅いだけ」か「本当に停止」かを UI が区別できず、ローカル軽量モデル（Gemma系）でフル HTML を書くと N 個目で 120 秒級になり、停止に見える。

## 根本原因（file:line・確認済み）

プラン生成ウォッチドッグ（#1569）は **`/api/atlas/plan-pools`（非同期ジョブ＋`/status` の `is_stalled`）にのみ**入っており、**パッチ生成経路は対象外**：

- ルート `app/api/atlas_pipeline.py:2008` `generate_patch_proposal` … **同期ブロッキング**。`service.propose_for_item(req)` を直接 return（非同期ジョブ無し）。
- `agent/atlas_patch_proposal_service.py` … `propose_for_item` → `generate_proposal_with_llm`（`MAX_LLM_GENERATION_ATTEMPTS = 2`）→ `call_llm_json(self.llm_json_fn, …)`。**`stream`/`on_progress` を渡していない**ため、アダプタは `_streaming_enabled=False` で**ブロッキング `_post_chat`（既定 120s）**を使う（`agent/atlas_llm_json_adapter.py`）。token heartbeat も stall 検知も無い。
- クライアント `web/js/atlas_claude_panel.js:1191-1249`（Stage 2 ループ）が各アイテムを `await root.AtlasPipelineAPI.generatePatchProposal({...})` で順に処理。
- `web/js/atlas_pipeline_api.js:233-234` `generatePatchProposal` は **`timeoutMs` 無指定** → `atlasFetch` の既定 **120 秒 AbortController** で待つだけ。フェーズ進捗パネルは各アイテムの呼び出しが返った後（`:1237`）にしか更新されないため、in-flight 中は固まって見える。

> 比較: プラン生成は `pollPlanPoolUntilReady`（`atlas_pipeline_api.js`）が `is_stalled` と絶対上限で待つ。パッチ生成にはこの仕組みが無い。

## 不具合の確認(再現)手順

1. レインボー HTML 等、複数 step（うち1つはフル HTML 生成）を含む plan を full-auto で実行し、パッチ生成段階に入る。
2. パネルが `Patch generation N/5` / `source: /api/atlas/patch-proposals/generate` で長時間動かないことを確認。
3. サーバ側ログ/journal で当該 pool の `patch_proposal_manual_started` 後、`patch_proposal_manual_proposed`/`_failed` まで**長時間イベントが出ない**ことを確認（= LLM 呼び出しでブロック）。
4. ブラウザ DevTools の Network で `/api/atlas/patch-proposals/generate` が **pending のまま ~120 秒**で abort されることを確認（client 既定タイムアウト）。
5. コード断定: 上記 file:line のとおり `propose_for_item` に stream/heartbeat が無いこと、`generatePatchProposal` に `timeoutMs` が無いことを確認。

→ これらが揃えば「パッチ生成がウォッチドッグ対象外でブロックしている」と確定。

## ゴール（Definition of Done）

1. パッチ生成中、UI が **進捗（current item / phase / 経過）と stall を区別**して表示し、トークンが流れている限り誤って打ち切らない。
2. 実際に無進捗のとき **`is_stalled` 相当を明示**（プラン生成と同じ語彙）。
3. `ATLAS_LLM_STREAMING=0` で従来ブロッキングへフォールバック。既存テスト緑・新規テスト緑・回帰なし。
4. 安全ゲート不変・PR/マージは人間指示まで。

## 実装方針（推奨：プラン生成の仕組みを再利用）

既存の Phase1/Phase2（`docs/atlas_codex_plan_watchdog_instruction.md`）と同型。**二択、A を推奨**。

### A（推奨）パッチ生成 LLM を streaming + token heartbeat にし、client を stall ベースに
- [ ] PG-A1: `propose_for_item` / `generate_proposal_with_llm` から LLM 呼び出しに **`on_progress`（token heartbeat）** を渡す。`call_llm_json` を拡張するか、`AtlasLLMJsonAdapter.with_progress(...)` を使う（プラン側 `app/api/atlas_pipeline.py` の `progress_cb → with_progress` を踏襲）。
- [ ] PG-A2: パッチ生成のジョブ進捗を保存し、`/patch-proposals/status`（または既存 status へ統合）で `is_stalled / seconds_since_progress / current_phase / last_token_at` を返す。`ATLAS_PLAN_STALL_AFTER_SEC` / `ATLAS_PLAN_FIRST_TOKEN_SEC` を再利用。
- [ ] PG-A3: `web/js/atlas_pipeline_api.js` の `generatePatchProposal` を **stall ベースのポーリング**に（固定 120s abort をやめ、`is_stalled` と絶対上限で待つ。`pollPlanPoolUntilReady` を一般化して流用）。`atlas_claude_panel.js` のループは per-item の進捗/フェーズを反映。

### B（代替）パッチ生成を非同期ジョブ化（plan-pools と同じ background + /status）
- [ ] PG-B1: `generate_patch_proposal` を background thread + job status ファイル化、`/status` に `is_stalled` 等を付与。client は plan と同じ poller を流用。

> A の方が変更が局所的で、token 単位の stall を直接検知できる。B はエンドポイント形を plan に揃える分かりやすさが利点。**着手時にどちらかを選び、本書末尾に判断を記録**。

## テスト

- [ ] streaming on_progress がパッチ生成経路でも token heartbeat を出す（fake adapter）。
- [ ] 無進捗で `is_stalled`（or `llm_stalled`）になる。
- [ ] `ATLAS_LLM_STREAMING=0` で従来ブロッキング動作（既存挙動不変）。
- [ ] client 契約テスト: `generatePatchProposal` が固定 120s abort ではなく stall/絶対上限を見る（JS テキスト検査の既存スタイル）。
- [ ] 既存 `tests/test_atlas_patch_proposal_api.py` 等が緑のまま。

## 受け入れ基準

- [ ] 大きめプランのパッチ生成が、トークンが流れる限り誤って固まらない/打ち切られない。
- [ ] 無進捗時のみ stall を明示。`ATLAS_LLM_STREAMING=0` で従来動作。
- [ ] 既存テスト緑・追加テスト緑・回帰なし。安全ゲート不変。

---

## 関連: 視覚テスト網羅ゴールの評価結果（参考・本書とは別タスク）

`GOAL-VISUAL-TEST-COVERAGE`（`docs/atlas_codex_visual_test_coverage_instruction.md`）は **WP-0〜WP-7（P0+P1）実装済み・テスト緑**（matrix: `tests/visual_fixtures.py` + `tests/test_visual_contract_matrix.py`）。**残ギャップは WP-8（任意・将来パターン）のみ**：
- JS `innerHTML` 動的構築 HTML の静的契約、操作必須アニメの `_nudge_interaction` 強化、`requirement_coverage` の語幹/複数形許容。

WP-8 は任意。着手するなら本書とは独立に進めてよい。
