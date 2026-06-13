# 保守性改善 計画書 — ui.html / main.py のモジュール分割

作成日: 2026-06-14 / 対象: `ui.html`（フロント）、`main.py`（バックエンド）

> 本書は **計画のみ**。コードは変更しない。各フェーズは独立 PR・挙動非変更（pure refactor）・検証付きで進める。

---

## 1. 現状（計測）

| ファイル | 行数 | 主因 |
|---|---|---|
| `ui.html` | 16,669 | **単一インライン `<script>` が 14,194 行**（インライン CSS は 7 行のみ） |
| `main.py` | 18,034 | **144 ルートが `app` 直付け** / 568 関数。`APIRouter` 使用は 3 のみ |
| `web/js/*.js`（既存） | 約 10,676 | 既に app.js/echo.js/panels.js/nexus.js/portal.js/forge.js/lumen*.js/skills_memory.js 等へ分割済み |
| `app/`（既存） | — | `app/api`, `app/lumen`, `app/nexus`, `app/portal`, `app/atlas`, `app/asr`, `app/audio` などのパッケージが存在 |

**結論**: 外部モジュール化の足場（`web/js/`、`app/`）は既にある。両モノリスを「既存パターンに沿って」段階的に薄くするのが本筋。

---

## 2. 原則

1. **挙動非変更**: 各 PR は pure refactor。コード移動のみで、ロジック・エンドポイント・DOM・データは変えない。
2. **増分**: 1 PR = 1 モジュール（または 1 ルーター群）。レビュー可能な粒度。
3. **検証ゲート**: 各フェーズで必ず検証してからマージ（§5）。
4. **ロールバック容易**: 移動単位が小さいので revert で即戻せる。
5. **契約テスト維持**: 既存の `tests/test_*_contract.py`（テキストレベル）を壊さない。移動でアンカー文字列が変わる場合のみテスト側も更新。

---

## 3. ui.html の分割計画

### 3.1 中核リスクと対策（最重要）

インライン script のトップレベルには `let mode = ...` など **script スコープの `let`/`const` 共有状態**がある。これらは classic script 間で共有される **global lexical environment** に入るため、別の classic script からも参照できる（実際 `panels.js` が `mode`/`saveLastSubtab` を参照して動作している）。

- ✅ **関数宣言の外出しは安全**（呼び出しは実行時。共有 lexical を参照可）。
- ⚠️ **トップレベルの実行文**（即時実行・TDZ）は、依存する `let`/`const` の宣言より後に走ると ReferenceError。→ 実行文は安易に動かさない。
- 🔑 **対策**: 共有状態を最初に読み込む `web/js/state.js` に集約し、**読み込み順序を厳守**（state → 既存基盤 → 新規モジュール → 末尾の bootstrap）。各 `<script src>` は `defer` を付けず、現状同様 `</body>` 直前の順序ロードを維持。

### 3.2 モジュール対応表（インライン script の `// ── X ──` 見出し基準）

| 新規ファイル | 取り込む既存セクション（目安行） |
|---|---|
| `web/js/state.js` | トップレベル共有 `let/const`（mode, 各種設定・状態） |
| `web/js/tts.js` | TTS (2790)、TTS翻訳 (3336)、SSEバッチTTS (3562) |
| `web/js/asr.js` | TTS/ASRタブ設定 (5279)、ASR設定 (5475)、音声クローン (5582) |
| `web/js/settings_db.js` | SETTINGS DB連動 (5685)、iOS Safari対応 (5673) |
| `web/js/init.js` | INIT (5886)、SYSTEM SUMMARY/HEALTH (5946) |
| `web/js/mode.js` | MODE/setMode/_setEchoTabVisibility/_updateMobTabs (6125)、FORGE SUBTABS (6816)、MOBILE/mobSwitch (9857) |
| `web/js/skills_proposals.js` | SKILL PROPOSALS (9986) |
| `web/js/git.js` | GIT (10085) |
| `web/js/model_db.js` | MODEL DATABASE (10195) |
| `web/js/drawer.js` | DRAWER (11067)、HISTORY LOADING (11286) |
| `web/js/input.js` | INPUT/TOKEN TRACKING (11341)、PREVIEW RUN (11370)、CLARIFY CARD (11375) |
| `web/js/chat_history.js` | CHAT HISTORY (11435) |
| `web/js/echo_mode.js` | ECHO MODE (11726)、Vaultファイルブラウザ (12866)、Vaultプレビュー/参照音声 (12999–13066) |
| `web/js/send.js` | SEND (13130)、MODEL SELECTOR (13160) |
| `web/js/plan.js` | guided workflow (15107)、PLAN APPROVAL (15228)、JOBポーリング (15324)、PROGRESS CARD (15588) |
| `web/js/messages.js` | MESSAGES (15692) |
| `web/js/output_preview.js` | OUTPUT PANEL (15882)、HTML PREVIEW (15921)、FILE BROWSER (15952)、INLINE EDITOR (16144) |
| `web/js/log.js` | LOG (16170)、AUTO SELECT/SKILL TOGGLES (16203) |

到達目標: インライン script は **bootstrap（DOMContentLoaded 配線）＋ごく少量**に縮小。

### 3.3 1モジュールあたりの手順（レシピ）

1. 対象セクションの関数群を新ファイルへ**そのまま移動**（リネーム禁止）。
2. 他ファイルから呼ばれる関数は末尾で `window.fn = fn;`（既存 panels.js の流儀に合わせる）。
3. `ui.html` の `</body>` 直前に `<script src="/static/js/<name>.js"></script>` を**依存順**で追加。
4. 移動元セクションを削除し、跡地に「moved to <file>」コメントを残す。
5. §5 の検証 → 緑なら PR。

### 3.4 順序（依存の浅い順 = 低リスクから）

`state.js` → `log.js` → `git.js` → `model_db.js` → `skills_proposals.js` → `tts.js`/`asr.js` → `messages.js`/`output_preview.js` → `drawer.js`/`chat_history.js`/`input.js` → `echo_mode.js` → `plan.js`/`send.js` → 最後に `mode.js`（最も結合が強い）。

### 3.5 注意

- **`ui/index.html` は gitignore**（生成物）。編集対象は **`ui.html`**（追跡）。（メモリ: ui-source-of-truth）
- インライン CSS は 7 行のみ。CSS 分割は対象外（既に `web/css/app.css` 外部化済み）。

---

## 4. main.py の分割計画

### 4.1 方針

144 ルートを **ドメイン別 `APIRouter`** へ抽出し、`main.py` は「アプリ生成 ＋ `include_router`」に縮小。ルートが依存する補助関数は段階的に `app/services/` 系へ移す（初期は import で繋ぐだけでも可）。配置は既存 `app/` パッケージに合わせる（例: `app/api/routers/`）。

### 4.2 ルーター対応表（パスプレフィックス基準）

| 新規ルーター | 取り込むルート（件数目安） |
|---|---|
| `runs_router` | `/api/runs` (18) |
| `plans_router` | `/api/plans` (7), `/plan` (1) |
| `models_router` | `/models` (14), `/model` (2), `/ensemble` (3) |
| `tts_router` | `/tts` (11), `/api/tts` (3), `/voice` (3) |
| `asr_router` | `/asr` (3) |
| `echo_router` | `/echo` (8) |
| `agent_router` | `/agent` (8) |
| `atlas_router` | `/api/atlas` (5) |
| `repo_router` | `/repo` (6) |
| `git_router` | `/git` (6) |
| `projects_router` | `/projects` (5) |
| `memory_router` | `/memory` (5) |
| `skills_router` | `/skills` (4) |
| `jobs_router` | `/jobs` (5) |
| `debug_router` | `/debug` (5), `/api/debug` (4) |
| `requirements_router` | `/api/requirements` (3) |
| `reviews_router` | `/api/reviews` (2) |
| `task_router` | `/task` (2), `/api/task` (2) |
| `misc_router` | `/chat`, `/stream`, `/llm`, `/mcp` (2), `/system`, `/ui` |

### 4.3 1ルーターあたりの手順（レシピ）

1. `router = APIRouter()` を作り、対象の `@app.get(...)` を `@router.get(...)` へ移動（パス・実装はそのまま）。
2. 依存する補助関数・グローバルは、まず `from main import ...` で繋ぐ（循環回避のため最終的に `app/services/` へ移す）。
3. `main.py` で `app.include_router(<router>)`。
4. §5 の検証（pytest）→ 緑なら PR。

### 4.4 順序（自己完結の高い順）

`git_router` → `memory_router` → `skills_router` → `repo_router` → `projects_router` → `asr_router`/`tts_router` → `models_router` → `echo_router` → `agent_router` → `atlas_router` → `runs_router`/`plans_router`（最も大きく依存も多い）→ 最後に `misc_router`。

---

## 5. 検証ゲート

| 対象 | 方法 |
|---|---|
| **main.py** | 既存 pytest スイートを実行（大量の `tests/test_*` が存在）。各ルーター抽出 PR で関連テスト＋スモークが緑であること。低リスク。 |
| **ui.html** | **各フェーズでアプリを起動し、全モード（Chat/Echo/Nexus/Forge/Atlas/Portal/Agent）と主要操作を目視確認**（本件のユーザー選択）。加えて `node --check`相当のインライン/外部 script 構文チェックと契約テスト。 |

ui.html フェーズの最低スモーク項目: 各モード切替、Nexus サブタブ（Memory/Skill/Log）、Forge サブタブ（Overview/Models/ASR/TTS）、Echo（Vault）、チャット送信、TTS/ASR、プラン承認フロー。

---

## 6. リスクと対策

- **JS 共有スコープ破壊** → `state.js` 先頭ロード＋順序厳守＋関数のみ移動（§3.1）。
- **読み込み順依存** → 末尾 `<script src>` の順序を依存順に固定。bootstrap は最後。
- **Python 循環 import** → 初期は `from main import helper` で繋ぎ、補助関数の `app/services/` 移設は後続 PR に分離。
- **契約テストのアンカーずれ** → 移動でアンカー文字列が動くテストのみ同 PR で更新。
- **大粒度化の誘惑** → 1 PR 1 モジュール厳守。混ぜない。

## 7. マイルストーン（提案）

- M1: `main.py` ルーター抽出（自己完結群: git/memory/skills/repo/projects）— 5 PR、pytest 検証。
- M2: `main.py` 中核群（models/echo/agent/atlas/runs/plans）— 6 PR。
- M3: `ui.html` 低結合モジュール（state/log/git/model_db/skills_proposals）— 5 PR、起動検証。
- M4: `ui.html` 中核（mode/echo_mode/plan/send/messages/output_preview ほか）— 残り。

各 M 完了時に `main.py`/`ui.html` の行数を再計測し縮小を可視化する。

## 8. Definition of Done（各 PR）

- [ ] 挙動非変更（移動のみ）。
- [ ] 該当検証ゲート（pytest もしくは起動目視）が緑。
- [ ] 関連契約テスト緑（必要時のみ更新）。
- [ ] `main.py` または `ui.html` の行数が減っている。
- [ ] 移動跡地に参照コメントを残す。
