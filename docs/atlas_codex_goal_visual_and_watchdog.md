# Codex ゴール指示書（連続実装・最後まで）: 視覚コントラクト修正 + プラン生成ウォッチドッグ

> このファイルは **「ゴール機能（最後まで連続実装）」用の統括ランブック**です。Codex はこの1ファイルを起点に、下記2タスクを**順番に最後まで**実装する。各タスクの実装詳細は、それぞれの**正典の指示書**に従うこと（本書は順序・全体完了判定・連続実行プロトコルを定義する）。

## 全体ゴール（Definition of Done）

1. **視覚コントラクト false-negative 修正** が完了し、対象 `index.html`（色名 keyframes・動き無し）が static で pass する。
2. **プラン生成ウォッチドッグ / stall 検知**（Phase 1 + Phase 2）が完了し、大規模プランが誤タイムアウトしない／実際の無進捗のみ stall 判定される。
3. **両タスクの全テストが緑**、かつ関連スイートに回帰なし。
4. 各指示書の「受け入れ基準」チェックボックスが**全て満たされ、リポジトリ上で更新済み**。
5. 変更は作業ブランチにコミット＆プッシュ済み。**最終 PR の作成・マージはユーザーの明示指示を待つ**（自動マージ禁止／安全ゲート不変）。

この5つが揃って初めて「ゴール達成」。途中で止めない（下記「連続実行プロトコル」）。

---

## 実行順序（この順で最後まで）

独立した2タスク。**小さく低リスクな方を先に**完了させてから次へ進む。

### ステップ 1 — 視覚コントラクト false-negative 修正（先）
- 正典: [`docs/atlas_codex_visual_contract_falsenegative_instruction.md`](atlas_codex_visual_contract_falsenegative_instruction.md)
- 規模: 小・独立・低リスク。今回の「色だけ変化するテキスト」を即通せる。
- 完了の合図: 当該指示書の「受け入れ基準」全チェック + 追加/既存テスト緑。

### ステップ 2 — プラン生成ウォッチドッグ / stall 検知（後）
- 正典: [`docs/atlas_codex_plan_watchdog_instruction.md`](atlas_codex_plan_watchdog_instruction.md)
- 規模: 大・2 Phase（Phase 1: フェーズ heartbeat → Phase 2: streaming トークン監視）。
- 必ず **Phase 1 を完了・テスト緑にしてから Phase 2** へ。各 Phase でコミットを分ける。
- 完了の合図: 当該指示書の「受け入れ基準」全チェック + 追加/既存テスト緑。

> ステップ1とステップ2の間で停止しない。ステップ1のテストが緑になったら、続けてステップ2に着手する。

---

## マスター・チェックリスト（全体進捗）

Codex は進捗に応じて本リストと各指示書内のチェックボックスを更新し、その都度コミットすること。

- [x] S1: 視覚コントラクト修正の実装（指示書 A/B）完了
- [x] S1: 視覚コントラクト修正のテスト緑（`tests/test_atlas_visual_artifact_verifier.py` ほか）
- [x] S1: 指示書「受け入れ基準」全チェック更新済み・コミット済み
- [ ] S2-P1: ウォッチドッグ Phase 1 実装完了
- [ ] S2-P1: Phase 1 テスト緑（status の is_stalled / poller 契約 / progress_cb 透過）
- [ ] S2-P2: ウォッチドッグ Phase 2 実装完了
- [ ] S2-P2: Phase 2 テスト緑（streaming / inactivity timeout / トークン heartbeat）
- [ ] S2: 指示書「受け入れ基準」全チェック更新済み・コミット済み
- [ ] FINAL: 全体検証ゲート（下記）通過、最終サマリを本書末尾に追記
- [ ] FINAL: 作業ブランチへプッシュ済み（PR は未作成のまま、ユーザー指示待ち）

---

## 連続実行プロトコル（最後まで止めない）

1. 本書 → ステップ1の正典指示書 → 実装 → テスト緑 → チェック更新 → コミット、を行い、**間を置かずステップ2へ**進む。
2. 各タスク内では指示書の「実装順序」に従い、論理単位ごとにコミット（メッセージに対象と理由を明記）。
3. **テストが赤の状態で次のステップへ進まない**。赤なら原因を特定して修正してから進む。
4. 既存テストを壊さない。壊れたら、それは設計ミスのサイン → 指示書の「テスト互換性」節を読み直して修正する（テストを安易に書き換えて緑にしない）。
5. **停止してよいのは次の場合のみ**:
   - 全ゴール達成（Definition of Done を満たした）。
   - 指示書の前提と実コードが食い違い、設計判断が必要で、推測で進めると安全性/正しさを損なう場合 → その時点までをコミット&プッシュし、**何がどう食い違ったか**を本書末尾「ブロッカー記録」に書いて停止。
6. 不明点を**勝手に仕様変更で埋めない**。指示書の file:line に従い、曖昧なら最小・後方互換な実装を選び、その判断を末尾に記録する。

---

## 全体検証ゲート（FINAL・両タスク完了後に実行）

両タスクのテストに加え、回帰確認として最低限これらを緑にする:

```bash
python -m pytest \
  tests/test_atlas_visual_artifact_verifier.py \
  tests/test_atlas_auto_verification_service.py \
  tests/test_atlas_pr9_visual_depth.py \
  tests/test_atlas_playwright_smoke_verifier.py \
  tests/test_atlas_llm_json_adapter.py \
  tests/test_atlas_planner_bridge.py \
  tests/test_atlas_api_pipeline.py \
  tests/test_ui_nexus_deep_heartbeat.py \
  -q
```

加えて、新規追加したテストファイル（視覚/ウォッチドッグ）も緑であること。`ruff` 等の lint/型チェックが構成されていれば通すこと。

> 既知の **無関係な既存 fail**（本ゴールの対象外）: `test_phase30_1...test_docs_state_chrome_extension_not_required`（README 文言）, `test_atlas_single_item_self_correction_loop...preserves_high_risk_gate`。これらは本変更が原因ではない。新たな赤を増やさないことが基準。

---

## ブランチ / コミット / PR

- 作業ブランチで進める（リポジトリの作業ブランチ運用に従う）。
- コミットは Phase / 論理単位で分割し、メッセージに対象と理由を明記。
- **PR の作成・マージはしない**（ユーザーが明示指示する）。バックエンドの安全方針（direct merge / remote push / self-apply は無効）を尊重し、安全ゲートの意味を変えない。
- モデル識別子や本書のメタ情報をコミットメッセージ/コード/PR本文に含めない。

---

## 最終報告（完了時に本書末尾へ追記）

ゴール達成時、Codex は本書の最後に「## 実装完了サマリ」を追記する:
- 変更ファイル一覧（タスク別）。
- 追加テストと結果（pytest の最終行）。
- 各指示書の受け入れ基準の達成状況。
- 既知の残課題（あれば。例: ブラウザ smoke が Windows で空エラーになる根本原因は別タスク）。

ブロックされた場合は「## ブロッカー記録」を追記して停止（上記プロトコル5）。

---

## 参考: 2タスクの関係

- 視覚コントラクト修正は **static 検証をブラウザ非依存で正す**根本対処（今回の `visual_contract_failed` を解消）。
- ウォッチドッグは **プラン生成の誤タイムアウト**を解消（別系統）。
- 両者は独立。PR #1565（runtime smoke override）のロジックは**変更しない**（併存）。
