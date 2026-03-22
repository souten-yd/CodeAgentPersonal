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

メモリDB: `./ca_data/memory.db`（全プロジェクト共有 SQLite）

### SKILLシステム

| 機能 | 説明 |
|---|---|
| **SKILL自動生成** | Stage 3失敗時にエラーを解析して不足ツールをPython関数としてSKILL化 |
| **ポストジョブ提案** | ジョブ完了後に実行ログを解析して不足SKILLをUIに提案 |
| **使用回数ソート** | プロンプトへのSKILL注入を使用回数降順でソート（実績のあるSKILLを優先） |
| **SKILL.md形式** | OpenClaw互換。`./ca_data/skills/スキル名/SKILL.md` に保存 |
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
- `search_in_files` — プロジェクト内全文検索
- `make_dir` / `move_path` / `delete_path` — ディレクトリ作成・移動/改名・削除

**コード実行（Docker）**
- `run_python` — Python in `claude_sandbox`
- `run_node` / `run_npm` — Node.js/npm
- `run_file` — Pythonファイル直接実行
- `setup_venv` — Python仮想環境構築
- `run_shell` — プロジェクトディレクトリで任意コマンド実行（pytest/ruff/mypy等）

**サーバー・ブラウザ**
- `run_server` — HTTPサーバー起動（port 8888）
- `run_browser` — Playwright（Chromium headless）
- `stop_server` — サーバー停止

**ユーティリティ**
- `web_search` — DuckDuckGo検索（設定でON/OFF）
- `clarify` — ユーザーへの確認・選択肢提示

**カスタムSKILL** — `./ca_data/skills/` に追加したSKILL.mdが自動でツールとして利用可能

### UI

| 機能 | 説明 |
|---|---|
| **リアルタイムSSE** | Server-Sent Eventsによるストリーミング表示（TPS/token数表示） |
| **7タブパネル** | Output / Preview / Log / Skills / Memory / Git / Models |
| **音声入力（β）** | チャット入力欄の🎙ボタンで録音→サーバー側Whisperで文字起こし（日本語/英語） |
| **リソースメーター** | ヘッダーで CPU / RAM / GPU / VRAM 使用率を定期更新表示 |
| **ファイルブラウザ** | プロジェクトファイルをリアルタイム表示・iframe preview |
| **設定パネル** | ⚙ボタンから: Steps・Auto Select・SKILL自動生成・Ensemble実行モード(parallel/serial)・VRAM監視・ストリーミング・コンテキスト長・検索件数・LLM URL |
| **GGUF検索/ダウンロード** | Modelsタブから Hugging Face のGGUFを検索し、RAM/VRAM適合目安（DL可否・完全オフロード可否）を確認して直接DL |
| **VLM Visionトグル** | VLMモデルごとに画像認識(vision)をON/OFF可能。OFF時はmulti用途の自動割り当て対象から除外 |
| **機能モード切替** | Modelsモーダルで `Model Orchestration` / `Ensemble(beta)` を切替可能（初期値: Model Orchestration） |
| **Coderオーケストレーション** | 軽量→高品質の3段コーダーを設定し、失敗時/品質未達時に段階昇格して再実行 |
| **VRAMガード** | `nvidia-smi/rocm-smi` で空きVRAMを監視し、必要時は `parallel → serial` へ自動切替（設定でON/OFF） |
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
| パーマネントメモリ | ✅ 新機能 | `ca_data/memory.db` 共有 |
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

Runpod / Linux (自動起動コマンドにもそのまま利用可):

```bash
python scripts/start_codeagent.py --mode auto
```

> `start.bat` は Python ランチャー (`scripts/start_codeagent.py`) を呼ぶ薄いラッパーです。  
> 起動ロジックを Python に共通化したため、Runpod の起動コマンドへ同じランチャーを指定できます。

`http://localhost:8000` を開いてください。

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

> ワークフローは **Secrets / Variables のどちらでも** 読み取れるようにしてあります（優先: Secrets）。  
> `DOCKERHUB_TOKEN` は Docker Hub の **Access Token** を使ってください（アカウントのログインパスワードは非推奨）。

### 2) 自動プッシュ条件

`.github/workflows/docker-publish.yml` により次のタイミングでビルド & push されます。

- `main` ブランチへの push
- `v*` 形式タグ（例: `v1.0.0`）の push
- 手動実行（`workflow_dispatch`）

イメージ名: `docker.io/<DOCKERHUB_USERNAME>/codeagent-personal`

### 2.1) ログインエラー時のチェック（`unauthorized: incorrect username or password`）

次を順番に確認してください。

1. **Token種別**
   - Docker Hub の `Account Settings → Personal access tokens` で発行したトークンか
   - Passwordを誤って入れていないか
2. **ユーザー名の一致**
   - Docker Hub の実ユーザー名（表示名ではない）と完全一致しているか
3. **余計な空白/改行**
   - Secrets/Variables貼り付け時に前後スペースや改行が入っていないか
4. **権限**
   - Push先が自分の namespace (`<username>/codeagent-personal`) になっているか
   - 組織 namespace に push する場合はその権限があるか

`Error: Username required` が出る場合は、`DOCKERHUB_USERNAME` が空として解釈されています。  
`Settings → Secrets and variables → Actions` の **Repository secrets / Repository variables** に同名キーを作成し、Environment secrets だけに入れていないかも確認してください。

このリポジトリのワークフローでは、実行時に値を trim（前後空白除去）し、空値なら明示エラーで停止します。

### 3) Runpodでの使い方（ダウンロード〜起動）

RunpodのPod作成時、Container Imageに以下を指定:

```
docker.io/<DOCKERHUB_USERNAME>/codeagent-personal:latest
```

起動コマンド例:

```bash
python scripts/start_codeagent.py --mode auto --host 0.0.0.0 --port 8000
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
│   ├── JobRunner      — Task実行 / フォールバック / 検証 / メモリ抽出
│   ├── MemoryDB       — パーマネントメモリ管理
│   ├── SkillSystem    — SKILL.md管理・ツールロード・類似マージ
│   └── VerifyEngine   — V-model 3フェーズ検証
├── ui.html            # フロントエンド SPA
│   ├── Chat / Task    — 会話・要件/計画・実行UI
│   ├── Output / Preview / Log
│   ├── Skills / Memory / Git / Models
│   └── Settings modal — 全設定を一元管理
├── ca_data/           # 実データの保存先
│   ├── memory.db      # パーマネントメモリ
│   ├── model_db.db    # モデルDB
│   ├── skills/        # カスタムSKILL格納フォルダ
│   │   └── スキル名/SKILL.md
│   └── workspace/     # プロジェクトファイル格納
│       └── プロジェクト名/
├── .codeagent/        # プロジェクト別補助データ
├── benchmark_mem.py   # VRAM/RAM計測ツール
├── start.bat          # Windows起動スクリプト
└── DLllama.bat        # llama.cppバイナリ自動ダウンロード
```

※ 旧バージョンの `./workspace` / `./skills` / `./memory.db` / `./model_db.db` が存在する場合は、起動時に `ca_data/` 配下へ自動移行されます。

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
| `POST` | `/mcp` | MCP JSON-RPC エンドポイント（OpenClaw等からツール呼び出し） |
| `GET` | `/mcp/info` | MCPサーバー情報と公開ツール一覧 |
| `GET` | `/voice/status` | 音声認識モデルのロード状態 |
| `POST` | `/voice/load` | 音声認識モデルをオンデマンドでRAMへロード（CPU） |
| `POST` | `/voice/unload` | 音声認識モデルをアンロード（RAM解放） |
| `POST` | `/voice/transcribe` | 音声→テキスト（日本語/英語） |
| `GET` | `/system/usage` | CPU/GPU利用率、RAM/VRAM使用率の現在値 |
| `GET` | `/health` | ヘルスチェック |

※ `/projects` で作成・参照される実体ディレクトリは `./ca_data/workspace/{project}/` です。

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

- `CI_PIP_PACKAGES` (任意): 追加インストールするPython依存（**空白区切り**）。未設定時は `fastapi uvicorn requests`。
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
  - `runpod-smoke`: `RUNPOD_SMOKE_ENABLED=true` の場合のみ実行。Runpod 上の self-hosted runner (`self-hosted, linux, x64, nvidia, runpod`) で NVIDIA/Vulkan/依存チェック
- Dockerfile: `.github/docker/smoke.Dockerfile`
- Runpod セットアップスクリプト: `scripts/setup_runpod_ubuntu.sh`
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

4. ローカル確認

```bash
python3.11 scripts/check_environment.py --expect-python 3.11
```

### 補足

- Windows/NVIDIA は GitHub Hosted Runner だと GPU が保証されないため、`windows-smoke` は「Python/依存/最小動作」の確認を主目的にしています。
- Vulkan は最適化不要との前提に合わせ、`vulkaninfo --summary` が実行可能かどうかを確認するだけにしています。
