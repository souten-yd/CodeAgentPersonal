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
