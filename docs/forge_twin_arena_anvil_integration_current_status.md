# Forge / Twin / Arena / Anvil 統合改修 — Phase 0 現状棚卸し

作成日: 2026-06-21
対象指示書: 「KasaneCore Atlas — Forge / Twin / Arena / Anvil 統合改修 指示書」+「追加詳細指示: Weak LLM Reinforcement / Method Interface / Fallback Pipeline」

このドキュメントは Phase 0（現状棚卸し）の成果物。実装を始める前に、指示書が前提とする機能の「実装済み / スタブ / 設計のみ / 未接続 / 欠落」を実コードに照らして確定する。

---

## 0. 結論サマリ

指示書は「土台はあるが Method 層が足りない」という前提だが、実コードはそれより成熟している。

- **既に堅牢に存在**: ForgeRoute / RouteMatrix / ExecutionPolicySelector / TwinInjectionLevel / InstructionStyle / ModelCapabilityMode / ArenaRunner（非適用・raw保存）/ EvalPacks（unavailable≠passed を厳守）/ CapabilityScorer / ProfileStore / ProviderRegistry / local_openai_compatible(llama.cpp:8080) + LM Studio(:1234) catalog / OpenRouter / decomposition（**ただしファイルサイズ用**）。
- **完全に欠落（この改修の中核）**: `MethodVariant` / `MethodAdapter` / `MethodRegistry` / `MethodPipeline` / `MethodChain` / `FallbackStep` / `MethodResult` / `MethodRouter`。fallback graph、Arena radar、method別評価軸も無い。
- **拡張が必要**: `ExecutionPolicy` / `ForgeExecutionRequest` / `ForgeExecutionResult` / `ArenaCandidate` / `CandidateScore` に method/fallback/radar フィールドが無い（strict schema = `extra="forbid"` のため、正式追加しないと拒否される）。
- **評価軸**: capability dimension は現在 **8軸のみ**（impact_analysis, contract_preservation, test_generation, stale_test_judgment, flag_reasoning, repair_discipline, evidence_discipline, large_file_editing）。指示書が要求する `structured_output_fidelity` / `edit_intent_quality` / `anchor_selection_quality` / `abstraction_tolerance` / `patch_protocol_fidelity` / `fallback_recovery` などは欠落。
- **API**: `/api/forge/evaluation/*`（cases/run/rerun/optimize/model-profile）は**未実装**。`/api/forge/twin/*` facade も未実装（twin_control.py に別系統で存在）。Arena run/leaderboard/loadouts/cutover などは実装済み。
- **Real LLM 評価**: `twin_control_plane/real_llm_eval.py` が存在。Anvil 実起動 gate は未確立。

---

## 1. 命名衝突 注意（重要）

`agent/model_forge/decomposition_policy.py` は既に存在するが、**意味が指示書の `DecompositionPolicy` と異なる**。

- 既存: `DecompositionPolicy(tier, max_file_lines, prefer_split, max_source_files, rationale)` — **ファイル分割サイズ**のポリシー（frontier/standard/weak の3 tier）。`derive_decomposition_policy()` / `resolve_size_tier()` で planner プロンプトに反映済み。
- 指示書: `DecompositionPolicy = none|light|narrow_slice|micro_patch_only|one_anchor_at_a_time|...` という**タスク分解戦略の enum**。

→ 同名で衝突する。新規は `TaskDecompositionPolicy`（enum）など別名にするか、既存を `FileSizingPolicy` へリネームして整理する。**置き換え禁止**：既存は planner に production 接続済み。

---

## 2. コンポーネント分類

凡例: `production_connected` / `shadow_connected` / `component_complete` / `contract_present` / `scaffold_only` / `missing` / `risky_to_delete`

### 2.1 Forge core（agent/model_forge/）

| ファイル | 機能 | 分類 | 備考 |
|---|---|---|---|
| route_taxonomy.py | ForgeRoute(11種) | production_connected | DETERMINISTIC..PORTAL_REPLAY_REPAIR |
| route_matrix.py | ChangeClass→safe候補→route選択 | production_connected | 安全上位権限。MethodRouterはこれを上書きしない |
| route_fitness.py | benchmark嗜好でsafe候補を再順位 | production_connected | `best_route()` |
| execution_policy.py | ExecutionPolicySelector | production_connected | route/injection/style/gates決定。**method層なし** |
| schema.py | Forge DTO群（strict） | production_connected | method/radar/fallbackフィールド欠落 |
| arena_runner.py | 非適用でmodel×route実行+raw保存 | component_complete | adoption_state=not_applied固定。method metadata無し |
| eval_packs.py | capability 8軸の機械採点 | production_connected | unavailable≠passed厳守。**method/abstraction軸なし** |
| capability_scoring.py | pack結果→ProfileStore→ModelCapabilityProfile | production_connected | WEAKNESS_THRESHOLD=0.55 |
| decomposition_policy.py | **ファイルサイズ**ポリシー | production_connected | ⚠ 命名衝突（§1） |
| candidate_evaluator.py | EvaluatorOutcome(passed/failed/unavailable) | production_connected | |
| loadouts.py | Loadout保存/適用 | component_complete | role/method preference保存は未対応想定 |
| provider_registry.py / provider_base.py | プロバイダ抽象 | production_connected | |
| providers/local_openai_compatible.py | llama.cpp:8080 / LM Studio:1234 | component_complete | /v1/models catalog |
| providers/openrouter_*.py | OpenRouter catalog/client | component_complete | env名のみ保存、local_onlyブロック |
| cutover.py / shadow.py / retirement.py | active化の安全ゲート | production_connected | active化はここを通す |
| profile_store.py | append-only versioned profile | production_connected | |

### 2.2 Twin Control Plane（agent/twin_control_plane/）

| ファイル | 機能 | 分類 |
|---|---|---|
| contracts.py | ExecutionPolicy / TwinBrief / InstructionStyle / TwinInjectionLevel / GitPolicy / default_hard_constraints | production_connected（**method拡張必要**） |
| real_llm_eval.py | 実LLM評価 | component_complete |
| instruction_compiler.py | 指示コンパイル | component_complete |
| twin_brief.py / blast_map.py / contract_sentinel.py / twinproof.py / proof_ledger.py | 注入・ゲート・証跡 | production_connected |
| 他多数（repair/triage/failure系） | 既存triage/repair資産 | production_connected（削除禁止） |

### 2.3 API（app/api/）

| 既存ルート（forge.py） | 状態 |
|---|---|
| status / providers / models / settings / local-catalog / openrouter/catalog | ✅ |
| profiles / leaderboard / presets | ✅ |
| arena/run / arena/runs/{id} / arena/candidates/{id}/proposal-draft | ✅ |
| stage-policy / route-policy / loadouts / loadouts/{id}/apply | ✅ |
| portal-evidence / cutover / capsule/* | ✅ |
| **evaluation/cases / run / rerun / optimize / model-profile** | ❌ missing |
| **twin/settings / twin/profiles / twin/inspect/context / twin/inspect/impact** | ❌ missing（facade） |

twin_control.py: `/settings` `/profiles` `/evaluate` `/token-probe` は存在（Forge facade化が指示）。project_twin.py 別途存在（read-only inspector の再利用元）。

### 2.4 UI（web/js/）

| ファイル | 状態 |
|---|---|
| forge.js（1226行） | Forge UI存在。Benchmark/Arena/Loadouts導線あり。**radar / method comparison / fallback graph なし** |
| project_twin_panel.js | Project Twin独立パネル（→Advanced統合 or 非表示が指示） |
| ui.html | 単一HTML（memory: ui.html がsource of truth、ui/index.htmlはgitignore） |

---

## 3. 欠落リスト（新規実装が必要）

中核（追加詳細指示の3層）:
1. `agent/model_forge/method_taxonomy.py` — `MethodVariant` enum
2. `agent/model_forge/method_contracts.py` — `MethodRequest` / `MethodResult` / `MethodAdapter`(Protocol) / `MethodRegistry` / `FallbackStep` / `MethodChain` / `MethodPipelineResult`
3. `agent/model_forge/method_pipeline.py` — `MethodPipeline`（primary→fallback、trigger判定、hard_fail）
4. `agent/model_forge/method_router.py` — `MethodRouter`（profile→MethodChain/abstraction/decomposition/context/verification）
5. adapters: StructuredPatchJson / PatchDslJson / EditIntentList / AnchoredEditBlock / UnifiedDiff / ReviewOnly / RepairCompass / DeterministicTextPatch
6. deterministic compiler（edit_intent_list → Safe Apply patch）

評価軸の追加（method/abstraction/safety系 約20軸）、評価ケース（output_protocol / patch_construction / abstraction / fallback / weak LLM / frontier）。

API: `/api/forge/evaluation/*`、`/api/forge/twin/*` facade。

UI: Arena radar（Capability/Method/Safety/Speed/All）、fallback graph、method comparison、policy recommendation drawer、Advanced への Twin Settings + read-only Inspector 統合。

Anvil 実起動評価 gate（acceptance条件）。

---

## 4. 削除禁止 / risky_to_delete

- Project Twin の read-only inspection（project_twin.py、project_twin_panel.js の閲覧系）— 非表示化は可、機能削除は不可。Advanced の Twin Inspector として再利用。
- `decomposition_policy.py`（ファイルサイズ）— planner production接続済み。
- RouteMatrix / cutover / shadow / 各種 gate — 安全境界。
- twin_control_plane の repair/triage/failure 資産群。
- ProfileStore の既存 profile（append-only、上書き禁止）。

---

## 5. 既存が守っている安全不変条件（壊さない）

- `extra="forbid"` strict schema（拡張は正式フィールド追加で）。
- `unavailable` は score 平均に混ぜない・pass にしない（eval_packs / candidate_evaluator / profile_store 全てで一貫）。
- Arena は非適用・raw保存のみ・adoption_state=not_applied 固定。
- `default_hard_constraints()`: Safe Apply必須 / remote publish承認必須 / test・gate弱体化禁止 / stale test自動削除禁止。
- GitPolicy: remote publication/mutation は承認必須。

---

## 6. 推奨実装順序（指示書 Phase + 追加 Phase A–G の統合）

1. **Phase 1 + A（schema/DTO + method contracts）** — 最優先・低リスク。`MethodVariant`、method_contracts、ExecutionPolicy/ForgeExecution*/Arena* の後方互換拡張、`schema_version` migration。
2. **Phase B（adapters）+ deterministic compiler**。
3. **Phase 5/C（MethodRouter + MethodPipeline）** + ExecutionPolicySelector 統合（safe候補内での method選択のみ。route override しない）。
4. **Phase 2/D（評価ケース + 新dimension）**。
5. **Phase 3/E（evaluation API）+ twin facade**。
6. **Phase 4（real LLM runner 接続）**。
7. **Phase 6（optimizer / role assignment / loadout）**。
8. **Phase 7/F（UI: radar / fallback graph / method comparison / Advanced統合）**。
9. **Phase 8（execution integration: shadow→明示確認後active）**。
10. **Phase 9/G（tests + Anvil real eval gate）**。
11. **Phase 10（docs / rollback / proof levels）**。

各 Phase は §23 の完了報告フォーマットと proof level で報告。focused tests のみで `acceptance_complete` としない。Anvil 未評価なら `anvil_real_eval_pending`。

---

## 7. Proof level（このドキュメント）

`contract_present` — 実コードを読んで分類した棚卸し。コード変更なし。次フェーズ（Phase 1+A）でDTO追加から着手する。

---

## 8. PR1 Method 中核契約 完了証跡

Completed package: PR1 `feat/forge-method-contracts`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/method_taxonomy.py`, `agent/model_forge/method_contracts.py`, `tests/test_forge_method_contracts.py`, integration plan/status docs
Behavior implemented: 11 MethodVariant values, strict Method DTOs, MethodAdapter Protocol, MethodRegistry dispatch, fallback chain/result contracts
Focused tests: `python -m pytest -q tests/test_forge_method_contracts.py` -> 9 passed
Syntax checks: `python -m py_compile agent/model_forge/method_taxonomy.py agent/model_forge/method_contracts.py tests/test_forge_method_contracts.py` -> passed
Affected tests: `python -m pytest -q tests/test_forge_api.py tests/test_execution_policy_route_preference.py` -> 25 passed
Real model evidence: localhost:8080 `/v1/models` reported `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`; contract review response `chatcmpl-owUbo9qOtwR2wgv0yX72znbn85D6Jr1i` -> `VERDICT: PASS` (204 tokens)
Atlas UI evidence: unavailable; PR1 is a pure contract slice with no UI change
Project Intelligence evidence: unavailable; PR1 does not consume Project Intelligence
Runtime/Portal evidence: unavailable; PR1 has no runtime or Portal wiring
Unavailable checks: repository-local `venv_sys` was absent; equivalent system Python 3.11.9 with pytest 9.0.3 and pydantic 2.13.4 was used
Safety invariants: `unavailable` remains distinct from `passed`; strict `extra="forbid"` inherited from ForgeModel; no Proposal/Safe Apply/Verification bypass or route override introduced
Remaining gaps: schema integration, adapters, pipeline, router, evaluation/runtime/UI integration and Anvil acceptance remain pending
Next package: PR2 `feat/forge-method-schema-ext`
Blocker: none
Proof level: `method_contract_present`

---

## 9. PR2 Method schema 後方互換拡張 完了証跡

Completed package: PR2 `feat/forge-method-schema-ext`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/method_policy.py`, `agent/model_forge/schema.py`, `agent/model_forge/__init__.py`, `agent/twin_control_plane/contracts.py`, `tests/test_forge_method_schema_extension.py`, integration plan/status docs
Behavior implemented: method/fallback policy fields on ExecutionPolicy and Forge execution DTOs; Arena method/fallback/radar fields; ModelOptimizationProfile and RoleAssignment; separate task-decomposition and method policy enums
Focused tests: `python -m pytest -q tests/test_forge_method_schema_extension.py tests/test_model_forge_schema.py tests/test_forge_method_contracts.py` -> 28 passed
Syntax checks: `python -m py_compile agent/model_forge/method_policy.py agent/model_forge/schema.py agent/twin_control_plane/contracts.py agent/model_forge/__init__.py tests/test_forge_method_schema_extension.py` -> passed
Affected tests: `python -m pytest -q tests/test_execution_policy_route_preference.py tests/test_forge_api.py tests/test_twin_forge_git_steward_initial.py` -> 31 passed
Real model evidence: localhost:8080 model `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`; schema compatibility review response `chatcmpl-8hbRsrg5APZSU9bkRRDg1KcufvarndOu` -> `VERDICT: PASS` (395 tokens)
Atlas UI evidence: unavailable; PR2 has no UI change
Project Intelligence evidence: unavailable; PR2 adds contracts only
Runtime/Portal evidence: unavailable; no execution wiring was added
Unavailable checks: repository-local `venv_sys` remains absent; system Python 3.11.9 was used
Safety invariants: old `forge.v1` payloads remain readable; unknown fields remain rejected; radar `None` remains distinct from numeric zero; existing file-size decomposition policy was untouched; no route or Safe Apply authority changed
Remaining gaps: adapters, pipeline, router, evaluation/runtime/UI integration and Anvil acceptance remain pending
Next package: PR3 `feat/forge-adapters-structured`
Blocker: none
Proof level: `method_contract_present`

---

## 10. PR3 構造化 Method adapters 完了証跡

Completed package: PR3 `feat/forge-adapters-structured`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/method_artifacts.py`, `agent/model_forge/structured_adapters.py`, `tests/test_forge_structured_adapters.py`, integration plan/status docs
Behavior implemented: StructuredPatchJson, PatchDslJson, EditIntentList adapters; content-addressed artifact refs; deterministic normalization to Atlas `file_changes[]`; registry builder; unsafe path and forbidden action blocking
Focused tests: `python -m pytest -q tests/test_forge_structured_adapters.py tests/test_forge_method_contracts.py tests/test_forge_method_schema_extension.py` -> 27 passed
Syntax checks: `python -m py_compile agent/model_forge/method_artifacts.py agent/model_forge/structured_adapters.py tests/test_forge_structured_adapters.py` -> passed
Affected tests: `python -m pytest -q tests/test_atlas_file_safe_apply_executor.py tests/test_atlas_edit_primitives.py tests/test_forge_api.py` -> 60 passed
Real model evidence: localhost:8080 `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`, response `chatcmpl-v2ZcNxhAlwtNktwKyF5oaSY1GWsc1y6m` (215 tokens), produced an anchored `edit_intent_list`; adapter parse/compile/verify returned passed and contract_valid with an `atlas_file_changes.v1` artifact
Atlas UI evidence: unavailable; PR3 has no UI change
Project Intelligence evidence: unavailable; PR3 prompt accepts refs but does not wire Project Intelligence
Runtime/Portal evidence: unavailable; adapter component is not connected to runtime in this PR
Unavailable checks: `tests/test_atlas_patch_proposal_to_safe_apply_e2e.py` has 4 stale failures because it expects synchronous `/api/atlas/plan-pools` response field `plan_pool`, while the current endpoint returns queued `{pool_id,status}`; no stale test was removed or weakened
Safety invariants: compilation never applies files; generated artifacts require approval and keep `safe_apply_ready=false`; unsafe/protected paths and delete/command actions are blocked; `unavailable` is not converted to passed
Remaining gaps: remaining adapters, pipeline, router, evaluation/runtime/UI integration and Anvil acceptance remain pending
Next package: PR4 `feat/forge-adapters-anchored`
Blocker: none
Proof level: `method_contract_present`

---

## 11. PR4 残り Method adapters 完了証跡

Completed package: PR4 `feat/forge-adapters-anchored`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/remaining_adapters.py`, `tests/test_forge_remaining_adapters.py`, integration plan/status docs
Behavior implemented: anchored edit block, multi-file unified diff, deterministic text replacement, review-only, and RepairCompass adapters; combined registry for all implemented adapters
Focused tests: `python -m pytest -q tests/test_forge_remaining_adapters.py tests/test_forge_structured_adapters.py tests/test_forge_method_contracts.py` -> 36 passed
Syntax checks: `python -m py_compile agent/model_forge/remaining_adapters.py tests/test_forge_remaining_adapters.py` -> passed
Affected tests: `python -m pytest -q tests/test_atlas_file_safe_apply_executor.py tests/test_atlas_edit_primitives.py tests/test_forge_api.py` -> 60 passed
Real model evidence: localhost:8080 `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`, response `chatcmpl-2eWEUks1G7FkadoHju29DOrSvid1Ws5h` (202 tokens), produced a valid AnchoredEditBlock; adapter parse/compile/verify returned passed and contract_valid
Atlas UI evidence: unavailable; PR4 has no UI change
Project Intelligence evidence: unavailable; PR4 is an adapter component slice
Runtime/Portal evidence: unavailable; adapters are not runtime-connected in this PR
Unavailable checks: repository-local `venv_sys` remains absent; system Python 3.11.9 was used
Safety invariants: patch-producing adapters retain approval_required and `safe_apply_ready=false`; review/repair adapters never produce a patch; unified diff deletion and invalid anchors fail closed
Remaining gaps: pipeline, router, evaluation/runtime/UI integration and Anvil acceptance remain pending
Next package: PR5 `feat/forge-method-pipeline`
Blocker: none
Proof level: `method_contract_present`

---

## 12. PR5 MethodPipeline 完了証跡

Completed package: PR5 `feat/forge-method-pipeline`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/method_pipeline.py`, `tests/test_forge_method_pipeline.py`, integration plan/status docs
Behavior implemented: primary-to-fallback execution, trigger matching, bounded attempts, unavailable classification, attempt/evidence aggregation, authority bypass hard-fail, strict fallback request modification allow-list
Focused tests: `python -m pytest -q tests/test_forge_method_pipeline.py tests/test_forge_remaining_adapters.py tests/test_forge_structured_adapters.py` -> 34 passed
Syntax checks: `python -m py_compile agent/model_forge/method_pipeline.py tests/test_forge_method_pipeline.py` -> passed
Affected tests: `python -m pytest -q tests/test_forge_api.py tests/test_execution_policy_route_preference.py tests/test_atlas_file_safe_apply_executor.py` -> 49 passed
Real model evidence: forced `schema_invalid` primary followed by localhost:8080 `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf` fallback response `chatcmpl-q3YNlOI0NpBNLspTbUTpjqyQ6QcDvJUQ`; final status passed with selected method `edit_intent_list` and two recorded attempts
Atlas UI evidence: unavailable; PR5 has no UI change
Project Intelligence evidence: unavailable; pipeline is not connected to Project Intelligence in this PR
Runtime/Portal evidence: unavailable; invoker is injected and production runtime connection remains pending
Unavailable checks: fallback evidence uses an intentionally forced schema failure, not a naturally occurring real-model failure; natural fallback proof remains pending for PR16
Safety invariants: provider unavailable is never passed; Safe Apply readiness without Proposal is blocked; fallback cannot modify route/provider/ref authority fields; no file is applied
Remaining gaps: router, evaluation/runtime/UI integration, natural real-model fallback and Anvil acceptance remain pending
Next package: PR6 `feat/forge-method-router`
Blocker: none
Proof level: `method_pipeline_component_complete`

---

## 13. PR6 MethodRouter + Policy 統合 完了証跡

Completed package: PR6 `feat/forge-method-router`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/method_router.py`, `agent/model_forge/execution_policy.py`, `tests/test_forge_method_router.py`, integration plan/status docs
Behavior implemented: profile/route/change-class/failure-aware MethodChain selection and policy fields; weak structured output -> edit intent; weak large editing -> anchored; repeated failures -> review-only
Focused tests: `python -m pytest -q tests/test_forge_method_router.py tests/test_forge_method_pipeline.py tests/test_execution_policy_route_preference.py tests/test_twin_forge_git_steward_initial.py` -> 23 passed
Syntax checks: `python -m py_compile agent/model_forge/method_router.py agent/model_forge/execution_policy.py tests/test_forge_method_router.py` -> passed
Affected tests: `python -m pytest -q tests/test_forge_api.py tests/test_model_forge_schema.py tests/test_twin_control_plane_active_integration.py tests/test_twin_control_plane_shadow_integration.py` -> 50 passed
Real model evidence: localhost:8080 response `chatcmpl-GSjGqYwEHpQMIIkvkitpNn5qFK3MhH1t`; weak structured profile selected `edit_intent_list` while preserving route `patch_dsl`, then real output passed pipeline contract with `safe_apply_ready=false`
Atlas UI evidence: unavailable; PR6 has no UI change
Project Intelligence evidence: unavailable; context package mode is selected but Project Intelligence payload injection is not connected here
Runtime/Portal evidence: unavailable; ExecutionPolicy carries shadow method metadata but runtime invocation remains pending
Unavailable checks: natural fallback and Anvil runtime evidence remain pending
Safety invariants: RouteMatrix result is never overridden by MethodRouter; critical route remains critical; legacy profiles without new dimensions are not misclassified; review-only produces no patch
Remaining gaps: evaluation dimensions/API, real runner, optimizer/loadout, UI, runtime shadow integration and Anvil acceptance remain pending
Next package: PR7 `feat/forge-eval-dimensions`
Blocker: none
Proof level: `method_router_shadow_connected`

---

## 14. PR7 Method 評価軸 + cases 完了証跡

Completed package: PR7 `feat/forge-eval-dimensions`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/eval_packs.py`, `tests/test_forge_method_eval_dimensions.py`, integration plan/status docs
Behavior implemented: eight method/abstraction/fallback/scope/context capability dimensions with normal and adversarial cases; existing weighted scoring and unavailable exclusion reused
Focused tests: `python -m pytest -q tests/test_forge_method_eval_dimensions.py tests/test_model_forge_capability_eval_packs.py tests/test_forge_method_router.py` -> 19 passed
Syntax checks: `python -m py_compile agent/model_forge/eval_packs.py tests/test_forge_method_eval_dimensions.py` -> passed
Affected tests: `python -m pytest -q tests/test_forge_api.py tests/test_model_forge_schema.py` -> 34 passed
Real model evidence: localhost:8080 response `chatcmpl-fujCkdng5mh309rQTEnNHdFKghAY7XFg` for case `sof_schema`; JSON parsed, but model used `type=create` instead of the requested Atlas action field and returned `ok.` instead of exact `ok`, so the single semantic fidelity case is recorded failed
Atlas UI evidence: unavailable; PR7 has no UI change
Project Intelligence evidence: unavailable; evaluation cases are pure data and not project-connected
Runtime/Portal evidence: unavailable; evaluation runner/API are not added in this PR
Unavailable checks: full method dimension run and authoritative score remain pending; one live case is not a dimension acceptance result
Safety invariants: unavailable remains `score=None` and contributes no pass/mean weight; adversarial failure carries double weight; parse success is not treated as semantic evaluation success
Remaining gaps: evaluation API/runner, real runner, optimizer/loadout, UI, runtime shadow integration and Anvil acceptance remain pending
Next package: PR8 `feat/forge-evaluation-api`
Blocker: none
Proof level: `method_router_shadow_connected`

---

## 15. PR8 Evaluation API 完了証跡

Completed package: PR8 `feat/forge-evaluation-api`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/evaluation_service.py`, `agent/model_forge/forge_service.py`, `app/api/forge.py`, `tests/test_forge_evaluation_api.py`, integration plan/status docs
Behavior implemented: cases/run/rerun/optimize-preview/model-profile endpoints; strict requests; mechanical score persistence; append-only profile evidence; unavailable no-score behavior
Focused tests: `python -m pytest -q tests/test_forge_evaluation_api.py tests/test_forge_method_eval_dimensions.py tests/test_model_forge_capability_eval_packs.py` -> 18 passed
Syntax checks: `python -m py_compile agent/model_forge/evaluation_service.py agent/model_forge/forge_service.py app/api/forge.py tests/test_forge_evaluation_api.py` -> passed
Affected tests: `python -m pytest -q tests/test_forge_api.py tests/test_model_forge_schema.py tests/test_forge_method_router.py` -> 40 passed
Real model evidence: PR7 live response `chatcmpl-fujCkdng5mh309rQTEnNHdFKghAY7XFg` was submitted as failed case evidence; API run `forge_eval_877db954dcd1` produced score 0.0/failed, persisted the weakness, and returned a `preview_not_applied` edit-intent recommendation
Atlas UI evidence: unavailable; PR8 has no UI change
Project Intelligence evidence: unavailable; evaluation API does not inspect projects
Runtime/Portal evidence: unavailable; real provider runner is PR10 and this API accepts mechanical CaseResult input only
Unavailable checks: full live evaluation run remains pending; optimization is preview only and does not create/apply a loadout
Safety invariants: unavailable-only runs create no scored profile; weak feedback is not used; preview is not applied; strict bodies reject hidden apply fields
Remaining gaps: Twin facade, real runner, optimizer/loadout, UI, runtime shadow integration and Anvil acceptance remain pending
Next package: PR9 `feat/forge-twin-facade-api`
Blocker: none
Proof level: `method_router_shadow_connected`

---

## 16. PR9 Twin facade API 完了証跡

Completed package: PR9 `feat/forge-twin-facade-api`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `app/api/forge.py`, `tests/test_forge_twin_facade_api.py`, integration plan/status docs
Behavior implemented: Forge-prefixed Twin settings/profiles facade and strict read-only Project Twin context/impact inspectors using existing stores and brokers
Focused tests: `python -m pytest -q tests/test_forge_twin_facade_api.py tests/test_project_twin_api.py` -> 11 passed
Syntax checks: `python -m py_compile app/api/forge.py tests/test_forge_twin_facade_api.py` -> passed
Affected tests: `python -m pytest -q tests/test_forge_api.py tests/test_forge_evaluation_api.py tests/test_twin_forge_git_steward_initial.py` -> 32 passed
Real model evidence: localhost:8080 advisory review response `chatcmpl-YrjB63J7F1sWONJcPrRTExlfmMvAL6Tx` -> `VERDICT: PASS` after clarifying that reversible settings update is required while inspect endpoints remain read-only
Atlas UI evidence: unavailable; Advanced UI integration is PR14
Project Intelligence evidence: in-memory Project Twin deterministic graph exercised through facade; context and reverse impact returned existing verified refs without mutation
Runtime/Portal evidence: unavailable; facade does not execute runtime or Portal operations
Unavailable checks: live project database inspection was not required; deterministic injected store was used
Safety invariants: inspect endpoints expose no apply/execute/mutate route; strict bodies reject hidden apply fields; settings delegates only to existing reversible process-scoped configuration; no source mutation authority added
Remaining gaps: real runner, optimizer/loadout, UI, runtime shadow integration and Anvil acceptance remain pending
Next package: PR10 `feat/forge-real-llm-runner`
Blocker: none
Proof level: `method_router_shadow_connected`

---

## 17. PR10 Real LLM runner 完了証跡

Completed package: PR10 `feat/forge-real-llm-runner`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/real_method_runner.py`, `agent/model_forge/evaluation_service.py`, `agent/model_forge/forge_service.py`, `app/api/forge.py`, real-runner/evaluation tests, integration plan/status docs
Behavior implemented: OpenAI-compatible live Method evaluation for Anvil/local/LM Studio/OpenRouter; durable raw/output metadata; token/latency/response ID/base URL evidence; run-live API; unavailable and Local Only gates
Focused tests: `python -m pytest -q tests/test_forge_real_method_runner.py tests/test_forge_evaluation_api.py tests/test_forge_method_pipeline.py` -> 17 passed
Syntax checks: focused `py_compile` for runner/evaluation/service/API/tests -> passed
Affected tests: `python -m pytest -q tests/test_forge_api.py tests/test_model_forge_local_openai.py tests/test_model_forge_openrouter_client.py tests/test_model_forge_provider_policy.py tests/test_forge_method_eval_dimensions.py` -> 49 passed
Real model evidence: localhost:8080, model `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`, provider label `anvil`, evaluation run `forge_eval_ad0e5883f8ce`; two edit-intent cases executed with durable evidence and both failed contract compilation (`content_missing`, `file_changes_missing`), producing score 0.0/failed rather than a false pass
Atlas UI evidence: unavailable; PR10 has no UI change
Project Intelligence evidence: unavailable; real runner uses bounded synthetic evaluation targets, not project source
Runtime/Portal evidence: unavailable; provider execution is proven but Portal runtime is not involved
Unavailable checks: only four mechanically checkable method dimensions are live-enabled; semantic-only dimensions return unavailable; formal Anvil pass/fallback proof remains PR16
Safety invariants: external provider blocked in Local Only; missing credential/transport failure is unavailable; secrets are read from env and never persisted; no output is applied; failed model output remains failed
Remaining gaps: optimizer/loadout, UI, runtime shadow integration and formal Anvil/fallback acceptance remain pending
Next package: PR11 `feat/forge-optimizer-loadout`
Blocker: none
Proof level: `real_llm_evaluated`

---

## 18. PR11 Optimizer / Role / Loadout 完了証跡

Completed package: PR11 `feat/forge-optimizer-loadout`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/optimizer.py`, `agent/model_forge/loadouts.py`, evaluation/service/API integration, optimizer/loadout tests, integration plan/status docs
Behavior implemented: evidence-backed ModelOptimizationProfile, coder/reviewer RoleAssignments, method preference/fallback persistence in Loadout, non-applying optimize preview, existing gated apply marker integration
Focused tests: `python -m pytest -q tests/test_forge_optimizer_loadout.py tests/test_forge_evaluation_api.py tests/test_forge_method_router.py` -> 14 passed
Syntax checks: focused optimizer/loadout/evaluation/service/API `py_compile` -> passed
Affected tests: `python -m pytest -q tests/test_forge_api.py tests/test_forge_loadouts.py tests/test_forge_method_schema_extension.py` -> 32 passed
Real model evidence: profile derived from localhost:8080 run `forge_eval_ad0e5883f8ce` generated coder `edit_intent_list`, fallback `anchored_edit_block`, reviewer `review_only`, confidence 0.6, and a `preview_not_applied` loadout carrying the real run evidence ref
Atlas UI evidence: unavailable; loadout UI changes begin PR12
Project Intelligence evidence: unavailable; optimizer consumes Forge evidence profiles only
Runtime/Portal evidence: unavailable; generated loadout is not automatically applied
Unavailable checks: role fitness across multiple models remains limited by available evidence; single-model preview does not prove optimality
Safety invariants: optimizer never applies; save and apply remain separate existing APIs; risky stage overrides still require acknowledgement/cutover gates; reviewer assignment constructs no patch
Remaining gaps: UI radar/fallback/Advanced, runtime shadow integration and formal Anvil acceptance remain pending
Next package: PR12 `feat/forge-ui-radar`
Blocker: none
Proof level: `real_llm_evaluated`

---

## 19. PR12 Arena radar + candidate drawer 完了証跡

Completed package: PR12 `feat/forge-ui-radar`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `web/js/forge.js`, `web/css/app.css`, `tests/test_forge_ui_radar.py`, integration plan/status docs
Behavior implemented: candidate detail drawer, dependency-free SVG radar, Capability/Method/Safety/Speed/All filters, explicit unavailable labels and mobile sizing
Focused tests: `python -m pytest -q tests/test_forge_ui_radar.py tests/test_forge_arena_ui.py tests/test_forge_ui_shell.py` -> 11 passed
Syntax checks: Node evaluation through render tests -> passed
Affected tests: `python -m pytest -q tests/test_forge_api.py tests/test_forge_optimizer_loadout.py` -> 23 passed
Real model evidence: existing localhost:8080 evaluation profile/radar DTO fields are render inputs; PR12 performs no model call
Atlas UI evidence: Node DOM render confirms detail action, SVG/filter markup, zero score, unavailable label, and Safe Apply-only adoption text; in-app browser tooling unavailable in this session, so live visual layout evidence is unavailable
Project Intelligence evidence: unavailable; PR12 is Arena UI only
Runtime/Portal evidence: unavailable; UI does not execute runtime
Unavailable checks: interactive browser click/layout/mobile screenshot verification
Safety invariants: unavailable is labeled missing evidence rather than numeric zero; candidate detail adds no direct apply action; Proposal/Safe Apply/Verification wording remains
Remaining gaps: fallback graph/method comparison, Advanced Twin UI, runtime shadow integration and formal Anvil acceptance remain pending
Next package: PR13 `feat/forge-ui-fallback-graph`
Blocker: none
Proof level: `real_llm_evaluated`

---

## 20. PR13 fallback graph / method comparison 完了証跡

Completed package: PR13 `feat/forge-ui-fallback-graph`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `web/js/forge.js`, `web/css/app.css`, `tests/test_forge_ui_method_comparison.py`, integration plan/status docs
Behavior implemented: candidate drawer fallback graph with primary/configured/attempted states, Benchmark method comparison table, policy recommendation drawer with explicit advisory/non-applying status
Focused tests: `python -m pytest -q tests/test_forge_ui_method_comparison.py tests/test_forge_ui_radar.py tests/test_forge_arena_ui.py tests/test_forge_ui_shell.py` -> 15 passed
Syntax checks: Node evaluation through render tests and `git diff --check` -> passed
Affected tests: `python -m pytest -q tests/test_forge_api.py tests/test_forge_optimizer_loadout.py` -> 23 passed
Real model evidence: existing localhost:8080 evaluation candidate DTOs supply method/fallback/score fields; PR13 performs no model call
Atlas UI evidence: Node render confirms fallback states, comparison values, advisory status, Safe Apply gating, and policy action; in-app browser tooling unavailable, so live click/layout evidence is unavailable
Project Intelligence evidence: unavailable; PR13 is Forge UI only
Runtime/Portal evidence: unavailable; fallback graph is observational and executes no method
Unavailable checks: interactive browser drawer/mobile screenshot verification
Safety invariants: recommendation is `advisory_not_applied`; no routing mutation; fallback graph does not execute; Proposal/Safe Apply/Verification remain mandatory; unavailable fallback evidence is not presented as success
Remaining gaps: Advanced Twin UI, runtime shadow integration, and formal Anvil acceptance remain pending
Next package: PR14 `feat/forge-ui-advanced-twin`
Blocker: none
Proof level: `real_llm_evaluated`

---

## 21. PR14 Forge Advanced Twin 統合完了証跡

Completed package: PR14 `feat/forge-ui-advanced-twin`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `ui.html`, `web/js/forge.js`, `web/css/app.css`, `tests/test_forge_ui_advanced_twin.py`, `tests/test_forge_twin_panel_ui.py`, integration plan/status docs
Behavior implemented: Forge Advanced read-only Twin settings/profile snapshot, context slice and impact inspectors through PR9 facade, independent Twin subtab hidden while legacy panel implementation remains intact, responsive single-column mobile inspector
Focused tests: `python -m pytest -q tests/test_forge_ui_advanced_twin.py tests/test_forge_twin_panel_ui.py tests/test_forge_twin_facade_api.py tests/test_forge_ui_method_comparison.py tests/test_forge_ui_radar.py tests/test_forge_ui_shell.py` -> 22 passed
Syntax checks: Node evaluation through render tests and `git diff --check` -> passed
Affected tests: `python -m pytest -q tests/test_forge_api.py tests/test_twin_control_api.py tests/test_project_twin_analysis.py` -> 30 passed
Real model evidence: existing localhost:8080 model profile can be displayed; PR14 performs no model call
Atlas UI evidence: Node/static render confirms settings/profile snapshot, both inspector forms, no apply/execute endpoint, hidden independent tab, preserved legacy panel, and mobile one-column rule; live browser tooling unavailable
Project Intelligence evidence: facade-backed context and impact are read-only Project Twin evidence; no inferred item is promoted to verified by the UI
Runtime/Portal evidence: unavailable; inspector performs no runtime execution
Unavailable checks: interactive browser layout/click/mobile screenshot verification
Safety invariants: Twin inspector exposes no apply/execute action; settings are read-only in the consolidated UI; existing Project Twin inspection code is preserved; hidden navigation does not delete capability; evidence remains advisory
Remaining gaps: runtime shadow integration and formal Anvil acceptance remain pending
Next package: PR15 `feat/forge-execution-shadow`
Blocker: none
Proof level: `real_llm_evaluated`

---

## 22. PR15 Atlas execution shadow 統合完了証跡

Completed package: PR15 `feat/forge-execution-shadow`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/atlas_shadow.py`, execution bridge/service/stage defaults, Proof Ledger schema, `app/api/atlas_pipeline.py`, shadow integration tests, integration plan/status docs
Behavior implemented: plan/patch bridge and verification/repair API hooks record result digest/status, evidence-backed method policy, fallback chain and evaluation refs; per-phase local artifacts connect to idempotent `forge_shadow` Proof Ledger entries; Atlas output remains authoritative and unchanged
Focused tests: `python -m pytest -q tests/test_forge_atlas_execution_shadow.py tests/test_forge_execution_bridge.py tests/test_model_forge_stage_matrix.py tests/test_twin_proof_ledger_store.py tests/test_twin_control_plane_patch_impact_proof_ledger.py` -> 24 passed
Syntax checks: focused `py_compile` and `git diff --check` -> passed
Affected tests: verification/Safe Apply/self-correction/method suites -> 53 passed, 1 failed; failing `test_safe_apply_one_and_verify_success` was separately reproduced unchanged on detached `origin/main` because requirement coverage remains partial despite pytest passing, so it is a known baseline failure and not counted as passed
Real model evidence: localhost:8080 model `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`; `test_real_stage_shadow_four_stages` passed; patch_generation/test_generation/failure_classification/repair all legacy score 1.0 and Forge score 1.0, winner tie, regression false; Forge latencies 2719/2953/2688/2655 ms
Atlas UI evidence: unavailable; PR15 is backend integration
Project Intelligence evidence: evaluation refs and method policy are advisory inputs; missing profile records `model_evaluation_profile:unavailable` rather than passed
Runtime/Portal evidence: real local provider calls proven for four shadow stages; Portal is not involved
Unavailable checks: known baseline Atlas success-test assertion remains inconsistent with current requirement coverage gate; no active/cutover runtime test is performed because this PR is shadow-only
Safety invariants: result payload content is not persisted, only SHA-256 digest/status; `changes_production_routing=false`; `active_auto_enabled=false`; non-shadow stage creates no artifact; recorder failures cannot change legacy output; Proposal/Safe Apply/Verification authority remains
Remaining gaps: formal Anvil fallback evaluation and final acceptance remain pending
Next package: PR16 `feat/forge-anvil-real-eval`
Blocker: none
Proof level: `real_llm_evaluated` (`shadow_connected` acceptance also satisfied)

---

## 23. PR16 Anvil real-eval acceptance 完了証跡

Completed package: PR16 `feat/forge-anvil-real-eval`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/anvil_acceptance.py`, `tests/test_forge_anvil_acceptance.py`, integration plan/status docs
Behavior implemented: `check_anvil_ready` confirms the model is served at `/v1/models` (Anvil ready state after `/model/switch` -> `/model/status`); `make_live_invoker` drives `MethodPipeline` against the OpenAI-compatible `/v1/chat/completions`; `benchmark_scenarios` builds acceptance flows from the real Forge benchmark cases so any fallback is genuine, not forced; the runner persists a truthful report (readiness, per-attempt status/reasons, fallback_reasons, natural_fallback flags) and never applies a file or grants Safe Apply readiness. When the model is not served the run is recorded `anvil_real_eval_pending` and is not upgraded to passed.
Focused tests: `venv_sys/Scripts/python.exe -m pytest -q tests/test_forge_anvil_acceptance.py` -> 6 passed
Syntax checks: `py_compile agent/model_forge/anvil_acceptance.py tests/test_forge_anvil_acceptance.py` -> passed
Affected tests: `pytest -q tests/test_forge_anvil_acceptance.py tests/test_forge_real_method_runner.py tests/test_forge_method_pipeline.py tests/test_forge_evaluation_api.py` -> 23 passed
Real model evidence: localhost:8080 served `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`. Run `anvil_eval_2113a25c169c` over benchmark dimension `edit_intent_quality` produced a **natural** fallback chain on real output: `edit_intent_list` blocked (`content_missing` / `file_changes_missing`) -> `anchored_edit_block` failed (`anchor_not_found`) -> `review_only` passed, recovering without applying a file. `natural_fallback_observed=true`, `natural_fallback_recovered=true`. A control run with simple unambiguous goals (`anvil_eval_8b641ee43df7`) passed the primary methods on the first attempt with no fallback, recorded honestly as `anvil_real_eval_pending` — fallback is observed only when the model genuinely fails.
Atlas UI evidence: unavailable; PR16 is backend acceptance tooling with no UI change
Project Intelligence evidence: unavailable; PR16 does not consume Project Intelligence
Runtime/Portal evidence: real local provider calls proven across primary + fallback methods; Portal not involved
Unavailable checks: the KasaneCore app (Anvil control-plane HTTP surface `/models/db`, `/model/switch`, `/model/status`) was not running during this run; the model was already loaded and served directly on the 8080 backend, so readiness was confirmed via `/v1/models` and the `/model/switch` -> `/model/status` HTTP transitions were not exercised in this run
Safety invariants: no file applied; `safe_apply_ready` never set without a proposal (pipeline hard-fails `safe_apply_bypass`); `unavailable`/`pending` never upgraded to `passed`; RouteMatrix not overridden; remote publication gated by the item PR workflow
Remaining gaps: router fallback triggers do not yet cover the full real failure vocabulary (`content_missing` / `file_changes_missing`) — to be fixed in PR18 (MethodRouter v2); a dedicated natural-fallback pack across all failure modes is PR17; frontier verification of weak-LLM evaluations across all dimensions is PR21
Next package: PR17 `feat/forge-natural-fallback-pack`
Blocker: none
Proof level: `anvil_real_eval_passed` (natural fallback recovered on real model)

---

## 24. PR17 Natural fallback pack 完了証跡

Completed package: PR17 `feat/forge-natural-fallback-pack`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/natural_fallback_pack.py`, `tests/test_forge_natural_fallback_pack.py`, integration plan/status docs
Behavior implemented: a case per real failure mode (schema_invalid / content_missing / file_changes_missing / anchor_not_found / unsafe_target_path / provider_unavailable). Each sends a genuine prompt; the real model's failing output is classified by the mechanical adapters and `MethodPipeline` falls back naturally. A clean primary success is recorded as a safe outcome (failure simply not induced this run); an unreachable provider is recorded `unavailable` and never upgraded to passed. No file is applied.
Focused tests: `venv_sys/Scripts/python.exe -m pytest -q tests/test_forge_natural_fallback_pack.py` -> 5 passed
Syntax checks: `py_compile agent/model_forge/natural_fallback_pack.py tests/test_forge_natural_fallback_pack.py` -> passed
Affected tests: covered together with PR16 acceptance + pipeline suites (23 passed) on the merged base
Real model evidence: localhost:8080 `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`, run `fallback_pack_4fb0e81b8664`: 6/6 modes handled, proof `natural_fallback_real_eval_passed`. `file_changes_missing` / `anchor_not_found` / `unsafe_target_path` were genuinely induced and recovered through natural fallback to edit-intent or review-only; `provider_unavailable` surfaced `transport_error:URLError` -> final `unavailable` (not passed); `content_missing` was not induced because the model succeeded on the first attempt and was recorded honestly as a safe outcome.
Atlas UI evidence: unavailable; backend tooling
Project Intelligence evidence: unavailable
Runtime/Portal evidence: real local provider calls across all induced modes plus a deliberate unreachable-endpoint transport failure
Unavailable checks: `content_missing` could not be induced this run (model succeeded); `patch_apply_failure` is represented through the compile/verify failure reasons (content_missing/file_changes_missing/anchor_not_found) rather than a post-apply failure, because Safe Apply is never executed in evaluation
Safety invariants: no file applied; a passed terminal is always review-only (no patch); `unavailable` never upgraded to passed; RouteMatrix not overridden
Remaining gaps: the production MethodRouter still does not trigger fallback on content_missing / file_changes_missing (PR18); frontier verification of weak-LLM evaluations across all dimensions (PR21)
Next package: PR18 `feat/forge-method-router-v2`
Blocker: none
Proof level: `natural_fallback_real_eval_passed`

---

## 25. PR21 Frontier verification of weak-LLM evaluation 完了証跡

Completed package: PR21 `feat/forge-frontier-eval-verification` (brought forward at user request: "弱LLMの評価終わったら、フロンティアモデルで想定通りそもそも評価できるのか確認して欲しい")
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/frontier_verification.py`, `tests/test_forge_frontier_verification.py`, integration plan/status docs
Behavior implemented: `FrontierVerificationHarness` pairs each weak-LLM/mechanical result with a frontier verdict (`confirms_pass` / `confirms_fail` / `over_claim` / `under_claim` / `cannot_assess` / `unavailable`); `over_claim`/`under_claim` are recorded as mismatches and the weak-LLM result is never upgraded; with no judge configured every verdict is `unavailable` (not passed). `StaticFrontierJudge` replays a frontier model's recorded verdicts deterministically.
Focused tests: `venv_sys/Scripts/python.exe -m pytest -q tests/test_forge_frontier_verification.py` -> 6 passed
Syntax checks: `py_compile agent/model_forge/frontier_verification.py tests/test_forge_frontier_verification.py` -> passed
Affected tests: evaluation service/runner suites unaffected (harness is additive, advisory-only)
Real model evidence: localhost:8080 `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`. Live benchmark run over 4 method dimensions, then frontier (Claude Opus 4.8) independently inspected the raw outputs. Verification run `forge_eval_7c0f35514120`: 8 cases assessed, **6 agreements, 2 mismatches**. Agreements: structured_output_fidelity (strict JSON), patch_protocol_fidelity (valid DSL, no Safe-Apply bypass), edit_intent_quality (empty anchors / empty list = genuine failure). Mismatches: `anchor_selection_quality:asq_unique` and `:asq_ambiguous` flagged `over_claim` because the mechanical adapter only checks that the anchored block parses with a non-empty anchor and never verifies anchor uniqueness / ambiguity avoidance against file content — so the "passed" over-claims that capability. Proof `frontier_verification_mismatch`.
Benchmark soundness: the live evaluation path (run_live -> RealMethodRunner -> mechanical scoring -> evidence) executed end-to-end without error; the only issue is semantic under-coverage in anchor selection, recorded above (not a path failure).
Atlas UI evidence: unavailable; backend verification tooling
Project Intelligence evidence: unavailable
Runtime/Portal evidence: real local provider calls across all 4 method dimensions
Unavailable checks: only the 4 mechanically-evaluable method dimensions were verifiable end-to-end; the remaining benchmark dimensions need the live eval-dimension expansion in PR19 before frontier verification can cover all axes. No frontier API is wired in product; the frontier verdict here is the session frontier model's recorded assessment via StaticFrontierJudge, which is honest (advisory, replayable) rather than an algorithm imitating a frontier model.
Safety invariants: weak-LLM results never upgraded by frontier verdicts; `unavailable`/mismatch never counted as passed; no routing or Safe Apply change
Remaining gaps: extend live evaluation to all dimensions (PR19) then re-run full-coverage frontier verification; the anchor-selection evaluator should additionally verify uniqueness/ambiguity against file content (future eval-pack hardening)
Next package: PR18 `feat/forge-method-router-v2`
Blocker: none
Proof level: `frontier_verification_mismatch` (harness `component_complete`; 6/8 weak verdicts confirmed, 2 over-claims surfaced and not upgraded)

---

## 26. PR18 MethodRouter v2 完了証跡

Completed package: PR18 `feat/forge-method-router-v2`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/method_policy.py`, `agent/model_forge/method_router.py`, `tests/test_forge_method_router_v2.py`, integration plan/status docs
Behavior implemented: (1) **fixed the PR16 trigger gap** — all fallback steps now trigger on `RECOVERABLE_TRIGGERS` (schema_invalid / content_missing / file_changes_missing / missing_edit_anchor / invalid_edit_intent / anchor_not_found / empty_output / unsafe_target_path / forbidden_action_type / failed / blocked) and every method chain ends in a review-only terminal; (2) capability-aware refinements applied only from measured dimensions: abstraction weak -> fill_in_template (severe -> yes_no_gate), context_overload weak -> minimal refs, test_generation strong -> test_first_slice + focused tests, repair strong -> repair_compass, evidence weak -> verifier separation + full gate, structured weak + edit_intent strong -> deterministic compile path, frontier_assisted -> lower injection; (3) policy enums expanded (TaskDecompositionPolicy +5, InstructionAbstractionLevel +5). MethodRouter still never overrides RouteMatrix.
Focused tests: `venv_sys/Scripts/python.exe -m pytest -q tests/test_forge_method_router_v2.py` -> 11 passed
Syntax checks: `py_compile agent/model_forge/method_policy.py agent/model_forge/method_router.py` -> passed
Affected tests: `pytest -q tests/test_forge_method_router.py tests/test_forge_method_router_v2.py tests/test_forge_method_pipeline.py tests/test_execution_policy_route_preference.py tests/test_forge_method_schema_extension.py tests/test_forge_anvil_acceptance.py` -> 40 passed
Real model evidence: localhost:8080 `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`. A weak-structured profile's router-generated chain run through MethodPipeline naturally fell back: edit_intent_list -> blocked (file_changes_missing) -> anchored_edit_block -> failed (anchor_not_found) -> review_only -> passed. The old narrow triggers would have ignored file_changes_missing; the production router now recovers.
Atlas UI evidence: unavailable; routing logic change only
Project Intelligence evidence: unavailable
Runtime/Portal evidence: real local provider calls across the router-derived fallback chain
Unavailable checks: tool_call_patch routing for tool-calling-capable providers is not yet wired (no tool-calling provider profile available locally); recorded as future work rather than claimed
Safety invariants: RouteMatrix authority preserved (route never overridden); strong/weak derived only from measured scores so legacy profiles are non-regressed; new enum values are additive; review-only decisions are never refined; no Safe Apply / Proposal / Verification change
Remaining gaps: tool_call_patch + provider-capability gating; full-axis live evaluation (PR19) then full-coverage frontier re-verification (PR21)
Next package: PR19 `feat/forge-multimodel-roleassignment`
Blocker: none
Proof level: `method_router_shadow_connected` (v2 rules + real fallback verified)

---

## 27. PR19 Multi-model RoleAssignment + live eval expansion 完了証跡

Completed package: PR19 `feat/forge-multimodel-roleassignment`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/multimodel_optimizer.py`, `agent/model_forge/real_method_runner.py`, `tests/test_forge_multimodel_roleassignment.py`, integration plan/status docs
Behavior implemented: `MultiModelRoleOptimizer.assign` evaluates several `ModelCandidate`s together and assigns planner/implementer/verifier/repairer/reviewer to the best-fit model plus a robust fallback model; selection is constraint-aware (latency/cost/local_only/privacy), external providers are excluded in local_only or when privacy_sensitive, review roles (verifier/reviewer) never construct a patch, and per-role required vs missing evidence is recorded so an unmeasured dimension is never counted as competence. Twin injection level is derived from capability mode (weak->4 .. frontier->1). RealMethodRunner live coverage expanded from 4 to 7 method-backed dimensions (large_file_editing->anchored, evidence_discipline->review_only, repair_discipline->repair_compass); non-method dimensions (abstraction_tolerance / scope_boundary_discipline / context_overload_sensitivity / fallback_recovery) remain mechanical_evaluator_unavailable.
Focused tests: `venv_sys/Scripts/python.exe -m pytest -q tests/test_forge_multimodel_roleassignment.py` -> 8 passed
Syntax checks: `py_compile agent/model_forge/multimodel_optimizer.py agent/model_forge/real_method_runner.py` -> passed
Affected tests: `pytest -q tests/test_forge_multimodel_roleassignment.py tests/test_forge_real_method_runner.py tests/test_forge_optimizer_loadout.py tests/test_forge_evaluation_api.py` -> 20 passed
Real model evidence: localhost:8080 `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`, run `forge_eval_34b23a14d9c1`: the three newly-live dimensions produced real outcomes instead of unavailable — repair_discipline 1.0, evidence_discipline 1.0, large_file_editing 0.4 (mixed anchor_not_found failures).
Atlas UI evidence: unavailable; backend optimizer + runner
Project Intelligence evidence: per-role missing_evidence is surfaced, not assumed
Runtime/Portal evidence: real local provider calls across the three new dimensions
Unavailable checks: review_only / repair_compass mechanical checks are format-level (a non-empty review / non-empty steps array passes), so they can over-claim semantic quality — this is the same limitation PR21 frontier verification flags for anchor_selection; recorded honestly rather than claimed as semantic competence. Cost/latency for local candidates are operator-supplied estimates, not measured here.
Safety invariants: non-applying preview; review roles never build a patch; external providers excluded under local_only/privacy; unmeasured dimensions recorded as missing evidence, never counted; applying still requires the existing loadout/cutover flow
Remaining gaps: mechanical evaluators for non-method dimensions; semantic (not format-only) checks for review/repair/anchor; then full-coverage frontier re-verification
Next package: PR20 `feat/forge-active-execution-gated`
Blocker: none
Proof level: `real_runtime_evaluated` (7 live dimensions; multi-model assignment component_complete)

---

## 28. PR20 Gated active method execution 完了証跡

Completed package: PR20 `feat/forge-active-execution-gated`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/method_activation.py`, `tests/test_forge_method_activation.py`, integration plan/status docs
Behavior implemented: `MethodActivationGate` reads the PR15 atlas_shadow records for a stage and computes readiness (>= min_samples, a stable dominant method recommendation, model-evaluation evidence present, and all records shadow-only). `activate` requires both an explicit `acknowledge=True` and readiness, writes an activation record with `active_method_enabled=True` and `active_auto_enabled=False` (invariant), and records proof_requirements stating Proposal/Safe Apply/Verification and RouteMatrix authority remain. `deactivate` reverts to shadow with no acknowledgement so recovery is always one call away. This is the cutover-equivalent gate for using the MethodRouter decision as active pre-execution policy.
Focused tests: `venv_sys/Scripts/python.exe -m pytest -q tests/test_forge_method_activation.py` -> 9 passed
Syntax checks: `py_compile agent/model_forge/method_activation.py tests/test_forge_method_activation.py` -> passed
Affected tests: `pytest -q tests/test_forge_method_activation.py tests/test_forge_atlas_execution_shadow.py` -> 15 passed
Real model evidence: not applicable — this is a control-plane gating decision over accumulated shadow evidence, not a model call. The shadow evidence it consumes is produced by PR15/PR16/PR19 real runs.
Atlas UI evidence: unavailable; backend gate
Project Intelligence evidence: unavailable
Runtime/Portal evidence: not applicable
Unavailable checks: no active rollout was executed end-to-end against Atlas in this PR; the gate only authorises activation. Wiring the gate's `is_active` into the Atlas execution path (so an active stage actually uses the Forge method policy) is the next integration step and is intentionally not enabled by default.
Safety invariants: automation never enabled (`active_auto_enabled` always False); activation requires explicit acknowledgement and sufficient stable shadow evidence; deactivation needs no acknowledgement; Proposal/Safe Apply/Verification and RouteMatrix authority preserved and asserted in proof_requirements; non-shadow records block activation
Remaining gaps: connect `is_active` into the Atlas pre-execution method selection (still gated, default off); operator UI for activation/rollback
Next package: PR22 `feat/forge-atlas-route-validation`
Blocker: none
Proof level: `active_gated_ready` (gate component_complete; default off, no automation)

---

## 29. PR22 Atlas route validation 完了証跡

Completed package: PR22 `feat/forge-atlas-route-validation`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/atlas_route_validation.py`, `tests/test_forge_atlas_route_validation.py`, integration plan/status docs
Behavior implemented: `AtlasRouteValidator` derives the benchmark-optimal route + Twin injection level from a model's evaluation profile (via `ExecutionPolicySelector`) and validates the Atlas planning / code_development / completion phases: each phase's route must be within RouteMatrix safe candidates (no override), code_development must align with the benchmark-optimal route, evidence must be present, and completion must carry verification + Safe Apply proof. The verdict is shadow-only (`changes_production_routing=False`), honouring the PR20 gate. Missing phases yield `atlas_route_validation_pending`; phase failures yield `atlas_route_validation_mismatch`.
Focused tests: `venv_sys/Scripts/python.exe -m pytest -q tests/test_forge_atlas_route_validation.py` -> 6 passed
Syntax checks: `py_compile agent/model_forge/atlas_route_validation.py tests/test_forge_atlas_route_validation.py` -> passed
Affected tests: route_matrix / execution_policy suites unaffected (validator is additive, read-only)
Real model evidence: localhost:8080 `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`. A real benchmark (structured_output_fidelity 1.0, patch_protocol_fidelity 1.0, edit_intent_quality 0.0) yielded optimal route `patch_dsl` + Twin injection 3 + method `patch_dsl_json`; a representative Atlas run (planning=sliced_impact, code_development=patch_dsl, completion=critical_gate with verification + Safe Apply proof) validated overall_valid with proof `atlas_route_validation_passed`.
Atlas UI evidence: unavailable; backend validator
Project Intelligence evidence: unavailable
Runtime/Portal evidence: real benchmark profile feeding the route/injection derivation
Unavailable checks: phase observations are supplied to the validator rather than harvested live from a running Atlas execution; wiring the validator to consume real Atlas plan/patch/verify artifacts is the next integration step. Validation is shadow-only and does not change routing.
Safety invariants: shadow-only; RouteMatrix authority enforced (unsafe routes flagged); completion requires verification + Safe Apply proof; production routing unchanged; honours the PR20 active gate
Remaining gaps: harvest phase observations from real Atlas execution artifacts; the deeper integration/UI items noted across PR16-21 proofs
Next package: none in the Phase 2 plan — PR16-22 are all merged. Full acceptance still depends on the recorded remaining gaps (non-method mechanical evaluators, semantic vs format-only checks, active-gate wiring into Atlas, real-browser UI verification).
Blocker: none
Proof level: `atlas_route_validation_passed` (real benchmark -> optimal route + injection -> Atlas phase validation)

---

## 30. H1 Non-method live capability evaluators 完了証跡 (Phase 3 / P0-1)

Completed package: H1 `feat/forge-nonmethod-live-evaluators`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/live_capability_eval.py`, `agent/model_forge/evaluation_service.py`, `tests/test_forge_live_capability_eval.py`, integration plan/status docs
Behavior implemented: `LiveCapabilityEvaluator` scores the four non-method dimensions that previously returned `mechanical_evaluator_unavailable`. scope_boundary_discipline / context_overload_sensitivity / abstraction_tolerance use concrete prompts with deterministic checkers (allowed vs forbidden path, relevant token vs distractor, constraint retention vs template echo). fallback_recovery runs the real MethodPipeline and asserts both natural recovery and that a failed primary attempt is never reported as passed. `run_live` now splits dimensions: method-backed -> RealMethodRunner, non-method -> LiveCapabilityEvaluator. Transport failures and unparseable answers are `unavailable`, never passed.
Focused tests: `venv_sys/Scripts/python.exe -m pytest -q tests/test_forge_live_capability_eval.py` -> 9 passed
Syntax checks: `py_compile agent/model_forge/live_capability_eval.py agent/model_forge/evaluation_service.py tests/test_forge_live_capability_eval.py` -> passed
Affected tests: `pytest -q tests/test_forge_live_capability_eval.py tests/test_forge_evaluation_api.py tests/test_forge_real_method_runner.py` -> 19 passed
Real model evidence: localhost:8080 `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`, run `forge_eval_50d47ff13bd2`: scope_boundary_discipline 1.0, context_overload_sensitivity 1.0, abstraction_tolerance 1.0, fallback_recovery 1.0 (fb_recover recovered via fallback from a blocked primary; fb_no_false_pass confirmed primary_status=blocked, not passed). Live evaluation coverage is now 11/16 dimensions (7 method-backed + 4 non-method).
Atlas UI evidence: unavailable; backend evaluator
Project Intelligence evidence: unavailable
Runtime/Portal evidence: real local provider calls across all four non-method dimensions plus a live fallback pipeline run
Unavailable checks: the remaining 5 dimensions (impact_analysis, contract_preservation, test_generation, stale_test_judgment, flag_reasoning) are the original control-plane judgment dimensions scored from supplied outcomes, not live-model cases; out of scope for this live-runner expansion. The prompt-based checkers are still partly format/string oriented and will be hardened toward deeper semantics in H2.
Safety invariants: `unavailable` never upgraded to passed; fallback_recovery explicitly guards against a false pass; no file applied; no routing change
Remaining gaps: H2 semantic hardening (anchor uniqueness/ambiguity vs file content, review/repair content quality); H3 full-axis frontier re-verification
Next package: H2 `feat/forge-semantic-eval-hardening`
Blocker: none
Proof level: `real_runtime_evaluated` (11/16 live dimensions; non-method evaluators component_complete)

---

## 31. H2 Semantic evaluation hardening 完了証跡 (Phase 3 / P0-2)

Completed package: H2 `feat/forge-semantic-eval-hardening`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/live_capability_eval.py`, `agent/model_forge/real_method_runner.py`, `tests/test_forge_live_capability_eval.py`, `tests/test_forge_multimodel_roleassignment.py`, integration plan/status docs
Behavior implemented: resolves the PR21 over_claim. `anchor_selection_quality` is now checked against **real file content** — the chosen anchor must occur exactly once (a repeated/ambiguous token fails). `evidence_discipline` (keep unavailable distinct from passed; reject mock as live evidence) and `repair_discipline` (minimal repair scope; decline unrelated broad rewrite) became semantic judgment cases. These three dimensions moved from the format-only method runner to `LiveCapabilityEvaluator`; `large_file_editing` stays method-backed.
Focused tests: `venv_sys/Scripts/python.exe -m pytest -q tests/test_forge_live_capability_eval.py tests/test_forge_multimodel_roleassignment.py` -> 23 passed
Syntax checks: `py_compile` on the four changed Python files -> passed
Affected tests: included above; the multimodel test was updated to the new routing
Real model evidence: localhost:8080 `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`, run `forge_eval_878e6329cc25`: anchor_selection_quality 1.0 (model selected the unique anchors `def UNIQUE_TARGET_FN():` and `def reset_UNIQUE_MARKER():`, avoiding the ambiguous repeated `x = 0`), evidence_discipline 1.0, repair_discipline 1.0. The anchor check now fails if a repeated token is chosen, which is the over_claim PR21 surfaced.
Atlas UI evidence: unavailable; backend evaluator
Project Intelligence evidence: unavailable
Runtime/Portal evidence: real local provider calls across the three hardened dimensions
Unavailable checks: large_file_editing remains a method-backed (anchored) check rather than full file-content semantic placement; review prose quality beyond severity/structure is not graded; these are recorded rather than claimed
Safety invariants: `unavailable` never upgraded to passed; the adversarial traps (mock-as-live, broad-rewrite, ambiguous anchor) are explicitly caught; no routing change
Remaining gaps: H3 full-axis frontier re-verification (should now confirm anchor_selection instead of over_claim)
Next package: H3 `feat/forge-fullaxis-frontier-verify`
Blocker: none
Proof level: `real_runtime_evaluated` (semantic anchor/evidence/repair checks; PR21 over_claim resolved)

---

## 32. H3 Full-axis frontier re-verification 完了証跡 (Phase 3)

Completed package: H3 `feat/forge-fullaxis-frontier-verify`
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/full_axis_verification.py`, `tests/test_forge_full_axis_verification.py`, integration plan/status docs
Behavior implemented: `all_live_dimensions()` enumerates every live axis (4 method-backed + 7 semantic/non-method = 11). `FullAxisFrontierVerifier` runs the PR21 harness over an evaluation run and reports covered vs uncovered live dimensions. The frontier verdict stays advisory; weak results are never upgraded.
Focused tests: `venv_sys/Scripts/python.exe -m pytest -q tests/test_forge_full_axis_verification.py` -> 4 passed
Syntax checks: `py_compile agent/model_forge/full_axis_verification.py tests/test_forge_full_axis_verification.py` -> passed
Affected tests: PR21 frontier_verification suite unaffected (additive wrapper)
Real model evidence: localhost:8080 `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`, eval run `forge_eval_5013afe646b3`: all 11 live dimensions evaluated by the weak LLM and re-verified by the frontier (Claude Opus 4.8) -> 23 cases assessed, 23 agreements, 0 mismatches, proof `frontier_verification_passed`, 0 uncovered live dimensions. Crucially `anchor_selection_quality` moved from `over_claim` (PR21) to `confirms_pass`, verifying the H2 semantic hardening.
Atlas UI evidence: unavailable; backend verification
Project Intelligence evidence: unavailable
Runtime/Portal evidence: real local provider calls across all 11 live dimensions
Unavailable checks: the 5 original judgment dimensions (impact_analysis, contract_preservation, test_generation, stale_test_judgment, flag_reasoning) are scored from supplied outcomes, not live-model cases, so they are outside the live full-axis run; the frontier judge here is the session frontier model's recorded assessment (StaticFrontierJudge), not a wired frontier API.
Safety invariants: weak-LLM results never upgraded; `unavailable`/mismatch never counted as passed; no routing change
Remaining gaps (track-level, recorded honestly): active-gate wiring into the Atlas execution path; harvesting Atlas phase observations from live artifacts; real-browser UI verification; tool_call provider gating; Anvil control-plane HTTP flow under the running app; live evaluators for the 5 original judgment dimensions.
Next package: none — Phase 2 (PR16-22) and Phase 3 P0 hardening (H1-H3) are complete; the remaining gaps above are P1/P2 integration/UI items.
Blocker: none
Proof level: `frontier_verification_passed` (all 11 live axes; anchor over_claim resolved end-to-end)

---

## 33. Current 8080 model evaluation snapshot

Run `forge_eval_ce8ef28d3fb0` (localhost:8080 `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`, 11 live dimensions): **9/11 dimensions passed, 2 failed.**
- Strong (1.0): structured_output_fidelity, patch_protocol_fidelity, anchor_selection_quality, abstraction_tolerance, context_overload_sensitivity, scope_boundary_discipline, repair_discipline, evidence_discipline, fallback_recovery.
- Weak: **edit_intent_quality 0.0** (empty old/new anchors, empty intent list) and **large_file_editing 0.4** (anchor_not_found on 2/3). The model is reliable at strict JSON/DSL, anchor selection, and judgment, but unreliable at producing exact existing-text edit anchors. This is the classic weak-LLM failure the Method layer is designed to route around (edit_intent -> anchored -> review_only natural fallback).

## 34. H4 Capability rescue policy 完了証跡 (rescue / fallback for all-NG)

Completed package: H4 `feat/forge-capability-rescue` (responds to: "全部NGだった場合は、救出するための手法もしくはフォールバックが必要")
Status: completed; publication and merge performed as the item PR workflow
Changed modules/files: `agent/model_forge/capability_rescue.py`, `tests/test_forge_capability_rescue.py`, integration plan/status docs
Behavior implemented: `CapabilityRescuePlanner.plan` reads a model's measured capability and produces a rescue ladder when construction methods fail: (1) a direct construction method is viable -> `none`; (2) only edit-intent viable -> `deterministic_compile`; (3) all construction methods fail but a capable fallback model exists -> `escalate_fallback_model`; (4) all fail, change is mechanically expressible -> `deterministic_text_patch` (system builds the patch); (5) otherwise -> `review_only` with requires_human_review. Every rescue chain ends in review_only and hard-fails Safe Apply / proposal / verification bypass. Unmeasured dimensions are never treated as competence; AUDIT_ONLY always degrades to review_only; a fallback model that is itself incapable is not escalated to.
Focused tests: `venv_sys/Scripts/python.exe -m pytest -q tests/test_forge_capability_rescue.py` -> 9 passed
Syntax checks: `py_compile agent/model_forge/capability_rescue.py tests/test_forge_capability_rescue.py` -> passed
Affected tests: additive module; method_router/pipeline suites unaffected
Real model evidence: using the real snapshot profile (run `forge_eval_ce8ef28d3fb0`) the planner returns `none` (direct construction viable: structured/patch/anchored). Synthetic all-NG profiles return `deterministic_text_patch` (no fallback, mechanically feasible), `review_only` (not feasible -> human applies), and `escalate_fallback_model` (a capable fallback present) — demonstrating the rescue path for the degenerate all-fail case.
Atlas UI evidence: unavailable; planning policy
Project Intelligence evidence: unavailable
Runtime/Portal evidence: rescue is a planning decision over the benchmark profile; no model call required
Unavailable checks: wiring the rescue plan into the live ExecutionPolicy/Atlas path (so a rescued chain actually runs) is a follow-up; the planner currently produces the chain/decision
Safety invariants: rescue never bypasses Safe Apply/Proposal/Verification; review_only never auto-applies; weak/unmeasured never counted as competence
Remaining gaps: connect rescue plan into ExecutionPolicySelector so a failing model is rescued at execution time; surface rescue level in UI
Next package: P1 active-gate / rescue wiring into the execution path
Blocker: none
Proof level: `component_complete` (rescue ladder implemented + demonstrated; execution wiring pending)

---

## 35. TA1 Twin Assist contracts completion proof

Completed package: TA1 `feat/forge-twin-assist-contracts`
Status: completed; ready for item PR publication and merge
Changed modules/files: `agent/model_forge/twin_assist_taxonomy.py`, `agent/model_forge/twin_assist_contracts.py`, `tests/test_forge_twin_assist_contracts.py`, Twin Assist plan/entrypoint/status docs
Behavior implemented: added the seven stable `TwinAssistMode` values and strict Forge DTOs for cases, run requests, attempts, baseline-vs-assisted comparisons, and evaluation reports. Status is a closed passed/failed/unavailable/blocked contract; scores, latency, timeout, and injection level are bounded; mutable collections use isolated default factories.
Focused tests: `C:/Users/kkens/KasaneCore/venv_sys/Scripts/python.exe -m pytest -q tests/test_forge_twin_assist_contracts.py` -> 12 passed
Syntax checks: `compileall -q agent/model_forge/twin_assist_taxonomy.py agent/model_forge/twin_assist_contracts.py` -> passed
Affected tests: Twin Assist contracts focused suite covers taxonomy stability, strict extra-field rejection, non-shared defaults, status closure, unavailable honesty, and numeric bounds
Real model evidence: localhost:8080 `/v1/models` responded with `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`; no inference was required for this pure-contract package
Baseline score: unavailable; runner begins in TA3
Assisted score: unavailable; runner begins in TA3
Lift: unavailable; runner begins in TA3
Harm cases: unavailable; scoring begins in TA2/TA3
Best assist mode: unavailable; evaluation begins in TA3
Atlas UI evidence: unavailable; UI is TA7
Unavailable checks: repository-local `venv_sys` is absent; the configured interpreter exists at `C:/Users/kkens/KasaneCore/venv_sys`. Live generation, proposal, Safe Apply, Portal, and browser evidence are not applicable to a pure-contract package.
Safety invariants: `unavailable` is distinct from `passed`; contracts are additive; no file apply, production routing change, provider execution, Proposal bypass, or Safe Apply bypass
Remaining gaps: case packs/scoring, Atlas proposal runner, localized slots, policy/ProfileStore, API/UI, readiness/matrix/slot gates/post-apply E2E, and real 8080 comparison evidence
Next package: TA2 `feat/forge-twin-assist-packs`
Blocker: none
Proof level: `component_complete`
