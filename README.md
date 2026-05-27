<p align="center">
  <img src="assets/kasane-core-logo.svg" width="120" alt="KasaneCore logo" />
</p>

<h1 align="center">KasaneCore (CodeAgent Personal)</h1>

<p align="center">
  <strong>完全ローカル動作・クラウド非依存のAIコーディングエージェント基盤</strong><br>
  llama.cpp × FastAPI × Vue3 で、要件定義からパッチ適用・ロールバックまで一気通貫
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue" />
  <img src="https://img.shields.io/badge/FastAPI-0.110+-green" />
  <img src="https://img.shields.io/badge/llama.cpp-CUDA%2012.8-orange" />
  <img src="https://img.shields.io/badge/Vue-3.5-brightgreen" />
  <img src="https://img.shields.io/badge/license-see%20repo-lightgrey" />
</p>

---

## KasaneCoreとは

KasaneCoreは、ローカルLLM（llama.cpp / GGUF）を中核に、**コーディングエージェント・音声I/O・Web調査・文書RAG**を単一のFastAPIバックエンドに統合した個人向けAI開発環境です。

OpenAIのAPIキーもクラウドサービスも必要ありません。RTX 3070やM5 Macがあれば、すべてオフラインで動きます。

### 他のコードエージェントとの違い

| 機能 | **KasaneCore** | Claude Code | GitHub Copilot Agent | Cursor Agent | Devin |
|---|:---:|:---:|:---:|:---:|:---:|
| **完全ローカル動作** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **ローカルGGUF/llama.cpp** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Planner/Executor/Evaluator分離** | ✅ | ❌ | ❌ | ❌ | △ |
| **ロール別LLM割当 (9種)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **明示的承認ゲート (17項目)** | ✅ | △ | △ | △ | △ |
| **スナップショット+ロールバック** | ✅ | ❌ | △ | ❌ | △ |
| **LLMによる自動評価 (Evaluator)** | ✅ | ❌ | ❌ | ❌ | ✅ |
| **SQLite永続メモリ** | ✅ | ❌ | ❌ | ❌ | △ |
| **文書RAG + Web調査 (Nexus)** | ✅ | ❌ | ❌ | △ | ❌ |
| **音声I/O (Echo)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **天気・ニュース (Lumen)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Self-improvement (Level 4)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Draft PR自動生成** | ✅ | ❌ | ✅ | ❌ | ✅ |
| **SearXNG統合 (プライベート検索)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **月額費用** | $0 | 従量課金 | $10〜/月 | $20/月 | $500/月〜 |

---

## アーキテクチャ全体図

```
┌─────────────────────────────────────────────────────────────────┐
│                    ブラウザ UI                                    │
│   ui.html (Vanilla JS)  +  web/atlas-next/ (Vue3 + Vite)       │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTP / SSE / WebSocket
┌───────────────────────────────▼─────────────────────────────────┐
│               FastAPI バックエンド (main.py)                      │
│                     145 エンドポイント                            │
│  ┌──────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────┐  │
│  │  Lumen   │ │ Atlas  │ │  Echo  │ │ Nexus  │ │   Models   │  │
│  │  (Chat)  │ │(Coding)│ │(Voice) │ │ (RAG)  │ │(llama.cpp) │  │
│  └──────────┘ └────────┘ └────────┘ └────────┘ └────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                │
                   ┌────────────▼────────────┐
                   │   llama-server (GGUF)   │
                   │  OpenAI互換 /v1/chat/   │
                   │  completions API        │
                   └─────────────────────────┘
```

---

## 🧠 Atlas — コーディングワークフローエンジン

Atlasは、KasaneCoreの心臓部です。「ただのチャット」ではなく、**要件定義から実装・検証・パッチ適用・ロールバックまで**を段階的な安全ゲートで制御しながら自律実行します。

### Atlasのワークフロー全体

```
ユーザー入力 (自然言語の要件)
         │
         ▼
┌─────────────────────────────────────────┐
│ RequirementAnalyzer                      │
│ → 要件を構造化し、あいまい点を洗い出す     │
└──────────────────┬──────────────────────┘
                   │ 不明点あり → ClarificationService (ユーザーへ質問)
                   │ 明確 ↓
┌──────────────────▼──────────────────────┐
│ DeepPlanner                              │
│ → 3つのアーキテクチャ案 (A/B/C) を生成   │
│ → 最適案を選択し、実装フェーズに分解       │
│ → Nexusコンテキスト + リポジトリ構造考慮  │
└──────────────────┬──────────────────────┘
                   ↓
┌──────────────────▼──────────────────────┐
│ AtlasPlanPoolBuilder                     │
│ → Program / Epic / Task の三層計画を構築  │
│ → 各アイテムにリスクレベルを付与          │
└──────────────────┬──────────────────────┘
                   ↓
┌──────────────────▼──────────────────────┐
│ PlanReviewer → PlanApprovalManager       │
│ → 計画レビュー・ユーザー承認ゲート        │
└──────────────────┬──────────────────────┘
                   ↓ 承認後
┌──────────────────▼──────────────────────┐
│ AtlasPipelineRunner                      │
│                                          │
│  ┌─────────────────────────────────┐    │
│  │ AutopilotPolicyGate              │    │
│  │ リスク評価 → allow/approve/block  │    │
│  └────────────────┬────────────────┘    │
│                   ↓ allow               │
│  ┌─────────────────────────────────┐    │
│  │ AtlasChangeSnapshotService       │    │
│  │ 変更前ファイルのSHA256スナップショット│   │
│  └────────────────┬────────────────┘    │
│                   ↓                     │
│  ┌─────────────────────────────────┐    │
│  │ ImplementationExecutor           │    │
│  │ ファイル編集 / コマンド実行        │    │
│  └────────────────┬────────────────┘    │
│                   ↓                     │
│  ┌─────────────────────────────────┐    │
│  │ AtlasFileSafeApplyExecutor       │    │
│  │ パッチの安全適用                  │    │
│  └────────────────┬────────────────┘    │
│                   ↓                     │
│  ┌─────────────────────────────────┐    │
│  │ VerificationRunner               │    │
│  │ テスト実行・検証                  │    │
│  └────────────────┬────────────────┘    │
│                   ↓                     │
│  ┌─────────────────────────────────┐    │
│  │ AtlasLLMEvaluatorService         │    │
│  │ LLMによる実行結果の自動評価        │    │
│  └────────────────┬────────────────┘    │
│                   ↓ 失敗時              │
│  ┌─────────────────────────────────┐    │
│  │ BoundedRetryService              │    │
│  │ 上限付き再試行 (policy制御)        │    │
│  └─────────────────────────────────┘    │
└──────────────────┬──────────────────────┘
                   ↓ 成功 / ロールバック
┌──────────────────▼──────────────────────┐
│ AtlasJournal                             │
│ → 全イベント・成果物の永続化              │
│ → 中断からの再開 (ContinuationService)   │
└──────────────────────────────────────────┘
```

### Atlasの実行安全モデル (Level 0〜4)

Atlasは**段階的な権限昇格モデル**を採用しています。現在のランタイムは `level_4_self_improvement_platform` まで到達済みです。

| Level | 名称 | 実行できること |
|---|---|---|
| **0** | Manual Only | 計画・プレビューのみ。ファイル変更なし |
| **1** | Guarded Single Step | dry_run証明 + 明示的承認後、1アクションのみ実行 |
| **2** | Guarded Bounded Loop | 上限付きループ。各ステップで承認ゲート |
| **3** | Autonomous Loop Candidate | ドラフトPR生成まで。自動マージ禁止 |
| **4** | Self-Improvement Platform | 自己改善パッチ提案・ローカルブランチ作成まで |

**Level 1 承認ゲート (17項目)** — 以下が全て揃わないと実行できません：

```
snapshot_restore        / patch_transaction       / risk_classification
dry_run_proof           / explicit_approval_token / allowlisted_verification
rollback_readiness      / artifact_capture        / stop_kill_switch
loop_bounds             / remote_git_restriction  / self_improvement_gate
audit_log               / data_root_path_safety   / forbidden_command_policy
backend_authority       / ui_non_authority
```

### リスクレベルによる自動判定

| リスク | 動作 | 例 |
|---|---|---|
| `low` | 自動実行可 | ドキュメント更新、テスト追加 |
| `medium` | ポリシー依存 | 通常のコード変更 |
| `high` | 承認必須 | APIの変更、設定ファイル変更 |
| `critical` | **ブロック** | `main.py`, `Dockerfile`, ワークフロー系 |

**保護ファイル** (変更に必ず承認が必要):
```
app/api/**  /  app/atlas/**  /  agent/**
main.py  /  Dockerfile  /  requirements*.txt
web/js/atlas_dashboard.js  /  docs/atlas_development_constitution.md
```

### Atlas CodeIntel — コードインテリジェンス

Atlasは静的解析でコードベースを理解します：

- **シンボルインデックス** — Python AST解析でクラス・関数・メソッドを全列挙
- **依存グラフ** — モジュール間のimport関係を自動追跡
- **関連テストの自動発見** — 変更ファイルに対応するテストを自動特定
- **除外パス** — `.git` / `__pycache__` / `node_modules` / `ca_data` を自動スキップ

### Atlas自動化ロードマップ

現在 PR-ATLAS-SCALE-147 完了、最終目標は `fully_autonomous_code_agent` です。

```
SCALE-100〜112: 読み取り専用オペレーターレビュー機能 ✅
SCALE-113〜127: Level-1 ガード付き実行 ✅
SCALE-128〜132: パッチ提案・トランザクション・ローカルブランチ ✅
SCALE-133〜135: Draft PR生成・更新 ✅
SCALE-136〜138: 上限付きループ (Level-2) ✅
SCALE-139〜143: 自律実装ループ候補 (Level-3) ✅
SCALE-144〜147: Self-improvement + Level-4 ✅
SCALE-148〜:    外部リカバリースーパーバイザー・完全自律化 🚧
```

---

## 💬 Lumen — インテリジェントチャット

Lumenは、日常会話からWeb検索・天気・ニュースまでを扱う**チャットサーフェス**です。

### インテント自動分類

メッセージを受け取ると、Lumenは即座に意図を検出します：

| インテント | トリガーキーワード | 動作 |
|---|---|---|
| `chat` | (その他) | ローカルLLMとの通常会話 |
| `weather` | 天気 / 気温 / 雨 / forecast / temperature | Open-Meteo天気取得 |
| `news` | ニュース / 速報 / headlines / latest news | 軽量ニュースダイジェスト |
| `web` | 検索 / 調べて / URL / https:// | SearXNG経由のWeb検索 |
| `nexus_deep_research_suggestion` | 詳しく調査 / レポート / 深掘り | Nexus Deep Researchへ誘導 |

### 天気機能 (Open-Meteo / APIキー不要)

```
「明日の横浜の天気は？」
    ↓
位置情報を自動抽出 ("横浜")
    ↓
Open-Meteo Geocoding → 座標解決
    ↓
Open-Meteo Forecast → 3日間予報取得
    ↓
LLMへ圧縮コンテキストを渡して自然言語回答生成
```

**日本語の時制も理解します：**
`今日` / `明日` / `明後日` / `今夜` / `今朝` / `週末` / `来週`

### ニュース機能 (マルチソース)

SearXNG・GDELT DOC 2.0・RSSフィードを統合したニュースダイジェスト。Yahoo!ニュースRSSは `personal_use_only` フラグ付きで自動通知。証拠保存なし・Nexus Deep Research自動起動なしの**軽量モード**で動作します。

### Lumenの境界設計

Lumenは意図的に**軽量**に設計されています：

```
Lumenが担当 ✅         Lumenが担当しない ❌
─────────────────────  ──────────────────────────────
通常チャット             ファイル編集・コマンド実行
天気 (Open-Meteo)       Deep Research (Nexus管轄)
ニュースダイジェスト       自律ループ・自動継続
1回限りのWeb検索         承認済みタスク実行
会話履歴の継続           モデル切替オーケストレーション
```

### 検索ポリシー制御

```python
tool_policy  = "off" | "auto" | "on"   # ツール使用方針
search_policy = "off" | "auto" | "on"  # Web検索方針
```

**予算上限 (ハードキャップ):**

| バジェット | 既定 | 最大 |
|---|---|---|
| Web検索: クエリ数 | 3 | 5 |
| Web検索: 1クエリ結果数 | 5 | 10 |
| Web検索: 取得文字数 | 12,000 | 30,000 |
| Web検索: タイムアウト | 20秒 | 60秒 |
| 天気: 予報日数 | 3 | 7 |

---

## 🎙️ Echo — 音声I/Oシステム

EchoはリアルタイムASR（音声認識）・翻訳・TTS（音声合成）を統合した**音声ワークベンチ**です。

### サポートする音声エンジン

**ASRエンジン (自動選択):**

| エンジン | バックエンド | 用途 |
|---|---|---|
| `faster-whisper` | CUDA / CPU | Runpod推奨。large-v3-turboをバンドル |
| `whisper.cpp` | Vulkan | **Windows AMD GPU対応**。RX 9070 XT等で動作 |
| `auto` | 環境検出 | OS・GPU・Runpod判定で自動選択 |

**Windowsでのwhisper.cpp Vulkan自動セットアップ:**
```bat
setup_whisper_cpp_vulkan_windows.bat
```
→ `ca_data/bin/whisper.cpp-vulkan/` と `ggml-large-v3-turbo.bin` を自動取得

**TTSエンジン:**

| エンジン | 特徴 |
|---|---|
| **Style-Bert-VITS2** | 高品質日本語TTS。koharune-amiモデルをDockerにバンドル |
| **Qwen3-TTS** | 多言語対応TTS (要requirements-tts.txt) |

### Echo言語ルーター

ASR言語とTTS言語を独立して制御できます：

```
入力音声 (ASR: ja) → 認識テキスト (日本語)
                           ↓
                    LLM翻訳 (ja → en) ← output_language="en" の場合
                           ↓
                    TTS合成 (Style-Bert-VITS2)
                           ↓
                    音声出力 (英語読み上げ)
```

**jp_extra モデル** では入力がどの言語でも日本語音声に自動変換されます。

### WebSocket リアルタイムストリーム

`/echo/stream` はWebSocketベースのリアルタイム音声セッションで、ASRチャンク処理・TTS応答・EchoVaultへの自動保存を同時並行で処理します。

---

## 🔍 Nexus — 知識調査システム

Nexusは、PDFやWebページの取り込みから、証拠収集・Deep Research・レポート生成まで担う**知識調査エンジン**です。

### リサーチフロー

```
クエリ入力
  │
  ▼
ResearchPlanner
  → 意図推定 (infer_research_intent)
  → ソースミックス設計 (官公庁/論文/ニュース/企業/一般)
  → カバレッジマトリクス構築
  │
  ▼
plan_web_queries (SearXNG)
  → 並行マルチクエリ実行 (ThreadPoolExecutor)
  → エンジンヘルストラッキング + フォールバック
  │
  ▼
source_collector
  → ランキング・重複排除・ソースミックス最適化
  │
  ▼
Downloader (並行)
  → PDF / HTML 取得 (上限: 20MB/ファイル, 100MB合計)
  → PyMuPDF テキスト抽出
  │
  ▼
Evidence構築
  → チャンキング・インデックス化
  → evidence.db 保存
  │
  ▼
AnswerBuilder
  → 証拠付き回答生成
  → 引用マッピング (citation_mapper)
  │
  ▼
GapAnalysis (recursive/deepモード)
  → カバレッジ不足の自動検出
  → フォローアップクエリ生成
  │
  ▼
ReportBuilder
  → Markdown レポート生成
  → エクスポートバンドル (.zip)
```

### リサーチモード

| モード | 説明 |
|---|---|
| `standard` | 標準調査。単一ラウンド |
| `deep` | 深度優先。ギャップ分析 + フォローアップ付き |
| `recursive` | 再帰的調査。最大ダウンロード予算を自動拡張 |
| `news` | ニュース特化。GDELT / SearXNG / RSS統合 |
| `market` | 市場調査特化。企業情報・投資・規制を優先収集 |
| `official` | 公的機関特化。`.gov` / `.go.jp` / `.ac.jp` 優先 |
| `academic` | 学術特化。arXiv / DOI / IEEE 優先 |

### ソース自動分類

ResearchPlannerは取得したURLを自動分類します：

```
官公庁  → .gov / .go.jp / .europa.eu / .mil / .ac.jp
学術    → arxiv.org / doi.org / ieee.org / nature.com / sciencedirect.com
ニュース → reuters / bloomberg / nikkei / nhk / bbc
企業IR  → ir. / investor / annual / company / corp
レポート → white paper / PDF / 調査 / 報告書 / 白書
```

### Nexusカバレッジマトリクス

調査の「穴」を自動検出する10次元マトリクス：

```
市場規模 / キープレイヤー / 技術トレンド / 規制
サプライチェーン / リスク / タイムライン / 投資
公的政策 / 学術的根拠
```

### Agentツールとして呼び出せるNexus機能

```python
nexus_search_library      # 文書ライブラリ内検索 (Evidence)
nexus_web_search          # Web検索 → Evidence自動保存 → job_id返却
nexus_build_report        # Evidence → Markdownレポート生成
nexus_upload_document     # PDFアップロード → テキスト抽出 → インデックス化
nexus_news_scan           # ニューススキャン
nexus_market_research     # マーケット調査
nexus_export_bundle       # 全成果物をZIPエクスポート
```

---

## 🤖 AgentLoop — コア実行エンジン

### 三層計画構造

```
ProgramPlan (プログラム全体目標)
    └── EpicPlan (機能エリア)
            └── ExecutableTask (実行可能なアクション)
                    └── DefinitionOfDone (完了条件チェックリスト)
```

各タスクは完了条件を持ち、Evaluatorが自動評価します：

```
implementation フェーズ → ["構文OK", "必須関数存在", "参照ファイル整合"]
execution_verification  → ["実行時エラーなし", "期待挙動確認"]
```

### ExecutionPolicy — 実行制御

AgentLoopは以下のゲートを通過しないとアクションを実行できません：

```python
capability_decision = policy.check_action(action)    # ツール使用可否
human_gate = policy.assess_human_gate(action)        # 人間確認要否
autostop = policy.evaluate_autostop(evaluation)      # 自動停止判定
```

### Executorのエラー分類テーブル

失敗時に自動でエラー種別を特定し、再試行戦略を決定します：

| エラー種別 | 最大再試行 | フォールバック戦略 |
|---|---|---|
| `json_output_failed` | 2 | 最小JSONプロンプトで再計画 |
| `target_closed` | 1 | 静的HTML検証に切替 |
| `edit_old_str_not_found` | 1 | ファイル再読込して小パッチ適用 |
| `command_not_found` | 1 | ランタイム検査して代替ツール使用 |
| `timeout` | 2 | タスク分割またはスコープ縮小 |
| `not_found` | 0 | サポートツールセットで再計画 |

### HybridMemoryStore

```
短期メモリ (deque)
  → ステップ実行結果の即時保持
  → 直近N件のToolResult

長期メモリ (SQLite)
  → エラー解決策 (error_solution)
  → 環境固有の知識 (env_knowledge)
  → 作業手順 (workflow)
  → TaskOutcome記録
  → ArchitectureDecision記録
  → RiskRegister
```

### SKILLシステム

`ca_data/skills/<name>/SKILL.md` を置くだけでAgentの能力を拡張：

```markdown
# ログ解析スキル

## Purpose
サーバーログからエラー原因を特定する

## When to use
- ERROR / WARN / Traceback を含むログを解析するとき

## Steps
1. read_file でログ全体を取得
2. search_code で "ERROR\|WARN\|Traceback" を抽出
3. 発生時刻順に整理し、原因候補と修正案を提示
```

ホットリロード対応。再起動不要でAgentが即座に参照します。

---

## 🛠️ BuiltinツールとNexusツール

### Builtinツール

| ツール | 説明 |
|---|---|
| `read_file` | ファイル読み込み |
| `write_file` | ファイル書き込み |
| `apply_patch` | Git unified diff形式でパッチ適用 |
| `search_code` | プロジェクト内コード/テキスト検索 |
| `run_command` | 任意コマンド実行 |
| `run_tests` | テストコマンド実行 (`CODEAGENT_TEST_CMD`) |
| `get_error_trace` | 直近の失敗情報・エラートレース取得 |

### LLMロール別エンドポイント

```python
LLM_URL_PLANNER  = CODEAGENT_LLM_PLANNER   # 計画立案
LLM_URL_EXECUTOR = CODEAGENT_LLM_EXECUTOR  # 実行判断
LLM_URL_CHAT     = CODEAGENT_LLM_CHAT      # 通常会話・明確化
LLM_URL_LIGHT    = CODEAGENT_LLM_LIGHT     # 軽量処理
```

モデルDBでロールを個別割当 (9種類)：
```
plan / chat / search / verify / code / complex / reason / multi / translate
```

---

## 📦 セットアップ

### 必要環境

| 項目 | 推奨 |
|---|---|
| OS | Windows 10/11 · Linux · Runpod |
| Python | 3.11 |
| RAM | 32GB以上 |
| VRAM | 16GB以上 (RTX 3070等) |
| GPU | NVIDIA CUDA · AMD Vulkan · CPU fallback |

### Windows ローカル

```bash
git clone https://github.com/souten-yd/KasaneCore.git
cd KasaneCore

# llama-server を配置、またはパス指定
set LLAMA_SERVER_PATH=C:\path\to\llama-server.exe

start.bat
# → http://localhost:8000
```

初回起動で `venv_sys/` が自動作成されます。

### Linux / Runpod

```bash
# 通常起動
python scripts/start_codeagent.py

# Runpod専用
bash scripts/runpod_start.sh

# オプション
python scripts/start_codeagent.py \
  --host 0.0.0.0 \
  --port 8000 \
  --primary-port 8080 \
  --api-timeout 120 \
  --llm-timeout 180
```

### Docker (Runpod推奨)

```bash
docker build -t kasanecore .
docker run -p 8000:8000 -p 8080:8080 \
  -v /workspace/ca_data:/workspace/ca_data \
  -v /workspace/LLMs:/workspace/LLMs \
  kasanecore
```

**Dockerイメージにバンドルされているもの：**
- llama.cpp CUDA バイナリ (`souten-yd/llama-builder` の Linux amd64 CUDA リリースより自動取得)
- faster-whisper `large-v3-turbo` モデル
- Style-Bert-VITS2 (`koharune-ami` モデル込み)
- `Gemma-4-E4B-it-Q4_K_M.gguf` (デフォルトLLM)
- SearXNG (Runpod時は自動起動)

---

## ⚙️ 環境変数一覧

### LLMエンドポイント

| 変数 | 既定値 | 説明 |
|---|---|---|
| `LLM_URL` | `http://localhost:8080/v1/chat/completions` | 共通LLM |
| `CODEAGENT_LLM_PLANNER` | `LLM_URL` | Planner / Verifier用 |
| `CODEAGENT_LLM_EXECUTOR` | `LLM_URL` | Executor用 |
| `CODEAGENT_LLM_CHAT` | `LLM_URL` | Chat / Clarify用 |
| `CODEAGENT_LLM_LIGHT` | `LLM_URL` | 軽量処理用 |
| `CODEAGENT_LLM_MODE` | `single` | LLM実行モード |

### コア

| 変数 | 既定値 | 説明 |
|---|---|---|
| `LLAMA_SERVER_PATH` | 自動検出 | llama-server実行ファイル |
| `LLAMA_ROOT_DIR` | `./llama` (Runpod: `/workspace/llama`) | llama.cpp配置先 |
| `CODEAGENT_RUNTIME` | 自動判定 | `runpod` / `local` / `docker` |
| `CODEAGENT_CA_DATA_DIR` | `./ca_data` (Runpod: `/workspace/ca_data`) | 永続データ |
| `CODEAGENT_WORK_DIR` | `ca_data/workspace` | プロジェクト作業ディレクトリ |
| `CODEAGENT_SKILLS_DIR` | `ca_data/skills` | SKILLファイル |
| `CODEAGENT_TEST_CMD` | 自動推定 | テスト実行コマンド |
| `KASANE_DEBUG_TEST_HARNESS` | `0` (Docker: `1`) | デバッグテストハーネス |

### llama-server / VRAM

| 変数 | 既定値 | 説明 |
|---|---|---|
| `LLAMA_CACHE_TYPE_K` | `q8_0` | KVキャッシュ型(K) |
| `LLAMA_CACHE_TYPE_V` | `q8_0` | KVキャッシュ型(V) |
| `DEFAULT_LLM_CTX_SIZE` | `16384` | デフォルトコンテキスト長 |

### ASR / TTS / Echo

| 変数 | 既定値 | 説明 |
|---|---|---|
| `CODEAGENT_ASR_DEFAULT_MODEL` | `large-v3-turbo` | faster-whisperモデル |
| `CODEAGENT_ASR_ENGINE` | `auto` | `faster_whisper` / `whisper_cpp` / `auto` |
| `CODEAGENT_WHISPER_CPP_BACKEND` | `vulkan` (Win) / `cpu` | whisper.cppバックエンド |
| `CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR` | `/workspace/ca_data/tts/style_bert_vits2/models` | SBV2モデル |
| `CODEAGENT_STYLE_BERT_VITS2_ENABLE_ONNX_MODEL` | `1` (Win自動) | ONNXモデル使用 |
| `ECHO_UPLOAD_MAX_BYTES` | `104857600` (100MB) | Echo音声アップロード上限 |

### Nexus / SearXNG

| 変数 | 既定値 | 説明 |
|---|---|---|
| `NEXUS_WEB_SEARCH_PROVIDER` | `searxng` | 検索プロバイダ |
| `NEXUS_SEARXNG_URL` | Runpod: `:8088` / 他: `http://searxng:8080` | SearXNG URL |
| `NEXUS_SEARCH_FREE_ONLY` | `true` | 無料プロバイダのみ |
| `BRAVE_SEARCH_API_KEY` | 空 | Brave Search (オプション) |
| `NEXUS_MAX_UPLOAD_MB` | `200` | 最大アップロードサイズ |
| `AUTO_START_SEARXNG` | Runpod: `true` / 他: `false` | SearXNG自動起動 |
| `SEARXNG_ENGINE_PROFILE` | `adaptive_broad_research` | SearXNGエンジンプロファイル |

---

## 📁 ディレクトリ構成

```
KasaneCore/
├── main.py                     # FastAPIバックエンド (145エンドポイント)
├── agent/
│   ├── loop.py                 # AgentLoop (Planner/Executor/Evaluator統合)
│   ├── planner.py              # Program/Epic/Task 三層計画
│   ├── evaluator.py            # DoD評価 + 再計画レベル判定
│   ├── executor.py             # Action実行 + エラー分類テーブル
│   ├── memory.py               # HybridMemoryStore (短期deque + 長期SQLite)
│   ├── context_builder.py      # プロジェクトコンテキスト構築
│   ├── deep_planner.py         # アーキテクチャ3案生成 + 選択
│   ├── tools/
│   │   ├── registry.py         # ToolRegistry
│   │   ├── builtin.py          # read/write/patch/search/run/tests
│   │   └── nexus_tools.py      # Nexus連携7ツール
│   └── atlas_*.py              # Atlasサービス群 (140ファイル超)
├── app/
│   ├── api/                    # APIルーター群
│   ├── atlas/                  # 実行安全ゲート (Level1〜Level4)
│   ├── asr/                    # faster-whisper / whisper.cpp
│   ├── tts/                    # Style-Bert-VITS2 / Qwen3-TTS
│   ├── audio/                  # オーディオランタイム設定
│   ├── nexus/                  # RAG・Deep Research・レポート
│   ├── lumen/                  # インテント検出・天気・ニュース
│   └── services/               # jobs / system_usage / audio_runtime
├── web/
│   ├── atlas-next/             # Vue3 + Vite (Atlasワークフロー UI)
│   │   └── src/components/     # WorkflowShell / PlanReview / PatchReview...
│   └── js/ css/               # メインUIアセット
├── docs/                       # 設計ドキュメント・ロードマップ
├── tests/                      # contractテスト (Phase2〜Phase31, 200件超)
├── scripts/
│   ├── start_codeagent.py      # クロスプラットフォームランチャー
│   ├── runpod_start.sh         # Runpod起動
│   ├── setup_llama_runpod.sh   # llama.cppセットアップ
│   ├── setup_whisper_cpp_vulkan_windows.bat  # AMD Vulkan ASRセットアップ
│   └── smoke_ui_modes_playwright.py          # UIスモークテスト
├── docker/
│   └── start-services.sh       # SBV2モデル検証 + SearXNG + FastAPI起動
├── ca_data/                    # 永続データ (gitignore対象)
├── ui.html                     # メインUI (824KB)
├── Dockerfile                  # マルチステージビルド (CUDA 12.8)
├── requirements.txt            # コア依存
├── requirements-tts.txt        # TTS依存 (PyTorch cu128 分離)
└── start.bat                   # Windowsランチャー
```

---

## 💾 永続データ

```
ca_data/
├── memory.db              # HybridMemoryStore (短期+長期)
├── model_db.db            # GGUFモデルDB + ロール割当
├── skills/                # SKILL.mdファイル (ホットリロード)
├── workspace/             # プロジェクト作業ディレクトリ
├── EchoVault/             # Echo録音・文字起こし・成果物
└── nexus/
    ├── nexus.db           # Evidenceインデックス
    ├── uploads/           # アップロード文書
    ├── extracted/         # 抽出テキスト
    ├── reports/           # 生成レポート
    └── exports/           # ZIPエクスポート
```

**Runpod永続化推奨パス:**
```
/workspace/ca_data   /workspace/LLMs   /workspace/llama
```

---

## 🧪 テスト

```bash
# 全contractテスト
pytest -q

# TTS回帰テスト
python scripts/check_style_bert_vits2_tts.py
pytest -q tests/test_style_bert_vits2_tts_contract_regression.py \
          tests/test_tts_language_router.py \
          tests/test_text_normalizer_jp_extra.py

# UIスモーク (Playwright / mock-backed / 9シナリオ)
python scripts/smoke_ui_modes_playwright.py

# バックエンド preflight確認 (バックエンド起動済み前提)
PLAYWRIGHT_SMOKE_BASE_URL=http://127.0.0.1:8000 \
RUN_ATLAS_BACKEND_PREFLIGHT=1 \
python scripts/smoke_ui_modes_playwright.py

# Atlas E2E dry-run (approve/execute/apply は実行しない)
PLAYWRIGHT_SMOKE_BASE_URL=http://127.0.0.1:8000 \
RUN_ATLAS_BACKEND_E2E=1 \
python scripts/smoke_ui_modes_playwright.py

# デバッグテストハーネス (KASANE_DEBUG_TEST_HARNESS=1)
python scripts/run_debug_test_matrix.py
# → http://localhost:8000/debug/tests でGUI確認
```

**Playwright導入:**
```bash
python -m pip install playwright
python -m playwright install chromium
```

---

## 🗺️ 実装状況

| 機能 | 状態 |
|---|---|
| Lumen (チャット・天気・ニュース) | Stable |
| Task SSEストリーム | Stable |
| モデル管理 (GGUF/llama-server) | Stable |
| SQLite永続メモリ | Stable |
| SKILLシステム | Stable |
| Runpod / Docker | Stable |
| Atlas ワークフロー (Plan→Approve→Execute) | Experimental |
| Atlas Guarded Operator Loop | Experimental |
| Atlas Self-Improvement (Level 4) | Experimental |
| Nexus Deep/Recursive Research | Experimental |
| Echo (ASR/TTS/翻訳) | Experimental |
| Style-Bert-VITS2 | Experimental |
| Qwen3-TTS | Experimental |
| Atlas Next (Vue3 UI) | Experimental |

---

## ライセンス

ライセンスファイルが存在する場合はその内容に従ってください。
