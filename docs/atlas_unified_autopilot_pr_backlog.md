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

- Approval未取得の変更が適用されない。
- Approval stateが保存される。
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

- low-riskかつ承認済みのPlanItemのみsafe_applyできる。
- high-riskはdry_runまたはapproval待ちになる。
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

- allowlistされたtest commandのみ実行される。
- 非allowlist commandは拒否される。
- Testsがpassする。

### 変更禁止範囲

- 任意run_command実行禁止。
- delete自動実行禁止。
- UI変更禁止。

## PR-ATLAS-PIPE-9: DebugLoopRunner

### 目的

失敗した検証に対してmax retryつきのdebug loopを追加する。

### 主な変更

- DebugLoopRunnerを追加する。
- max retry、stop condition、failure summaryを追加する。
- TestCommandRunnerと連携する。

### 完了条件

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

- Outcomeが保存される。
- 保存失敗がPipeline全体の不要なhard failureにならない。
- Testsがpassする。

### 変更禁止範囲

- Nexus既存data破壊禁止。
- UI変更禁止。
- API破壊禁止。

## PR-ATLAS-PIPE-13: Atlas API統合

### 目的

Planner、Plan Pool、Autopilot PipelineをAtlas APIへ統合する。

### 主な変更

- Atlas API endpointを追加または拡張する。
- Task / Agent APIではなくAtlas APIとして提供する。
- Approval操作をAtlas APIへ統合する。

### 完了条件

- Atlas APIからPlan PoolとAutopilot dry_runを操作できる。
- Task / Agent APIが増えていない。
- API contract testsがpassする。

### 変更禁止範囲

- Standalone Task API追加禁止。
- Standalone Agent API追加禁止。
- 既存Atlas / Lumen / Echo / Nexus API破壊禁止。

## PR-ATLAS-PIPE-14: Atlas UI統合

### 目的

Plan Pool、approval、dry_run結果をAtlas UIに統合する。

### 主な変更

- Atlas UI内にPlan Pool viewを追加する。
- Approval controlsを追加する。
- Pipeline run log / final report表示を追加する。
- iPhone Safariで横崩れしないresponsive layoutにする。

### 完了条件

- Atlas UIからPlan PoolとAutopilot状態を確認できる。
- iPhone Safari相当の幅で横崩れしない。
- UI contract testsがpassする。

### 変更禁止範囲

- Standalone Task page追加禁止。
- Standalone Agent page追加禁止。
- 既存Lumen / Echo / Nexus UI破壊禁止。

## PR-ATLAS-PIPE-15: チャット継続運用の自動化

### 目的

長いChatGPTチャットから新しいチャットへ移っても、checkpointを貼るだけで再開できる運用を強化する。

### 主な変更

- Checkpoint更新手順を整備する。
- Completed PRs / Current PR / Next PRの更新ルールを追加する。
- BacklogとADRの同期確認を追加する。

### 完了条件

- 新チャットでcheckpointから作業再開できる。
- PRごとにcheckpoint更新が確認される。
- Contract testsがpassする。

### 変更禁止範囲

- runtime変更禁止。
- UI変更禁止。
- API変更禁止。
- 既存Atlas / Lumen / Echo / Nexus挙動変更禁止。
