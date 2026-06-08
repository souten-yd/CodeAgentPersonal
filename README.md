<p align="center">
  <img src="assets/kasane-core-logo.svg" width="130" alt="KasaneCore logo" />
</p>

<h1 align="center">KasaneCore</h1>

<p align="center">
  <strong>あなたのGPUの中で、計画し・コードを書き・検証し・直す。</strong><br>
  クラウドにもAPIキーにも依存しない、完全ローカルの自律コーディングエージェント。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/100%25-Local-success" />
  <img src="https://img.shields.io/badge/No_API_Key-required-success" />
  <img src="https://img.shields.io/badge/Python-3.11-blue" />
  <img src="https://img.shields.io/badge/FastAPI-0.110+-009688" />
  <img src="https://img.shields.io/badge/llama.cpp-CUDA_12.8_/_Vulkan-orange" />
  <img src="https://img.shields.io/badge/endpoints-300+-blueviolet" />
</p>

<p align="center">
  <em>「インベーダーゲームを作って」と打つ。あとは眺めているだけでいい。</em>
</p>

---

## ✨ 30秒でわかるKasaneCore

```
┌────────────────────────────────────────────────────────────────┐
│  あなた:  「インベーダーゲームを作って」                          │
│                                                                  │
│  Atlas:   要件を分解 → 8ステップの計画を立案 → リスク評価         │
│           → step1: index.html を生成・適用・検証 ✓               │
│           → step2: styles.css …          ✓                      │
│           → step3〜7: script.js にゲームロジックを実装 ✓         │
│           → step8: テストを生成 ✓                               │
│                                                                  │
│  成果物:  動くSpace Invaders (HTML+CSS+JS) — 全部ローカルLLMで    │
└────────────────────────────────────────────────────────────────┘
```

OpenAIもAnthropicも要りません。RTX 3070 と GGUF モデルがあれば、**要件定義からコード生成・適用・検証・自己修復まで**、すべてオフラインで完結します。

そしてKasaneCoreは、コーディングだけのツールではありません。**チャット・音声・Web調査・文書RAG** を一つのFastAPIバックエンドに重ね合わせた（=Kasane）、個人のためのAIワークベンチです。

---

## ⚔️ 何が違うのか

| | **KasaneCore** | Claude Code | Copilot Agent | Cursor | Devin |
|---|:---:|:---:|:---:|:---:|:---:|
| 🔒 **完全ローカル動作** | ✅ | ❌ | ❌ | ❌ | ❌ |
| 🧠 **ローカルGGUF / llama.cpp** | ✅ | ❌ | ❌ | ❌ | ❌ |
| 🔁 **計画→生成→適用→検証→自己修復ループ** | ✅ | ✅ | △ | △ | ✅ |
| 🚦 **段階的権限モデル (Level 0〜4)** | ✅ | △ | △ | △ | △ |
| 🛡️ **承認ゲート17項目 + スナップショット/ロールバック** | ✅ | △ | △ | ❌ | △ |
| 🤖 **LLMによる自動評価 (Evaluator)** | ✅ | ❌ | ❌ | ❌ | ✅ |
| 🧬 **自己改善 (Self-Improvement / Level 4)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| 🔍 **文書RAG + Deep Research (Nexus)** | ✅ | ❌ | ❌ | △ | ❌ |
| 🎙️ **音声I/O・翻訳 (Echo)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| 💴 **月額** | **¥0** | 従量 | $10〜 | $20 | $500〜 |

---

## 🧩 4つのサーフェス

KasaneCoreは、役割の異なる4つのサーフェスを単一バックエンドに「重ねて」います。

```
        🧠 Atlas              💬 Lumen            🎙️ Echo            🔍 Nexus
   ─────────────────    ─────────────────   ───────────────   ─────────────────
   自律コーディング        インテリジェント       音声I/O・翻訳        知識調査・RAG
   計画→実装→検証         チャット             ASR / TTS         Deep Research
   →適用→自己修復         天気・ニュース・検索    リアルタイム配信     レポート生成
```

| | サーフェス | ひとことで |
|---|---|---|
| 🧠 | **Atlas** | 自然言語の要件から、安全ゲート付きでコードを自律生成・適用・検証する**心臓部** |
| 💬 | **Lumen** | 会話・天気・ニュース・Web検索をさばく軽量チャット |
| 🎙️ | **Echo** | faster-whisper / whisper.cpp + Style-Bert-VITS2 による音声ワークベンチ |
| 🔍 | **Nexus** | PDF/Webの取り込みから証拠収集・Deep Research・レポート生成まで |

---

# 🧠 Atlas — 自律コーディングエンジン

Atlasは「ただのチャット」ではありません。**要件定義 → 計画 → コード生成 → 安全適用 → 検証 → 自己修復**を、段階的な安全ゲートで制御しながら自律実行します。

## 🎬 Atlasが頭の中でやっていること

```
  あなたの一文 ──▶  ① RequirementAnalyzer    要件を構造化、曖昧点を検出
                          │ (不明なら質問)
                          ▼
                    ② DeepPlanner            アーキ案A/B/Cを生成→最適案を選択
                          │                   リポジトリ構造とNexus文脈を考慮
                          ▼
                    ③ PlanPoolBuilder         Program / Epic / Task の三層計画
                          │                   各ステップにリスクと検証条件を付与
                          │                   要件 ↔ ステップを内容ベースで自動紐付け
                          ▼
                    ④ 承認ゲート              （Level/プリセットに応じて）
                          ▼
       ┌──────────────  ⑤ 実行ループ（ステップごと）  ──────────────┐
       │  Snapshot ─▶ Generate ─▶ SafeApply ─▶ Verify ─▶ Evaluate   │
       │   (SHA256)     (LLM)      (安全適用)   (テスト/    (LLM判定)  │
       │                                       ブラウザ)              │
       │                              失敗 ▼                          │
       │                       BoundedRetry / 自己修正（上限付き）      │
       └──────────────────────────────┬────────────────────────────┘
                                       ▼
                    ⑥ Journal             全イベント永続化・中断から再開
                                          Draft PR 準備（自動マージはしない）
```

各ステップは**生成して終わり**ではありません。生成 → 適用 → 検証（JSなら構文・ブラウザsmoke、Pythonならpytest）→ LLM評価 → 失敗なら根本原因をフィードバックして再生成、という**ループ**で品質を担保します。

## 🚦 実行安全モデル（Level 0〜4）

Atlasは**段階的な権限昇格**で動きます。いきなり何でも実行するのではなく、証拠と承認が揃って初めて一段上がります。

| Level | 名称 | できること |
|:---:|---|---|
| **0** | Manual Only | 計画・プレビューのみ。ファイルは一切触らない |
| **1** | Guarded Single Step | dry-run証明 + 明示承認で、1アクションだけ実行 |
| **2** | Guarded Bounded Loop | 上限付きループ。各ステップに承認ゲート |
| **3** | Autonomous Loop | 自律実行 → **Draft PRまで**。自動マージは禁止 |
| **4** | Self-Improvement | 自分自身への改善パッチ提案・ローカルブランチ作成 |

> 🛡️ **Level 1 を通過するには17の承認ゲートが全て揃う必要があります** — snapshot/restore・risk classification・dry-run proof・explicit approval token・allowlisted verification・rollback readiness・stop kill-switch・loop bounds・remote-git restriction・audit log … 「速いが危険」ではなく「速くても安全」を選んだ設計です。

## 🎯 リスクで動きが変わる

| リスク | 動作 | 例 |
|:---:|---|---|
| 🟢 `low` | 自動実行可 | 新規ソースファイルの作成、ドキュメント、テスト追加 |
| 🟡 `medium` | ポリシー依存 | 既存ソースの変更 |
| 🟠 `high` | 承認必須 | 削除・リネーム、APIの変更 |
| 🔴 `strict_gate` | **強ゲート** | `main.py` / `app/api/**` / `.github/workflows/**` / secrets |

リスク分類は**変更の種類**で判定します（新規作成=追加的=low、既存変更=medium、削除=high…）。外部プロジェクトの普通のファイルが過剰にブロックされることはありません。

## 🧭 コードを「理解」してから書く — Atlas CodeIntel

- **シンボルインデックス** — Python AST解析でクラス/関数/メソッドを全列挙
- **依存グラフ** — モジュール間importを自動追跡
- **関連テストの自動発見** — 変更対象に対応するテストを特定
- **兄弟ファイルの実装接地** — テスト生成時、対象実装の**実APIを読んでから**書く（存在しない関数をでっち上げない）
- **クロスファイル整合** — 生成物どうしの参照（`<script src>` / import）が**実ファイル名で噛み合う**

---

# 💬 Lumen — インテリジェントチャット

会話から天気・ニュース・Web検索まで、意図を即座に見分けてさばく軽量サーフェス。

```
「明日の横浜の天気は？」
   └─▶ intent=weather → 位置抽出 → Open-Meteo (APIキー不要) → 3日予報 → 自然言語で回答
「最新のAIニュースを調べて」
   └─▶ intent=web/news → SearXNG・GDELT・RSS → 軽量ダイジェスト
```

| Intent | トリガー | 動作 |
|---|---|---|
| `chat` | その他 | ローカルLLMとの通常会話 |
| `weather` | 天気 / 気温 / forecast | Open-Meteo（キー不要・日本語の時制も理解） |
| `news` | ニュース / 速報 / headlines | マルチソース・ダイジェスト |
| `web` | 検索 / 調べて / https:// | SearXNG経由のWeb検索（予算上限つき） |
| `nexus_deep_research` | 深掘り / レポート | Nexus Deep Researchへ誘導 |

> Lumenは意図的に**軽量**。ファイル編集・自律ループ・Deep Researchはやりません（それぞれAtlas・Nexusの担当）。境界がはっきりしているから速い。

---

# 🎙️ Echo — 音声I/Oシステム

リアルタイムASR・翻訳・TTSを統合した音声ワークベンチ。**言語ルーター**で「日本語で話して英語で返す」も自在。

| 種別 | エンジン | 用途 |
|---|---|---|
| ASR | `faster-whisper` (CUDA/CPU) | large-v3-turbo をバンドル |
| ASR | `whisper.cpp` (Vulkan) | **Windows AMD GPU 対応**（RX 9070 XT 等） |
| TTS | **Style-Bert-VITS2** | 高品質日本語TTS（koharune-ami 同梱） |
| TTS | Qwen3-TTS | 多言語TTS |

```
🎤 入力(ja) ─▶ ASR ─▶ テキスト(ja) ─▶ LLM翻訳(ja→en) ─▶ TTS ─▶ 🔊 出力(en)
```

`/echo/stream`（WebSocket）でASRチャンク・TTS応答・EchoVault保存を並行処理。Windowsは `setup_whisper_cpp_vulkan_windows.bat` でVulkan ASRをワンクリック準備。

---

# 🔍 Nexus — 知識調査システム

クエリ一つから、ソース設計 → 並行収集 → 証拠化 → ギャップ分析 → レポート生成までを自走する調査エンジン。

```
クエリ ─▶ ResearchPlanner (意図推定・ソースミックス設計・カバレッジ行列)
        ─▶ SearXNG 並行マルチクエリ ─▶ ランキング/重複排除
        ─▶ Downloader (PDF/HTML, PyMuPDF抽出) ─▶ Evidence DB
        ─▶ AnswerBuilder (引用付き) ─▶ GapAnalysis ─▶ Markdownレポート + ZIP
```

| モード | 説明 |
|---|---|
| `standard` | 単一ラウンドの標準調査 |
| `deep` | ギャップ分析 + フォローアップ |
| `recursive` | 再帰調査・ダウンロード予算を自動拡張 |
| `news` / `market` / `official` / `academic` | 領域特化（ニュース / 市場 / 公的機関 / 学術） |

Agentツールとしても呼べます：`nexus_web_search` / `nexus_build_report` / `nexus_upload_document` / `nexus_market_research` / `nexus_export_bundle` …

---

## 🏗️ アーキテクチャ全体図

```
┌──────────────────────────────────────────────────────────────┐
│                    ブラウザ UI (ui.html)                       │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP / SSE / WebSocket
┌──────────────────────────────▼───────────────────────────────┐
│                FastAPI バックエンド (main.py)                   │
│                     300+ エンドポイント                         │
│   ┌────────┐  ┌────────┐  ┌───────┐  ┌───────┐  ┌──────────┐  │
│   │ Atlas  │  │ Lumen  │  │ Echo  │  │ Nexus │  │  Models  │  │
│   │(Coding)│  │ (Chat) │  │(Voice)│  │ (RAG) │  │(llama.cpp)│ │
│   └────────┘  └────────┘  └───────┘  └───────┘  └──────────┘  │
└──────────────────────────────┬───────────────────────────────┘
                   ┌────────────▼────────────┐
                   │   llama-server (GGUF)   │
                   │  OpenAI互換 /v1/chat    │
                   └─────────────────────────┘
```

**役割別にLLMを割り当て可能**（9ロール: plan / chat / search / verify / code / complex / reason / multi / translate）。計画は賢いモデル、軽処理は軽量モデル、といった使い分けがモデルDBでできます。

---

## 🚀 クイックスタート

### Windows（ローカル）

```bash
git clone https://github.com/souten-yd/KasaneCore.git
cd KasaneCore

set LLAMA_SERVER_PATH=C:\path\to\llama-server.exe   # llama-server を指定
start.bat                                            # → http://localhost:8000
```
初回起動で `venv_sys/` が自動作成されます。

### Linux / Runpod

```bash
python scripts/start_codeagent.py --host 0.0.0.0 --port 8000
# Runpod専用ランチャー
bash scripts/runpod_start.sh
```

### Docker（Runpod推奨）

```bash
docker build -t kasanecore .
docker run -p 8000:8000 -p 8080:8080 \
  -v /workspace/ca_data:/workspace/ca_data \
  -v /workspace/LLMs:/workspace/LLMs \
  kasanecore
```

> 📦 Dockerイメージ同梱: llama.cpp CUDAバイナリ / faster-whisper large-v3-turbo / Style-Bert-VITS2(koharune-ami) / デフォルトGGUF / SearXNG（Runpod時 自動起動）

### 必要環境

| 項目 | 推奨 |
|---|---|
| OS | Windows 10/11 · Linux · Runpod |
| Python | 3.11 |
| RAM / VRAM | 32GB / 16GB以上（RTX 3070等） |
| GPU | NVIDIA CUDA · AMD Vulkan · CPU fallback |

---

## ⚙️ 主要な環境変数

<details>
<summary><strong>LLMエンドポイント / コア</strong>（クリックで展開）</summary>

| 変数 | 既定値 | 説明 |
|---|---|---|
| `LLM_URL` | `http://localhost:8080/v1/chat/completions` | 共通LLM |
| `CODEAGENT_LLM_PLANNER` | `LLM_URL` | Planner / Verifier |
| `CODEAGENT_LLM_EXECUTOR` | `LLM_URL` | Executor |
| `CODEAGENT_LLM_CHAT` | `LLM_URL` | Chat / Clarify |
| `CODEAGENT_LLM_LIGHT` | `LLM_URL` | 軽量処理 |
| `LLAMA_SERVER_PATH` | 自動検出 | llama-server実行ファイル |
| `CODEAGENT_RUNTIME` | 自動判定 | `runpod` / `local` / `docker` |
| `CODEAGENT_CA_DATA_DIR` | `./ca_data` | 永続データ |
| `CODEAGENT_WORK_DIR` | `ca_data/workspace` | プロジェクト作業ディレクトリ |
| `CODEAGENT_TEST_CMD` | 自動推定 | テスト実行コマンド |
| `DEFAULT_LLM_CTX_SIZE` | `16384` | デフォルトコンテキスト長 |

</details>

<details>
<summary><strong>ASR / TTS / Echo</strong></summary>

| 変数 | 既定値 | 説明 |
|---|---|---|
| `CODEAGENT_ASR_DEFAULT_MODEL` | `large-v3-turbo` | faster-whisperモデル |
| `CODEAGENT_ASR_ENGINE` | `auto` | `faster_whisper` / `whisper_cpp` / `auto` |
| `CODEAGENT_WHISPER_CPP_BACKEND` | `vulkan`(Win) / `cpu` | whisper.cppバックエンド |
| `CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR` | `…/tts/style_bert_vits2/models` | SBV2モデル |
| `ECHO_UPLOAD_MAX_BYTES` | `104857600` (100MB) | 音声アップロード上限 |

</details>

<details>
<summary><strong>Nexus / SearXNG</strong></summary>

| 変数 | 既定値 | 説明 |
|---|---|---|
| `NEXUS_WEB_SEARCH_PROVIDER` | `searxng` | 検索プロバイダ |
| `NEXUS_SEARXNG_URL` | Runpod:`:8088` / 他:`http://searxng:8080` | SearXNG URL |
| `NEXUS_SEARCH_FREE_ONLY` | `true` | 無料プロバイダのみ |
| `NEXUS_MAX_UPLOAD_MB` | `200` | 最大アップロードサイズ |
| `AUTO_START_SEARXNG` | Runpod:`true` / 他:`false` | SearXNG自動起動 |

</details>

---

## 🧠 拡張: SKILLシステム

`ca_data/skills/<name>/SKILL.md` を置くだけでAgentの能力が増えます（**再起動不要・ホットリロード**）。

```markdown
# ログ解析スキル
## When to use
- ERROR / WARN / Traceback を含むログを解析するとき
## Steps
1. read_file でログ取得
2. search_code で "ERROR|WARN|Traceback" を抽出
3. 発生時刻順に整理し、原因候補と修正案を提示
```

---

## 📁 ディレクトリ構成

```
KasaneCore/
├── main.py                 # FastAPIバックエンド (300+ エンドポイント)
├── agent/
│   ├── loop.py             # AgentLoop (Planner/Executor/Evaluator統合)
│   ├── deep_planner.py     # アーキ3案生成→選択
│   ├── memory.py           # HybridMemoryStore (短期deque + 長期SQLite)
│   ├── tools/              # builtin (read/write/patch/search/run) + nexus_tools
│   └── atlas_*.py          # 🧠 Atlasサービス群 (190+ ファイル)
├── app/
│   ├── api/                # APIルーター群
│   ├── atlas/              # 実行安全ゲート (Level1〜Level4)
│   ├── asr/ tts/ audio/    # 🎙️ Echo (faster-whisper / whisper.cpp / SBV2)
│   ├── nexus/              # 🔍 RAG・Deep Research・レポート
│   └── lumen/              # 💬 インテント・天気・ニュース
├── web/                    # UIアセット
├── docs/                   # 設計ドキュメント・ロードマップ
├── tests/                  # contractテスト (800+ ファイル)
├── scripts/                # ランチャー・セットアップ・スモーク
├── ui.html                 # メインUI
├── Dockerfile              # マルチステージ (CUDA 12.8)
└── start.bat               # Windowsランチャー
```

### 💾 永続データ (`ca_data/`)

```
memory.db        HybridMemoryStore(短期+長期)
model_db.db      GGUFモデルDB + ロール割当
skills/          SKILL.md (ホットリロード)
workspace/       プロジェクト作業ディレクトリ
EchoVault/       Echo録音・文字起こし・成果物
nexus/           Evidence DB・uploads・reports・exports
```

---

## 🧪 テスト

```bash
pytest -q                                          # 800+ contractテスト

python scripts/smoke_ui_modes_playwright.py        # UIスモーク (Playwright / 9シナリオ)

PLAYWRIGHT_SMOKE_BASE_URL=http://127.0.0.1:8000 \
RUN_ATLAS_BACKEND_E2E=1 \
python scripts/smoke_ui_modes_playwright.py        # Atlas E2E dry-run

python -m pip install playwright && python -m playwright install chromium
```

---

## 🗺️ 実装状況

| サーフェス | 機能 | 状態 |
|---|---|---|
| 🧠 Atlas | 計画 → 生成 → 適用 → 検証 → 自己修復 | **動作中**（マルチファイル生成を実証・継続強化中） |
| 🧠 Atlas | Guarded Operator Loop / Self-Improvement(Lv4) | Experimental |
| 💬 Lumen | チャット・天気・ニュース・Web検索 | Stable |
| 🎙️ Echo | ASR / TTS / 翻訳 / リアルタイム配信 | Experimental |
| 🔍 Nexus | Deep / Recursive Research・レポート | Experimental |
| ⚙️ 基盤 | モデル管理・SQLite永続メモリ・SKILL・Runpod/Docker | Stable |

> 🚧 **現在地**: Atlasの自律コード生成パイプライン（計画→生成→適用→検証）を、実タスク（HTML/CSS/JSのゲーム生成）で一気通貫に通せるところまで到達。最終目標は `fully_autonomous_code_agent`。安全ゲートは常に最優先で維持します。

---

## 📜 ライセンス

ライセンスファイルが存在する場合はその内容に従ってください。

<p align="center"><sub>Built to run on your own machine. 🖥️⚡</sub></p>
