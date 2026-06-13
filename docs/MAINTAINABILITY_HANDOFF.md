# 保守性リファクタ 引き継ぎ書（新規セッション / Codex 用）

> 親計画: [`docs/MAINTAINABILITY_PLAN.md`](./MAINTAINABILITY_PLAN.md)。本書は**現在地と次の着手手順**のみ。

## 現在地（2026-06-14 時点）

`main.py` の薄いラッパー系ルートを `app/api/*.py`（`APIRouter`）へ抽出済み。`main.py` **18,034 → 17,541 行**。

| 抽出済みルーター | 参考 PR |
|---|---|
| `app/api/git.py` | #1825 |
| `app/api/skills.py` `memory.py` `repo.py` | #1826 |
| `app/api/ensemble.py` `voice.py` | #1827 |
| `app/api/mcp.py` | #1828 |

登録は `app/server.py::include_routers()`、`main.py` 228行 `include_routers(app)` 経由で `main:app` に反映。

## 確立した抽出パターン（薄いラッパー）

1. `app/api/<domain>.py` を作成し `router = APIRouter(tags=["<domain>"])`。
2. `main.py` の `@app.<verb>(...)` を `@router.<verb>(...)` へ移動（ロジックはそのまま）。
3. ハンドラが参照する **main のヘルパー/状態/モデルは関数本体内で遅延 import**
   （`from main import X`）。※ `include_routers` は 228行で実行され、ヘルパーは main の後方定義のため、**トップレベル import は循環**になる。遅延 import（=リクエスト時、main 完全ロード後）で回避。
4. `app/server.py::include_routers()` に import 追加＋`app.include_router(<router>)`。
5. `main.py` の元定義を削除し参照コメントを残す。
6. 契約テスト追加（`tests/test_router_extraction_*` を踏襲）。

## 残り（密結合グループ）と着手順

`models`(14) → `tts`(11) → `echo`(8) → `agent`(8) → `api/runs`(18) → `api/plans`(7) → 残り small（`task` `debug` `asr` `model` `system` `stream` `llm` `chat` `projects`(5) `jobs`(5)）。

### 密結合グループの注意

- これらは module 状態（例: `agent_state` / `agent_state_lock`）・Pydantic モデル（`AgentTaskDecisionRequest` 等）・重いロジックに依存。**いずれも main の名前空間にあるため遅延 import で参照可能**（薄いラッパーと同じ手が使える）。
- ただし本体が長い（agent は ~240 行）。**転記ミスを避けるため、コードはエディタで丸ごと移動**し、変更は `@app.`→`@router.` と遅延 import の付与のみに限定する。
- さらに整理したい場合は、ヘルパー本体を `app/services/<domain>.py` へ移し、main と router の双方がそこから import する形にする（計画書 §4.3）。**一段深い変更なので別 PR に分離**。
- 状態オブジェクトを跨ぐグループ（agent/echo）は、状態が**単一の main インスタンスで共有される**点を壊さないこと（複製しない／遅延 import で同一オブジェクトを参照）。

### 各グループの主な依存（遅延 import 対象の目安）

- **agent**: `agent_state`, `agent_state_lock`, `AgentSession`, `_require_project_key`, `_log_agent_registry_tools`, `execute_chat_with_optional_web_search`, `_resolve_runtime_llm_url`, `_resolve_effective_search_enabled`, `_execute_agent_session_queue`, `AgentTaskDecisionRequest`, `AgentTaskProjectRequest`, `AgentTaskReviseRequest`
- **models/tts/echo**: 各ドメインの管理関数・`_model_manager`・ASR/TTS ランタイム・echo セッション状態（`_echo_sessions` 等）。グループ単位で `grep -nE '@app\.[a-z]+\("/<grp>'` で範囲特定 → 依存を洗い出す。

## 検証ゲート（各 PR 必須）

```bash
python -m py_compile main.py app/api/<domain>.py app/server.py
# 循環なし & 全ルート登録（heavy import: ~1-2分）
python -c "import main; print(sorted(r.path for r in main.app.routes if r.path.startswith('/<grp>')))"
python -m pytest tests/test_router_extraction_*_contract.py -q
```

DoD: 挙動非変更／上記3つ緑／`main.py` 行数減／元定義跡にコメント。

## フロント（M3/M4・別軸）

`ui.html` の 14,194 行インライン script を `web/js` へ分割（計画書 §3）。**各フェーズでブラウザ起動検証が必須**（オーナー実施）。共有 `let/const` は `state.js` 先頭ロード＋順序厳守＋関数のみ移動。`ui.html` が編集対象（`ui/index.html` は gitignore の生成物）。

## 未処理

- **#1824（Lumen 集約: Nexus/Forge/Echo 完全移動）はブラウザ目視検証が未実施**。各モード（Chat/Echo/Nexus/Forge/Atlas/Portal/Agent）の起動確認を要する。

## 新規セッションへの起動プロンプト例

> `docs/MAINTAINABILITY_PLAN.md` と `docs/MAINTAINABILITY_HANDOFF.md`、参考 PR #1825〜#1828 を読み、`main.py` の密結合グループを `models→tts→echo→agent→api/runs→api/plans` の順に1グループ1PRで抽出。確立パターン（遅延 import）に従い、密結合本体はエディタで丸ごと移動して差分を最小化。各 PR は py_compile＋`import main`（循環なし・全ルート登録）＋契約テスト緑をマージ条件に。
