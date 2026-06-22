<p align="center">
  <img src="assets/kasane-core-logo.svg" width="132" alt="KasaneCore logo" />
</p>

<h1 align="center">KasaneCore</h1>

<p align="center">
  <strong>あなたのGPUの中に、考える・作る・試す・封じ込める・配る AI工房を。</strong><br>
  Atlas / Lumen / Echo / Nexus / Play / Portal / Forge / Digital Twin を重ね合わせた、ローカルファーストのAIワークベンチ。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Local_First-100%25-success" />
  <img src="https://img.shields.io/badge/API_Key-Optional-success" />
  <img src="https://img.shields.io/badge/Python-3.11-blue" />
  <img src="https://img.shields.io/badge/FastAPI-300%2B_endpoints-009688" />
  <img src="https://img.shields.io/badge/llama.cpp-CUDA_/_Vulkan-orange" />
  <img src="https://img.shields.io/badge/Atlas_Play-Preview_&_Run-blueviolet" />
  <img src="https://img.shields.io/badge/Portal-Package_Catalog-ff69b4" />
  <img src="https://img.shields.io/badge/Forge-Eval→Route→Fallback-black" />
  <img src="https://img.shields.io/badge/Twin_Injection-Sweep_0–4-success" />
</p>

<p align="center">
  <em>作るだけで終わらない。動かして、観察して、パッケージ化して、再利用して、モデルまで鍛えていく。</em>
</p>

---

## ✨ 30秒でわかるKasaneCore

KasaneCoreは、単なるチャットUIでも、単なるコード生成ツールでもありません。

自然言語の要件から、ローカルLLMが計画を立て、コードを書き、安全に適用し、Playで起動・プレビューし、結果をCapsuleとしてパッケージ化し、Portalで再実行・保存・破棄し、Forgeでモデル/ルートの実力を比べ、Digital Twinでプロジェクトの構造や影響範囲を見える化します。

```text
┌─────────────────────────────────────────────────────────────────────┐
│ あなた: 「小さなHTMLゲームを作って。動作確認までして。」              │
│                                                                     │
│ Atlas        要件整理 → 計画 → 実装 → Safe Apply → 検証              │
│ Play         生成物を起動 → Preview / Logs / Proxy / Console観察     │
│ Capsule      成功した成果物を決定論的ZIPにパッケージ化               │
│ Portal       パッケージをImport / Install / Run / Save / Discard     │
│ Forge        どのモデル・ルートが良かったかArenaと証拠で評価          │
│ DigitalTwin  影響範囲・依存・文脈スライスを読み取り専用で投影          │
│                                                                     │
│ 成果物: 作って終わりではなく、遊べる・配れる・学べるプロジェクトへ     │
└─────────────────────────────────────────────────────────────────────┘
```

OpenAIやAnthropicのAPIキーがなくても、GGUFモデルと `llama.cpp` があれば、ローカルGPU上でかなりの範囲を完結できます。外部モデルを使いたい場合も、Forgeのポリシーでルートを分け、ローカル優先・外部禁止・評価用だけ許可といった運用にできます。

> **現在地:** KasaneCoreは急速に成長中のローカルAIワークベンチです。Lumenなど安定している面もあれば、Atlas/Play/Portal/Forge/Digital Twinのように強力だがExperimentalな面もあります。READMEでは夢を隠さず、同時に状態も正直に示します。

---

## 🧩 いまのKasaneCoreを構成する9つの面

```text
        🧠 Atlas             ▶ つくる
        🎮 Atlas Play        ▶ 動かす・見る
        📦 Capsule           ▶ 封じ込める
        🌀 Portal            ▶ 配る・再実行する
        🔥 Forge             ▶ モデルを比べる・鍛える
        🧬 Digital Twin      ▶ プロジェクトを写し取る
        💬 Lumen             ▶ 話す・調べる
        🎙️ Echo              ▶ 聞く・話す・訳す
        🔍 Nexus             ▶ 深く調査する
```

| Surface | 役割 | ひとことで |
|---|---|---|
| 🧠 **Atlas** | 自律コーディング | 要件整理、計画、実装、Safe Apply、検証、自己修復の心臓部 |
| 🎮 **Atlas Play** | 実行・プレビュー | 生成したWeb/HTML/Python等を起動し、Preview・Logs・Proxyで観察 |
| 📦 **Capsule** | パッケージ化 | Playで確認した成果物を、決定論的なZIPパッケージへ封じ込める |
| 🌀 **Portal** | 配布・再実行 | パッケージをImport / Install / Runし、データ保存・破棄・Snapshotを管理 |
| 🔥 **Forge** | モデル工房 | モデル/プロバイダ/ルートをArenaで比較し、LoadoutやStage Policyで制御 |
| 🧬 **Project Digital Twin** | 構造投影 | プロジェクトのノード、依存、影響範囲、文脈スライスを読み取り専用で可視化 |
| 💬 **Lumen** | 軽量チャット | 会話、天気、ニュース、Web検索を担当する日常エージェント |
| 🎙️ **Echo** | 音声I/O | ASR、TTS、翻訳、議事録、リアルタイム音声処理 |
| 🔍 **Nexus** | Deep Research | Web/PDF/文書RAG、証拠収集、引用付きレポート生成 |

---

# 🧠 Atlas — ローカル自律コーディングエンジン

AtlasはKasaneCoreの中核です。チャットでコードを吐くだけではなく、要件を構造化し、計画を作り、変更を安全に適用し、テストやプレビューで確認し、失敗時には原因を見て修正ループへ戻します。

```text
要求
  ↓
Requirement Analyzer
  ↓
Planner / Deep Planner
  ↓
PlanPool / Item mapping / Risk classification
  ↓
Approval Gate
  ↓
Generate Patch
  ↓
Safe Apply
  ↓
Verify / Evaluate
  ↓
Retry / Repair / Draft PR artifact
```

## Atlasのうれしいところ

- **計画してから書く** — いきなりファイルを書かず、要件・制約・リスク・検証条件を先に整理。
- **Safe Apply前提** — 危険な変更、削除、設定変更、外部公開、認証まわりは強く止める。
- **PlanPool** — Program / Epic / Task の階層で複数ステップを扱う。
- **Requirement mapping** — 要件と計画項目を紐付け、漏れを検出しやすくする。
- **自己修復ループ** — 生成 → 適用 → 検証 → 失敗原因 → 再生成を上限付きで回す。
- **Draft PR志向** — 自動マージではなく、確認可能な成果物へ寄せる。
- **ローカルモデル対応** — GGUF / llama.cpp / OpenAI互換ローカルエンドポイントを利用可能。

## 実行安全モデル

| Level | 名称 | できること |
|:---:|---|---|
| **0** | Manual Only | 計画・プレビュー中心。ファイル変更はしない |
| **1** | Guarded Single Step | dry-run証明 + 明示承認で1アクション実行 |
| **2** | Guarded Bounded Loop | 上限付きループ。各段階で安全ゲート |
| **3** | Autonomous Loop | 自律実行し、最終的にDraft PR相当まで進める |
| **4** | Self-Improvement | KasaneCore自身への改善提案をローカルに作る |

> KasaneCoreの思想は「速いけど危ない」ではなく、**ワクワクするほど自動化しつつ、止まるべきところでは止まる**ことです。

---

# 🎮 Atlas Play — 作ったものをその場で動かす

Atlas Playは、生成した成果物をただのファイルで終わらせず、実行対象として扱うためのレイヤーです。

## できること

- Workspace fileの一覧・読み取り・書き込み
- 起動対象の自動解決
- Launch Profileに基づく環境解決
- 単体セッション / Composite Session の起動
- Static Previewの配信
- HTTP Proxy / WebSocket Proxy
- Console event / failed request / observations の記録
- Stop / Restart / Purge / Startup orphan reconciliation

## なぜ重要か

コード生成エージェントは「コードを書いた」と「本当に動いた」の間に大きな谷があります。Playはこの谷を埋めるための面です。

```text
Atlasで生成
  ↓
Playで起動
  ↓
Previewで確認
  ↓
Console / Failed Requestを観察
  ↓
必要ならAtlasへ修正フィードバック
```

---

# 📦 Capsule — 成功した成果物を封じ込める

Capsuleは、Playで確認したプロジェクトを再利用可能なパッケージに変換します。

## 特徴

- **決定論的アーカイブ** — 同じ内容なら再現しやすいZIPを作る。
- **Manifest / checksums / findings** を同梱。
- **runtime dataは含めない** — 実行中に生まれたユーザーデータを勝手に混ぜない。
- **秘密情報チェック** — `.env`、API key、secret、token、private keyらしきものを検出。
- **除外ルール** — `.git`、`node_modules`、`venv`、`ca_data`、`.portal`、`data` などを標準除外。

Capsuleは、AtlasとPortalをつなぐ箱です。

```text
Play session
  ↓ successful
Capsule build
  ↓ deterministic ZIP
Portal catalog
```

---

# 🌀 Portal — 作ったアプリを配って、実行して、データを管理する

Portalは、Capsule化された成果物を扱うカタログ兼ランタイムです。

## できること

- Package catalog表示
- `.zip` / `.portal.zip` のImport
- Import preflight / quarantine / manifest / checksum検証
- Package export
- Install / Run / Stop / Purge
- Run sheetでPreview / Logs表示
- 実行データのSave / Snapshot / Discard
- Installation data backup / delete
- Snapshotからの起動
- Portal上の成果物をAtlasへFork
- Forge traceとの連携

## Portalの思想

AIで作ったものは、生成直後はまだ「作品の卵」です。Portalに入れることで、**再実行できる作品、保存できる作品、捨てられる作品、改造できる作品**になります。

```text
Capsule package
  ↓ Import
Portal catalog
  ↓ Install
Run sheet
  ├─ Preview
  ├─ Logs
  ├─ Save data
  ├─ Snapshot
  └─ Discard
```

> 生成AIの成果物に「セーブデータを残す / 捨てる / バックアップする」というゲームやアプリらしい体験を持ち込むのがPortalです。

---

# 🔥 Forge — モデルを測って、鍛えて、適材適所に配る工房

Forgeは、KasaneCoreのモデル工房です。「このモデル、なんとなく良さそう」ではなく、**実測スコアで能力を測り、その能力に応じてルート・生成方法・Twin補助量を自動で決め、失敗したら締め直す**——そこまでを一気通貫でやります。弱いローカルLLMでも、補助の当て方しだいで戦えるようにするのがゴールです。

## 1️⃣ 測る — Benchmark & 能力プロファイル

- Provider / Model / Profile / Leaderboard、Benchmark Preset、Arena Run
- 16次元の能力評価（structured出力・パッチ整合・影響分析・契約保全・テスト生成・抽象耐性 …）を**実測**し、`ModelProfile` として証拠付きで蓄積
- **起動済みローカルモデルをポート指定で評価**（既定 `127.0.0.1:8080`、Anvil登録不要）。base_urlはサーバ側で解決し、健全性をライブprobe
- **Benchmarkタブ1ボタン**で「ベンチマーク + 注入スイープ + Twin評価」をまとめて実行 → 結果はその場でカーブ＆レーダー表示

## 2️⃣ どれだけ補助が要るか測る — Twin Injection Sweep

同じモデルを **Twin注入レベル0〜4** で段階評価し、能力曲線を描きます。

- **min_sufficient**（最小注入）= 性能のピークから許容誤差内に収まる**いちばん低い**注入量。弱モデルを過剰補助しないための「天井」。
- **max_score**（最大スコア）= ピーク注入量。能力最優先のときの「床」。
- 目的は**ワンタップで切替**。読み方Tipsと「自律度（高いほど少ない補助で動ける）」も併記し、**面積が大きいほど能力が高い**で統一。

## 3️⃣ 補助の効きを測る — Twin Assist 評価（補助あり / なし）

実プロジェクトのフィクスチャ上で、**補助なし(baseline)** と **補助あり(Twinガイダンス注入)** のコード生成を同条件で走らせ、**lift（上がり幅）/ harm（悪化率）** を測ります。アシスト効果はレーダーで「補助あり vs なし」を重ねて可視化。

## 4️⃣ 能力に応じて配る — Execution Policy（評価が実コードに効く）

ベンチ結果は飾りではありません。`ProfileStore → capability_profile → ExecutionPolicySelector` を通って、**実際の自律コード生成のルート・方法・Twin注入量を変えます**。

```text
Benchmark scores ─▶ Capability Profile ─▶ Execution Policy
                                           ├─ Route        (RouteMatrix×ベンチ選好)
                                           ├─ Method        (強い→直接生成 / 弱い→決定論テキスト・anchor・edit-intent)
                                           └─ Twin Injection (能力・スイープ・リスクから決定)
```

## 5️⃣ 失敗したら締め直す — Failure Escalation（フォールバック）

生成が検証NGになったら、ただ作り直すのではなく**ポリシーごと締め直します**。

```text
生成 → 検証NG → 再生成（毎回エスカレーション）
        ├─ Twin注入量を +1（少ない補助から始めて、必要な分だけ増やす）
        ├─ 繰り返すと review-only / 弱LLM向けの安全な方法へ切替
        └─ ルートの安全範囲は決して超えない
```

「最小の補助で始めて、失敗したら補助を足す」——この梯子が自律ループに実配線されています。

## 🛡️ 安全設計

- Forgeは明示的に有効化するまでOFF。Legacy Atlas実行経路は主経路として残す。
- Secret値は返さない。外部プロバイダはポリシーで許可されるまで使わない。
- **Production routingの自動切替はしない**。Cutoverには証拠と確認を要求。
- 評価は評価。ファイル適用や本番ルーティングを勝手に変えない（Safe Apply前提）。

> Forgeの思想は **「弱いモデルを、賢い補助で戦力化する」**。能力を測り、最小の補助で動かし、足りなければ補助を足し、それでもダメなら安全側へ降りる。すべてフロンティアLLM非依存で回ります。

## 📊 プラットフォームの効果をどう測るか（評価方法）

「補助があると本当に良くなるのか？」を、雰囲気でなく**実測で**示すための評価デザインです。すべて同一モデル・同一フィクスチャ・同一採点で、変える軸は「補助の当て方」だけにします。

| 比較軸 | 何を変える | 何が分かる | 指標 |
|---|---|---|---|
| **補助あり / なし** | Twinガイダンス注入の有無 | プラットフォームの正味効果 | `lift`（上がり幅）, `harm`（悪化率） |
| **注入レベル 0→4** | 段階的な補助量 | 能力曲線・最小十分量 | level別 mean score, `min_sufficient` |
| **失敗エスカレーション** | 連続失敗時の締め直し | フォールバックの妥当性 | 注入↑・review-only化の発火 |

評価は決定論的に採点（パッチ生成可否・対象ファイル整合・期待シンボル・契約保全・テスト標的）。**補助なし(baseline)** を必ず対照に置くので、「補助あり」の数字が単独で良く見える錯覚を避けられます。再現は `tests/fixtures/twin_assist`（トラッキング済み）上で、Benchmarkタブの1ボタン、または `injection_sweep_profile` / `TwinAssistRunner` を直接呼んで取得できます。

### 実測レポート（ローカル `Qwen3.6-35B-A3B-IQ4_XS` @ `127.0.0.1:8080`）

正直な実測です。盛りません。**有能なモデルでは「補助を盛らない」のが正解**で、プラットフォームはそれを実証します。

**① Twin補助あり / なし（フルパック5ケース, baseline + slot/anchor, 約221秒）**

| ケース | 補助なし | 補助あり(best) | lift | harm |
|---|:--:|:--:|:--:|:--:|
| large_existing_file_insert | 0.8 | 0.8 | 0.0 | no |
| cross_file_api_consistency | 0.6 | 0.6 | 0.0 | no |
| public_contract_preservation | 0.8 | 0.8 | 0.0 | no |
| edit_intent_rescue | 0.6 | 0.6 | 0.0 | no |
| dependency_aware_test_selection | 0.8 | 0.8 | 0.0 | no |
| **平均** | — | **0.72** | **+0.00** | **0.0** |

→ この35Bは素のままで十分強く（baseline 0.6–0.8）、補助は**害もないが上積みも出ない**。

**② 注入スイープ（レベル0→4, 約35秒）**

| 次元 | level 0 | 1 | 2 | 3 | 4 | 最小十分 |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| structured_output_fidelity | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | **0** |
| edit_intent_quality | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |

→ structuredは満点・注入不要、edit_intentは注入を増やしても0のまま＝**注入では埋まらない弱み**。

**③ 評価が実コードルーティングを変える（これが正味の効果）**

上記プロファイル（structured=1.0 / edit_intent=0.0）を `ExecutionPolicySelector` に通すと:

```text
route=repair_loop  method=repair_compass_steps  injection=2
avoid_method_variants = ['edit_intent_list']        # ← 測定された弱みの方法を自動回避
reasons = injection_sweep_min_sufficient=0,          # ← 有能なので注入は最小（ルート下限）
          known_weaknesses=edit_intent_quality
```

**結論（正直版）:** 有能なモデルに対するプラットフォームの価値は「補助でスコアを盛る」ことではなく、**①弱みを測って自動で回避し（edit_intent_listを使わない）、②過剰注入を避け（min_sufficient=0）、③補助しても害が出ないことを保証する**ことでした。lift が出るのは baseline に伸びしろがある**より弱いモデル / より難しいケース**で、評価デザインはそれもそのまま捉えます。フォールバック（失敗時に注入↑→弱方法へ）は別途、解決器レベルで `注入 0<1<2`・2回目で review-only を実証済みです。

### 🤝 相乗効果（弱いLLMほど効く）

強いモデルでは差が出にくいので、**弱点が実際に出る制御モデル**で「素のまま vs プラットフォーム全部入り」を比較します（再現: `python scripts/forge_synergy_demo.py`）。弱点には2種類あり、**プラットフォームは弱点の種類で正しいレバーを選びます**。

```text
弱いモデル（制御）  raw(注入なし)  →  プラットフォーム
  structured_output      0.00      →   1.00   ← 注入で弱点を回収（min_sufficient=2を発見）
  edit_intent            0.00      →   0.00   ← 注入では直らない
  平均                    0.00      →   0.50
```

**注入では直らない弱点（edit_intent）には、別の補助手法を提案:**

```text
⚠ edit_intent_quality（注入では直らない）
   避ける手法    : edit_intent_list
   代わりに使う  : deterministic_text_patch → twin_localized_slot_patch → anchored_edit_block
   理由          : 編集意図リストを正しく出せない → 構造を外部(Atlas)が持つ方式へ
```

| 弱点の種類 | プラットフォームのレバー | 例 |
|---|---|---|
| ガイダンスで従える | **Twin注入を最小十分まで足す** | structured 0→1.0（level 2） |
| 構造的にできない | **別の生成手法に切替** | edit_intent → 決定論テキスト/スロット |
| 生成が検証NG | **失敗エスカレーション** | 注入↑→繰り返しでreview-only |

> これが相乗効果です。**弱みを測る → 直る弱みは注入で埋め、直らない弱みは手法を変え、それでもダメなら安全側へ降りる。** 弱いローカルLLMほど伸びしろが大きく、プラットフォームの価値が出ます。

---

# 🧬 Project Digital Twin — プロジェクトの写し身

Project Digital Twinは、プロジェクトの構造を読み取り専用で投影するレイヤーです。

## できること

- Twin health / revision確認
- node + 近傍ノードのlazy expansion
- bounded / paginated query
- path trace
- change impact
- bounded context slice

## 重要な制約

Digital Twinは、実行も、変更も、承認状態の変更もしません。あくまで読み取り専用の投影です。

```text
Project files / symbols / relations
  ↓
Twin store
  ↓
Graph / impact / context slice
  ↓
Atlas planning context
```

これにより、Atlasはプロジェクトを「ファイルの束」ではなく、**関係性を持った構造物**として扱いやすくなります。

---

# 💬 Lumen — 日常会話と軽量タスク

Lumenは、日常的な会話、天気、ニュース、Web検索を担当する軽量サーフェスです。

| Intent | 例 | 動作 |
|---|---|---|
| `chat` | 普通の会話 | ローカルLLMへ送る |
| `weather` | 明日の東京の天気 | Open-Meteo系の天気取得 |
| `news` | 最新ニュース | マルチソース要約 |
| `web` | 調べて / URL | SearXNG等の検索 |
| `nexus_deep_research` | 深掘り調査 | Nexusへ誘導 |

Lumenは軽いから良い。重いコード生成はAtlasへ、深い調査はNexusへ、音声はEchoへ。役割分担をはっきりさせています。

---

# 🎙️ Echo — 聞く・話す・訳す

Echoは音声I/Oのためのサーフェスです。

| 種別 | エンジン | 用途 |
|---|---|---|
| ASR | faster-whisper | CUDA/CPUで音声認識 |
| ASR | whisper.cpp | Windows AMD / Vulkan運用の選択肢 |
| TTS | Style-Bert-VITS2 | 高品質日本語TTS |
| TTS | Qwen系TTS | 多言語TTSの実験 |

```text
🎤 音声入力
  ↓
ASR
  ↓
LLM / 翻訳 / 整形
  ↓
TTS
  ↓
🔊 音声出力
```

EchoVaultに録音・文字起こし・成果物を残し、会話や議事録のワークフローへつなげられます。

---

# 🔍 Nexus — Deep Research / RAG / Evidence

Nexusは、Webや文書を扱う調査レイヤーです。

## できること

- Web search
- PDF / HTML download
- document upload
- evidence DB
- source ranking
- gap analysis
- recursive research
- markdown report
- export bundle

```text
Query
  ↓
Research plan
  ↓
Search / download / extract
  ↓
Evidence DB
  ↓
Gap analysis
  ↓
Report
```

Atlasがコードを書く前にNexusで仕様・規格・参考実装を調べる、Lumenから軽いWeb検索を回す、という連携ができます。

---

## ⚔️ 公平な比較: KasaneCoreと他のAIコーディングエージェント

この比較は、公開情報とKasaneCoreの現在のコードベースをもとにした**機能設計・運用思想の比較**です。速度、モデル性能、SWE-bench等の絶対スコア比較ではありません。

凡例: ✅ 強い / 標準対応、◯ 対応、△ 条件付き・限定的、❌ 主目的ではない / 標準ではない、? 公開情報だけでは判断困難

| # | 比較項目 | KasaneCore | Claude Code | GitHub Copilot Agent | Cursor | Devin | OpenHands |
|---:|---|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 完全ローカル運用 | ✅ | ❌ | ❌ | △ | ❌ | ◯ |
| 2 | GGUF / llama.cppを主役にできる | ✅ | ❌ | ❌ | △ | ❌ | △ |
| 3 | クラウド管理の手軽さ | △ | ✅ | ✅ | ✅ | ✅ | △ |
| 4 | IDE / Terminal統合の成熟度 | △ | ✅ | ✅ | ✅ | ◯ | ◯ |
| 5 | 自然言語→計画→コード編集 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 6 | コマンド実行・検証ループ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 7 | Safe Apply / 明示承認ゲート | ✅ | ◯ | ◯ | ◯ | ◯ | ◯ |
| 8 | Snapshot / Rollback志向 | ✅ | △ | △ | △ | ◯ | ◯ |
| 9 | 上限付き自律ループ | ✅ | ◯ | ◯ | ◯ | ✅ | ✅ |
| 10 | ブラウザ/HTML成果物のPlay Preview | ✅ | △ | △ | △ | ◯ | ◯ |
| 11 | 生成成果物のパッケージ化 | ✅ Capsule | ❌ | ❌ | ❌ | △ | △ |
| 12 | アプリカタログ / 再実行Portal | ✅ Portal | ❌ | ❌ | ❌ | ❌ | ❌ |
| 13 | 実行データSave / Snapshot / Discard | ✅ | ❌ | ❌ | ❌ | △ | △ |
| 14 | Project Digital Twin / Impact graph | ✅ | △ | △ | △ | △ | △ |
| 15 | モデルArena / Leaderboard | ✅ Forge | ❌ | ❌ | ❌ | ❌ | △ |
| 16 | Loadout / Stage Policy / Cutover | ✅ Forge | ❌ | ❌ | ❌ | ❌ | △ |
| 17 | Deep Research / 文書RAG内蔵 | ✅ Nexus | △ | △ | △ | △ | △ |
| 18 | ASR / TTS / 翻訳内蔵 | ✅ Echo | ❌ | ❌ | ❌ | ❌ | ❌ |
| 19 | Skill / Hook / Tool拡張 | ✅ | ✅ | ✅ | ◯ | △ | ✅ |
| 20 | No API Keyで始めやすい | ✅ | ❌ | ❌ | ❌ | ❌ | △ |
| 21 | チーム向けSaaS運用 | △ | ✅ | ✅ | ✅ | ✅ | △ |
| 22 | 企業サポート / 運用品質 | △ | ✅ | ✅ | ✅ | ✅ | △ |
| 23 | ローカル改造しやすさ | ✅ | △ | △ | △ | ❌ | ✅ |
| 24 | 研究・実験プラットフォーム性 | ✅ | ◯ | ◯ | ◯ | ◯ | ✅ |

## 比較の読み方

### KasaneCoreが強いところ

KasaneCoreの強みは、**ローカルファーストで、作る・動かす・封じ込める・配る・評価する・調べる・話す**が一体化していることです。

特に、Portal / Play / Capsule / Forge / Digital Twin まで同じワークベンチにある点はかなり独特です。単なる「AIがコードを書く」ではなく、生成物をローカル環境で育てる工房に近い設計です。

### 他エージェントが強いところ

Claude Code、GitHub Copilot、Cursor、Devinは、導入の簡単さ、クラウドモデル品質、IDE/PR/チーム連携、商用サポートの面で強いです。特に既存のGitHub/IDE中心の開発フローに入るなら、これらの完成度は高いです。

OpenHandsはオープンなエージェント基盤として強く、サンドボックス実行や研究・拡張の文脈で魅力があります。

### 公平な結論

KasaneCoreは、現時点で「万人向けに最も完成された商用サービス」ではありません。けれど、**自分のGPU、自分のデータ、自分のプロジェクト、自分のモデル評価まで握りたい人**にとっては、非常にワクワクする方向へ伸びています。

---

## 🏗️ アーキテクチャ

```text
┌──────────────────────────────────────────────────────────────┐
│                         Browser UI                            │
│  Lumen / Atlas / Echo / Nexus / Forge / Portal                 │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP / SSE / WebSocket
┌──────────────────────────────▼───────────────────────────────┐
│                      FastAPI Backend                           │
│  app.api.atlas_*  app.api.portal  app.api.forge                 │
│  app.api.project_twin  app.api.echo  app.api.nexus              │
└──────────────────────────────┬───────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
┌───────▼────────┐   ┌────────▼────────┐   ┌─────────▼─────────┐
│ llama-server    │   │ ca_data / SQLite │   │ workspace / files  │
│ GGUF / CUDA     │   │ plans, memory,   │   │ generated apps     │
│ Vulkan / CPU    │   │ portal, forge    │   │ previews, packages │
└────────────────┘   └─────────────────┘   └───────────────────┘
```

---

## 📁 ディレクトリ構成

```text
KasaneCore/
├── main.py                         # Production FastAPI entrypoint
├── ui.html                         # Main browser UI
├── agent/
│   ├── loop.py                     # Agent loop
│   ├── planner.py                  # Planner
│   ├── deep_planner.py             # Deep planner
│   ├── model_forge/                # 🔥 Forge: providers, arena, stage policy, loadouts
│   ├── project_twin/               # 🧬 Digital Twin store / contracts / context broker
│   └── atlas_*.py                  # Atlas services
├── app/
│   ├── api/
│   │   ├── atlas_play.py           # 🎮 Atlas Play API
│   │   ├── atlas_capsule.py        # 📦 Capsule API
│   │   ├── portal.py               # 🌀 Portal API
│   │   ├── forge.py                # 🔥 Forge API
│   │   ├── project_twin.py         # 🧬 Digital Twin API
│   │   ├── echo.py                 # 🎙️ Echo API
│   │   ├── lumen.py                # 💬 Lumen API
│   │   └── nexus.py                # 🔍 Nexus API
│   ├── atlas/
│   │   ├── play/                   # Play sessions, preview, proxy, workspace policy
│   │   └── capsule/                # Capsule builder, contracts, package metadata
│   ├── portal/                     # Portal catalog/runtime/recovery/paths
│   ├── nexus/                      # Research / RAG / reports
│   ├── asr/ tts/ audio/            # Echo audio runtime
│   └── server.py                   # Router registration / app factory migration
├── web/                            # Static assets
├── docs/                           # Roadmaps / handoff / design docs
├── tests/                          # Contract / unit / smoke tests
├── scripts/                        # Launchers / setup / smoke scripts
├── Dockerfile
└── start.bat
```

---

## 💾 永続データ

```text
ca_data/
├── memory.db                       # Hybrid memory
├── model_db.db                     # Model DB / role assignment
├── skills/                         # SKILL.md hot reload
├── workspace/                      # Project workspaces
├── atlas_play/                     # Play sessions / target graph / preview data
├── portal/                         # Package catalog / installations / runtime data
├── model_forge/                    # Forge profiles / arena runs / loadouts / cutovers
├── project_twin/                   # Digital Twin SQLite store
├── nexus/                          # Evidence DB / reports / uploads
└── EchoVault/                      # Audio transcripts / recordings / outputs
```

---

## 🚀 Quick Start

### Windows

```bat
git clone https://github.com/souten-yd/KasaneCore.git
cd KasaneCore

set LLAMA_SERVER_PATH=C:\path\to\llama-server.exe
start.bat
```

Open: `http://localhost:8000`

### Linux / Runpod

```bash
python scripts/start_codeagent.py --host 0.0.0.0 --port 8000
# or
bash scripts/runpod_start.sh
```

### Docker

```bash
docker build -t kasanecore .
docker run -p 8000:8000 -p 8080:8080 \
  -v /workspace/ca_data:/workspace/ca_data \
  -v /workspace/LLMs:/workspace/LLMs \
  kasanecore
```

---

## ⚙️ 主要な環境変数

### Core / LLM

| 変数 | 既定 | 説明 |
|---|---|---|
| `LLM_URL` | `http://localhost:8080/v1/chat/completions` | OpenAI互換LLM endpoint |
| `CODEAGENT_LLM_PLANNER` | `LLM_URL` | Planner / Verifier用 |
| `CODEAGENT_LLM_EXECUTOR` | `LLM_URL` | Executor用 |
| `CODEAGENT_LLM_CHAT` | `LLM_URL` | Chat / Clarify用 |
| `CODEAGENT_LLM_LIGHT` | `LLM_URL` | 軽量処理用 |
| `LLAMA_SERVER_PATH` | auto | llama-server実行ファイル |
| `CODEAGENT_CA_DATA_DIR` | `./ca_data` | 永続データroot |
| `CODEAGENT_WORK_DIR` | `ca_data/workspace` | workspace root |
| `DEFAULT_LLM_CTX_SIZE` | `16384` | default context length |

### Forge

| 変数 | 既定 | 説明 |
|---|---|---|
| `FORGE_ENABLED` | off | Forge UI/APIの明示有効化 |
| `FORGE_SOURCE_MODE` | `local_only` | local_only等のソースポリシー |
| `FORGE_LOCAL_BASE_URL` | empty | ローカルOpenAI互換provider URL |
| `FORGE_LOCAL_MODEL` | empty | ローカルproviderのmodel id |
| `FORGE_OPENROUTER_ENABLED` | off | OpenRouter providerの明示有効化 |
| `FORGE_OPENROUTER_MODEL` | empty | OpenRouter側model id |

### Nexus

| 変数 | 既定 | 説明 |
|---|---|---|
| `NEXUS_WEB_SEARCH_PROVIDER` | `searxng` | Web検索provider |
| `NEXUS_SEARXNG_URL` | runtime依存 | SearXNG URL |
| `NEXUS_SEARCH_FREE_ONLY` | `true` | 有償/クォータproviderを避ける |
| `NEXUS_MAX_UPLOAD_MB` | `200` | upload上限 |
| `AUTO_START_SEARXNG` | runtime依存 | Runpod等でSearXNG自動起動 |

### Echo

| 変数 | 既定 | 説明 |
|---|---|---|
| `CODEAGENT_ASR_ENGINE` | `auto` | faster_whisper / whisper_cpp / auto |
| `CODEAGENT_ASR_DEFAULT_MODEL` | `large-v3-turbo` | ASR model |
| `CODEAGENT_WHISPER_CPP_BACKEND` | runtime依存 | Vulkan / CPU等 |
| `CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR` | runtime依存 | SBV2 models directory |
| `ECHO_UPLOAD_MAX_BYTES` | `104857600` | audio upload上限 |

---

## 🧪 Tests / Smoke

```bash
pytest -q

python scripts/smoke_ui_modes_playwright.py

PLAYWRIGHT_SMOKE_BASE_URL=http://127.0.0.1:8000 \
RUN_ATLAS_BACKEND_E2E=1 \
python scripts/smoke_ui_modes_playwright.py

python -m pip install playwright
python -m playwright install chromium
```

---

## 🛡️ Safety Philosophy

KasaneCoreは、自律化を進めながらも、次の原則を重視します。

- **Remote git push / merge / self-applyを勝手にしない**
- **危険変更は承認ゲートへ送る**
- **Portal importはquarantine + preflight + manifest + checksum**
- **Capsule exportにruntime dataを混ぜない**
- **Forgeはsecretを返さない**
- **Forgeはproduction routingを自動切替しない**
- **Project Digital Twinは読み取り専用**
- **Playはresource limit / threat model / preview gatewayを持つ**
- **ログと証拠を残し、後から追えるようにする**

---

## 🗺️ 実装状況

| 領域 | 状態 | メモ |
|---|---|---|
| Lumen | Stable | Chat / weather / news / web intent |
| Model DB / local LLM runtime | Stable | GGUF / llama.cpp / role assignment |
| Nexus | Experimental | Deep / recursive research, evidence, report |
| Echo | Experimental | ASR / TTS / translation / realtime audio |
| Atlas planning / codegen | Experimental | PlanPool, Safe Apply, verification loopを継続強化中 |
| Atlas Play | Experimental | Preview / proxy / session管理 |
| Capsule | Experimental | Deterministic package builder |
| Portal | Experimental | Package catalog / run / data lifecycle |
| Forge | Experimental | Model arena / loadout / stage policy / guarded cutover |
| Project Digital Twin | Experimental | Read-only graph / impact / context projection |

---

## 🧠 SKILL System

`ca_data/skills/<name>/SKILL.md` を置くだけで、Agentの振る舞いを拡張できます。

```markdown
# ログ解析スキル

## When to use
- ERROR / WARN / Traceback を含むログを解析するとき

## Steps
1. read_file でログ取得
2. search_code で関連箇所を確認
3. 原因候補、再現手順、修正案を整理
```

---

## 🌟 Roadmap Flavor

KasaneCoreが目指しているのは、単に「AIがコードを書く」世界ではありません。

- Atlasが作る
- Playが動かす
- Capsuleが封じ込める
- Portalが作品化する
- Forgeがモデルを鍛える
- Digital Twinがプロジェクトを理解する
- Nexusが外の知識を集める
- Echoが声を与える
- Lumenが日常の入口になる

つまり、**個人のGPUの中に、小さなAI開発スタジオを作る**ことです。

<p align="center">
  <strong>KasaneCore: Local-first AI workshop for building, running, packaging, replaying, and improving software agents.</strong>
</p>

---

## 📜 License

ライセンスファイルが存在する場合は、その内容に従ってください。

<p align="center"><sub>Built to run on your own machine. 🖥️⚡</sub></p>
