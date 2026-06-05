# Codex 指示書＋ゴール: ブラウザ/視覚検証（Playwright）の網羅テスト整備 + 既存実装の改良

> **本書は「実装指示書」と「連続実装ゴール（最後まで）」を兼ねる**。Codex / Claude はこの1ファイルを起点に、ブラウザ/視覚検証システムの**網羅テストを追加**し、テストで露見する**既存実装の弱点も改良**する。実装は作業ブランチへコミット&プッシュ。**PR 作成・マージはユーザーの明示指示まで禁止**。

## 目的（なぜやるか）

「レインボー Hello world」の `visual_contract_failed` のように、ブラウザ/視覚検証は**今後もいろいろなパターンで誤判定・不具合が発生する**ことが見込まれる。場当たり修正ではなく、**成果物パターン × 検証シナリオのマトリクスを網羅するテスト基盤**を作り、同時に**検証器の false-negative / 誤分類 / 診断不足を根本改良**する。

## 対象システム（System Under Test, file:line）

- `agent/atlas_visual_artifact_verifier.py` … 静的コントラクト（`_ANIMATION_SIGNALS`/`_COLOR_SIGNALS`/`_MOTION_SIGNALS`/`_WAVE_PHASE_SIGNALS`、`verify_static`、`_check_signals`）。
- `agent/atlas_playwright_smoke_verifier.py` … 実ブラウザ smoke（`verify`、`_check_style_changes_over_time`、`_check_canvas_changes_over_time`、`_diagnose_js_wiring`/`_hard_js_errors`/`_js_error_reason`、`_nudge_interaction`、`_serve_artifact_dir`、`_is_browser_not_installed_error`、`_result`、定数 `_ANIMATION_TASK_HINT`/`_ANIMATION_POLL_INTERVAL_MS`/`_ANIMATION_MAX_WAIT_MS`）。
- `agent/atlas_auto_verification_service.py` … 統合（`_evaluate_visual`、`_run_visual_verification`、`_HARD_SMOKE_REASONS`、hard/soft、`verify_level`、`requirement_coverage`）。
- `agent/atlas_test_harness_provisioner.py` … pytest provisioning。
- E2E/ハーネス: `scripts/smoke_ui_modes_playwright.py`（`SMOKE_SCENARIOS`）、`scripts/run_debug_test_matrix.py`（`TEST_PRESETS`）、`main.py` の `/debug/tests`、`.github/workflows/playwright-ui-smoke.yml`。

## 既存テスト（重複させない・壊さない）

`tests/test_atlas_visual_artifact_verifier.py` / `test_atlas_playwright_smoke_verifier.py` / `test_atlas_auto_verification_service.py` / `test_atlas_pr8_visual_verification_wiring.py` / `test_atlas_pr9_visual_depth.py`、および `test_phase25_*` / `test_phase26_1b` / `test_phase30_1`/`_4`。本書のテストは**これらを置換せず補完**する。既存テストの前提（例: 「movement 課題は motion 必須」）を壊さないこと。

## 既着手タスクとの関係（重要）

`docs/atlas_codex_visual_contract_falsenegative_instruction.md`（= WP-1/WP-2 と smoke 診断の一部）が**先に実装されている可能性**がある。本書はその上位の網羅計画。**既に実装済みなら検証して延伸**（transition / animation shorthand / SVG / JS setProperty 等）し、未実装なら本書 WP として実装する。PR #1565 の runtime-override ロジックは**変更しない**（併存）。

---

## ゴール（Definition of Done）

1. 下記**テストマトリクス**の全パターンに対し、`static` / `smoke` / `auto_verification` の期待結果を検証するテストが存在し緑。
2. P0 の**実装改良**が適用され、正しい成果物が誤って fail しない／不正な成果物は依然 fail する。
3. ブラウザ**有/無の両方**でスイートが意味を持つ（PW 必須テストは `skipif`、ロジックは fake page で検証）。
4. 既存テスト全緑・新規テスト緑、関連スイートに回帰なし。
5. 本書末尾のチェックリスト全消化、作業ブランチへ push 済み。**PR/マージは人間指示まで保留**。

---

## 全体設計

### 1) 共有フィクスチャ・ライブラリ（WP-0）

`tests/visual_fixtures.py`（新規）に、HTML 文字列フィクスチャと「期待結果テーブル」を集約。各テストはここを import。

- `FIXTURES: dict[str, str]` … パターン名 → HTML（または複数ファイル生成用ヘルパ）。
- `STATIC_EXPECTATIONS: list[Case]` … `(name, task_description, expect_status, must_pass_checks, must_miss_checks)`。
- `AUTOVERIFY_EXPECTATIONS` … smoke をフェイク注入したときの最終 status/warnings/verify_level。
- 複数ファイル成果物は `write_multifile(tmp_path, name)` ヘルパで生成。

これにより新パターン追加は**1行のフィクスチャ＋1行の期待**で済む（将来の不具合パターンを継続追加しやすくする＝本タスクの主目的）。

### 2) テストマトリクス（網羅対象）

| # | パターン | フィクスチャ要点 | task_description | static 期待 | smoke 期待(ブラウザ有) | auto_verify 最終 |
|---|---|---|---|---|---|---|
| 1 | color 名前keyframes | `@keyframes{0%{color:red}…100%{color:purple}}` | rainbow color text | **passed** | passed | passed |
| 2 | color hsl keyframes | `@keyframes` + `hsl()` | color animation | passed | passed | passed |
| 3 | css変数hue(JS) | `style.setProperty('--hue', …)` + rAF | hue rotate | **passed** | passed | passed |
| 4 | SVG/SMIL | `<animateTransform>` / `<animate>` | rotate svg icon | **passed** | passed/skip | passed |
| 5 | 回転のみ(色なし) | `transform: rotate` + rAF, 色変化なし | spin a cube | **passed**(motion要件) | passed | passed |
| 6 | canvasゲーム | `getContext` + rAF でピクセル変化 | canvas game | passed | passed(pixel) | passed |
| 7 | 静的(非アニメ) | `<h1>Hello</h1>` | animate colors | failed(全欠落) | failed/skip | failed |
| 8 | JS ReferenceError | `undefinedFn()` | show page | (該当外) | **failed:js_error**(hard) | failed |
| 9 | module不整合 | 非module で `export` | game | — | failed:js_error:module_script_mismatch | failed |
| 10 | script欠落 | `src=js/missing.js` | game | failed(animation) | failed:js_error:missing_script_src | failed |
| 11 | 多ファイル(外部) | index+css+js に signal | animate color motion | passed | passed | passed |
| 12 | 多ファイル(空) | 外部jsが空 | animate | failed | failed | failed |
| 13 | 期待テキスト欠落 | 期待文字列なし | (expected_text指定) | — | **failed:expected_text_missing**(hard) | failed |
| 14 | ブラウザ未導入 | launch時 "Executable doesn't exist" | any | (staticは通常通り) | **skipped:playwright_browser_not_installed** | static次第 |
| 15 | launch空エラー | launch が空メッセージ例外 | any | (static) | failed:`playwright_error: <型名>` | static次第 |
| 16 | 色課題で動きなし(虹文字) | 名前keyframes色、transformなし | rainbow text | **passed**(motion不要) | passed | passed |
| 17 | 動き課題で動きなし | 色はあるが task=move、transformなし | make it move around | **failed**(motion必須) | — | failed |
| 18 | transition色変化 | `transition: color` + JS class toggle | color change on load | passed(色) | passed/soft | passed |

> 表の「—」はそのパターンで主検証しない欄。smoke の hard/soft 分類は `_HARD_SMOKE_REASONS`（js_error / expected_text_missing / html_file_missing = hard）に従う。

### 3) ブラウザ無し環境での担保

- PW 必須の実起動テストは `@pytest.mark.skipif(not _PLAYWRIGHT_AVAILABLE, ...)`。
- ロジック（hard/soft 分類、style/canvas 判定、override、診断分岐）は **fake page / `sync_playwright` の monkeypatch**（既存 `test_atlas_pr9_visual_depth.py` / `_FakeCanvasPage` 流儀）で**ブラウザ無しでも検証**する。
- マトリクスの static / auto_verify 行は**ブラウザ不要**（smoke はフェイク注入）。これがCIの主カバレッジ。

---

## 作業パッケージ（実装改良 + テスト）

各 WP は「① 実装改良（必要時）」「② テスト追加」をセット。**P0 → P1 の順**。各 WP 完了でコミット。

### WP-0（P0・基盤）共有フィクスチャ + マトリクス駆動テスト
- `tests/visual_fixtures.py` と `tests/test_visual_contract_matrix.py`（パラメタライズド）を新設。表の static / auto_verify 行を網羅。
- smoke はフェイク（`_FakeSmoke` 相当）で注入し、auto_verification の最終判定を検証。

### WP-1（P0・実装改良）静的「色変化」検出の拡張
対象 `_COLOR_SIGNALS` / `verify_static`（既存 visual-falseneg 指示と整合）:
- `@keyframes` 内の複数 `color:`/`background-color:`（**色名含む**）を色変化として検出（既存指示の `_keyframe_color_mutation` を採用/延伸）。
- 追加検出: CSS `transition:`（color/background 対象）、`animation:` shorthand、JS `setProperty('--…color|hue…', …)` / `style.color=` の動的更新。
- テスト: マトリクス #1,#2,#3,#18。

### WP-2（P0・実装改良）motion 必須のタスク連動
対象 `verify_static`（既存 visual-falseneg 指示と整合）:
- color は「色課題のとき必須」、motion は「動き課題のとき必須」。汎用アニメは color/motion のいずれか必須（`visual_change_signal`）。
- テスト: マトリクス #5,#16,#17（#17 で弱体化していないことを担保）。

### WP-3（P0・実装改良）SVG/SMIL & CSS transition のアニメ signal
対象 `_ANIMATION_SIGNALS`:
- `<animate`, `<animateTransform`, `<animateMotion`, `<set` (SMIL)、CSS `animation:` / `transition:` を animation_signal として追加。
- テスト: マトリクス #4,#18。

### WP-4（P0・実装改良）smoke 診断の堅牢化
対象 `atlas_playwright_smoke_verifier.py` 例外ハンドラ & `_is_browser_not_installed_error`、`scripts/smoke_ui_modes_playwright.py` の `launch_browser_with_retry`:
- 例外 reason に**例外型名**を付与（空 `playwright_error:` 撲滅）。`playwright_error:` プレフィックスは維持（hard/soft 分類不変）。
- browser-not-installed 検知を堅牢化（空/ローカライズ/`BrowserType.launch` を含むメッセージ）。検知時は `browser_smoke_skipped: playwright_browser_not_installed`。
- テスト: マトリクス #14,#15（`sync_playwright` を monkeypatch し、空例外・"Executable doesn't exist"・通常エラーを撃ち分け）。

### WP-5（P1・実装改良）サンプリング堅牢化 & 明示診断
対象 `_check_style_changes_over_time` / `_check_canvas_changes_over_time` / `_serve_artifact_dir`:
- `_ANIMATION_MAX_WAIT_MS` / `_ANIMATION_POLL_INTERVAL_MS` を env 可変化（`ATLAS_VISUAL_SAMPLE_MAX_MS` / `_INTERVAL_MS`）でCI flaky 低減。
- canvas taint/CORS → `animation_not_detected:canvas_inaccessible` を明示 reason 化。
- `_serve_artifact_dir` の bind 失敗 → warning を診断に残す（file:// フォールバックは維持）。
- テスト: fake page でタイミング/ taint / bind 失敗分岐（ブラウザ不要）。

### WP-6（P1・実装改良）エントリ HTML 解決 & CSS-only 視覚タスク
対象 `_resolve_visual_html` / `_is_visual_task`:
- 複数 `.html` のとき **`index.html` を優先**（無ければ最初）。
- `.html` が無く CSS/JS のみの視覚タスクは、リンク元 HTML を辿る or `verification_command_missing` を明示理由化（誤って success にしない）。
- テスト: マトリクス #11 系の多 HTML、CSS-only ケース。

### WP-7（P1・実装改良）タスクキーワードの単語境界整合
対象 `_ANIMATION_TASK_HINT`（smoke）/ `_ANIMATION_TASK_KEYWORDS`（static）/ 新 `_COLOR_TASK_KEYWORDS`/`_MOTION_TASK_KEYWORDS`:
- 単語境界化（"inanimate" が "animat" に誤マッチしない 等）。smoke と static のキーワードを**整合**（片方だけ animation 扱いになる不一致を解消）。
- テスト: 偽陽性（"inanimate object"）/ 整合（同 task で両者の is_animation 判定が一致）。

### WP-8（P2・任意）将来パターン
- 動的に書き換えられる HTML（JSで innerHTML 構築）、操作必須アニメの `_nudge_interaction` 強化、requirement_coverage の複数形/語幹許容。**P0/P1 完了後・余力時のみ**。本書末尾に TODO として残してよい。

---

## 連続実装プロトコル（最後まで止めない）

1. WP-0 → WP-1 → … の順。各 WP は「実装改良（必要なら）→ テスト → 緑 → コミット」。
2. **テストが赤のまま次 WP へ進まない**。既存テストを安易に書き換えて緑にしない（設計を直す）。
3. 既着手の `visual_contract_falsenegative` 指示が実装済みなら、WP-1/WP-2 は**差分のみ延伸**（重複実装しない）。
4. 停止してよいのは「全 DoD 達成」または「設計判断が必要で推測続行が安全/正しさを損なう」場合のみ。後者は途中までを push し、本書末尾「ブロッカー記録」に記載して停止。
5. P2(WP-8) は任意。P0+P1 完了で DoD 達成とみなしてよい。

## 全体検証ゲート（最後に実行）

```bash
python -m pytest \
  tests/test_visual_contract_matrix.py \
  tests/test_atlas_visual_artifact_verifier.py \
  tests/test_atlas_playwright_smoke_verifier.py \
  tests/test_atlas_auto_verification_service.py \
  tests/test_atlas_pr8_visual_verification_wiring.py \
  tests/test_atlas_pr9_visual_depth.py \
  -q
```
ブラウザ導入環境では `python -m playwright install chromium` 後に PW-gated テストも緑であること。`scripts/run_debug_test_matrix.py` の static_contracts プリセットが緑であること。lint/型チェックが構成されていれば通す。

> 既知の無関係 fail（対象外）: `test_phase30_1...test_docs_state_chrome_extension_not_required`、`test_atlas_single_item_self_correction_loop...preserves_high_risk_gate`。新たな赤を増やさないことが基準。

## チェックリスト

- [x] WP-0 フィクスチャ + マトリクス駆動テスト
- [x] WP-1 静的色検出拡張（実装+テスト）
- [x] WP-2 motion タスク連動（実装+テスト）
- [x] WP-3 SVG/SMIL & transition signal（実装+テスト）
- [x] WP-4 smoke 診断堅牢化（実装+テスト）
- [ ] WP-5 サンプリング堅牢化 & 明示診断（実装+テスト）
- [ ] WP-6 エントリHTML解決 & CSS-only（実装+テスト）
- [ ] WP-7 キーワード単語境界整合（実装+テスト）
- [ ] WP-8 将来パターン（任意 / TODO 記載可）
- [ ] 全体検証ゲート通過・既存緑・回帰なし
- [ ] 本書末尾に「実装完了サマリ」追記、ブランチへ push（PR は未作成）

## ガードレール

- PR 作成・マージはしない（ユーザー明示指示まで）。バックエンドの安全方針（direct merge / remote push / self-apply 無効）と承認・ロールバックの意味を変えない。
- 既存の公開 reason 文字列のプレフィックス（`browser_smoke_failed:` / `browser_smoke_warning:` / `visual_missing:` / `js_error:`）を壊さない（消費側がある）。
- モデル識別子や本書のメタ情報をコミット/コード/PR に含めない。

## 最終報告（完了時に本書末尾へ追記）

「## 実装完了サマリ」: 変更ファイル一覧（WP別）、追加テスト数と pytest 最終行、マトリクス網羅状況、残 TODO（WP-8 等）。ブロック時は「## ブロッカー記録」。
