# CodeAgent Personal

CodeAgent Personal は、ローカルLLM、llama.cpp、FastAPI、Web UI、Docker/venv実行環境を組み合わせた、個人向けの自律型コードエージェント基盤です。

チャット、タスク実行、エージェントループ、モデル管理、永続メモリ、SKILL拡張、音声入出力、文書検索・レポート生成を統合し、ローカルPCやRunpod上で開発作業を支援します。

単なるチャットUIではなく、LLMがプロジェクト内のファイルを読み、編集し、コマンドを実行し、テスト結果を見て再試行するための開発支援プラットフォームです。

---

## 1. 概要

CodeAgent Personal は、以下の機能を統合したローカルファーストのAI開発環境です。

- ローカルLLM / llama.cpp / GGUFモデルの利用
- FastAPIバックエンドによるAPI提供
- Web UIによるチャット、タスク、モデル、メモリ、SKILL管理
- AgentLoopによる計画、実行、評価、再試行
- プロジェクトファイルの読み書き、パッチ適用、検索、コマンド実行
- SQLiteによる永続メモリ
- SKILL.md によるツール拡張
- Nexusによる文書投入、検索、Web調査、レポート生成
- Echoによる音声入力、ASR、翻訳、TTS連携
- Qwen3-TTS / Style-Bert-VITS2 などのTTS実行環境連携
- Windowsローカル / Linux / Runpod での運用

---

## 2. このプロジェクトで出来ること

| 分類 | 出来ること |
|---|---|
| Chat | ローカルLLMと会話し、必要に応じてプロジェクト文脈やWeb検索を利用できます |
| Task | ユーザーの指示をもとに、ファイル編集、コマンド実行、検証を含む開発タスクを実行できます |
| Agent | Planner / Executor / Evaluator を使った自律的な実装ループを実行できます |
| Models | GGUFモデルの管理、llama-server起動、ロール割当、VRAM確認を行えます |
| Memory | エラー解決策、環境知識、ワークフローをSQLiteに永続化できます |
| SKILL | `SKILL.md` によるツール拡張や、自動生成されたスキルの利用ができます |
| Nexus | 文書アップロード、検索、Web調査、Evidence管理、レポート生成を行えます |
| Echo | 音声入力、ASR、LLM翻訳、TTS読み上げ、録音保存を行えます |
| TTS | Qwen3-TTS / Style-Bert-VITS2 などの音声生成ランタイムと連携できます |
| Sandbox | Docker、venv、Runpod環境を使ってコードを実行できます |
| Git | タスク実行前後のスナップショットや変更履歴確認に利用できます |

---

## 3. 主要な利用モード

### 3.1 Chat

通常のチャットモードです。

用途:

- 技術相談
- 実装方針の相談
- コード説明
- 軽い修正案の作成
- Web検索を含む調査

### 3.2 Task

具体的な開発タスクを実行するモードです。

用途:

- バグ修正
- ファイル追加
- UI修正
- API追加
- テスト実行
- ログ解析
- 実装修正

### 3.3 Agent

より自律的に動くコードエージェントモードです。

Agentは、以下の流れで作業します。

1. ユーザー指示を読む
2. 必要なプロジェクト文脈を集める
3. 実行計画を立てる
4. ツールを使ってファイル確認・編集・コマンド実行を行う
5. 実行結果を評価する
6. 失敗時はエラー情報をもとに再試行する
7. 必要に応じてユーザーへ確認する

### 3.4 Echo

音声入力と音声出力を扱うモードです。

用途:

- 音声入力
- 音声認識
- リアルタイム翻訳
- TTS読み上げ
- 参照音声を使った音声生成
- 録音・文字起こし保存

### 3.5 Nexus

文書検索・調査支援モードです。

用途:

- PDFや文書のアップロード
- テキスト抽出
- ライブラリ検索
- Web調査
- Evidence整理
- レポート生成
- 成果物ダウンロード

---

## 4. 内部アーキテクチャ

| コンポーネント | 役割 |
|---|---|
| FastAPI backend | API、SSE、ジョブ管理、モデル管理、ツール呼び出しを担当します |
| Web UI | Chat / Task / Agent / Echo / Nexus / Models / Skills / Memory などの操作画面を提供します |
| AgentLoop | 計画、実行、評価、再試行を統合するエージェント中核です |
| Planner | 次に行うべき作業やアクションを計画します |
| Executor | ツール呼び出し、ファイル操作、コマンド実行を行います |
| Evaluator | 実行結果を評価し、成功・失敗・再試行の判断を行います |
| ToolRegistry | Agentから呼び出せるツールを登録・管理します |
| MemoryStore | SQLiteによる永続メモリを管理します |
| SKILL system | `SKILL.md` ベースで追加ツールや手順を管理します |
| ModelManager | llama-server、モデルDB、モデルロード、ロール割当を管理します |
| Nexus | 文書投入、検索、Web調査、Evidence、レポート生成を担当します |
| TTS runtimes | Qwen3-TTS / Style-Bert-VITS2 などの音声生成を担当します |
| EchoVault | Echo関連の録音、文字起こし、成果物を保存します |

---

## 5. Agentツール一覧

Agentモードでは、ToolRegistryに登録されたツールを使って作業します。

### 5.1 基本ツール

| ツール | 用途 |
|---|---|
| `read_file` | ファイルを読み込みます |
| `write_file` | ファイルを書き込みます |
| `apply_patch` | Git patch形式で変更を適用します |
| `search_code` | プロジェクト内のコードやテキストを検索します |
| `run_command` | プロジェクト内で任意コマンドを実行します |
| `run_tests` | テストコマンドを実行します |
| `get_error_trace` | 直近の失敗情報やエラートレースを取得します |

### 5.2 Nexus連携ツール

| ツール | 用途 |
|---|---|
| `nexus_search_library` | Nexusライブラリ内の文書を検索します |
| `nexus_web_search` | Web検索を実行し、検索結果をNexus Evidenceとして保存して`job_id`を返却します。返却された`job_id`は`nexus_build_report` / `nexus_export_bundle`に接続可能です |
| `nexus_build_report` | Evidenceや検索結果からレポートを生成します |
| `nexus_build_report_legacy` | 旧形式のNexusレポート生成を実行します |
| `nexus_upload_document` | Nexusへ文書をアップロードします |
| `nexus_news_scan` | ニュース調査を実行します |
| `nexus_market_research` | マーケット調査を実行します |
| `nexus_export_bundle` | Nexus成果物をバンドル出力します |

---

## 6. 機能詳細

## 6.1 チャット機能

Chatでは、ローカルLLMと通常の会話ができます。

主な機能:

- OpenAI互換の `/v1/chat/completions` エンドポイントを持つLLMサーバーと接続
- llama.cpp / llama-server との連携
- ストリーミング表示
- Markdown表示
- Web検索設定が有効な場合の検索利用
- プロジェクト文脈を使った相談

---

## 6.2 タスク実行機能

Taskでは、指定したプロジェクトに対して開発タスクを実行します。

主な機能:

- ファイル読み取り
- ファイル書き込み
- パッチ適用
- コード検索
- コマンド実行
- テスト実行
- エラー解析
- 再試行
- 実行ログ表示
- プレビュー表示

---

## 6.3 Agent機能

Agentは、Planner / Executor / Evaluator を使って自律的に作業します。

基本フロー:

```text
User Request
  ↓
Context Builder
  ↓
Planner
  ↓
Tool Action
  ↓
Executor
  ↓
Evaluator
  ↓
Retry / Finish / Clarify
```

想定用途:

- UI修正
- API追加
- バグ修正
- ログからの原因特定
- テスト失敗の修正
- 小規模なリファクタリング
- READMEや仕様書の整備

---

## 6.4 モデル管理

CodeAgent Personal は、llama.cpp の `llama-server` を利用してローカルLLMを呼び出します。

主な機能:

- llama-server の自動検出
- `LLAMA_SERVER_PATH` による明示指定
- 起動時のモデルDB確認
- モデルの自動ロード要求
- OpenAI互換APIへの接続
- Planner / Executor / Chat / Light などの用途別LLM URL
- GGUFモデル管理
- VRAM使用量確認
- VLM / Vision用途のモデル管理

主なLLM URL:

| 変数 | 用途 |
|---|---|
| `LLM_URL` | 既定のLLM API URL |
| `CODEAGENT_LLM_PLANNER` | Planner用LLM |
| `CODEAGENT_LLM_EXECUTOR` | Executor用LLM |
| `CODEAGENT_LLM_CHAT` | Chat用LLM |
| `CODEAGENT_LLM_LIGHT` | 軽量処理用LLM |
| `CODEAGENT_LLM_MODE` | LLM実行モード |

既定では、ローカルの以下に接続します。

```text
http://127.0.0.1:8080/v1/chat/completions
```

---

## 6.5 Memory

Memoryは、タスクやエラーから得た知識を永続化する仕組みです。

保存先:

```text
ca_data/memory.db
```

想定されるメモリ種別:

| 種別 | 内容 |
|---|---|
| `error_solution` | エラーと解決策 |
| `env_knowledge` | 環境固有の知識 |
| `workflow` | 作業手順 |
| `general` | その他の知識 |

用途:

- 過去のエラー解決策を再利用
- 環境固有の注意点を保持
- タスク実行時に関連メモリを文脈として利用
- UIから検索・編集・削除

---

## 6.6 SKILL

SKILLは、`SKILL.md` によってCodeAgentの能力を拡張する仕組みです。

保存先:

```text
ca_data/skills/
```

Runpod既定:

```text
/workspace/ca_data/skills/
```

環境変数で上書きできます。

```text
CODEAGENT_SKILLS_DIR=/path/to/skills
```

基本構成:

```text
ca_data/skills/
└─ sample_skill/
   └─ SKILL.md
```

`SKILL.md` の例:

```md
# Sample Skill

## Purpose

このスキルは、特定のログ形式を解析するための手順を提供します。

## When to use

- サーバーログを解析するとき
- エラー原因を分類するとき

## Steps

1. ログ全体を読む
2. ERROR / WARN / Traceback を抽出する
3. 発生時刻順に整理する
4. 原因候補と修正案を提示する
```

---

## 6.7 Nexus

Nexusは、文書投入、検索、Web調査、レポート生成を扱う調査支援機能です。

主な機能:

- 文書アップロード
- テキスト抽出
- チャンク化
- ライブラリ検索
- Evidence生成
- Web検索
- ニュース調査
- マーケット調査
- レポート生成
- バンドル出力
- 成果物ダウンロード

Nexusの永続化先:

```text
ca_data/nexus/
├─ nexus.db
├─ uploads/
├─ extracted/
├─ reports/
└─ exports/
```

### Nexusの基本フロー

```text
Upload
  ↓
Extract
  ↓
Search
  ↓
Evidence
  ↓
Report
  ↓
Download / Export
```

---

## 6.8 Echo / ASR / TTS

Echoは、音声を扱うモードです。

主な機能:

- マイク録音
- 音声認識
- LLM翻訳
- TTS読み上げ
- 録音・文字起こし保存
- 参照音声アップロード
- TTSエンジン切替

Echo関連データ保存先:

```text
ca_data/EchoVault/
```

アップロード音声の既定上限:

```text
ECHO_UPLOAD_MAX_BYTES=104857600
```

対応候補フォーマット:

```text
wav, mp3, m4a, webm, ogg, flac
```

---

## 6.9 TTS

TTSは、複数の音声生成ランタイムを扱います。

確認されている主な連携:

- Qwen3-TTS
- Style-Bert-VITS2

Style-Bert-VITS2 のモデル保存先は、Runpodでは以下が既定です。

```text
/workspace/ca_data/tts/style_bert_vits2/models
```

環境変数で指定できます。

```text
CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR=/path/to/models
```

TTS機能はモデルサイズ、依存ライブラリ、GPU環境の影響を強く受けるため、環境ごとの検証が必要です。

---

## 7. ディレクトリ構成

主要構成は以下です。

```text
CodeAgentPersonal/
├─ main.py                         # FastAPI backend
├─ agent/                          # AgentLoop, Planner, Executor, Evaluator, Tools
│  ├─ loop.py
│  ├─ planner.py
│  ├─ executor.py
│  ├─ evaluator.py
│  ├─ memory.py
│  └─ tools/
│     ├─ builtin.py
│     ├─ nexus_tools.py
│     └─ registry.py
├─ app/
│  ├─ nexus/                       # Nexus document/search/report features
│  └─ tts/                         # TTS runtimes
├─ ui/                             # Web UI
├─ assets/                         # UI assets
├─ scripts/
│  ├─ start_codeagent.py           # Cross-platform launcher
│  ├─ runpod_start.sh              # Runpod startup script
│  └─ setup_llama_runpod.sh        # Runpod llama.cpp setup
├─ ca_data/                        # Persistent data
│  ├─ memory.db
│  ├─ model_db.db
│  ├─ skills/
│  ├─ workspace/
│  ├─ EchoVault/
│  └─ nexus/
├─ .codeagent/                     # Credentials and local private data
├─ start.bat                       # Windows launcher
├─ requirements.txt
└─ README.md
```

---

## 8. 必要環境

| 項目 | 推奨 / 必須 |
|---|---|
| OS | Windows 10/11, Linux, Runpod |
| Python | 3.11推奨 |
| FastAPI | `requirements.txt` から導入 |
| llama.cpp | `llama-server` が必要 |
| Docker | サンドボックス実行や一部機能で使用 |
| Git | patch適用、履歴管理、開発作業に必要 |
| RAM | 32GB以上推奨 |
| VRAM | 16GB以上推奨 |
| GPU | NVIDIA CUDA / AMD Vulkan / CPU fallback など環境に応じて利用 |
| Node.js | Node系プロジェクトやUIビルドで必要になる場合あり |

最小依存は `requirements.txt` に定義されています。

```text
fastapi
python-multipart
uvicorn
websockets
requests
pydantic
psutil
faster-whisper
```

TTS関連は依存衝突を避けるため、別requirementsに分離されている場合があります。

---

## 9. セットアップ

## 9.1 Windows ローカル

### 1. リポジトリを取得

```bat
git clone https://github.com/souten-yd/CodeAgentPersonal.git
cd CodeAgentPersonal
```

### 2. llama-server を準備

`llama-server` を配置するか、環境変数で指定します。

```bat
set LLAMA_SERVER_PATH=C:\path\to\llama-server.exe
```

未指定の場合、ランチャーは以下を探索します。

```text
./llama/llama-server.exe
./llama/llama-server
./llama/bin/llama-server
```

### 3. 起動

```bat
start.bat
```

`start.bat` は `scripts/start_codeagent.py` を呼び出す薄いラッパーです。

初回起動時、ローカル環境では `venv_sys/` が作成され、`requirements.txt` の依存がインストールされます。

### 4. ブラウザで開く

```text
http://localhost:8000
```

LAN内の別端末からアクセスする場合は、起動ログに表示されるLAN IPを使用します。

---

## 9.2 Linux / Runpod

### 通常起動

```bash
python scripts/start_codeagent.py
```

### Runpod用起動

```bash
bash scripts/runpod_start.sh
```

Runpodでは、既定で以下のような永続パスを使用します。

```text
/workspace/ca_data
/workspace/ca_data/workspace
/workspace/ca_data/skills
/workspace/LLMs
/workspace/llama
```

Runpodでの主な既定値:

| 項目 | 既定値 |
|---|---|
| `CODEAGENT_CA_DATA_DIR` | `/workspace/ca_data` |
| `CODEAGENT_WORK_DIR` | `/workspace/ca_data/workspace` |
| `CODEAGENT_SKILLS_DIR` | `/workspace/ca_data/skills` |
| llama root | `/workspace/llama` |
| FastAPI port | `8000` |
| llama-server port | `8080` |

---

## 10. 起動コマンド

### Windows

```bat
start.bat
```

### Linux / Runpod

```bash
python scripts/start_codeagent.py
```

### オプション付き起動

```bash
python scripts/start_codeagent.py --host 0.0.0.0 --port 8000 --primary-port 8080
```

| オプション | 既定値 | 説明 |
|---|---|---|
| `--host` | `0.0.0.0` | FastAPIのホスト |
| `--port` | `8000` | FastAPIのポート |
| `--primary-port` | `8080` | llama-serverのポート |
| `--api-timeout` | `120` | FastAPI起動待ち秒数 |
| `--llm-timeout` | `180` | LLM起動待ち秒数 |

---

## 11. 基本的な使い方

## 11.1 Chatを使う

1. Web UIを開く
2. Chat入力欄に質問を入力
3. 必要に応じてモデルや検索設定を変更
4. 回答を確認

用途例:

```text
このエラーの原因を説明して
この関数をリファクタリングして
この設計の問題点を教えて
```

---

## 11.2 Task / Agentを使う

1. プロジェクトを選択
2. 入力欄に実行したいタスクを書く
3. TaskまたはAgentを実行
4. Output / Log / Preview / Git / Memory を確認
5. 失敗時はログを見て再実行、またはAgentに修正を依頼

タスク例:

```text
Echo画面の録音ボタンが再度押さないと録音待機に戻らない問題を修正してください。
原因を特定し、必要なUI状態管理とAPI処理を修正してください。
```

---

## 11.3 Modelsを使う

1. Models画面を開く
2. GGUFモデルを検索
3. モデルをダウンロードまたは既存パスを登録
4. ロールを割り当てる
5. 必要に応じてモデルをロード

主なロール:

| ロール | 用途 |
|---|---|
| `plan` | 計画作成 |
| `chat` | 通常会話 |
| `search` | 検索・調査 |
| `verify` | 検証 |
| `code` | コーディング |
| `complex` | 複雑な実装 |
| `reason` | 推論 |
| `multi` | VLM / 画像認識 |
| `translate` | 翻訳 |

---

## 11.4 Memoryを使う

Memory画面では、永続メモリを確認・編集できます。

用途:

- 過去のエラー解決策の確認
- 環境固有の注意点の保存
- よく使う作業手順の保存
- 不要なメモリの削除

---

## 11.5 SKILLを追加する

1. `ca_data/skills/` にスキル用ディレクトリを作成
2. `SKILL.md` を作成
3. CodeAgentを起動またはホットリロードを待つ
4. Agentが必要に応じて参照

例:

```text
ca_data/skills/log_analysis/SKILL.md
```

---

## 11.6 Echoを使う

1. Echo画面を開く
2. マイク入力を開始
3. 音声認識結果を確認
4. 翻訳または応答生成
5. TTS読み上げ
6. EchoVaultに保存された録音や文字起こしを確認

---

## 11.7 Nexusを使う

1. Nexus画面を開く
2. 文書をUpload
3. Job状態を確認
4. Searchで検索
5. Evidenceを確認
6. Reportを生成
7. BundleまたはReportをDownload

---

## 12. 主要API

FastAPI backend は `main.py` と `app/nexus/` 以下でAPIを提供します。

以下は主要APIです。細かい内部APIは実装を確認してください。

---

## 12.1 System / Health

| Method | Path | 用途 |
|---|---|---|
| `GET` | `/health` | FastAPIの疎通確認 |
| `GET` | `/system/summary` | CPU / RAM / GPU / VRAM などのシステム概要取得 |

---

## 12.2 Models

| Method | Path | 用途 |
|---|---|---|
| `GET` | `/models/db/status` | モデルDBの状態確認 |
| `POST` | `/model/auto-load` | 既定モデルの自動ロード要求 |
| `GET` | `/models/...` | モデル一覧、検索、設定取得系 |
| `POST` | `/models/...` | モデル登録、更新、ダウンロード系 |

実際のモデルAPIは変更される可能性があるため、`main.py` の route 定義を確認してください。

---

## 12.3 Nexus

Nexusは `app.include_router(nexus_router, prefix="/nexus")` で `/nexus` 以下に登録されています。

### Health / Summary

| Method | Path | 用途 |
|---|---|---|
| `GET` | `/nexus/health` | Nexus疎通確認 |
| `GET` | `/nexus/summary` | Nexusサマリー取得 |
| `GET` | `/nexus/dashboard/summary` | Dashboard用サマリー取得 |

### Documents

| Method | Path | 用途 |
|---|---|---|
| `GET` | `/nexus/documents` | 文書一覧取得 |
| `GET` | `/nexus/library/documents` | ライブラリ文書一覧取得 |
| `GET` | `/nexus/documents/{document_id}` | 文書詳細取得 |
| `DELETE` | `/nexus/documents/{document_id}` | 文書削除 |
| `DELETE` | `/nexus/library/documents/{document_id}` | ライブラリ文書削除 |
| `GET` | `/nexus/library/documents/{document_id}/download` | 元文書ダウンロード |
| `GET` | `/nexus/library/documents/{document_id}/download/text` | 抽出テキストダウンロード |
| `GET` | `/nexus/library/documents/{document_id}/download/markdown` | 抽出Markdownダウンロード |

### Jobs / Evidence

| Method | Path | 用途 |
|---|---|---|
| `GET` | `/nexus/jobs/active` | アクティブジョブ一覧 |
| `GET` | `/nexus/jobs/{job_id}` | ジョブ状態取得 |
| `GET` | `/nexus/jobs/{job_id}/events` | ジョブイベント取得 |
| `GET` | `/nexus/evidence` | Evidence一覧取得 |

### Upload / Search

| Method | Path | 用途 |
|---|---|---|
| `POST` | `/nexus/upload` | 文書アップロード |
| `POST` | `/nexus/search` | Nexusライブラリ検索 |
| `POST` | `/nexus/ask` | 検索結果をもとに簡易回答 |

### Web Search / Research

| Method | Path | 用途 |
|---|---|---|
| `POST` | `/nexus/web/search` | Web検索 |
| `GET` | `/nexus/web/status` | Web検索プロバイダ状態 |
| `POST` | `/nexus/web/research` | Web調査ジョブ開始 |
| `POST` | `/nexus/web/collect` | Webソース収集 |

### Research Jobs

| Method | Path | 用途 |
|---|---|---|
| `POST` | `/nexus/research/run` | Researchジョブ開始 |
| `GET` | `/nexus/research/jobs/{job_id}` | Researchジョブ状態 |
| `GET` | `/nexus/research/jobs/{job_id}/events` | Researchイベント |
| `GET` | `/nexus/research/jobs/{job_id}/answer` | Research回答取得 |
| `GET` | `/nexus/research/jobs/{job_id}/sources` | ソース一覧取得 |
| `GET` | `/nexus/research/jobs/{job_id}/evidence` | Evidence取得 |
| `GET` | `/nexus/research/jobs/{job_id}/bundle` | Research結果バンドル取得 |

### Sources

| Method | Path | 用途 |
|---|---|---|
| `GET` | `/nexus/sources/{source_id}` | ソース詳細取得 |
| `GET` | `/nexus/sources/{source_id}/text` | ソース本文取得 |
| `GET` | `/nexus/sources/{source_id}/markdown` | Markdown取得 |
| `GET` | `/nexus/sources/{source_id}/original` | 元ソース取得 |
| `GET` | `/nexus/sources/{source_id}/chunks` | チャンク取得 |

### News / Market

| Method | Path | 用途 |
|---|---|---|
| `POST` | `/nexus/news/search` | ニュース検索 |
| `POST` | `/nexus/news/scan` | ニューススキャン |
| `POST` | `/nexus/news/mvp` | ニュースMVP調査 |
| `POST` | `/nexus/market/research` | マーケット調査 |
| `POST` | `/nexus/market/compare` | マーケット比較 |
| `POST` | `/nexus/market/mvp` | マーケットMVP調査 |
| `GET` | `/nexus/news/watchlists` | Watchlist一覧 |
| `GET` | `/nexus/news/watchlists/{watchlist_id}` | Watchlist詳細 |

---

## 12.4 Echo / TTS

Echo / TTS APIは `main.py` と `app/tts/` の実装を参照してください。

主な用途:

| 分類 | 用途 |
|---|---|
| Echo状態取得 | 録音・認識・TTS状態の取得 |
| 音声アップロード | 参照音声や入力音声のアップロード |
| ASR | 音声認識 |
| TTS | 音声生成 |
| Style-Bert-VITS2 | モデル一覧、音声生成、インポート |
| Qwen3-TTS | Qwen3-TTSランタイムによる音声生成 |

---

## 13. 環境変数

## 13.1 Core

| 変数名 | 既定値 | 用途 |
|---|---|---|
| `LLM_URL` | `http://localhost:8080/v1/chat/completions` | 既定LLM URL |
| `CODEAGENT_LLM_PLANNER` | `LLM_URL` | Planner用LLM |
| `CODEAGENT_LLM_EXECUTOR` | `LLM_URL` | Executor用LLM |
| `CODEAGENT_LLM_CHAT` | `LLM_URL` | Chat用LLM |
| `CODEAGENT_LLM_LIGHT` | `LLM_URL` | 軽量処理用LLM |
| `CODEAGENT_LLM_MODE` | `single` または launcher指定値 | LLM実行モード |
| `LLAMA_SERVER_PATH` | 自動検出 | llama-serverのパス |
| `LLAMA_ROOT_DIR` | ローカル `./llama` / Runpod `/workspace/llama` | llama.cpp配置先 |
| `CODEAGENT_RUNTIME` | 自動判定 | `runpod`, `local`, `docker` などの実行環境指定 |
| `CODEAGENT_CA_DATA_DIR` | ローカル `./ca_data` / Runpod `/workspace/ca_data` | 永続データ保存先 |
| `CODEAGENT_WORK_DIR` | `ca_data/workspace` | プロジェクト作業ディレクトリ |
| `CODEAGENT_SKILLS_DIR` | `ca_data/skills` | SKILL保存先 |
| `CODEAGENT_MODEL_DB_PATH` | `ca_data/model_db.db` | モデルDBパス |
| `CODEAGENT_SYS_VENV_DIR` | `venv_sys` | ローカル起動用system venv |
| `CODEAGENT_TEST_CMD` | 自動推定 | `run_tests` の既定コマンド |

---

## 13.2 Runpod

| 変数名 | 既定値 | 用途 |
|---|---|---|
| `RUNPOD_POD_ID` | Runpod側で設定 | Runpod判定 |
| `RUNPOD_API_KEY` | Runpod側で設定 | Runpod判定 |
| `RUNPOD_AUTO_SETUP_LLAMA` | `true` | llama-serverがない場合に自動セットアップ |
| `RUNPOD_AUTO_INSTALL_DOCKER` | `true` 想定 | Docker自動導入 |
| `RUNPOD_BOOTSTRAP_VENV` | `/workspace/.venvs/codeagent-bootstrap` 想定 | Runpod起動用venv |
| `RUNPOD_BOOTSTRAP_PYTHON` | `python3.11` 優先 | 起動venv作成に使うPython |

---

## 13.3 Nexus

| 変数名 | 既定値 | 用途 |
|---|---|---|
| `NEXUS_ENABLE_WEB` | `true` | Web検索有効化 |
| `NEXUS_ENABLE_NEWS` | `true` | ニュース機能有効化 |
| `NEXUS_ENABLE_MARKET` | `true` | マーケット機能有効化 |
| `NEXUS_WEB_SEARCH_PROVIDER` | `searxng` | Web検索プロバイダ |
| `NEXUS_SEARXNG_URL` | Runpod: `http://127.0.0.1:8088` / 非Runpod: `http://searxng:8080` | SearXNG URL |
| `NEXUS_SEARCH_FALLBACK_PROVIDERS` | `searxng` | 検索フォールバック |
| `NEXUS_SEARCH_FREE_ONLY` | `true` | 無料プロバイダのみ許可 |
| `NEXUS_SEARCH_PAID_PROVIDERS_ENABLED` | `false` | 有料/クォータ制プロバイダ許可 |
| `NEXUS_SEARCH_PROVIDER_COOLDOWN_SEC` | `3600` | プロバイダ再試行クールダウン |
| `BRAVE_SEARCH_API_KEY` | 空 | Brave Search利用時のAPIキー |
| `NEXUS_MAX_UPLOAD_MB` | `200` | 最大アップロードサイズ |
| `NEXUS_MAX_DOWNLOAD_MB` | `20` | 1ファイル最大ダウンロードサイズ |
| `NEXUS_MAX_TOTAL_DOWNLOAD_MB` | `100` | 合計最大ダウンロードサイズ |
| `NEXUS_MAX_DOWNLOADS` | `20` | 最大ダウンロード数 |
| `NEXUS_DOWNLOAD_TIMEOUT_SEC` | `15` | ダウンロードタイムアウト |

---

## 13.4 Echo / TTS

| 変数名 | 既定値 | 用途 |
|---|---|---|
| `ECHO_UPLOAD_MAX_BYTES` | `104857600` | Echo音声アップロード上限 |
| `CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR` | Runpod: `/workspace/ca_data/tts/style_bert_vits2/models` | Style-Bert-VITS2モデル保存先 |

TTS関連は依存とモデルサイズの影響が大きいため、実行環境ごとの設定確認が必要です。

---

## 14. データ保存先

| パス | 内容 |
|---|---|
| `ca_data/memory.db` | 永続メモリ |
| `ca_data/model_db.db` | モデルDB |
| `ca_data/skills/` | SKILL |
| `ca_data/workspace/` | プロジェクト作業領域 |
| `ca_data/EchoVault/` | Echoの録音・文字起こし・成果物 |
| `ca_data/nexus/nexus.db` | Nexus DB |
| `ca_data/nexus/uploads/` | Nexusアップロード文書 |
| `ca_data/nexus/extracted/` | Nexus抽出テキスト |
| `ca_data/nexus/reports/` | Nexusレポート |
| `ca_data/nexus/exports/` | Nexusエクスポート |
| `.codeagent/.credentials` | GitHubトークン等の機密情報 |
| `venv_sys/` | ローカル起動用system venv |

### Git管理の注意

以下は通常Gitに含めないでください。

```text
ca_data/
.codeagent/
venv_sys/
.venv/
__pycache__/
*.db
```

Runpod運用では `/workspace/ca_data` を永続化対象にしてください。

---

## 15. 開発者向け情報

## 15.1 Backend起動

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

通常はランチャー経由を推奨します。

```bash
python scripts/start_codeagent.py
```

---

## 15.2 UIを変更する

主に以下を確認します。

```text
ui/
ui.html
assets/
```

起動時に `scripts/start_codeagent.py` が `ui.html` を `ui/index.html` にコピーする処理を持つため、UI更新時はコピー処理も考慮してください。

---

## 15.3 Agentツールを追加する

主な場所:

```text
agent/tools/builtin.py
agent/tools/nexus_tools.py
agent/tools/registry.py
```

追加手順:

1. `builtin.py` または専用ファイルに関数を追加
2. 戻り値を dict 形式にする
3. `registry.py` で `registry.register()` する
4. Agentが呼び出せるようにプロンプト・ツール定義を更新する

---

## 15.4 Nexus APIを追加する

主な場所:

```text
app/nexus/router.py
app/nexus/
```

追加手順:

1. `router.py` にエンドポイント追加
2. 必要な処理を `app/nexus/` 以下の責務別モジュールに分離
3. UI側から呼び出し
4. READMEのAPI一覧を更新

---

## 15.5 TTSランタイムを追加する

主な場所:

```text
app/tts/
```

確認対象:

- `engine_registry`
- `qwen3_tts_runtime`
- `style_bert_vits2_runtime`
- `style_bert_vits2_manager`
- `style_bert_vits2_paths`

追加時は依存衝突を避けるため、TTSごとにvenv分離する構成も検討してください。

---

## 16. トラブルシューティング

## 16.1 FastAPIが起動しない

確認:

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

確認ポイント:

- Python 3.11を使っているか
- `requirements.txt` が入っているか
- ポート8000が使用中ではないか
- `main.py` import時にTTS依存で落ちていないか

---

## 16.2 llama-serverに接続できない

確認:

```text
http://127.0.0.1:8080/health
```

確認ポイント:

- `LLAMA_SERVER_PATH` が正しいか
- llama-serverが存在するか
- モデルがロードできているか
- ポート8080が空いているか
- GPUメモリ不足になっていないか

---

## 16.3 モデルがロードできない

確認ポイント:

- GGUFファイルが壊れていないか
- VRAMが足りているか
- `--n-gpu-layers` が過大ではないか
- Vulkan / CUDA / HIP のバックエンドが環境に合っているか
- context size が大きすぎないか

---

## 16.4 Dockerが使えない

確認:

```bash
docker ps
```

確認ポイント:

- Docker Desktopが起動しているか
- Linuxではdocker daemonが起動しているか
- Runpodイメージにdockerが入っているか
- 権限があるか

---

## 16.5 SKILLが反映されない

確認ポイント:

- `CODEAGENT_SKILLS_DIR` が正しいか
- `SKILL.md` の配置が正しいか
- ファイル名が `SKILL.md` になっているか
- キャッシュやホットリロード待ちではないか

---

## 16.6 Memoryが効かない

確認ポイント:

- `ca_data/memory.db` が存在するか
- `CODEAGENT_CA_DATA_DIR` が想定通りか
- Runpodで `/workspace/ca_data` が永続化されているか
- DBが破損していないか

---

## 16.7 Nexus検索が失敗する

確認:

```bash
curl http://127.0.0.1:8000/nexus/health
curl http://127.0.0.1:8000/nexus/web/status
```

確認ポイント:

- `NEXUS_ENABLE_WEB=true` か
- `NEXUS_WEB_SEARCH_PROVIDER` が正しいか
- SearXNGが起動しているか
- `NEXUS_SEARXNG_URL` が正しいか
- Braveを使う場合は `BRAVE_SEARCH_API_KEY` が設定されているか

---

## 16.8 Echoで録音できない

確認ポイント:

- ブラウザのマイク権限
- iPhone Safari / Chrome の録音制約
- HTTPSが必要な環境ではないか
- 音声フォーマットが対応しているか
- `ECHO_UPLOAD_MAX_BYTES` を超えていないか

---

## 16.9 TTSモデルがロードできない

確認ポイント:

- モデルファイルが存在するか
- TTS用依存が入っているか
- GPU/CPU設定が正しいか
- Transformersやtorchのバージョンが合っているか
- Qwen3-TTSとStyle-Bert-VITS2の依存が衝突していないか

---

## 17. 実装状況

| 機能 | 状態 | 備考 |
|---|---|---|
| Chat | Stable | 基本会話機能 |
| Task | Experimental | ファイル編集・実行・検証を含む |
| Agent | Experimental | Planner / Executor / Evaluator ベース |
| Models | Experimental | GGUF/llama-server管理 |
| Memory | Stable | SQLite永続化 |
| SKILL | Experimental | `SKILL.md` ベース |
| Nexus | Experimental | 文書検索、Web調査、Evidence、Report |
| Echo | Experimental | ASR/TTS連携 |
| Qwen3-TTS | Experimental | 依存・GPU環境に注意 |
| Style-Bert-VITS2 | Experimental | モデル配置と依存に注意 |
| Runpod support | Experimental | `/workspace/ca_data` 永続化推奨 |

---

## 18. 推奨運用

### ローカル開発

- Windowsでは `start.bat` を使う
- `venv_sys/` は自動作成に任せる
- モデルは `C:\LLMs` や `./llama/models` など分かりやすい場所に置く
- `ca_data/` はバックアップ対象にする

### Runpod運用

- `/workspace/ca_data` を永続化する
- モデルは `/workspace/LLMs` に置く
- llama.cpp は `/workspace/llama` に配置する
- 起動は `scripts/runpod_start.sh` を使う
- TTSモデルも `/workspace/ca_data/tts/` 以下に置く

### Agent利用

- 1回の指示は具体的に書く
- 期待する修正範囲を書く
- テスト方法がある場合は明記する
- 大規模変更は段階的に依頼する
- 仕様不足がある場合はAgentに選択肢付きで質問させる

---

## 19. ライセンス

ライセンスファイルが存在する場合は、その内容に従ってください。

ライセンスが未設定の場合、このリポジトリの利用・再配布条件は明示されていません。公開・配布・商用利用を行う前にライセンスを設定してください。

---

## 20. 関連メモ

このREADMEは、CodeAgent Personalを「使う人」と「開発する人」の両方が参照できるように、概要、機能、起動方法、API、環境変数、保存先、開発者向け情報を一体化したものです。

APIや環境変数は実装変更に追従して更新してください。特に `main.py`、`agent/tools/registry.py`、`app/nexus/router.py`、`app/tts/` を変更した場合は、このREADMEも更新してください。

### TTS回帰テスト（軽量）

- `python scripts/check_style_bert_vits2_tts.py`
- `python scripts/check_style_bert_vits2_regression.py`
- `pytest -q tests/test_style_bert_vits2_tts_contract_regression.py tests/test_tts_language_router.py tests/test_text_normalizer_jp_extra.py`
- UIスモーク（Playwright）: `python scripts/smoke_ui_modes_playwright.py`
  - backend E2Eスモーク（opt-in）: `RUN_ATLAS_BACKEND_E2E=1 python scripts/smoke_ui_modes_playwright.py`
  - Playwright未導入時:
    - `python -m pip install playwright`
    - `python -m playwright install chromium`
  - Optional CI（manual）: `.github/workflows/playwright-ui-smoke.yml`（`workflow_dispatch` only, backend E2E is not enabled by default）

> モデル未配置環境では、モデル実体が必要なケースは `pytest` の `tmp_path` + `monkeypatch` で代替できるようにしてあります。

- Phase 25.4: Playwright UI smoke now aggregates scenario diagnostics, uploads artifacts, and fails at the end if any scenario failed (backend E2E remains opt-in via RUN_ATLAS_BACKEND_E2E=1).

- Phase 25.4.1: Playwright UI smoke now opens UI on HTTP origin (`http://127.0.0.1:<port>/`) with lightweight mock API responses, isolates scenarios by page/viewport, and writes concise summary + full per-scenario artifacts (backend E2E still opt-in).

## Playwright UI smoke (optional, manual)
- Optional Playwright UI smoke can be run manually (workflow_dispatch).
- Expected current baseline result is 9/9 PASS.
- Backend E2E remains explicit opt-in (`RUN_ATLAS_BACKEND_E2E=1`).
- Artifact summary is available in GitHub Actions (`artifacts/playwright/summary.md` + step summary).
