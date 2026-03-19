# CodeAgent

ローカルLLMを使ったAIコードエージェントプラットフォームです。マルチモデルオーケストレーション、Dockerサンドボックス、リアルタイムWebUIを備え、コードの計画・実装・テスト・実行をエージェントが自律的に行います。

## 特徴

- **マルチモデルオーケストレーション** — タスクの複雑さに応じて最適なLLMへ自動ルーティング
- **エージェント型タスク実行** — 計画・実装・検証・修正を反復ループで自動化
- **Dockerサンドボックス** — Python・Node.js・ブラウザ(Playwright)を隔離環境で実行
- **リアルタイムUI** — SSE(Server-Sent Events)によるストリーミング表示
- **Webサーチ統合** — DuckDuckGoによる検索をエージェントが自律的に活用
- **プロジェクト管理** — セッション履歴・ジョブ管理をSQLiteで永続化

## 必要環境

| 項目 | 要件 |
|---|---|
| OS | Windows 10/11 (起動スクリプトはWindows用) |
| Python | 3.11+ |
| Docker | Desktop 最新版 |
| llama.cpp | llama-server バイナリ |
| GPU | VRAM 16GB+ 推奨 (RX9070XT等) |
| RAM | 32GB+ 推奨 |

## セットアップ

### 1. llama-server のインストール

```bat
DLllama.bat
```

バックエンド選択 (Vulkan / HIP / CUDA) のプロンプトが表示されます。GPUに合わせて選択してください。

### 2. モデルのダウンロード

GGUF形式のモデルを用意し、`start.bat` 内のモデルパスを編集してください。

### 3. サーバーの起動

```bat
start.bat
```

起動後、ブラウザで `http://localhost:8000` を開いてください。

## 対応モデル

| モデル | VRAM | 速度 | 用途 |
|---|---|---|---|
| GPT-OSS-20B | 11.5 GB | 154 tok/s | 常駐基盤・汎用推論 |
| LFM2.5-1.2B (Router) | 1.6 GB | 291 tok/s | タスク分類・ルーティング |
| Gemma-3-12B | 8 GB | 60 tok/s | バランス型汎用 |
| Mistral-Small-3.2-24B | 11.2 GB | 37 tok/s | JSON安定・構造化出力 |
| Qwen3.5-35B-A3B | 19.7 GB | 28 tok/s | 高品質コード生成 |
| Qwen3-Coder-Next | 32.2 GB | 13 tok/s | 最高品質コード (SWE-bench 70.6%) |

## アーキテクチャ

```
CodeAgentPersonal/
├── main.py            # FastAPI バックエンド (4200行)
│                      #   ModelManager, ツール実装, エージェントループ, SQLite永続化
├── ui.html            # フロントエンド SPA (2500行)
│                      #   SSEストリーミング, プロジェクト管理, Markdownレンダリング
├── benchmark_mem.py   # VRAM/RAM 計測ツール
├── start.bat          # Windows 起動スクリプト
└── DLllama.bat        # llama.cpp バイナリ自動ダウンロード
```

## 主要 API エンドポイント

| メソッド | パス | 説明 |
|---|---|---|
| POST | `/task/stream` | ジョブ型ストリーミングタスク実行 |
| POST | `/chat` | 直接LLMチャット (エージェントなし) |
| POST | `/plan` | タスクプランのみ生成 |
| GET | `/projects` | プロジェクト一覧 |
| POST | `/projects` | プロジェクト作成 |
| GET | `/projects/{name}/history` | セッション履歴 |
| GET | `/llm/props` | 現在のモデル情報 |
| POST | `/search/enable` | Webサーチ有効化 |

## ツール一覧

エージェントが利用できるツール:

- `read_file` / `write_file` / `edit_file` — ファイル操作
- `patch_function` — 関数単位の差し替え
- `list_files` / `get_outline` — プロジェクト構造把握
- `run_python` / `run_node` / `run_npm` — コード実行 (Docker)
- `run_server` / `run_browser` — HTTPサーバー起動・Playwrightブラウザ操作
- `setup_venv` — Python仮想環境構築
- `web_search` — DuckDuckGo検索
- `clarify` — ユーザーへの確認・選択肢提示
