# KasaneCore (CodeAgent Personal)

KasaneCoreは、ローカルLLM（llama.cpp / GGUF）とFastAPIバックエンドを組み合わせた、個人向け自律型AIコーディングエージェント基盤です。
チャット、タスク実行、Atlasワークフロー、音声I/O（Echo）、文書調査（Nexus）を一つのUIに統合し、Windows・Linux・Runpod・Docker環境で動作します。

---

## アーキテクチャ概要

```
ブラウザ UI (ui.html / web/atlas-next Vue3)
        │
        ▼
FastAPI バックエンド (main.py)
        │
   ┌────┴────────────────────────────────────┐
   │                                         │
AgentLoop                               Nexus Router
(Planner / Executor / Evaluator)        (文書・Web調査)
   │
ToolRegistry
(read_file / write_file / apply_patch /
 run_command / run_tests / nexus_* ...)
   │
llama-server (llama.cpp / GGUF)
```

### Atlas とは

**Atlas** はKasaneCoreにおけるコーディングワークフロー全体を管掌する中枢コンポーネントです。単なるチャットではなく、要件定義→計画→実行→検証→パッチ適用→ロールバックまでを一貫して管理します。

```
ユーザー入力 (要件)
    ↓
RequirementAnalyzer → ClarificationService (不明点の確認)
    ↓
DeepPlanner → PlanPoolBuilder (Program/Epic/Task 三層計画)
    ↓
PlanReviewer → PlanApprovalManager (承認ゲート)
    ↓
AtlasPipelineRunner
  ├─ AutopilotPolicyGate (リスク評価・ブロック判定)
  ├─ ImplementationExecutor (ファイル編集・コマンド実行)
  ├─ AtlasFileSafeApplyExecutor (パッチ安全適用)
  ├─ VerificationRunner (テスト実行・検証)
  └─ BoundedRetryService (上限付き再試行)
    ↓
AtlasLLMEvaluatorService (LLMによる結果評価)
    ↓
ChangeSnapshotService → RollbackReadiness (スナップショット・ロールバック)
    ↓
AtlasJournal (全イベント永続化)
```

---

## 主なコンポーネント

### agent/ — エージェントコア

| モジュール | 役割 |
|---|---|
| `loop.py` | AgentLoop: Planner/Executor/Evaluatorを疎結合で接続する基本ループ |
| `planner.py` | Program/Epic/Task 三層計画インターフェース |
| `evaluator.py` | 実行結果をDoDで評価し再計画レベル (task/epic/program) を判定 |
| `executor.py` | Action実行 + エラー分類テーブル (timeout/json_output_failed 等) |
| `memory.py` | HybridMemoryStore: 短期(deque) + 長期(SQLite) + TaskOutcome記録 |
| `context_builder.py` | プロジェクトコンテキスト構築 |
| `policy.py` | ExecutionPolicy: human gate / autostop / capability check |
| `safety.py` | autostop通知生成 |
| `clarification_manager.py` | ユーザーへの確認フロー管理 |
| `deep_planner.py` | DeepPlanner: アーキテクチャ選択・実装フェーズ分解 |
| `task_planning_runner.py` | タスク計画実行ランナー |
| `tools/registry.py` | ToolRegistry: ツール名と実行関数の登録・呼び出し |
| `tools/builtin.py` | read_file / write_file / apply_patch / search_code / run_command / run_tests / get_error_trace |
| `tools/nexus_tools.py` | nexus_search_library / nexus_web_search / nexus_build_report / nexus_upload_document / nexus_news_scan / nexus_market_research / nexus_export_bundle |

### agent/atlas_* — Atlasサービス群 (140ファイル超)

主要なものを抜粋:

| モジュール | 役割 |
|---|---|
| `atlas_autopilot.py` | AtlasAutopilot: DeepPlanner + TaskDecomposer によるプレビュープラン生成 |
| `atlas_autopilot_policy.py` | AutopilotPolicyGate: リスクレベル(low/medium/high/critical)評価・承認要否判定 |
| `atlas_pipeline_runner.py` | AtlasPipelineRunner: PlanPool実行制御 (dry_run/policy評価/item処理) |
| `atlas_plan_pool_builder.py` | PlanPool構築 (要件→アイテム分解) |
| `atlas_plan_pool_storage.py` | PlanPool JSON永続化 |
| `atlas_journal.py` | AtlasJournal: 全イベント・成果物の永続化 |
| `atlas_continuation_service.py` | セッション継続: 中断したワークフローの再開サポート |
| `atlas_llm_evaluator_service.py` | LLMによる実行結果評価 (policy制御・フォールバックルール付き) |
| `atlas_code_intel_service.py` | Pythonシンボルインデックス / 依存グラフ / 関連テスト探索 |
| `atlas_context_refresh_service.py` | コンテキスト自動更新 |
| `atlas_patch_proposal_service.py` | パッチ提案生成 |
| `atlas_patch_candidate_approval_service.py` | パッチ候補の承認フロー |
| `atlas_patch_regen_from_recommendation_service.py` | 推奨事項からパッチ再生成 |
| `atlas_file_safe_apply_executor.py` | ファイルへの安全なパッチ適用 |
| `atlas_change_snapshot_service.py` | 変更前スナップショット取得 |
| `atlas_change_snapshot_restore_service.py` | スナップショットからのロールバック |
| `atlas_bounded_retry_service.py` | 上限付き再試行 |
| `atlas_guarded_operator_loop_service.py` | 確認トークン付き人間監視実行ループ |
| `atlas_next_action_orchestrator_service.py` | 次アクション選択・オーケストレーション |
| `atlas_multi_item_autopilot_service.py` | 複数アイテムの自動実行 |
| `atlas_manual_next_action_executor_service.py` | dry_run / 実行 の手動ステップ実行 |
| `atlas_debug_review_service.py` | デバッグレビュー |
| `atlas_recovery_service.py` | 最新実行状態からの復旧 |

### app/ — アプリケーション層

| パス | 役割 |
|---|---|
| `app/api/atlas_*.py` | Atlas APIエンドポイント群 (workflow-state / pipeline / guarded-loop 等) |
| `app/atlas/` | 実行安全性ゲート群 (level1〜level4, rollback, self-improvement 等) |
| `app/nexus/` | 文書調査: ingest / search / evidence / report / web_scout / market / news |
| `app/asr/` | ASR: faster-whisper / whisper.cpp ランタイム |
| `app/tts/` | TTS: Style-Bert-VITS2 / Qwen3-TTS エンジン + 言語ルーター |
| `app/audio/` | オーディオランタイム設定 |
| `app/lumen/` | Lumen: チャット用インテント検出 (weather/news/web/nexus_research) |
| `app/services/` | jobs / system_usage / audio_runtime 等のサービス層 |
| `app/api/` | runtime_controls / settings / system / echo / projects 等のルーター |
| `app/server.py` | static assets / workspace mount / router登録 |

### web/atlas-next/ — Atlasフロントエンド (Vue3 + Vite)

| コンポーネント | 役割 |
|---|---|
| `WorkflowShell.vue` | Atlasワークフロー全体のシェル |
| `RequirementInput.vue` | 要件入力 / Atlas Start |
| `PlanReviewPanel.vue` | 計画レビュー・承認 |
| `PlanLifecycleStrip.vue` | 計画進捗ストリップ |
| `GuardedExecutionPreparationPanel.vue` | 実行前ガード確認 |
| `GuardedExecutionReviewPanel.vue` | 実行確認・承認パネル |
| `ApprovalDryRunPreview.vue` | dry_run結果プレビュー |
| `PatchReviewPanel.vue` | パッチ差分レビュー |
| `Level1ReadinessPanel.vue` | Level1ゲート確認 (17項目) |
| `ExecutionSafetyBoundary.vue` | 実行安全境界 |
| `WorkflowReviewBoard.vue` | ワークフロー状態ボード |
| `ConversationWorkbench.vue` | 会話ワークベンチ |
| `ProgressRail.vue` | 進捗レール |

---

## ディレクトリ構成

```
KasaneCore/
├── main.py                        # FastAPIバックエンド (145エンドポイント)
├── agent/
│   ├── loop.py                    # AgentLoop
│   ├── planner.py / evaluator.py / executor.py
│   ├── memory.py                  # HybridMemoryStore
│   ├── tools/                     # ToolRegistry + builtin + nexus_tools
│   ├── atlas_*.py                 # Atlasサービス群 (140ファイル超)
│   └── ...
├── app/
│   ├── api/                       # APIルーター群
│   ├── atlas/                     # 実行安全ゲート (level1〜4等)
│   ├── asr/                       # faster-whisper / whisper.cpp
│   ├── tts/                       # Style-Bert-VITS2 / Qwen3-TTS
│   ├── audio/                     # オーディオランタイム
│   ├── nexus/                     # 文書調査システム
│   ├── lumen/                     # インテント検出
│   ├── services/                  # jobs / system_usage 等
│   └── server.py
├── web/
│   ├── atlas-next/                # Vue3 + Vite (Atlasフロントエンド)
│   └── js/ css/                   # メインUIアセット
├── tests/                         # contractテスト群 (phase2〜phase31)
├── scripts/
│   ├── start_codeagent.py         # クロスプラットフォームランチャー
│   ├── runpod_start.sh            # Runpod起動
│   ├── setup_llama_runpod.sh      # llama.cppセットアップ
│   ├── smoke_ui_modes_playwright.py # UIスモークテスト
│   └── ...
├── docker/
│   └── start-services.sh          # Docker起動スクリプト
├── ca_data/                       # 永続データ (gitignore対象)
├── ui.html                        # メインUI
├── Dockerfile                     # マルチステージビルド
├── requirements.txt
├── requirements-tts.txt           # TTS用 (CUDA依存分離)
└── start.bat                      # Windowsランチャー
```

---

## 主要APIエンドポイント

### Chat / Task

| Method | Path | 説明 |
|---|---|---|
| `POST` | `/chat` | チャット (chat/taskモード切替可) |
| `POST` | `/task/stream` | タスク実行 SSEストリーム |
| `POST` | `/llm/test` | LLM接続テスト |
| `POST` | `/api/task/plan` | プラン生成のみ |

### Atlas ワークフロー

| Method | Path | 説明 |
|---|---|---|
| `POST` | `/api/atlas/autopilot/preview` | Autopilotプレビュープラン生成 |
| `GET` | `/api/atlas/autopilot/{id}` | Autopilot状態取得 |
| `POST` | `/api/atlas/autopilot/{id}/tasks/{task_id}/plan` | タスクプラン生成 |
| `GET` | `/api/atlas/runs` | Atlas実行一覧 |
| `GET` | `/api/atlas/workflow-state/read-only` | ワークフロー状態 (読み取り専用) |
| `GET` | `/api/plans/{plan_id}` | プラン取得 |
| `GET` | `/api/plans/{plan_id}/approval` | 承認状態確認 |
| `POST` | `/api/plans/{plan_id}/approve` | プラン承認 |
| `POST` | `/api/plans/{plan_id}/execute` | プラン実行 |
| `POST` | `/api/plans/{plan_id}/request-revision` | 修正要求 |
| `POST` | `/api/plans/{plan_id}/reject` | プラン却下 |
| `GET` | `/api/runs/{run_id}` | 実行詳細 |
| `GET` | `/api/runs/{run_id}/log` | 実行ログ |
| `GET` | `/api/runs/{run_id}/patches` | パッチ一覧 |
| `GET` | `/api/runs/{run_id}/patch-dashboard` | パッチダッシュボード |
| `POST` | `/api/runs/{run_id}/patches/{patch_id}/approve` | パッチ承認 |
| `POST` | `/api/runs/{run_id}/patches/{patch_id}/apply` | パッチ適用 |
| `GET` | `/api/runs/{run_id}/verification/{id}` | 検証結果 |
| `GET` | `/api/runs/{run_id}/llm-telemetry` | LLMテレメトリ |

### モデル管理

| Method | Path | 説明 |
|---|---|---|
| `POST` | `/models/db` | モデル登録 |
| `GET` | `/models/hardware` | ハードウェア情報 |
| `GET` | `/models/gguf/search` | GGUFモデル検索 |
| `POST` | `/models/gguf/download` | GGUFダウンロード |
| `POST` | `/models/db/scan` | モデルスキャン |
| `POST` | `/models/roles` | ロール割当 |
| `POST` | `/models/orchestration` | モデルオーケストレーション設定 |
| `GET` | `/ensemble/settings` | アンサンブル設定 |
| `POST` | `/model/switch` | モデル切替 |
| `POST` | `/model/auto-load` | 自動ロード |

### メモリ / スキル / Git

| Method | Path | 説明 |
|---|---|---|
| `GET` | `/memory` | メモリ一覧 |
| `POST` | `/memory` | メモリ登録 |
| `PUT` | `/memory/{mid}` | メモリ更新 |
| `DELETE` | `/memory/{mid}` | メモリ削除 |
| `POST` | `/memory/analyze/{job_id}` | メモリ解析 |
| `GET` | `/skills` | スキル一覧 |
| `POST` | `/skills` | スキル登録 |
| `DELETE` | `/skills/{name}` | スキル削除 |
| `POST` | `/skills/reload` | スキルリロード |
| `GET` | `/git/status` | Git状態 |
| `POST` | `/git/commit` | Gitコミット |
| `GET` | `/git/diff` | Git差分 |
| `GET` | `/git/log` | Gitログ |

### ASR / TTS / Echo

| Method | Path | 説明 |
|---|---|---|
| `GET` | `/asr/status` | ASR状態 |
| `POST` | `/asr/load` | ASRモデルロード |
| `POST` | `/asr/unload` | ASRアンロード |
| `GET` | `/api/echo/status` (等) | Echo / TTS / ASR 各種 |

### Nexus (`/nexus/` prefix)

主要のみ:

| Method | Path | 説明 |
|---|---|---|
| `POST` | `/nexus/upload` | 文書アップロード |
| `POST` | `/nexus/search` | ライブラリ検索 |
| `POST` | `/nexus/ask` | 検索結果ベース回答 |
| `POST` | `/nexus/web/search` | Web検索 |
| `POST` | `/nexus/web/research` | Web調査ジョブ |
| `POST` | `/nexus/research/run` | Researchジョブ開始 |
| `GET` | `/nexus/research/jobs/{id}/answer` | Research回答 |
| `GET` | `/nexus/research/jobs/{id}/bundle` | 結果バンドル |
| `POST` | `/nexus/news/scan` | ニューススキャン |
| `POST` | `/nexus/market/research` | マーケット調査 |
| `POST` | `/nexus/report/build` | レポート生成 |

### システム / デバッグ

| Method | Path | 説明 |
|---|---|---|
| `GET` | `/health` | FastAPI疎通確認 |
| `GET` | `/system/usage` | CPU/RAM/GPU/VRAM情報 |
| `GET` | `/debug/llama` | llama-serverデバッグ |
| `GET` | `/debug/tests` | デバッグテストハーネス UI (KASANE_DEBUG_TEST_HARNESS=1 時のみ) |
| `POST` | `/api/debug/tests/run-all` | テスト一括実行 |

---

## Atlasの実行安全モデル

Atlasは段階的な安全ゲートで実行を制御します。

```
Level 0: dry_run のみ (実ファイル変更なし)
Level 1: ガード付き実行 (17項目のゲート確認)
  - snapshot_restore / patch_transaction / risk_classification
  - dry_run_proof / explicit_approval_token
  - rollback_readiness / artifact_capture
  - stop_kill_switch / loop_bounds / remote_git_restriction
  - self_improvement_gate / audit_log 等
Level 2: ランタイム遷移チェックポイント
Level 3: 自律ループ候補
Level 4: Self-improvement チェックポイント
```

**リスクレベルによる自動判定:**

| リスクレベル | 動作 |
|---|---|
| `low` | 自動実行可 |
| `medium` | ポリシー依存 |
| `high` | 承認必須 |
| `critical` | ブロック (実行不可) |

---

## LLMロール設定

| 環境変数 | 既定値 | 用途 |
|---|---|---|
| `LLM_URL` | `http://localhost:8080/v1/chat/completions` | 既定LLM |
| `CODEAGENT_LLM_PLANNER` | `LLM_URL` | Planner / Verifier |
| `CODEAGENT_LLM_EXECUTOR` | `LLM_URL` | Executor |
| `CODEAGENT_LLM_CHAT` | `LLM_URL` | Chat / Clarify |
| `CODEAGENT_LLM_LIGHT` | `LLM_URL` | 軽量処理 |
| `CODEAGENT_LLM_MODE` | `single` | LLM実行モード |

モデルDBでロールを個別に割り当て可能:

`plan` / `chat` / `search` / `verify` / `code` / `complex` / `reason` / `multi` (VLM) / `translate`

---

## 環境変数一覧

### コア

| 変数 | 既定値 | 説明 |
|---|---|---|
| `LLAMA_SERVER_PATH` | 自動検出 | llama-server実行ファイルパス |
| `LLAMA_ROOT_DIR` | `./llama` / Runpod: `/workspace/llama` | llama.cpp配置先 |
| `CODEAGENT_RUNTIME` | 自動判定 | `runpod` / `local` / `docker` |
| `CODEAGENT_CA_DATA_DIR` | `./ca_data` / Runpod: `/workspace/ca_data` | 永続データ保存先 |
| `CODEAGENT_WORK_DIR` | `ca_data/workspace` | プロジェクト作業ディレクトリ |
| `CODEAGENT_SKILLS_DIR` | `ca_data/skills` | SKILL保存先 |
| `CODEAGENT_MODEL_DB_PATH` | `ca_data/model_db.db` | モデルDB |
| `CODEAGENT_SYS_VENV_DIR` | `venv_sys` | ローカル起動用venv |
| `CODEAGENT_TEST_CMD` | 自動推定 | run_testsの既定コマンド |
| `KASANE_DEBUG_TEST_HARNESS` | `0` | デバッグテストハーネス有効化 (Docker: 1) |
| `CODEAGENT_HOST` | `0.0.0.0` | FastAPIホスト |
| `CODEAGENT_PORT` | `8000` | FastAPIポート |
| `LLAMA_PORT` | `8080` | llama-serverポート |

### llama-server / VRAM

| 変数 | 既定値 | 説明 |
|---|---|---|
| `LLAMA_CACHE_TYPE_K` | `q8_0` | KVキャッシュ型 (K) |
| `LLAMA_CACHE_TYPE_V` | `q8_0` | KVキャッシュ型 (V) |
| `DEFAULT_LLM_CTX_SIZE` | `16384` | デフォルトコンテキスト長 |

### ASR / TTS

| 変数 | 既定値 | 説明 |
|---|---|---|
| `CODEAGENT_ASR_DEFAULT_MODEL` | `large-v3-turbo` | faster-whisperモデル |
| `CODEAGENT_ASR_MODEL_PATH` | `/opt/asr_models/large-v3-turbo` | ASRモデルパス |
| `CODEAGENT_ASR_LOCAL_FILES_ONLY` | `1` | ローカルのみ使用 |
| `CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR` | `/workspace/ca_data/tts/style_bert_vits2/models` | SBV2モデルパス |
| `CODEAGENT_STYLE_BERT_VITS2_VENV_DIR` | `/opt/style-bert-vits2-venv` | SBV2 venv |
| `ECHO_UPLOAD_MAX_BYTES` | `104857600` | Echo音声アップロード上限 |

### Nexus / SearXNG

| 変数 | 既定値 | 説明 |
|---|---|---|
| `NEXUS_ENABLE_WEB` | `true` | Web検索有効化 |
| `NEXUS_ENABLE_NEWS` | `true` | ニュース機能 |
| `NEXUS_ENABLE_MARKET` | `true` | マーケット機能 |
| `NEXUS_WEB_SEARCH_PROVIDER` | `searxng` | 検索プロバイダ |
| `NEXUS_SEARXNG_URL` | Runpod: `http://127.0.0.1:8088` / 他: `http://searxng:8080` | SearXNG URL |
| `NEXUS_SEARCH_FREE_ONLY` | `true` | 無料プロバイダのみ |
| `BRAVE_SEARCH_API_KEY` | 空 | Brave Search APIキー |
| `NEXUS_MAX_UPLOAD_MB` | `200` | 最大アップロードサイズ |
| `AUTO_START_SEARXNG` | Runpod: `true` / 他: `false` | SearXNG自動起動 |

### Runpod

| 変数 | 説明 |
|---|---|
| `RUNPOD_POD_ID` | Runpod環境判定に使用 |
| `RUNPOD_API_KEY` | Runpod環境判定に使用 |
| `RUNPOD_AUTO_SETUP_LLAMA` | llama-server自動セットアップ |

---

## 必要環境

| 項目 | 推奨 |
|---|---|
| OS | Windows 10/11, Linux, Runpod |
| Python | 3.11 |
| RAM | 32GB以上 |
| VRAM | 16GB以上 (RTX 3070等) |
| GPU | NVIDIA CUDA / AMD Vulkan / CPU fallback |

### 依存関係 (requirements.txt)

```
fastapi>=0.110
python-multipart>=0.0.9
uvicorn>=0.27
websockets>=12.0
requests>=2.31
certifi>=2024.0.0
PyMuPDF>=1.24.0
pydantic>=2.6
psutil>=5.9
faster-whisper>=1.0
```

TTS依存 (requirements-tts.txt) は依存衝突回避のため分離:
```
torch==2.11.0+cu128
torchaudio==2.11.0+cu128
```

---

## セットアップ

### Windows ローカル

```bash
git clone https://github.com/souten-yd/KasaneCore.git
cd KasaneCore

# llama-serverを配置またはパス指定
set LLAMA_SERVER_PATH=C:\path\to\llama-server.exe

start.bat
# → http://localhost:8000
```

初回起動時に `venv_sys/` が自動作成され `requirements.txt` がインストールされます。

### Linux / Runpod

```bash
# 通常起動
python scripts/start_codeagent.py

# Runpod専用
bash scripts/runpod_start.sh

# オプション指定
python scripts/start_codeagent.py --host 0.0.0.0 --port 8000 --primary-port 8080
```

| オプション | 既定値 | 説明 |
|---|---|---|
| `--host` | `0.0.0.0` | FastAPIホスト |
| `--port` | `8000` | FastAPIポート |
| `--primary-port` | `8080` | llama-serverポート |
| `--api-timeout` | `120` | FastAPI起動待ち秒数 |
| `--llm-timeout` | `180` | LLM起動待ち秒数 |

### Docker (Runpod推奨)

```bash
docker build -t kasanecore .
docker run -p 8000:8000 -p 8080:8080 \
  -v /workspace/ca_data:/workspace/ca_data \
  -v /workspace/LLMs:/workspace/LLMs \
  kasanecore
```

Dockerイメージには以下がバンドルされています:

- llama.cpp CUDA 12.8バイナリ (ai-dock/llama.cpp-cudaより自動取得)
- faster-whisper large-v3-turbo モデル
- Style-Bert-VITS2 (koharune-amiモデル込み)
- Gemma-4-E4B-it-Q4_K_M.gguf (デフォルトLLM)
- SearXNG (Runpod時に自動起動)

---

## Runpod 永続化パス

| パス | 内容 |
|---|---|
| `/workspace/ca_data` | 全永続データ (必ず永続化推奨) |
| `/workspace/ca_data/memory.db` | エージェントメモリ |
| `/workspace/ca_data/model_db.db` | モデルDB |
| `/workspace/ca_data/skills/` | SKILLファイル |
| `/workspace/ca_data/workspace/` | プロジェクト作業ディレクトリ |
| `/workspace/ca_data/nexus/` | Nexus文書・レポート |
| `/workspace/ca_data/EchoVault/` | Echo録音・文字起こし |
| `/workspace/ca_data/tts/style_bert_vits2/models/` | SBV2モデル |
| `/workspace/LLMs` | GGUFモデル |
| `/workspace/llama` | llama.cpバイナリ |

---

## SKILL拡張

`ca_data/skills/` 以下に `SKILL.md` を置くことでAgentの能力を拡張できます。

```
ca_data/skills/
└── my_skill/
    └── SKILL.md
```

`SKILL.md` の例:

```markdown
# ログ解析スキル

## Purpose
サーバーログからエラー原因を特定する。

## When to use
- ログファイルを解析するとき
- エラー原因を分類するとき

## Steps
1. ログ全体を read_file で読む
2. ERROR / WARN / Traceback を search_code で抽出
3. 発生時刻順に整理
4. 原因候補と修正案を提示
```

---

## テスト

```bash
# 全テスト
pytest -q

# TTS回帰テスト
python scripts/check_style_bert_vits2_tts.py
pytest -q tests/test_style_bert_vits2_tts_contract_regression.py \
          tests/test_tts_language_router.py \
          tests/test_text_normalizer_jp_extra.py

# UIスモーク (Playwright)
python scripts/smoke_ui_modes_playwright.py

# バックエンドpreflight確認 (バックエンド起動済み前提)
PLAYWRIGHT_SMOKE_BASE_URL=http://127.0.0.1:8000 \
RUN_ATLAS_BACKEND_PREFLIGHT=1 \
python scripts/smoke_ui_modes_playwright.py

# バックエンドE2E (dry-run、実行/apply/approveは行わない)
PLAYWRIGHT_SMOKE_BASE_URL=http://127.0.0.1:8000 \
RUN_ATLAS_BACKEND_E2E=1 \
python scripts/smoke_ui_modes_playwright.py

# デバッグテストハーネス (KASANE_DEBUG_TEST_HARNESS=1 時)
python scripts/run_debug_test_matrix.py
```

Playwright未導入時:
```bash
python -m pip install playwright
python -m playwright install chromium
```

---

## データ保存先 (ローカル)

```
ca_data/
├── memory.db          # エージェントメモリ (HybridMemoryStore)
├── model_db.db        # GGUFモデルDB
├── skills/            # SKILL.mdファイル
├── workspace/         # プロジェクト作業ディレクトリ
├── EchoVault/         # Echo録音・文字起こし・成果物
└── nexus/
    ├── nexus.db
    ├── uploads/
    ├── extracted/
    ├── reports/
    └── exports/
```

`.gitignore` 対象: `ca_data/` / `.codeagent/` / `venv_sys/` / `.venv/` / `__pycache__/` / `*.db`

---

## 実装状況

| 機能 | 状態 | 備考 |
|---|---|---|
| Chat | Stable | LLM直接呼び出し / エージェントループ切替可 |
| Task (SSEストリーム) | Stable | plan → タスク実行 → 結果配信 |
| Atlas ワークフロー | Experimental | Plan/Approve/Execute/Patch/Rollback |
| Atlas Autopilot | Experimental | DeepPlanner + TaskDecomposer |
| Guarded Operator Loop | Experimental | 確認トークン付き人間監視実行 |
| モデル管理 | Stable | GGUF/llama-server/ロール割当 |
| Memory | Stable | SQLite永続化 / 短期・長期ハイブリッド |
| SKILL | Stable | SKILL.mdベース / ホットリロード |
| Nexus (文書調査) | Experimental | Web/PDF/ニュース/マーケット/レポート |
| Echo (音声I/O) | Experimental | ASR/TTS/翻訳連携 |
| Style-Bert-VITS2 | Experimental | モデル配置・依存環境に注意 |
| Qwen3-TTS | Experimental | requirements-tts.txt 分離インストール必要 |
| Runpod / Docker | Stable | Gemma+SBV2+Whisperバンドルイメージ |
| Atlas Next (Vue3) | Experimental | Workflow Workbench UI |

---

## ライセンス

ライセンスファイルが存在する場合はその内容に従ってください。未設定の場合、利用・再配布条件は明示されていません。
