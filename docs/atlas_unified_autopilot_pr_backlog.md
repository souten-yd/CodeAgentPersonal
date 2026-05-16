# Atlas Unified Autopilot PR Backlog

## PR-ATLAS-PIPE-0: 計画書とチャット継続用docs追加

### 目的

Atlas統合Autopilot方針、ADR、PR backlog、チャット継続checkpointをrepo内に固定する。

### 主な変更

- Master plan documentを追加する。
- Continuation checkpoint documentを追加する。
- ADR documentを追加する。
- PR backlog documentを追加する。
- Docs contract testを追加する。

### 完了条件

- 4つのdocsが存在する。
- Contract testが必須語句を検証する。
- `pytest -q tests/test_atlas_unified_autopilot_docs_contract.py` がpassする。

### 変更禁止範囲

- runtime変更禁止。
- UI変更禁止。
- API変更禁止。
- `main.py`変更禁止。
- 既存Atlas / Lumen / Echo / Nexus挙動変更禁止。

## PR-ATLAS-PIPE-1: PlanItem / PlanPool schema追加

### 目的

Atlas PlannerとAutopilotの境界になるPlanItem / PlanPool schemaを追加する。

### 主な変更

- `AtlasPlanItem` schemaを追加する。
- `AtlasPlanPool` schemaを追加する。
- dependency、status、approval状態の最小フィールドを定義する。
- 既存Planner出力との変換に備えた型を定義する。

### 完了条件

- `agent/atlas_plan_pool_schema.py` が存在する。
- `AtlasPlanItem` / `AtlasPlanPool` が定義される。
- SchemaはJSON roundtrip可能。
- runtime / storage / API / UI は変更しない。
- Schema contract testがpassする。
- runtime executionはまだ行わない。
- 既存API挙動に差分がない。

### 変更禁止範囲

- 新規Task API追加禁止。
- 新規Agent API追加禁止。
- UI変更禁止。
- 自動実行処理追加禁止。

## PR-ATLAS-PIPE-2: PlanPool storage追加

### 目的

Plan Poolを保存・復元できる内部storageを追加する。

### 主な変更

- PlanPool storage serviceを追加する。
- PlanItem status更新の保存処理を追加する。
- 既存PlanStorageとの関係を整理する。

### 完了条件

- `agent/atlas_plan_pool_storage.py` が存在する。
- PlanPoolを ca_data/atlas/plan_pools/ に保存できる。
- PlanPoolを読み込める。
- item状態更新時に item.status と completed/failed/blocked/skipped lists が同期する。
- path traversalを拒否する。
- runtime / API / UI は変更しない。
- 既存PlanStorageを壊さない。
- Contract / unit testsがpassする。

### 変更禁止範囲

- runtime自動実行禁止。
- UI変更禁止。
- Task / Agent API追加禁止。

## PR-ATLAS-PIPE-3: Planner出力をPlan Pool化

### 目的

既存TaskPlanningRunner / Planner / DeepPlanner出力をAtlas Plan Poolへ変換する。

### 主な変更

- Planner output to PlanPool mapperを追加する。
- PlanReviewer結果をPlanItem / pool metadataへ反映する。
- Nexus context metadataをPlan Poolへ保存できるようにする。

### 完了条件

- `agent/atlas_plan_pool_builder.py` が存在する。
- Plan payloadからAtlasPlanPoolを生成できる。
- Autopilot preview planからAtlasPlanPoolを生成できる。
- implementation_stepsが空でもfallback PlanItemsを生成できる。
- mapperはファイル保存しない。
- mapperはruntime/API/UIを変更しない。
- Planner結果からPlan Poolが生成される。
- 既存planning contractが維持される。
- Nexusが空でもwarningで継続する。

### 変更禁止範囲

- Autopilot自動適用禁止。
- 新規Task Runner追加禁止。
- 新規Agent Runner追加禁止。

## PR-ATLAS-PIPE-4: Autopilot Policy追加

### 目的

PlanReviewer等の既存risk detectionをAutopilot Policy Gateとして再利用する。

### 主な変更

- Policy Gate内部サービスを追加する。
- destructive / dependency / security / DB / API / UI risksを判定する。
- delete / run_commandの初期禁止ルールを明文化する。

### 完了条件

- `agent/atlas_autopilot_policy_schema.py` が存在する。
- `agent/atlas_autopilot_policy.py` が存在する。
- PlanItem / PlanPool / patch metadataをpolicy評価できる。
- high/critical risk、protected path、delete、run_command、non-allowlisted test commandを検出できる。
- policyは判定のみで、ファイル変更・コマンド実行・storage/API/UI操作をしない。
- Risk判定結果がPlanItem実行可否に反映される。
- High-risk itemはapproval待ちになる。
- Testsがpassする。

### 変更禁止範囲

- 自動safe_apply禁止。
- 任意command実行禁止。
- UI変更禁止。

## PR-ATLAS-PIPE-5: Pipeline Runner dry_run

### 目的

Plan PoolからPlanItemを取り出し、dry_run Pipelineとして実行する内部runnerを追加する。

### 主な変更

- Autopilot Pipeline Runnerを追加する。
- Policy Gate、approval state、ImplementationExecutor dry_runを接続する。
- Run logの最小形を追加する。

### 完了条件

- `agent/atlas_pipeline_runner_schema.py` が存在する。
- `agent/atlas_pipeline_runner.py` が存在する。
- PlanPoolからready itemを選択できる。
- Policy Gateを通してblock / require_approval / allowを処理できる。
- allow itemだけdry_runできる。
- executor未指定時はsimulation dry_runとして完了できる。
- safe_apply / API / UI は追加しない。
- PlanItemがdry_runで処理される。
- ファイル変更は適用されない。
- Pipeline contract testがpassする。

### 変更禁止範囲

- safe_apply禁止。
- delete自動実行禁止。
- run_command自動実行禁止。

## PR-ATLAS-PIPE-6: Approval Gate

### 目的

pool、item、patchのapproval gateを明示し、Autopilotの安全境界を固定する。

### 主な変更

- Pool approval stateを追加する。
- Item approval stateを追加する。
- Patch approval stateを追加する。
- Approvalなしでは適用されないことをtestする。

### 完了条件

- `agent/atlas_approval_schema.py` が存在する。
- `agent/atlas_approval_gate.py` が存在する。
- pool / item / patch approval recordを作成できる。
- approve / reject / revoke ができる。
- snapshotで承認状態を集約できる。
- Pipeline Runnerがrequire_approval itemでpending approvalを作成できる。
- Approval未取得の変更が適用されない。
- Approval stateが保存される。
- safe_apply / API / UI は追加しない。
- Testsがpassする。

### 変更禁止範囲

- UIでの新規user-facing Task / Agent追加禁止。
- 任意command実行禁止。
- 既存API破壊禁止。

## PR-ATLAS-PIPE-7: low-risk safe_apply

### 目的

low-risk PlanItemに限定してsafe_applyを段階導入する。

### 主な変更

- low-risk判定条件を追加する。
- ImplementationExecutor safe_applyをAutopilot capabilityとして接続する。
- Patch approvalを必須化する。

### 完了条件

- `agent/atlas_safe_apply_adapter_schema.py` が存在する。
- `agent/atlas_safe_apply_adapter.py` が存在する。
- low-risk create/updateだけsafe_apply対象として評価できる。
- delete/run_commandは禁止継続。
- protected path / non-low-risk / policy block / approval missing を検出できる。
- executor未指定時はsimulation可能。
- run_dry_runはsafe_applyを呼ばない。
- API / UI は追加しない。
- Testsがpassする。

### 変更禁止範囲

- delete自動実行禁止。
- 非allowlist command実行禁止。
- 新規Agent Runner追加禁止。

## PR-ATLAS-PIPE-8: TestCommandRunner

### 目的

検証用commandをallowlist方式で実行する内部runnerを追加する。

### 主な変更

- TestCommandRunnerを追加する。
- 初期allowlistを定義する。
- Timeout、working directory、log captureを実装する。

### 完了条件

- `agent/test_command_runner_schema.py` が存在する。
- `agent/test_command_runner.py` が存在する。
- allowlist式で検証コマンドだけ実行できる。
- shell=Falseを使用する。
- forbidden tokenを拒否する。
- run_many / run_item_tests がある。
- Pipeline Runnerのrun_dry_runではtest commandを自動実行しない。
- API / UI は追加しない。
- allowlistされたtest commandのみ実行される。
- 非allowlist commandは拒否される。
- Testsがpassする。

### 変更禁止範囲

- 任意run_command実行禁止。
- delete自動実行禁止。
- UI変更禁止。


## PR-ATLAS-PIPE-8B: Atlas Journal / Recovery checkpoint foundation

### 目的

Atlas Pipelineの大規模・長時間実行に備えて、PlanPool / PipelineRunState / events / checkpointをJSON、Markdown、events.ndjsonとして保存し、reload/chat recovery summaryを復元できる内部基盤を追加する。

### 主な変更

- `agent/atlas_journal_schema.py` を追加する。
- `agent/atlas_journal.py` を追加する。
- `agent/atlas_recovery_service.py` を追加する。
- JSON + Markdown + events.ndjson保存を追加する。
- reload/chat recovery summaryを返す内部serviceを追加する。

### 完了条件

- PlanPoolをjournal配下にJSON/Markdown保存できる。
- PipelineRunStateをJSON/Markdown保存できる。
- events.ndjsonにappend/readできる。
- checkpoint.md / next_actions.md / final_report.mdを書ける。
- latest/pool/runを復元できる。
- API/UIは追加しない。

### 変更禁止範囲

- API変更禁止。
- UI変更禁止。
- DebugLoopRunner追加禁止。
- TestCommandRunnerやsafe_applyの自動実行追加禁止。

## PR-ATLAS-PIPE-9: DebugLoopRunner

### 目的

失敗した検証に対してmax retryつきのdebug loopを追加する。

### 主な変更

- DebugLoopRunnerを追加する。
- max retry、stop condition、failure summaryを追加する。
- TestCommandRunnerと連携する。

### 完了条件

- `agent/debug_loop_schema.py` が存在する。
- `agent/debug_loop_runner.py` が存在する。
- test/safe_apply/pipeline失敗結果をDebugInputへ要約できる。
- syntax/import/test/policy/approval/timeout等を分類できる。
- max retryで停止できる。
- DebugLoopStateにattemptを記録できる。
- AtlasJournalへdebug_notes.md/eventsを保存できる。
- 自動patch生成 / safe_apply / test execution / API / UI は追加しない。
- max retryを超えたら停止する。
- Debug loopがpolicy / approvalを迂回しない。
- Testsがpassする。

### 変更禁止範囲

- 無制限retry禁止。
- 非allowlist command実行禁止。
- high-risk auto apply禁止。

## PR-ATLAS-PIPE-10: Nexus Research Request

### 目的

NexusをAtlasのResearch Request / Context Pack基盤として接続する。

### 主な変更

- Research Request schemaを追加する。
- Context Pack schemaを追加する。
- Planner / Autopilotから利用できるadapterを追加する。

### 完了条件

- `agent/atlas_nexus_research_schema.py` が存在する。
- `agent/atlas_nexus_research_adapter.py` が存在する。
- ResearchRequest / ContextPack / Finding schemaがある。
- nexus_clientなしでもwarning付きContextPackを返せる。
- client resultをContextPackに変換できる。
- PlanItemからResearchRequestを生成できる。
- JournalへContextPack JSON/Markdownを保存できる。
- API/UI/Web/DeepResearch jobは追加しない。
- Research RequestからContext Packを取得できる。
- Nexusが空でもwarningで継続する。
- Testsがpassする。

### 変更禁止範囲

- Nexus既存API破壊禁止。
- UI変更禁止。
- 自動適用処理追加禁止。

## PR-ATLAS-PIPE-11: Research Item実行

### 目的

PlanItemの一種としてResearch Itemを実行できるようにする。

### 主な変更

- Research Item typeを追加する。
- Nexus Research RequestをPlanItem実行に接続する。
- Research結果をPlan Pool metadataへ反映する。

### 完了条件

- Pipeline Runnerが `item_type=research` を処理できる。
- research itemはAtlasNexusResearchAdapterを呼ぶ。
- research itemはImplementationExecutorを呼ばない。
- research itemはsafe_apply/TestCommandRunnerを呼ばない。
- adapter未指定でもwarning付きContextPackで完了できる。
- ContextPackをJournalへ保存できる。
- 外部Web/DeepResearch job/API/UIは追加しない。
- Research ItemがContext Packを生成する。
- 通常implementation itemと区別できる。
- Testsがpassする。

### 変更禁止範囲

- ファイル変更の自動適用禁止。
- 新規user-facing Research feature追加禁止。
- 既存Nexus挙動破壊禁止。

## PR-ATLAS-PIPE-12: Nexus Outcome Writer

### 目的

Autopilot実行結果、run log、再利用可能lessonをNexusへ保存する内部writerを追加する。

### 主な変更

- NexusOutcomeWriterを追加する。
- final report、run log、reusable lesson saveを接続する。
- 保存失敗時のwarning継続を定義する。

### 完了条件

- `agent/nexus_outcome_schema.py` が存在する。
- `agent/nexus_outcome_writer.py` が存在する。
- pipeline/debug/safe_apply/research結果からOutcomeを生成できる。
- JournalへOutcome JSON/Markdownを保存できる。
- optional nexus_clientへsave_outcome/save_memory/add_memoryで保存できる。
- Nexus未接続でも処理継続する。
- API/UI/Nexus DB schema変更はしない。
- 保存失敗がPipeline全体の不要なhard failureにならない。
- Testsがpassする。

### 変更禁止範囲

- Nexus既存data破壊禁止。
- UI変更禁止。
- API破壊禁止。

## PR-ATLAS-PIPE-13: Atlas API統合

### 目的

Planner、Plan Pool、Autopilot Pipelineを既存Atlas APIへ段階統合する。

### 主な変更

- `/api/atlas/*` 配下へ最小Atlas API統合を追加する。
- PlanPool作成APIを追加する。
- PlanPool取得APIを追加する。
- PlanPool Markdown取得APIを追加する。
- Pipeline dry_run APIを追加する。
- Pipeline status取得APIを追加する。
- Recovery latest / pool取得APIを追加する。
- Task / Agent APIは追加しない。
- safe_apply APIは追加しない。

### 完了条件

- Atlas APIからPlanPool作成、PlanPool取得、Pipeline dry_run、Status取得、Recovery取得ができる。
- Task / Agent APIが増えていない。
- safe_apply/APIなし。
- API contract testsがpassする。

### 変更禁止範囲

- Standalone Task API追加禁止。
- Standalone Agent API追加禁止。
- safe_apply自動実行/API公開禁止。
- TestCommandRunner / DebugLoopRunner自動実行禁止。
- 外部Web / Deep Research Job起動禁止。
- 既存Atlas / Lumen / Echo / Nexus API破壊禁止。

## PR-ATLAS-PIPE-14: Add redesigned Atlas UI for PlanPool, Pipeline and Recovery

### 目的

PR-ATLAS-PIPE-13で追加した `/api/atlas/*` APIを使い、旧Atlas UIの複雑なボタン群を前面に出さない新Atlas Dashboardへ再設計する。

### 主な変更

- 新Atlas Dashboard UIを追加する。
- Goal ComposerからPlanPoolを作成する。
- PlanPool itemsをPlanItemカード/タイムラインとして表示する。
- Pipeline dry-run progressをstatus card、progress bar、latest events、next actionで表示する。
- Recovery bannerから最新状態を読み込み、ブラウザリロード後もPlanPool/status/eventsを復元する。
- Details drawerにMarkdown、events、raw JSON、checkpoint pathを隠す。
- Advanced settingsは初期状態でcollapsedにする。
- iPhone Safari対応として1カラム、flex-wrap、min-width:0、pre/logのみ横スクロールを徹底する。
- safe_apply/TestCommand/DebugLoop/DeepResearch等の実行UIは追加しない。

### 完了条件

- Atlas Dashboard root、Goal textarea、Create Plan、Start Dry-run、PlanPool list、Pipeline status、Recovery container、Details drawerが存在する。
- Advanced Settingsは初期状態で閉じている。
- iPhone Safari相当の幅で横崩れしない。
- Task / Agent API文字列やsafe_apply等の実行ボタンを新UIに増やしていない。
- UI contract testsと既存Atlas internal testsがpassする。

### 変更禁止範囲

- Standalone Task page追加禁止。
- Standalone Agent page追加禁止。
- safe_apply/TestCommandRunner/DebugLoopRunner/DeepResearchの実行UI追加禁止。
- 既存Lumen / Echo / Nexus UI破壊禁止。

## PR-ATLAS-PIPE-14B: Fix Atlas Dashboard visual design and static asset loading

### 目的

PR-ATLAS-PIPE-14で追加したAtlas Dashboardを、visual design rescue / static asset loading verificationとして実画面で使えるカード型UIへ整える。

### 主な変更

- Atlas Dashboardを正式Dashboardとして見えるカード型UIに再設計する。
- CSS/JSのcache bustingを追加し、ブラウザが古いstatic assetを読み続ける問題を避ける。
- 配信対象の`web/css/app.css`にAtlas専用selectorが含まれることをcontract testで確認する。
- iPhone Safari相当の幅で横崩れしないように、shell/grid/card/preのoverflowとmin-widthを整理する。
- safe_apply/TestCommand/DebugLoop/DeepResearch等の実行UIは追加しない。

### 完了条件

- 実画面でAtlas Dashboardがカード型UIとして表示される。
- CSSが確実に反映される。
- cache bustingがある。
- iPhone Safariで横崩れしない。
- safe_apply等の実行UIなし。

### 変更禁止範囲

- Standalone Task page追加禁止。
- Standalone Agent page追加禁止。
- safe_apply/TestCommandRunner/DebugLoopRunner/DeepResearchの実行UI追加禁止。
- 既存Lumen / Echo / Nexus UI破壊禁止。

## PR-ATLAS-PIPE-15: Add Atlas continuation handoff and operational polish

Status: completed

### 目的

Atlas Journal / Recovery / checkpointを活用し、新しいチャットに貼れば続きから再開できるContinuation Prompt、現在のPlanPool/Pipeline/Recovery状態、次にやるべき操作をAtlas Dashboardと`/api/atlas/*`から取得・コピーできるようにする。

### 主な変更

- `AtlasContinuationService`と`AtlasContinuationSummary`を追加する。
- `/api/atlas/continuation/latest` と `/api/atlas/continuation/pools/{pool_id}` を追加する。
- Details / Advanced Panel内にChat Continuation panelを追加する。
- Copy Continuation Prompt / Copy IDsを追加する。
- Recovery/latest、PlanPool Markdown、Pipeline state、events.ndjson、checkpoint pathをContinuation Summaryに接続する。

### 完了条件

- Atlas DashboardからContinuation Promptを生成・コピーできる。
- Continuation APIがsummary/prompt/path情報を返す。
- stale recoveryはwarning扱いを維持する。
- safe_apply/TestCommand/DebugLoop/DeepResearchの実行UIや実行APIを追加しない。
- iPhone Safari相当の幅でContinuation panelが横崩れしない。

### 変更禁止範囲

- Standalone Task / Agent UI追加禁止。
- `/api/task/*` / `/api/agent/*` 追加禁止。
- safe_apply/TestCommandRunner/DebugLoopRunner/DeepResearch/Web調査起動UI追加禁止。
- 任意コマンド実行追加禁止。
- 既存Atlas / Lumen / Echo / Nexus挙動破壊禁止。

## PR-ATLAS-PIPE-16: Atlas Planner integration / real planning bridge

### 目的

Create Planがfallback PlanPoolだけでなく、既存Planner / DeepPlanner / Requirement Analyzer の結果からPlanPoolを生成できるようにする。

### 範囲

- API/UIの既存導線を維持する。
- `plan_payload`がある場合は既存どおりPlanPoolを生成する。
- `plan_payload`がない場合でも、可能なら既存PlanningRunnerを呼ぶ。
- PlanningRunnerが失敗/未接続の場合はfallback PlanPoolへ戻す。
- Nexusが空でもfallbackに戻れるwarning扱いを維持する。

### 完了条件

- Atlas Create Planが実Planner結果からPlanPoolを作れる。
- fallback PlanPoolは安全な代替経路として残る。
- safe_apply/TestCommand/DebugLoop/DeepResearchの自動実行は追加しない。

### 変更禁止範囲

- safe_apply自動実行禁止。
- TestCommand自動実行禁止。
- DebugLoop自動実行禁止。
- DeepResearch/Web job起動禁止。
- Task/Agent API追加禁止。
- 任意コマンド実行追加禁止。
- 既存Lumen / Echo / Nexus破壊禁止。


## Completed: PR-ATLAS-PIPE-16: Integrate real Planner bridge into Atlas PlanPool creation

- Add AtlasPlannerBridge and schema as an internal bridge from existing TaskPlanningRunner output to AtlasPlanPool.
- Extend POST /api/atlas/plan-pools with planner_mode and requirement_mode while keeping plan_payload compatibility.
- Use real planner only when an app-provided LLM JSON function is available; otherwise continue with fallback PlanPool plus warnings.
- Preserve waiting_for_clarification as a non-error response shape for Details/JSON display.
- Do not add Task/Agent APIs or execute safe_apply/TestCommand/DebugLoop/DeepResearch.

## Completed: PR-ATLAS-PIPE-17: Pipeline execution orchestration polish / approval-aware continuation

- Make pipeline orchestration and continuation handling consistent for approval_required, waiting_for_clarification, stale recovery, and next-action prompts.
- Keep safe_apply automatic execution out of scope.

## Completed: PR-ATLAS-PIPE-18: Planner LLM function wiring / model backend connection

- Wire AtlasPlannerBridge llm_json_fn to the existing model backend while preserving fallback behavior.
- Keep execution controls and Task/Agent APIs out of scope.


## PR-ATLAS-PIPE-17: Polish Atlas Pipeline orchestration and approval-aware continuation

- Status: completed
- Adds AtlasOrchestrationSummary as a shared API/UI/Continuation helper for phase, severity, next_action, and gate flags.
- Improves waiting_for_clarification, approval_required/paused, stale recovery, completed, failed, and blocked handling without adding execution controls.
- Keeps safe_apply/TestCommandRunner/DebugLoopRunner/DeepResearch execution UI/API disabled.

## PR-ATLAS-PIPE-18: Planner LLM function wiring / model backend connection

- Status: completed
- Safely wire AtlasPlannerBridge llm_json_fn to the existing model backend so real Planner can run in real environments.
- Preserve fallback PlanPool behavior when model wiring is unavailable or planner output fails validation.
- Do not add automatic safe_apply, TestCommandRunner, DebugLoopRunner, DeepResearch/Web execution, or Task/Agent APIs.

- Current / Next implementation target: PR-ATLAS-PIPE-19 Planner clarification answer flow / Requirement refinement UI。


## PR-ATLAS-PIPE-17: completed

実装・merge済み。

## PR-ATLAS-PIPE-18: completed

実装・merge済み。

## PR-ATLAS-PIPE-19: Current / Next implementation target

### 範囲

- waiting_for_clarification時のquestionsをUIで表示
- 回答入力を受ける
- 既存RequirementDefinition / Planner bridgeへ回答を渡せる薄いschema/APIを追加
- 回答後に再Planningできる
- fallback安全継続
- safe_apply/TestCommand/DebugLoop/DeepResearchは実行しない
