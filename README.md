# CodeAgent Personal

ローカルLLMを使ったAIコードエージェントプラットフォーム。マルチモデルオーケストレーション・Dockerサンドボックス・パーマネントメモリを備え、コードの計画・実装・テスト・実行をエージェントが自律的に行います。

---

## 主な機能

### エージェントコア

| 機能 | 説明 |
|---|---|
| **マルチモデルオーケストレーション** | タスクの種類に応じてRouter LLM (1.2B) が最適なモデルへ自動ルーティング |
| **4段階フォールバック** | 失敗時: 同一再試行 → 別アプローチ → 3案生成 → プランナーLLM自動選択 |
| **プランナーLLM** | 複数失敗時に小型モデル(GPT-OSS-20B)が最適案を自動選択して再実行 |
| **V-model検証** | 全タスク完了後に Unit → Integration → 要件確認の3フェーズ自動テスト |
| **スキップ禁止フォールバック** | スキップ・ユーザー委任は提案・選択されない（常にエージェントが解決） |

### パーマネントメモリ（cross-project共有）

| 機能 | 説明 |
|---|---|
| **自動知識蓄積** | 全ジョブ完了後にログを解析してエラー解決策・環境知識・ワークフローをDB保存 |
| **タスク実行時参照** | 各タスク開始前にメモリを検索し、関連知識をコンテキストに注入 |
| **リトライ改善** | Stage 1/2再試行時に過去の類似エラーと解決策を自動注入して忘却を防止 |
| **使用回数ブースト** | よく参照されたメモリエントリが検索結果で上位表示（対数スケール） |
| **手動管理** | Memoryタブから追加・編集・削除・キーワード検索が可能 |
| **カテゴリ分類** | `error_solution` / `env_knowledge` / `workflow` / `general` |

メモリDB: `./memory.db`（全プロジェクト共有 SQLite）

### SKILLシステム

| 機能 | 説明 |
|---|---|
| **SKILL自動生成** | Stage 3失敗時にエラーを解析して不足ツールをPython関数としてSKILL化 |
| **ポストジョブ提案** | ジョブ完了後に実行ログを解析して不足SKILLをUIに提案 |
| **使用回数ソート** | プロンプトへのSKILL注入を使用回数降順でソート（実績のあるSKILLを優先） |
| **SKILL.md形式** | OpenClaw互換。`./skills/スキル名/SKILL.md` に保存 |
| **ホットリロード** | 10秒キャッシュでSKILLを自動更新。再起動不要 |
| **自動生成ON/OFF** | 設定パネルのトグルで制御（デフォルト: ON） |

### Dockerサンドボックス

| コンテナ | イメージ | 用途 |
|---|---|---|
| `claude_sandbox` | `python:3.11-slim` | Python実行・仮想環境 |
| `codeagent_browser` | `mcr.microsoft.com/playwright/python:v1.49.0-jammy` | ブラウザ自動化（Playwright） |
| `node:20-slim` | `node:20-slim` | Node.js/npm実行 |

**Playwright自動回復**: コンテナイメージ不一致を検出した場合に自動再作成。`playwright`モジュールが見つからない場合もリトライ。

### エージェントツール一覧

**ファイル操作**
- `read_file` / `write_file` / `edit_file` — ファイル読み書き・部分編集
- `patch_function` — 関数単位の差し替え（AST解析）
- `get_outline` — コード構造のAST解析
- `list_files` — プロジェクトファイル一覧

**コード実行（Docker）**
- `run_python` — Python in `claude_sandbox`
- `run_node` / `run_npm` — Node.js/npm
- `run_file` — Pythonファイル直接実行
- `setup_venv` — Python仮想環境構築

**サーバー・ブラウザ**
- `run_server` — HTTPサーバー起動（port 8888）
- `run_browser` — Playwright（Chromium headless）
- `stop_server` — サーバー停止

**ユーティリティ**
- `web_search` — DuckDuckGo検索（設定でON/OFF）
- `clarify` — ユーザーへの確認・選択肢提示

**カスタムSKILL** — `./skills/` に追加したSKILL.mdが自動でツールとして利用可能

### UI

| 機能 | 説明 |
|---|---|
| **リアルタイムSSE** | Server-Sent Eventsによるストリーミング表示（TPS/token数表示） |
| **5タブパネル** | Output / Preview / Log / Skills / Memory |
| **ファイルブラウザ** | プロジェクトファイルをリアルタイム表示・iframe preview |
| **設定パネル** | ⚙ボタンから: Steps・Auto Select・SKILL自動生成・ストリーミング・コンテキスト長・検索件数・LLM URL |
| **モバイル対応** | iPhone対応。タブバーはスクロール可能。Safe area対応 |
| **プロジェクト管理** | 複数プロジェクトを切り替え・作成 |
| **ジョブ履歴** | 実行中ジョブへの自動再接続。SQLite永続化 |
| **Markdownレンダリング** | marked.jsによる出力のMarkdown表示 |

---

## 機能評価と推奨度

### ✅ 有効・推奨機能

| 機能 | 状態 | 備考 |
|---|---|---|
| エージェントタスク実行 | ✅ 安定 | 4段階フォールバック実装済み |
| パーマネントメモリ | ✅ 新機能 | `memory.db` 共有 |
| SKILLシステム | ✅ 安定 | 自動生成・提案・ポストジョブ分析 |
| Playwright ブラウザ | ✅ 安定 | コンテナ自動修復実装済み |
| マルチモデル切り替え | ✅ 安定 | Router LLMで自動ルーティング |
| V-model検証 | ✅ 動作 | 全タスク完了時のみ実行 |
| Web検索 (DuckDuckGo) | ✅ 動作 | 設定パネルでON/OFF |

### ⚠️ 限定的・条件付き機能

| 機能 | 状態 | 備考 |
|---|---|---|
| `run_file` | ⚠️ 制限あり | コンテナパスの一致が必要。`run_python`で代替推奨 |
| `clarify` ツール | ⚠️ 実験的 | エージェントからの質問機能。応答タイムアウト600秒 |
| `patch_function` | ⚠️ 限定 | Python AST依存。構文エラーがあるファイルでは失敗 |
| LLMストリーミング | ⚠️ モデル依存 | 一部モデルで特殊トークンが出力される場合あり |
| V-model Unit Test | ⚠️ 精度可変 | LLMがテストコードを生成するため、テスト品質はモデル依存 |

### ❌ 廃止済み機能

| 機能 | 状態 | 理由 |
|---|---|---|
| LLM登録UI（複数エンドポイント管理） | ❌ 廃止 | 設定パネルの「LLM URL」テキスト入力に統合 |
| スキップ・手動実装フォールバック | ❌ 廃止 | 常にエージェントが解決する方針に変更 |

---

## 必要環境

| 項目 | 要件 |
|---|---|
| OS | Windows 10/11 |
| Python | 3.11+ |
| Docker | Desktop 最新版 |
| llama.cpp | llama-server バイナリ |
| GPU | VRAM 16GB+ 推奨 |
| RAM | 32GB+ 推奨 |

---

## セットアップ

### 1. llama-server インストール

```bat
DLllama.bat
```

バックエンド (Vulkan / HIP / CUDA) を選択。GPUドライバに合わせてください。

### 2. モデルのダウンロード

GGUF形式モデルを用意し、`start.bat` 内のモデルパスを編集。

### 3. 起動

```bat
start.bat
```

`http://localhost:8000` を開いてください。

---

## 対応モデル

| モデルキー | モデル名 | VRAM | 速度 | 用途 |
|---|---|---|---|---|
| `basic` | GPT-OSS-20B | 11.5GB | 154 tok/s | 常駐・汎用・プランナー |
| `router` | LFM2.5-1.2B | 1.6GB | 291 tok/s | タスク分類 |
| `gpt_oss` | GPT-OSS-20B | 11.8GB | 154 tok/s | 汎用推論 |
| `gemma` | Gemma-3-12B | 8GB | 60 tok/s | バランス型 |
| `mistral` | Mistral-Small-3.2-24B | 11.2GB | 37 tok/s | JSON安定・検証 |
| `qwen35` | Qwen3.5-35B-A3B | 19.7GB | 28 tok/s | 高品質コード生成 |
| `coder` | Qwen3-Coder-Next | 32.2GB | 13 tok/s | 最高品質 (SWE-bench 70.6%) |

---

## アーキテクチャ

```
CodeAgentPersonal/
├── main.py            # FastAPI バックエンド (4500行+)
│   ├── ModelManager   — 動的モデル切り替え
│   ├── ToolSet        — 16種のエージェントツール
│   ├── JobRunner      — 4段階フォールバック + SKILL自動生成
│   ├── MemoryDB       — パーマネントメモリ (memory.db)
│   ├── SkillSystem    — SKILL.md管理・ホットリロード
│   └── VerifyEngine   — V-model 3フェーズ検証
├── ui.html            # フロントエンド SPA (2800行+)
│   ├── SSE streaming  — リアルタイムジョブ監視
│   ├── Memory tab     — メモリ検索・管理UI
│   ├── Skills tab     — SKILL一覧・提案UI
│   └── Settings modal — 全設定を一元管理
├── memory.db          # パーマネントメモリ (自動生成)
├── skills/            # カスタムSKILL格納フォルダ
│   └── スキル名/SKILL.md
├── workspace/         # プロジェクトファイル格納
│   └── プロジェクト名/
├── benchmark_mem.py   # VRAM/RAM計測ツール
├── start.bat          # Windows起動スクリプト
└── DLllama.bat        # llama.cppバイナリ自動ダウンロード
```

---

## 主要 API エンドポイント

| メソッド | パス | 説明 |
|---|---|---|
| `POST` | `/jobs/submit` | ジョブ投入（バックグラウンド実行） |
| `GET` | `/jobs/{id}/poll` | ジョブイベントポーリング |
| `POST` | `/chat` | 直接LLMチャット |
| `POST` | `/plan` | タスクプランのみ生成 |
| `GET` | `/memory` | メモリ一覧・検索 (`?q=キーワード`) |
| `POST` | `/memory` | メモリ手動追加 |
| `PUT` | `/memory/{id}` | メモリ更新 |
| `DELETE` | `/memory/{id}` | メモリ削除 |
| `POST` | `/memory/analyze/{job_id}` | ジョブからメモリ手動抽出 |
| `GET` | `/skills` | SKILL一覧 |
| `POST` | `/skills` | SKILL保存 |
| `DELETE` | `/skills/{name}` | SKILL削除 |
| `GET` | `/projects` | プロジェクト一覧 |
| `POST` | `/search/enable` | Web検索有効化 |
| `GET` | `/health` | ヘルスチェック |
