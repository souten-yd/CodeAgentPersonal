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
| **ハルシネーション防止** | ツール呼び出し実行を強化。LLMが既実行ツールを再呼び出しする幻覚リトライを検出・遮断 |
| **Gitスナップショット自動化** | タスク開始前・完了後にバックエンドが自動コミット。job_id/task_id/stageをタグ付け。古いスナップショットは自動アーカイブ（最新100件保持） |

### パーマネントメモリ（cross-project共有）

| 機能 | 説明 |
|---|---|
| **自動知識蓄積** | 全ジョブ完了後にログを解析してエラー解決策・環境知識・ワークフローをDB保存 |
| **タスク実行時参照** | 各タスク開始前にメモリを検索し、関連知識をコンテキストに注入 |
| **リトライ改善** | Stage 1/2再試行時に過去の類似エラーと解決策を自動注入して忘却を防止 |
| **使用回数ブースト** | よく参照されたメモリエントリが検索結果で上位表示（対数スケール） |
| **手動管理** | Memoryタブから追加・編集・削除・キーワード検索が可能 |
| **カテゴリ分類** | `error_solution` / `env_knowledge` / `workflow` / `general` |

メモリDB: `./ca_data/memory.db`（全プロジェクト共有 SQLite）

### SKILLシステム

| 機能 | 説明 |
|---|---|
| **SKILL自動生成** | Stage 3失敗時にエラーを解析して不足ツールをPython関数としてSKILL化 |
| **ポストジョブ提案** | ジョブ完了後に実行ログを解析して不足SKILLをUIに提案 |
| **使用回数ソート** | プロンプトへのSKILL注入を使用回数降順でソート（実績のあるSKILLを優先） |
| **SKILL.md形式** | OpenClaw互換。ローカル既定:`<CODEAGENT_CA_DATA_DIR>/skills/スキル名/SKILL.md`（通常 `./ca_data/skills/...`） / Runpod既定:`/workspace/ca_data/skills/スキル名/SKILL.md` |
| **ホットリロード** | 10秒キャッシュでSKILLを自動更新。再起動不要 |
| **自動生成ON/OFF** | 設定パネルのトグルで制御（デフォルト: ON） |

### 実行サンドボックス（環境別）

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
- `search_in_files` — プロジェクト内全文検索
- `make_dir` / `move_path` / `delete_path` — ディレクトリ作成・移動/改名・削除

**コード実行**
- `run_python` — Runpodではプロジェクト `.venv` 優先、その他環境では `claude_sandbox` (Docker)
- `run_node` / `run_npm` — Node.js/npm
- `run_file` — Runpodでは `.venv` 優先、その他環境では Docker
- `setup_venv` — Python仮想環境 `.venv` 構築
- `run_shell` — プロジェクトディレクトリで任意コマンド実行（pytest/ruff/mypy等）

**サーバー・ブラウザ**
- `run_server` — HTTPサーバー起動（port 8888）
- `run_browser` — Playwright（Chromium headless）
- `stop_server` — サーバー停止

**ユーティリティ**
- `web_search` — DuckDuckGo検索（設定でON/OFF）。チャットモードでも利用可能
- `clarify` — ユーザーへの確認・選択肢提示

**カスタムSKILL** — 既定のスキル保存先（ローカル:`<CODEAGENT_CA_DATA_DIR>/skills` / Runpod:`/workspace/ca_data/skills`）に追加したSKILL.mdが自動でツールとして利用可能（`CODEAGENT_SKILLS_DIR`で上書き可）

### UI

| 機能 | 説明 |
|---|---|
| **リアルタイムSSE** | Server-Sent Eventsによるストリーミング表示（TPS/token数表示） |
| **7タブパネル** | Output / Preview / Log / Skills / Memory / Git / Models |
| **音声入力（β）** | チャット入力欄の🎙ボタンで録音→サーバー側Whisperで文字起こし（日本語/英語） |
| **リソースメーター** | ヘッダーで CPU / RAM / GPU / VRAM 使用率を定期更新表示（`/system/summary` で軽量集約ポーリング） |
| **ファイルブラウザ** | プロジェクトファイルをリアルタイム表示・iframe preview |
| **設定パネル** | ⚙ボタンから: Steps・Auto Select・SKILL自動生成・Ensemble実行モード(parallel/serial)・VRAM監視・ストリーミング・コンテキスト長・検索件数・LLM URL |
| **GGUF検索/ダウンロード** | Modelsタブから Hugging Face のGGUFを検索し、RAM/VRAM適合目安（DL可否・完全オフロード可否）を確認して直接DL |
| **VLM Visionトグル** | VLMモデルごとに画像認識(vision)をON/OFF可能。OFF時はmulti用途の自動割り当て対象から除外 |
| **機能モード切替** | Modelsモーダルで `Model Orchestration` / `Ensemble(beta)` を切替可能（初期値: Model Orchestration） |
| **Coderオーケストレーション** | 軽量→高品質の3段コーダーを設定し、失敗時/品質未達時に段階昇格して再実行 |
| **VRAMガード** | `nvidia-smi/rocm-smi` で空きVRAMを監視し、必要時は `parallel → serial` へ自動切替（設定でON/OFF） |
| **Web検索状態表示** | 設定パネルとタスク進捗カードで検索クエリ・状態をリアルタイム表示 |
| **待機UIの統一** | チャット/タスク両モードで統一されたウェイティングカードUI |
| **Echo モード（同時通訳）** | マイク音声をリアルタイムで ASR → LLM翻訳 → TTS 読み上げ。全画面表示。録音・文字起こし・議事録を `ca_data/EchoVault/` に自動保存。ボイスクローン（参照音声指定）対応 |
| **モバイル対応** | iPhone対応。タブバーはスクロール可能。Safe area対応 |
| **プロジェクト管理** | 複数プロジェクトを切り替え・作成 |
| **プロジェクトDL** | プロジェクト一覧の`DL`ボタンからPLフォルダをzipでダウンロード |
| **ジョブ履歴** | 実行中ジョブへの自動再接続。SQLite永続化 |
| **Markdownレンダリング** | marked.jsによる出力のMarkdown表示 |

---

## 機能評価と推奨度

### ✅ 有効・推奨機能

| 機能 | 状態 | 備考 |
|---|---|---|
| エージェントタスク実行 | ✅ 安定 | 4段階フォールバック + ハルシネーション防止実装済み |
| パーマネントメモリ | ✅ 安定 | `ca_data/memory.db` 共有 |
| SKILLシステム | ✅ 安定 | 自動生成・提案・ポストジョブ分析 |
| Playwright ブラウザ | ✅ 安定 | コンテナ自動修復実装済み |
| マルチモデル切り替え | ✅ 安定 | Router LLMで自動ルーティング |
| V-model検証 | ✅ 動作 | 全タスク完了時のみ実行 |
| Web検索 (DuckDuckGo) | ✅ 動作 | 設定パネルでON/OFF。チャット/タスク両モードで利用可 |
| Gitスナップショット自動化 | ✅ 安定 | タスク前後にバックエンドが自動コミット |
| チャットモードWeb検索 | ✅ 動作 | エージェントループ経由で`web_search`ツールを利用 |
| GitHubリポジトリ連携 | ✅ 動作 | `ca_data/`をGitHubへバックアップ |
| システムサマリーAPI | ✅ 安定 | `/system/summary` で軽量集約ポーリング |
| Echo モード（同時通訳） | ✅ 動作 | faster-whisper(ASR) + LLM翻訳 + Edge-TTS/VOICEVOX/Qwen3-TTS。EchoVault自動保存 |

### ⚠️ 限定的・条件付き機能

| 機能 | 状態 | 備考 |
|---|---|---|
| `run_file` | ⚠️ 制限あり | Runpodは`.venv`優先、非RunpodはDocker実行（環境差に注意） |
| `clarify` ツール | ⚠️ 実験的 | エージェントからの質問機能。応答タイムアウト600秒 |
| `patch_function` | ⚠️ 限定 | Python AST依存。構文エラーがあるファイルでは失敗 |
| LLMストリーミング | ⚠️ モデル依存 | 一部モデルで特殊トークンが出力される場合あり |
| V-model Unit Test | ⚠️ 精度可変 | LLMがテストコードを生成するため、テスト品質はモデル依存 |

### ❌ 廃止済み機能

| 機能 | 状態 | 理由 |
|---|---|---|
| LLM登録UI（複数エンドポイント管理） | ❌ 廃止 | 設定パネルの「LLM URL」テキスト入力に統合 |
| スキップ・手動実装フォールバック | ❌ 廃止 | 常にエージェントが解決する方針に変更 |
| UIからのGit操作（commit/checkout/reset） | ❌ 廃止 | バックエンドの自動スナップショットフローに移行 |

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

UIからのDLにも対応:
- Modelsタブでキーワード検索（downloads順 / 最新更新順）
- NVIDIAだけでなく **AMD Radeon (ROCm環境)** でも検索自体は可能（検索はHF API呼び出し）。VRAM取得は `rocm-smi` を優先対応
- LLMルートフォルダへ直接ダウンロード
- カタログからのダウンロード成功後はバックグラウンドでベンチマークを自動実行し、結果をモデルDBへ反映
- **Runpod(Ubuntu)** では既定保存先 `/workspace/LLMs`
- それ以外では既定保存先 `C:\LLMs`（必要に応じて任意フォルダへ変更可）

### 3. 起動

Windows:

```bat
start.bat
```

ローカル初回起動時は、ランチャーが自動でリポジトリ直下に `venv_sys/`（システム用Python仮想環境）を作成し、`requirements.txt` の依存導入を試行します（`requirements.txt` が無い場合は最小構成を自動生成）。  
2回目以降は `venv_sys/` の存在を確認して再利用し、その `python` で `uvicorn main:app` を起動します（毎回再作成しません）。

`CODEAGENT_SYS_VENV_DIR` を指定すると、`venv_sys` の配置先を変更できます。ローカルで Docker 実行する各ツール（`run_python`/`run_file`/`run_server`/`run_browser`/`run_npm`/`run_node`）はこの system venv を read-only マウントして起動します。

Runpod / Linux (自動起動コマンドにもそのまま利用可):

```bash
python scripts/start_codeagent.py
```

Runpodで「起動後に `docker.io` を自動導入」したい場合は、以下の起動スクリプトを使ってください（既定で有効）。

```bash
bash scripts/runpod_start.sh
```

- `RUNPOD_AUTO_INSTALL_DOCKER=true` (既定): `docker` が見つからない場合に `apt-get install docker.io` を実行
- `RUNPOD_AUTO_INSTALL_DOCKER=false`: Docker自動導入を無効化
- `RUNPOD_AUTO_SETUP_LLAMA=true` (既定): `llama-server` 不在時に `scripts/setup_llama_runpod.sh` で `ai-dock/llama.cpp-cuda` の **latest prebuilt** を取得し `/workspace/llama` へ配置
- `RUNPOD_AUTO_SETUP_LLAMA=false`: llama.cpp セットアップをスキップ
- `RUNPOD_AUTO_START_VOICEVOX=true`: 起動時に VOICEVOX の疎通確認を行う（Runpodでは `VOICEVOX_URL` の確認のみ。ローカルLinuxでは Docker自動起動も実施）
- `RUNPOD_VOICEVOX_START_TIMEOUT_SEC=120` (既定): VOICEVOX自動起動時の待機タイムアウト秒
- `RUNPOD_VOICEVOX_IMAGE=voicevox/voicevox_engine:cpu-ubuntu20.04-latest` (既定): 自動起動で使うイメージ
- `RUNPOD_VOICEVOX_CONTAINER_NAME=voicevox_engine` (既定): 自動起動で使うコンテナ名
- `RUNPOD_BOOTSTRAP_VENV=/workspace/.venvs/codeagent-bootstrap` (既定): Runpod起動時に利用する専用venv
- `RUNPOD_BOOTSTRAP_PYTHON` (既定: `python3.11` 優先、なければ `python3`): 起動時venv作成に使うPython実行ファイルを明示
- `CODEAGENT_RUNTIME=runpod` : Runpod判定を明示したい場合の強制フラグ（`/workspace` が存在する場合のみ有効）
- 既定のRunpod判定は `RUNPOD_POD_ID` / `RUNPOD_API_KEY` **かつ** `/workspace` 存在で判定
- Runpodでは `CODEAGENT_CA_DATA_DIR=/workspace/ca_data` が既定（`ca_data` をworkspaceへ永続保持）
- プロジェクトフォルダは既定で `CODEAGENT_WORK_DIR=/workspace/ca_data/workspace` を使用（`/workspace`配下で保持）
- スキル保存先は既定で `CODEAGENT_SKILLS_DIR=<CODEAGENT_CA_DATA_DIR>/skills`（Runpod既定は `/workspace/ca_data/skills`）
- Runpod環境の `run_python` / `run_file` はプロジェクト配下 `.venv` を利用（`setup_venv` で作成）

> `start.bat` は Python ランチャー (`scripts/start_codeagent.py`) を呼ぶ薄いラッパーです。  
> 起動ロジックを Python に共通化したため、Runpod の起動コマンドへ同じランチャーを指定できます。

`http://localhost:8000` を開いてください。

---

## ポート要件

**ユーザーが外部に公開する必要があるポートは 8000 番のみです。**

| ポート | 用途 | 公開要否 |
|---|---|---|
| **8000** | CodeAgent Web UI + API | ✅ 外部公開（Runpod HTTP ポートに設定） |
| 50021 | VOICEVOX Engine（任意） | ❌ サーバー内部のみ（公開不要） |
| 8888 | `run_server` ツール（Docker内） | ❌ Docker内部のみ（公開不要） |

Runpod では **HTTP Service のポートを 8000** に設定するだけで利用できます。

### VOICEVOX を使う場合（任意）

VOICEVOX は Docker で同一サーバー上に起動し、CodeAgent バックエンドがサーバー内部 (`localhost:50021`) から呼び出します。ユーザーは 50021 番ポートに直接アクセスしません。

#### A) 自動起動を有効化する場合（Runpod）

`scripts/runpod_start.sh` による起動時に、`VOICEVOX_URL` の疎通確認（`/version` と `/speakers`）を行います。話者が1件以上取得できるまで待機し、失敗時は診断ログを出します。  
※ Runpod では Pod 内で独自 Docker daemon を前提にした VOICEVOX コンテナ起動は行わず、接続先URLの検証のみ実施します。

```bash
export RUNPOD_AUTO_START_VOICEVOX=true
export VOICEVOX_URL=http://<reachable-voicevox-host>:50021
bash scripts/runpod_start.sh
```

- 成功時: `RUNPOD_VOICEVOX_AUTOSTART_STATUS=ready`
- 失敗時: `RUNPOD_VOICEVOX_AUTOSTART_HINT` に接続ヒントを設定
- UI側は `GET /tts/status` の `voicevox_diagnostics` / `voicevox_hint` / `voicevox_autostart_status` でヒント表示可能

#### B) 手動運用する場合（ローカルDocker/従来手順）

```bash
# CPU版（推奨）
docker run -d --name voicevox_engine \
  -p 127.0.0.1:50021:50021 \
  voicevox/voicevox_engine:cpu-ubuntu20.04-latest

# GPU版（NVIDIA）
docker run -d --name voicevox_engine \
  --gpus all \
  -p 127.0.0.1:50021:50021 \
  voicevox/voicevox_engine:nvidia-ubuntu20.04-latest
```

- `-p 127.0.0.1:50021:50021` とすることで **ホスト外部からはアクセスできない**（ポート公開不要）
- VOICEVOX が別ホストにある場合は環境変数で指定: `VOICEVOX_URL=http://<host>:50021`
- Settings パネルの「VOICEVOX URL」フィールドからも変更可能（設定は自動保存）
- 起動後、Settings → TTS → VOICEVOX の「接続テスト / ロード」ボタンで接続確認

### 依存が不足する場合（`fastapi` 未導入など）

```bash
python -m pip install -r requirements.txt
python scripts/check_environment.py
```

企業/クラウド環境でPyPIへの直接アクセスが制限される場合は、ミラーを指定してください。

```bash
PIP_INDEX_URL=https://<your-mirror>/simple python -m pip install -r requirements.txt
```

厳密に要件を検証したい場合は `--strict` を付けます。

```bash
python scripts/check_environment.py --expect-python 3.11 --strict
```

---

## Docker自動プッシュ（GitHub Actions）

Runpodで `docker pull` してすぐ使えるように、GitHub ActionsでDocker Hubへ自動プッシュできます。

### 1) 事前準備（GitHub Secrets）

リポジトリの **Settings → Secrets and variables → Actions** で以下を登録:

- `DOCKERHUB_USERNAME` : Docker Hubユーザー名
- `DOCKERHUB_TOKEN` : Docker Hub Access Token（PasswordではなくToken推奨）

### 2) 自動プッシュ条件

`.github/workflows/docker-publish.yml` により次のタイミングでビルド & push されます。

- `main` ブランチへの push
- `v*` 形式タグ（例: `v1.0.0`）の push
- 手動実行（`workflow_dispatch`）

イメージ名: `docker.io/<DOCKERHUB_USERNAME>/codeagent-personal`

### 3) Runpodでの使い方（ダウンロード〜起動）

RunpodのPod作成時、Container Imageに以下を指定:

```
docker.io/<DOCKERHUB_USERNAME>/codeagent-personal:latest
```

起動コマンド例:

```bash
python scripts/start_codeagent.py --host 0.0.0.0 --port 8000
```

必要なら `PORT` / `PRIMARY_PORT` を環境変数で上書きしてください。

### 4) ローカル確認コマンド

```bash
docker build -t codeagent-personal:local .
docker run --rm -p 8000:8000 codeagent-personal:local
```

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
├── main.py            # FastAPI バックエンド
│   ├── ModelManager   — 動的モデル切り替え / ロール別モデル選択
│   ├── ToolSet        — ファイル・実行・ブラウザ・検索ツール
│   ├── JobRunner      — Task実行 / フォールバック / 検証 / メモリ抽出 / ハルシネーション防止
│   ├── MemoryDB       — パーマネントメモリ管理
│   ├── SkillSystem    — SKILL.md管理・ツールロード・類似マージ
│   ├── VerifyEngine   — V-model 3フェーズ検証
│   ├── SnapshotManager — タスク前後のGit自動スナップショット管理
│   └── RepoManager    — GitHubリポジトリ連携・ca_dataシンク
├── ui.html            # フロントエンド SPA
│   ├── Chat / Task    — 会話（エージェントループ統合）・要件/計画・実行UI
│   ├── Output / Preview / Log
│   ├── Skills / Memory / Git / Models
│   └── Settings modal — 全設定を一元管理
├── ca_data/           # 実データの保存先
│   ├── memory.db      # パーマネントメモリ（スナップショット履歴テーブル含む）
│   ├── model_db.db    # モデルDB（設定永続化含む）
│   ├── skills/        # カスタムSKILL格納フォルダ
│   │   └── スキル名/SKILL.md
│   ├── EchoVault/     # Echo モードの録音・文字起こし・議事録
│   └── workspace/     # プロジェクトファイル格納
│       └── プロジェクト名/
├── .codeagent/        # センシティブデータ保存先（gitignore済み）
│   └── .credentials   # GitHubトークン等の資格情報（APIで非公開）
├── benchmark_mem.py   # VRAM/RAM計測ツール
├── start.bat          # Windows起動スクリプト
└── DLllama.bat        # llama.cppバイナリ自動ダウンロード
```

※ 旧バージョンの `./workspace` / `./skills` / `./memory.db` / `./model_db.db` が存在する場合は、起動時に `ca_data/` 配下へ自動移行されます。

---

## 主要 API エンドポイント

### ジョブ・チャット

| メソッド | パス | 説明 |
|---|---|---|
| `POST` | `/jobs/submit` | ジョブ投入（バックグラウンド実行） |
| `GET` | `/jobs/{id}/poll` | ジョブイベントポーリング |
| `POST` | `/chat` | チャット（エージェントループ経由、web_search対応） |
| `POST` | `/plan` | タスクプランのみ生成 |

### メモリ・スキル・プロジェクト

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/memory` | メモリ一覧・検索 (`?q=キーワード`) |
| `POST` | `/memory` | メモリ手動追加 |
| `PUT` | `/memory/{id}` | メモリ更新 |
| `DELETE` | `/memory/{id}` | メモリ削除 |
| `POST` | `/memory/analyze/{job_id}` | ジョブからメモリ手動抽出 |
| `GET` | `/skills` | SKILL一覧 |
| `POST` | `/skills` | SKILL保存 |
| `DELETE` | `/skills/{name}` | SKILL削除 |
| `GET` | `/projects` | プロジェクト一覧 |

### システム・ヘルス

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/system/summary` | ヘルス・モデル・CPU/RAM/GPU/VRAMを一括取得（軽量集約ポーリング用） |
| `GET` | `/system/usage` | CPU/GPU利用率、RAM/VRAM使用率の現在値 |
| `GET` | `/system/usage/debug` | VRAM/GPU診断情報（詳細デバッグ用） |
| `GET` | `/health` | ヘルスチェック（LLM・サンドボックス状態） |

### Web検索・ストリーミング

| メソッド | パス | 説明 |
|---|---|---|
| `POST` | `/search/enable` | Web検索有効化 |
| `POST` | `/search/disable` | Web検索無効化 |
| `GET` | `/search/status` | Web検索の有効/無効状態取得 |
| `POST` | `/search/num` | 検索件数設定 |
| `POST` | `/streaming/enable` | LLMストリーミング有効化 |
| `POST` | `/streaming/disable` | LLMストリーミング無効化 |
| `GET` | `/streaming/status` | ストリーミング状態取得 |

### モデル管理

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/models/roles` | モデルロール割り当て取得 |
| `POST` | `/models/roles` | モデルロール割り当て更新（plan/chat/search/verify/code/complex等） |
| `GET` | `/models/orchestration` | オーケストレーションポリシー取得 |
| `POST` | `/models/orchestration` | オーケストレーションポリシー更新 |
| `GET` | `/models/hardware` | GPU/ハードウェア情報取得 |
| `POST` | `/models/db/benchmark/{mid}` | モデルのパフォーマンスベンチマーク実行 |
| `POST` | `/models/db/toggle/{mid}` | モデルの有効/無効切り替え |
| `POST` | `/models/db/toggle_vlm/{mid}` | VLMビジョンモードのON/OFF切り替え |
| `POST` | `/models/db/scan` | GGUFモデルスキャン |
| `GET` | `/models/db/scan/status` | スキャン進捗取得 |
| `POST` | `/model/auto-load` | 最適パラメータでモデルを自動ロード |
| `GET` | `/llm/props` | 現在のLLMプロパティ取得 |
| `GET` | `/llm/ctx` | コンテキストウィンドウ取得 |
| `POST` | `/llm/ctx` | コンテキストウィンドウ設定 |

### Ensemble設定

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/ensemble/settings` | Ensemble実行モード設定取得 |
| `POST` | `/ensemble/settings` | Ensemble設定更新（parallel/serial） |
| `GET` | `/ensemble/vram` | Ensembleモード用リソース状態取得 |

### GitHubリポジトリ連携

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/repo/config` | リポジトリ設定取得（トークンは非公開） |
| `POST` | `/repo/config` | GitHubトークン・リポジトリ設定保存 |
| `POST` | `/repo/init` | GitHubリポジトリを初期化してリモートを設定 |
| `POST` | `/repo/sync` | `ca_data/` をGitHubへコミット＆プッシュ |
| `GET` | `/repo/test-connection` | GitHubトークンの有効性とレート制限確認 |
| `GET` | `/repo/status` | 現在のリポジトリ状態取得 |

### Echo モード（同時通訳）

| メソッド | パス | 説明 |
|---|---|---|
| `WS` | `/echo/stream` | リアルタイム同時通訳 WebSocket ストリーム（ASR→翻訳→TTS） |
| `GET` | `/echo/sessions` | EchoVault セッション一覧取得 |
| `GET` | `/echo/sessions/{filename}` | EchoVault セッションファイルダウンロード |
| `DELETE` | `/echo/sessions/{filename}` | EchoVault セッション削除 |
| `POST` | `/echo/voice-ref` | ボイスクローン用参照音声の登録（base64） |
| `GET` | `/echo/voice-ref` | 現在の参照音声情報取得 |
| `DELETE` | `/echo/voice-ref` | 参照音声クリア |

### TTS（音声合成）

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/tts/status` | TTS エンジン状態（Edge-TTS / VOICEVOX / Qwen3-TTS）および `voicevox_http_available` |
| `GET` | `/tts/voices` | 利用可能な音声一覧（エンジン別） |
| `POST` | `/tts/load` | TTS エンジンのロード（`engine`: `voicevox` / `qwen3tts`） |
| `POST` | `/tts/unload` | TTS エンジンのアンロード |
| `POST` | `/tts/synthesize` | テキスト→音声（WAV）。`ref_audio_base64` でボイスクローン対応 |

### MCP・音声入力

| メソッド | パス | 説明 |
|---|---|---|
| `POST` | `/mcp` | MCP JSON-RPC エンドポイント（OpenClaw等からツール呼び出し） |
| `GET` | `/mcp/info` | MCPサーバー情報と公開ツール一覧 |
| `GET` | `/voice/status` | 音声認識モデルのロード状態 |
| `POST` | `/voice/load` | 音声認識モデルをオンデマンドでRAMへロード（CPU） |
| `POST` | `/voice/unload` | 音声認識モデルをアンロード（RAM解放） |
| `POST` | `/voice/transcribe` | 音声→テキスト（日本語/英語） |

※ `/projects` で作成・参照される実体ディレクトリは `./ca_data/workspace/{project}/` です。

### Echo モード — リアルタイム同時通訳

UI 上部の **Echo** ボタンで Echo モード（全画面）に切り替えます。

1. **● Start** ボタンを押してマイク録音開始
2. 発話が自動で文字起こし（faster-whisper）→ LLM 翻訳 → TTS 読み上げ
3. セッション終了後、録音(.webm)・文字起こし・議事録が `ca_data/EchoVault/` に保存
4. **📁 Files** ボタンでセッション一覧を確認・ダウンロード可能

**TTS エンジン設定**（Settings パネル）:

| エンジン | 特徴 | 追加準備 |
|---|---|---|
| Edge-TTS | クラウド音声合成。追加インストール不要 | なし |
| VOICEVOX | ローカル高品質日本語 TTS | Docker で起動（下記参照） |
| Qwen3-TTS | ローカル高品質多言語 TTS + ボイスクローン対応 | `pip install torch transformers`（CUDA推奨） |

**新タブ構成（Echo）**:
- **ASR** タブ: 音声認識モデル・デバイス・プリロード設定
- **TTS** タブ: Echo の TTS エンジン設定、Qwen3 モデルロード、Voice Clone（Qwen3専用）
- **認識後に自動読み上げ**: 初期値は **OFF**（`echo_autoplay_tts=false`）

**Voice Clone（Qwen3-TTS 専用）操作手順**:
1. Echo の **TTS** タブで TTS エンジンを **Qwen3 TTS** に設定
2. 同タブの **Voice Clone（Qwen3専用）** で参照音声を登録（🎙 録音 / 📁 ファイル / 🖥 PC音声）
3. 必要に応じて **参照テキスト（任意）** を入力
4. 読み上げ実行時、参照音声がある場合はボイスクローン合成、未設定時は通常合成
5. エラー時は「参照音声あり/なし」の状態に応じたメッセージが表示されます（例: 参照音声の再登録案内）

**WebSocket 依存**: Echo モードは WebSocket を使用します。`requirements.txt` に `websockets>=12.0` が含まれており、`pip install -r requirements.txt` で自動インストールされます。

### 音声入力（Whisper CPU/RAM）

- 依存: `faster-whisper`（例: `pip install faster-whisper`）
- モデル選定方針（優先順）: **日本語精度 > 速度 > 軽量**
  - 推奨デフォルト: `small`（多言語、日本語精度と速度のバランス）
  - 軽量高速優先: `base` / `tiny`
- `device="cpu"` / `compute_type="int8"` でGPU非依存、RAM運用。
- 常時ロードせず、`/voice/load` と `/voice/unload` および `auto_unload=true` でオンデマンド運用。

---

## GitHub Actions + Runpod テスト運用

`python:3.11-slim` 想定に合わせ、CI の Python は **3.11固定** です。

### GitHub Actionsで使う環境変数（Repository Variables）

`Settings > Secrets and variables > Actions > Variables` で以下を設定できます。

- `CI_PIP_PACKAGES` (任意): 追加インストールするPython依存（**空白区切り**）。未設定時は `fastapi uvicorn requests pydantic psutil nvidia-ml-py`。
- `RUNPOD_SMOKE_ENABLED` (任意): `true` のときだけ `runpod-smoke` を実行。未設定/`false` ではジョブをスキップ（self-hosted runner待ちの長時間ペンディング防止）。

> このworkflowでは必須のSecretはありません（外部APIキー未使用）。

### DockerイメージをレジストリへPushする場合の変数一覧

現状のworkflowは **build + runまで** で、Pushは行いません。
Pushを追加する場合は、`Settings > Secrets and variables > Actions` で以下を設定してください。

**Repository Variables (推奨)**
- `DOCKER_IMAGE_NAME`: 例 `codeagent-smoke`
- `DOCKER_IMAGE_TAG`: 例 `latest` / `${{ github.sha }}`
- `DOCKER_REGISTRY`: 例 `ghcr.io` / `docker.io`
- `DOCKER_NAMESPACE`: 例 `<github-user-or-org>`

**Repository Secrets (必須)**
- `DOCKER_USERNAME`: レジストリログインユーザー名
- `DOCKER_PASSWORD`: レジストリアクセストークン（Docker Hub token / GHCR PAT）

**GHCR利用時の補足**
- `GITHUB_TOKEN` でPushする構成も可能ですが、workflowに `packages: write` 権限が必要です。
- PAT利用時は `write:packages` 権限を付与してください。

### 追加したもの

- Workflow: `.github/workflows/runpod-test.yml`
  - `docker-smoke`: `python:3.11-slim` ベースのDockerイメージをビルドし、コンテナ内で環境スモークテスト
  - `windows-smoke`: GitHub Hosted Runner (`windows-latest`) で Python 3.11 の起動確認と依存 import
  - `runpod-smoke`: `RUNPOD_SMOKE_ENABLED=true` の場合のみ実行。Runpod 上の self-hosted runner (`self-hosted, linux, x64, nvidia, runpod`) で NVIDIA/CUDA/依存チェック
- Dockerfile: `.github/docker/smoke.Dockerfile`
- Runpod セットアップスクリプト: `scripts/setup_runpod_ubuntu.sh`

- ランチャー (`scripts/start_codeagent.py`) は Runpod で `llama-server` が見つからない場合、`scripts/setup_llama_runpod.sh` を実行して `ai-dock/llama.cpp-cuda` の **latest prebuilt** を取得し、`LLAMA_SERVER_PATH` を自動設定します。
- `scripts/setup_llama_runpod.sh` は **手動運用向け** の prebuilt 導入スクリプトです（CIや特殊環境向け）。
- CUDA対応の本番イメージはルートの `Dockerfile` に統一しました（builderでllama.cppをビルドしruntimeへ `llama-server`/`llama-cli` と共有ライブラリをコピー）。
- 環境確認スクリプト: `scripts/check_environment.py`


### DockerコンテナでのGitHub Actions実行

`docker-smoke` ジョブは、`.github/docker/smoke.Dockerfile` を使ってコンテナを作成し、以下を行います。

1. `python:3.11-slim` からイメージをビルド
2. `CI_PIP_PACKAGES` で指定した依存をインストール
3. `scripts/check_environment.py --expect-python 3.11` をコンテナ内で実行

これにより、ローカルDocker想定 (`python:3.11-slim`) と同じ前提でCI検証できます。

### Runpod 側の前提

1. Ubuntu 系イメージで Pod を作成（NVIDIA GPU）
2. GitHub Actions self-hosted runner を導入し、以下ラベルを付与
   - `self-hosted`
   - `linux`
   - `x64`
   - `nvidia`
   - `runpod`
3. 依存導入

```bash
bash scripts/setup_runpod_ubuntu.sh
```

3.5. llama.cpp の導入

```bash
# 通常は不要（ランチャーが latest prebuilt を自動導入）
python scripts/start_codeagent.py

# 明示的に再取得する場合のみ:
# bash scripts/setup_llama_runpod.sh --refresh-prebuilt
```

4. ローカル確認

```bash
python3.11 scripts/check_environment.py --expect-python 3.11
```

### 補足

- Windows/NVIDIA は GitHub Hosted Runner だと GPU が保証されないため、`windows-smoke` は「Python/依存/最小動作」の確認を主目的にしています。
- Runpod smoke は CUDA 運用を前提とし、`nvidia-smi` と llama.cpp の CUDA ビルド可否を重視します。
