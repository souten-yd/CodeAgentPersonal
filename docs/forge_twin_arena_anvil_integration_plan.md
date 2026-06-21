# Forge / Twin / Arena / Anvil 統合改修 — 実装計画 & 進捗トラッカー

作成日: 2026-06-21 / Owner: souten
ペア文書: `docs/forge_twin_arena_anvil_integration_current_status.md`（Phase 0 棚卸し）

この文書はこの改修トラックの **living plan**。各項目を1PRとして実装し、PRごとにレビュー→マージする。完了時は本文書の進捗テーブルと current_status を更新する。

---

## 運用ルール

- **項目=1PR**: 各 PR 項目ごとにローカルブランチを切り、実装・テスト後に PR を作成しマージする（ユーザーがこのトラックで PR 作成・マージを明示承認済み: 2026-06-21）。
- ブランチ命名: `feat/forge-method-<項目スラッグ>` を基本とする。
- 各 PR は「小さく完結する垂直スライス」。既存を置き換えず**統合・拡張**。
- strict schema（`extra="forbid"`）拡張は正式フィールド追加 + 後方互換 + migration テストを伴う。
- 安全不変条件を壊さない: `unavailable≠passed` / Safe Apply 境界 / remote publish 承認必須 / test・gate 弱体化禁止 / stale test 自動削除禁止 / Arena 非適用。
- 各 PR 完了時は `AGENTS.md` の Evidence Rules 形式で証跡を残す。focused テストのみで `acceptance_complete` としない。
- **命名衝突注意**: 既存 `decomposition_policy.py` はファイルサイズ用。タスク分解 enum は `TaskDecompositionPolicy` 等の別名で新設する（既存を破壊しない）。
- **削除禁止**: Project Twin read-only inspection / 既存 decomposition_policy.py / RouteMatrix / cutover / shadow / 各 gate / ProfileStore 既存 profile。

---

## PR 項目一覧（実装順）

| # | ブランチ | 内容 | 主な追加/変更 | 依存 | 状態 |
|---|---|---|---|---|---|
| 1 | feat/forge-method-contracts | Method 中核契約（DTO） | `method_taxonomy.py`(MethodVariant) / `method_contracts.py`(MethodRequest, MethodResult, MethodAdapter(Protocol), MethodRegistry, FallbackStep, MethodChain, MethodPipelineResult) + tests | — | ☑ merged |
| 2 | feat/forge-method-schema-ext | 既存 schema の後方互換拡張 | ExecutionPolicy / ForgeExecutionRequest / ForgeExecutionResult / ArenaCandidate / CandidateScore に method/fallback/radar フィールド追加。`ModelOptimizationProfile` / `RoleAssignment` 追加。補助 enum（TaskDecompositionPolicy, InstructionAbstractionLevel, ContextPackageMode, OutputProtocol, PatchConstructionMode, VerificationMode, RepairMode）。schema_version migration + 互換テスト | 1 | ☑ merged |
| 3 | feat/forge-adapters-structured | MethodRegistry + 構造化系 adapter | StructuredPatchJsonAdapter / PatchDslJsonAdapter / EditIntentListAdapter + edit_intent→Safe Apply deterministic compiler + tests | 1,2 | ☑ merged |
| 4 | feat/forge-adapters-anchored | 残り adapter | AnchoredEditBlock / UnifiedDiff / DeterministicTextPatch / ReviewOnly / RepairCompass + tests | 3 | ☑ merged |
| 5 | feat/forge-method-pipeline | MethodPipeline | primary→fallback 実行、trigger 判定（schema_invalid / anchor_not_found 等）、hard_fail（Safe Apply bypass 等）、attempts 記録 + tests | 3,4 | ☑ merged |
| 6 | feat/forge-method-router | MethodRouter + Policy 統合 | profile→MethodChain/abstraction/decomposition/context/verification。ExecutionPolicySelector へ method 添付（safe 候補内のみ・route override 禁止）+ tests | 2,5 | ☑ merged |
| 7 | feat/forge-eval-dimensions | 新評価軸 + ケース | capability dimension 追加（structured_output_fidelity, patch_protocol_fidelity, edit_intent_quality, anchor_selection_quality, abstraction_tolerance, fallback_recovery, scope_boundary_discipline, context_overload_sensitivity 等）+ eval packs（output_protocol/patch_construction/abstraction/fallback/weak_local/frontier/safety_adversarial）+ tests | 1,2 | ☑ merged |
| 8 | feat/forge-evaluation-api | 評価 API | `/api/forge/evaluation/{cases,run,rerun,optimize,model-profile}` + tests | 6,7 | ☑ merged |
| 9 | feat/forge-twin-facade-api | Twin facade API | `/api/forge/twin/{settings,profiles,inspect/context,inspect/impact}`（read-only inspector 再利用）+ tests | — | ☐ pending |
| 10 | feat/forge-real-llm-runner | 実 LLM runner 接続 | Anvil / local OpenAI compat / LM Studio / OpenRouter 実行、unavailable handling、evidence/token/latency。evaluation/run と接続 + tests | 8 | ☐ pending |
| 11 | feat/forge-optimizer-loadout | optimizer / role / loadout | route/method/injection/style fitness → RoleAssignment → Loadout 生成。Loadout に method preference/fallback 保存 + tests | 6,7 | ☐ pending |
| 12 | feat/forge-ui-radar | Arena radar + drawer | SVG radar（外部ライブラリ無し、Capability/Method/Safety/Speed/All、unavailable≠0）+ candidate drawer + render test | 8,11 | ☐ pending |
| 13 | feat/forge-ui-fallback-graph | fallback graph + method 比較 | candidate drawer に fallback graph、Benchmark に method 比較表、policy recommendation drawer + render test | 12 | ☐ pending |
| 14 | feat/forge-ui-advanced-twin | Advanced への Twin 統合 | Forge Advanced に Twin Settings + read-only Twin Inspector。独立 Twin タブ非表示。mobile 崩れ無し + test | 9,13 | ☐ pending |
| 15 | feat/forge-execution-shadow | 実行統合（shadow） | Atlas plan/patch/verify/repair に評価結果を渡す。shadow mode で記録のみ。active は明示確認後（このトラックでは shadow まで）+ tests | 6,10 | ☐ pending |
| 16 | feat/forge-anvil-real-eval | Anvil 実評価 + 仕上げ | Anvil 起動→実モデル評価で fallback 実証。全テスト（unit/integration/adversarial/UI/real-gated）。docs/rollback/proof levels 更新 | 10,12,13,14,15 | ☐ pending |

状態凡例: ☐ pending / ◐ in_progress / ☑ merged

---

## 各 PR の受け入れ基準（要点）

- **PR1**: MethodVariant enum / MethodAdapter Protocol / MethodRegistry dispatch / 各 DTO の schema テストが通る。実行ロジック無し（contract_present）。
- **PR2**: 既存 DTO に新フィールドがデフォルト付きで追加され、既存 JSON が読める（後方互換テスト）。decomposition 命名衝突なし。
- **PR3-4**: 各 adapter が `prepare_prompt/parse_output/compile_patch/verify_contract` を実装。edit_intent_list が deterministic compile で Safe Apply patch を生成。
- **PR5**: schema_invalid→edit_intent、anchor_not_found→次手法、Safe Apply bypass→hard_fail のパイプラインテストが通る。
- **PR6**: 構造化弱モデル→edit_intent_list、大規模編集弱→anchored、繰り返し失敗→review_only を MethodRouter が選ぶ。RouteMatrix を override しない。
- **PR7**: 新 dimension が `unavailable≠passed` を守る。adversarial ケースが weight 加算。
- **PR8-9**: API が DTO を返し、strict schema を破らない。既存 Forge/Twin API 互換テストが通る。
- **PR10**: 実 LLM 未起動時は unavailable（passed にしない）。起動時は evidence_refs 生成。
- **PR11**: 評価結果から RoleAssignment / Loadout が生成され、適用は既存 cutover/confirmation を通る。
- **PR12-14**: radar が unavailable を 0 と区別。fallback graph 描画。Advanced で Twin read-only。mobile 崩れ無し。
- **PR15**: shadow 記録のみ。Safe Apply/verification/proof ledger 接続。active 自動切替なし。
- **PR16**: Anvil 実評価の証跡（起動コマンド/model_id/base_url/`/v1/models`/run_id/raw refs/score/fallback 実証）。Anvil 未評価なら `anvil_real_eval_pending`、`acceptance_complete` にしない。

---

## Proof level（このトラック共通）

`contract_present` → `component_complete` → `method_contract_present` → `method_pipeline_component_complete` → `method_router_shadow_connected` → `shadow_connected` → `real_llm_evaluated` → `real_runtime_evaluated` → `anvil_real_eval_passed` → `fallback_real_eval_passed` → `production_connected` → `acceptance_complete`

---

## 進捗ログ

- 2026-06-21: Phase 0 棚卸し完了（current_status.md）。本計画策定。実装は PR1 から着手予定（ユーザー指示によりここで一旦停止）。
- 2026-06-21: PR1 Method 中核契約を実装。focused 9 passed、既存回帰 25 passed、syntax 成功。localhost:8080 の Qwen3.6-35B-A3B による契約レビューは `VERDICT: PASS`。proof level は `method_contract_present`。
- 2026-06-21: PR2 Method schema をadditive拡張。旧 `forge.v1` payload互換、strict DTO、新radar表現を検証（focused 28 passed、回帰31 passed、syntax成功）。localhost:8080 LLMレビューは `VERDICT: PASS`。
- 2026-06-21: PR3 構造化adapter 3種とcontent-addressed artifact store、deterministic `atlas_file_changes.v1` compilerを実装。focused 27 passed、Safe Apply/Forge回帰60 passed。localhost:8080実モデル出力をedit intentから安全な非適用patchへ変換成功。
- 2026-06-21: PR4 AnchoredEditBlock / UnifiedDiff / DeterministicTextPatch / ReviewOnly / RepairCompass adaptersを実装。focused 36 passed、回帰60 passed。localhost:8080実モデルのanchored blockを非適用patchへ変換成功。
- 2026-06-21: PR5 MethodPipelineを実装。trigger fallback、attempt履歴、unavailable、bounded retry、authority hard-failを検証（focused 34 passed、回帰49 passed）。forced schema failureからlocalhost:8080実モデルedit intentへのfallback成功。
- 2026-06-21: PR6 MethodRouterをExecutionPolicySelectorへ添付。RouteMatrix権限を維持し、弱点・失敗回数に応じたmethod/policyを選択（focused 23 passed、回帰50 passed）。localhost:8080実モデルでweak-profile route→method→pipeline成功。
- 2026-06-21: PR7 method/abstraction/fallback/safety評価8軸と通常/adversarialケースを追加。focused 19 passed、回帰34 passed。localhost:8080単一structured fidelityケースはsemantic不一致でfailed（正式dimension scoreは未算出）。
- 2026-06-21: PR8 evaluation cases/run/rerun/optimize/model-profile APIとrun永続化を実装。focused 18 passed、回帰40 passed。PR7のlocalhost:8080実case failureをAPI投入し、failed profileと非適用method previewを確認。
