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
| 9 | feat/forge-twin-facade-api | Twin facade API | `/api/forge/twin/{settings,profiles,inspect/context,inspect/impact}`（read-only inspector 再利用）+ tests | — | ☑ merged |
| 10 | feat/forge-real-llm-runner | 実 LLM runner 接続 | Anvil / local OpenAI compat / LM Studio / OpenRouter 実行、unavailable handling、evidence/token/latency。evaluation/run と接続 + tests | 8 | ☑ merged |
| 11 | feat/forge-optimizer-loadout | optimizer / role / loadout | route/method/injection/style fitness → RoleAssignment → Loadout 生成。Loadout に method preference/fallback 保存 + tests | 6,7 | ☑ merged |
| 12 | feat/forge-ui-radar | Arena radar + drawer | SVG radar（外部ライブラリ無し、Capability/Method/Safety/Speed/All、unavailable≠0）+ candidate drawer + render test | 8,11 | ☑ merged |
| 13 | feat/forge-ui-fallback-graph | fallback graph + method 比較 | candidate drawer に fallback graph、Benchmark に method 比較表、policy recommendation drawer + render test | 12 | ☑ merged |
| 14 | feat/forge-ui-advanced-twin | Advanced への Twin 統合 | Forge Advanced に Twin Settings + read-only Twin Inspector。独立 Twin タブ非表示。mobile 崩れ無し + test | 9,13 | ☑ merged |
| 15 | feat/forge-execution-shadow | 実行統合（shadow） | Atlas plan/patch/verify/repair に評価結果を渡す。shadow mode で記録のみ。active は明示確認後（このトラックでは shadow まで）+ tests | 6,10 | ☑ merged |
| 16 | feat/forge-anvil-real-eval | Anvil 実評価 + 仕上げ | Anvil 起動→実モデル評価で fallback 実証。全テスト（unit/integration/adversarial/UI/real-gated）。docs/rollback/proof levels 更新 | 10,12,13,14,15 | ☐ pending |

---

## 拡張 PR 一覧（弱 LLM 補強の完成形 — Phase 2）

PR1〜15 がマージされ Method 層の骨格は揃ったが、レビュー指摘（2026-06-21）により「弱 LLM 補強の完成形」にはまだ届いていない。残る P0/P1/P2 を以下の追加 PR として実装する。各項目=1PR・マージはこれまで同様。

| # | ブランチ | 内容 | 主な追加/変更 | 依存 | 状態 |
|---|---|---|---|---|---|
| 16 | feat/forge-anvil-real-eval | **(P0)** Anvil 正式 acceptance | Anvil 起動コマンド記録 / `/models/db` 読取 / `/model/switch` ロード / `/model/status` ready / `/v1/models` 確認 / `/api/forge/evaluation/run-live` 実評価 / structured・edit_intent・anchor・fallback・evidence ケース実行 / **自然発生 fallback 証跡** / `raw_output_ref`・`parsed_output_ref`・`evidence_refs` 保存 / proof level `anvil_real_eval_passed` 追加。Anvil 未達なら `anvil_real_eval_pending`、`acceptance_complete` にしない | 10,12,13,14,15 | ☑ merged |
| 17 | feat/forge-natural-fallback-pack | **(P0)** 自然発生 fallback パック | 強制証跡でなく実モデルで自然に失敗→fallback する評価ケース群: schema_invalid / patch_apply_failure / anchor_not_found / content_missing / file_changes_missing / unsafe_path / provider_unavailable。MethodPipeline が自然に fallback する証跡を保存 + tests | 5,7,10,16 | ☑ merged |
| 18 | feat/forge-method-router-v2 | **(P1)** MethodRouter v2（分岐拡充） | 追加ルール: evidence weak→verifier分離 / test_generation strong→test_first / repair strong→repair_loop / abstraction weak→explicit_template・yes_no_gate / context overload weak→minimal/focused refs / frontier strong→blueprint_slice・低注入 / tool_call strong→tool_call_patch / structured weak+edit_intent strong→deterministic compile path / provider capability(structured/tool 対応)考慮。policy enum 拡充（TaskDecompositionPolicy に one_failure_at_a_time/test_first_slice/contract_first_slice/one_file_one_change/one_contract_one_patch、InstructionAbstractionLevel に guided_goal/checklist_steps/fill_in_template/constrained_slots/yes_no_gate）。RouteMatrix は引き続き override しない + tests | 6,7 | ☑ merged |
| 19 | feat/forge-multimodel-roleassignment | **(P1)** Multi-model RoleAssignment | 複数モデル同時評価→ planner/implementer/verifier/repairer/reviewer/fallback の多モデル最適割当。latency/cost/local_only/privacy を含む組合せ最適化。role ごとの必須証跡。RealMethodRunner の live 評価軸拡張（fallback_recovery / abstraction_tolerance / scope_boundary_discipline / context_overload_sensitivity / evidence_discipline / repair_discipline / large_file_editing） + tests | 7,10,11,16 | ☑ merged (method-backed 3軸を live 化; 非method軸は honestly unavailable) |
| 20 | feat/forge-active-execution-gated | **(P1)** Active 実行 gated 統合 | shadow evidence 蓄積→cutover 条件明確化→明示確認後のみ active で MethodRouter を実行前 policy として使用。Proposal/Safe Apply/Verification は絶対維持。active 自動化はデフォルト OFF。既存 cutover/shadow gate を通す + tests | 15,16,18,19 | ☑ merged |
| 21 | feat/forge-frontier-eval-verification | **(検証)** 全評価軸の弱 LLM 結果をフロンティアで検証 | Forge ベンチマークの**全評価項目**について、8080(弱 LLM)が生成した評価内容（score/judgment/evidence）の妥当性を**フロンティアモデルで検証**する verification harness。不一致は `frontier_verification_mismatch` として記録（弱 LLM 結果を passed に格上げしない）。完成後にベンチマークを実行し評価経路の健全性を確認 + tests | 7,8,10,16,17,19 | ☑ merged (4 method 軸; 全軸は PR19 後) |
| 22 | feat/forge-atlas-route-validation | **(検証)** Atlas 計画/コード/完了の妥当性確認 | Forge モデルベンチマーク結果から決定した**最適経路 + Twin 注入量**の経路を用いて、Atlas の計画・コード開発・完了までの妥当性を検証。shadow 証跡で記録し production routing は変更しない（PR20 の active gate を尊重） + tests | 19,20,21 | ☑ merged |

状態凡例: ☐ pending / ◐ in_progress / ☑ merged

### 横断的な検証要件（ユーザー指示 2026-06-21）

1. **評価は 8080 ポートの LLM（弱 LLM, Qwen3.6-35B-A3B）で実行する**。
2. **全評価項目について、弱 LLM が生成した評価結果の妥当性をフロンティアモデルで検証する**（PR21）。弱 LLM の評価は advisory。フロンティア検証で不一致なら `frontier_verification_mismatch`、`unavailable≠passed` を厳守。
3. **完成後にベンチマークを実行し、評価経路に問題がないことを確認する**（PR21 末尾）。
4. **Forge ベンチマーク結果から最適経路と Twin 注入量を決定し、その経路で Atlas の計画・コード開発・完了の妥当性を確認する**（PR22）。production routing は変更せず shadow/gated で行う。

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
- **PR17**: 実モデルに対し schema_invalid / anchor_not_found / content_missing / file_changes_missing / unsafe_path / provider_unavailable を実際に誘発し、MethodPipeline が**自然に** fallback する証跡を保存。強制注入でないこと。
- **PR18**: 追加ルールが profile の弱点に応じて発火し、対応する method/policy を選ぶ。新 enum 値が schema を破らず後方互換。RouteMatrix を override しない。
- **PR19**: 複数モデルから planner/implementer/verifier/repairer/reviewer/fallback が証跡付きで割り当てられ、適用は既存 cutover/confirmation を通る。live 評価軸の拡張が `unavailable≠passed` を守る。
- **PR20**: shadow evidence が十分な場合のみ明示確認で active 化でき、Proposal/Safe Apply/Verification を維持。active 自動化はデフォルト OFF。off/shadow/active のロールアウトが既存 gate を通る。
- **PR21**: 全評価軸について 8080 弱 LLM の評価結果をフロンティアが検証し、一致/不一致を記録。不一致を passed に格上げしない。ベンチマーク end-to-end 実行で評価経路の健全性を確認。
- **PR22**: 最適経路+Twin 注入量で Atlas 計画/コード/完了の妥当性を shadow 検証し、production routing を変更しない。

---

## Proof level（このトラック共通）

`contract_present` → `component_complete` → `method_contract_present` → `method_pipeline_component_complete` → `method_router_shadow_connected` → `shadow_connected` → `real_llm_evaluated` → `real_runtime_evaluated` → `anvil_real_eval_passed` → `natural_fallback_real_eval_passed` → `frontier_verification_passed` → `atlas_route_validation_passed` → `active_gated_ready` → `production_connected` → `acceptance_complete`

---

## Phase 3 ハードニング（acceptance_complete へ向けた残ガップ消化）

Phase 2 完了後の残ガップを優先度順に消化する。

| # | ブランチ | 内容 | 状態 |
|---|---|---|---|
| H1 | feat/forge-nonmethod-live-evaluators | **(P0-1)** 非method軸の live 機械評価器（scope_boundary_discipline / context_overload_sensitivity / abstraction_tolerance / fallback_recovery）。run_live に統合 | ☑ merged |
| H2 | feat/forge-semantic-eval-hardening | **(P0-2)** 形式のみ判定を semantic 判定へ（anchor 一意性/曖昧性のファイル内容照合、review/repair の内容質） | ☑ merged |
| H3 | feat/forge-fullaxis-frontier-verify | 全軸での弱LLM結果フロンティア再検証（H1/H2 後） | ☑ merged |
| H4 | feat/forge-capability-rescue | **(救出/フォールバック)** モデルが構築系を全滅した場合の救出ポリシー（deterministic compile→deterministic text→fallback model 昇格→review_only。常に Safe Apply 維持） | ☑ merged |

---

## 進捗ログ

- 2026-06-21: **H4 Capability Rescue Policy を実装（全NG時の救出/フォールバック）**。ユーザー指摘「全部NGだった場合は救出手法/フォールバックが必要」に対応。`agent/model_forge/capability_rescue.py`（測定済みスコアから viable な構築手法を判定し、救出ラダー: 直接構築可→`none` / edit_intent のみ→`deterministic_compile` / 全滅+有能fallbackモデル→`escalate_fallback_model` / 全滅+機械表現可→`deterministic_text_patch` / 全滅+不可→`review_only`(人間適用)。全 chain が review_only 終端、Safe Apply hard-fail 維持、未測定軸を能力扱いしない）+ `tests/test_forge_capability_rescue.py` 9 passed。**現行 8080 モデル評価（run `forge_eval_ce8ef28d3fb0`）= 9/11 軸合格、弱点は edit_intent_quality(0.0)/large_file_editing(0.4)**。実プロファイルは `none`（直接構築可）、全NG仮想プロファイルは det_text/review_only/escalate に正しく分岐することを実証。
- 2026-06-21: **H3 全軸フロンティア再検証を実装（Phase 3 完了）**。`agent/model_forge/full_axis_verification.py`（全 live 軸 = method 4 + semantic/非method 7 を列挙し PR21 ハーネスで検証、未カバー軸を明示）+ `tests/test_forge_full_axis_verification.py` 4 passed。**8080 実モデル run `forge_eval_5013afe646b3`**: 全11 live 軸を弱LLMで評価しフロンティア（Claude Opus 4.8）が再検証 → **23ケース / 23一致 / 0不一致、proof `frontier_verification_passed`、未カバー0**。**`anchor_selection_quality` は PR21 の `over_claim` から `confirms_pass` に転じ、H2 の semantic 化が検証された**。これで「全評価項目の弱LLM結果をフロンティアで検証」が全 live 軸で成立。
- 2026-06-21: **H2 semantic 評価ハードニングを実装（P0-2）**。`anchor_selection_quality` を実ファイル内容に対する **anchor 一意性照合**へ（選んだ anchor の出現回数==1 を検証。曖昧な反復トークンを選べば FAIL）— PR21 の over_claim を解消。`evidence_discipline`（unavailable を passed にしない / mock を live と扱わない）と `repair_discipline`（最小スコープ / broad rewrite 拒否）を判定 prompt 化。3軸を method runner から `LiveCapabilityEvaluator` へ移動。`tests/test_forge_live_capability_eval.py` 拡充 + PR19 テスト更新（23 passed）。**8080 実モデル run `forge_eval_878e6329cc25`**: 3軸とも semantic に passed（asq は `def UNIQUE_TARGET_FN():`/`def reset_UNIQUE_MARKER():` の一意 anchor を選択、曖昧 `x = 0` を回避）。
- 2026-06-21: **H1 非method軸 live 評価器を実装（P0-1）**。`agent/model_forge/live_capability_eval.py`（具体・決定的に検証可能なプロンプト + 機械チェッカー。fallback_recovery は MethodPipeline 経由で「自然回復」と「failed primary を passed にしない」を検証）+ `evaluation_service.run_live` に統合（method軸=adapter runner / 非method軸=LiveCapabilityEvaluator に分岐）+ `tests/test_forge_live_capability_eval.py` 9 passed + 回帰 19 passed。**8080 実モデル run `forge_eval_50d47ff13bd2`**: 4軸すべて実スコア化（scope/context/abstraction/fallback_recovery=1.0、fallback は primary blocked→自然回復）。これで live 評価は 11/16 軸（method 7 + 非method 4）に拡大、4軸が `mechanical_evaluator_unavailable` を脱した。
- 2026-06-21: **PR22 Atlas 経路妥当性検証を実装（Phase 2 完了）**。`agent/model_forge/atlas_route_validation.py`（ベンチマークプロファイル→`ExecutionPolicySelector` で最適経路+Twin注入量を導出→Atlas の planning/code_development/completion 各フェーズを RouteMatrix 安全性・最適経路整合・evidence・verification/safe_apply proof で検証。shadow 専用 `changes_production_routing=False`）+ `tests/test_forge_atlas_route_validation.py` 6 passed。**実ベンチマーク e2e**: 8080 で structured/patch=1.0・edit=0.0 のプロファイルを実測 → 最適経路 `patch_dsl`・Twin 注入 3 を導出 → Atlas 3 フェーズ検証 overall_valid、proof `atlas_route_validation_passed`。**これで Phase 2（PR16〜22）の計画項目はすべて merged**。残ガップは current_status の各証跡末尾に honest 記録（非method軸の機械評価器、形式のみ判定の semantic 強化、active gate の Atlas 実行経路接続、実ブラウザ UI、外部 tool_call provider）。
- 2026-06-21: **PR20 Active 実行 gated 統合を実装**。`agent/model_forge/method_activation.py`（PR15 の atlas_shadow 記録を読み、サンプル数・method 安定性・evidence 有無・shadow-only を判定 → `evaluate_readiness`。`activate` は ack 必須 かつ ready 必須、`active_auto_enabled` は常に False、Proposal/Safe Apply/Verification 維持を proof_requirements に明記。`deactivate` は ack 不要で常に復帰可能）+ `tests/test_forge_method_activation.py` 9 passed + shadow 回帰 15 passed。cutover と同型の安全ゲート。実モデル実行は不要（shadow 証跡上の制御プレーン判断のため）。
- 2026-06-21: **PR19 Multi-model RoleAssignment + live 評価軸拡張を実装**。`agent/model_forge/multimodel_optimizer.py`（複数モデルから planner/implementer/verifier/repairer/reviewer を役割別最適割当 + robust fallback model。latency/cost/local_only/privacy 制約。role ごと required/missing evidence を記録し未測定軸を能力と見なさない。review 役は patch 非構築）+ RealMethodRunner の live 軸を 4→7 に拡張（large_file_editing→anchored / evidence_discipline→review_only / repair_discipline→repair_compass、非 method 軸は honestly unavailable）+ `tests/test_forge_multimodel_roleassignment.py` 8 passed + 回帰 20 passed。**実モデル run `forge_eval_34b23a14d9c1`**: repair_discipline=1.0 / evidence_discipline=1.0 / large_file_editing=0.4 と新軸が live 評価可能に（unavailable でなくなった）。注: review/repair の機械判定は形式レベルのため PR21 フロンティア検証で over_claim 判定対象になり得る（既知の限界）。
- 2026-06-21: **PR18 MethodRouter v2 を実装**。PR16 で発見した **trigger 欠落バグを修正**（fallback step が実 failure 語彙 content_missing/file_changes_missing 等を含む `RECOVERABLE_TRIGGERS` で発火、各 chain に review_only 終端を追加）+ 能力依存 refinement（abstraction weak→fill_in_template/yes_no_gate、context overload→minimal、test_gen strong→test_first_slice/focused、repair strong→repair_compass、evidence weak→verifier 分離+full_gate、structured weak+edit strong→deterministic compile、frontier_assisted→低注入）+ policy enum 拡充。measured 軸のみで strong/weak 判定し legacy/weak profile を非回帰。`tests/test_forge_method_router_v2.py` 11 passed + 既存 router/exec/pipeline/schema/anvil 回帰 40 passed。**実モデル検証**: weak-structured profile の router chain を 8080 で実行 → edit_intent_list(file_changes_missing)→anchored(anchor_not_found)→review_only(passed) と自然 fallback、旧 trigger では取りこぼしていた経路を回復。RouteMatrix は override せず。
- 2026-06-21: **PR21 フロンティア検証ハーネスを実装**（ユーザー直接依頼により順序繰り上げ）。`agent/model_forge/frontier_verification.py`（弱 LLM/機械判定の各ケースにフロンティア verdict を対応付け、`over_claim`/`under_claim` を mismatch として記録、弱結果を格上げしない。judge 未設定時は `unavailable`）+ `tests/test_forge_frontier_verification.py` 6 passed。**実 e2e 検証 run `forge_eval_7c0f35514120`**: 8080 で 4 method 軸をライブ評価し、フロンティア（Claude Opus 4.8）が生出力を独立検証 → 8 評価 / 6 一致 / **2 不一致**（`anchor_selection_quality:asq_unique`・`asq_ambiguous` は機械判定が形式のみで anchor 一意性/曖昧性回避を検証しておらず `over_claim`）。proof `frontier_verification_mismatch`。**重要知見: 形式忠実度軸（structured/patch_protocol）と明白失敗（edit_intent）は妥当に評価できているが、意味依存軸（anchor 選択）は意図通り評価できていない**。全軸カバレッジは live 評価軸を拡張する PR19 後に再実施。
- 2026-06-21: **PR17 自然 fallback パックを実装**。`agent/model_forge/natural_fallback_pack.py`（6 失敗モードを実モデルで誘発し、自然 fallback での安全回復／unreachable provider の正直な unavailable を記録）+ `tests/test_forge_natural_fallback_pack.py`。決定的 5 passed。**8080 実モデル run `fallback_pack_4fb0e81b8664`: 6/6 モード安全処理、proof `natural_fallback_real_eval_passed`**。file_changes_missing / anchor_not_found / unsafe_target_path は誘発＋自然 fallback で回復、provider_unavailable は transport_error で unavailable（passed にしない）。content_missing はモデルが一発成功し正直に「誘発されず・安全」と記録。
- 2026-06-21: **PR16 Anvil 正式 acceptance を実装**。`agent/model_forge/anvil_acceptance.py`（`/v1/models` で Anvil ready 確認 → MethodPipeline を 8080 実モデルへ接続 → 自然 fallback を観測・記録、Safe Apply 境界維持）+ `tests/test_forge_anvil_acceptance.py`。決定的テスト 6 passed、affected 回帰 23 passed。**8080 実モデル（Qwen3.6-35B-A3B）で自然 fallback を実証**: run `anvil_eval_2113a25c169c` — `edit_intent_list`→`content_missing`/`file_changes_missing`(blocked)→`anchored_edit_block`→`anchor_not_found`(failed)→`review_only`(passed) と自然連鎖して回復、proof level `anvil_real_eval_passed`。実バグ発見: 既存 router の fallback trigger は実 failure 語彙（content_missing/file_changes_missing）を取りこぼす → PR18 で是正予定。
- 2026-06-21: **Phase 2 拡張計画を策定**。PR1〜15 マージ済みを確認（HEAD `91e07e32`、`feat/forge-execution-shadow`）。レビュー指摘を踏まえ残作業を PR16(Anvil 正式 acceptance)/PR17(自然 fallback パック)/PR18(MethodRouter v2)/PR19(Multi-model RoleAssignment)/PR20(Active gated)/PR21(フロンティア検証+ベンチマーク健全性)/PR22(Atlas 経路妥当性) として定義。8080 弱 LLM（Qwen3.6-35B-A3B）到達確認済み。AGENTS.md の Active Goal を本拡張計画に同期。
- 2026-06-21: PR15 Atlas plan/patch/verify/repairへmethod/evaluation shadow artifact + Proof Ledger接続を追加。focused 24 passed、8080 real 4-stage比較1 passed（全stage score 1.0 tie、routing変更なし）。Atlas回帰は53 passed / 1 known baseline failure（origin/mainでも再現）を正直に記録。
- 2026-06-21: PR14 Forge Advanced にTwin settings/profile snapshotとread-only context/impact inspectorを統合。旧Twin panel/APIは保持し独立subtabのみ非表示。focused 22 passed、回帰30 passed、ブラウザ実機確認は unavailable。
- 2026-06-21: PR13 fallback graph / Benchmark method comparison / policy recommendation drawer を実装。Node render 15 passed、Forge API/optimizer 回帰 23 passed。recommendation は `advisory_not_applied` で routing を変更せず、ブラウザ実機確認は tooling unavailable と記録。

- 2026-06-21: Phase 0 棚卸し完了（current_status.md）。本計画策定。実装は PR1 から着手予定（ユーザー指示によりここで一旦停止）。
- 2026-06-21: PR1 Method 中核契約を実装。focused 9 passed、既存回帰 25 passed、syntax 成功。localhost:8080 の Qwen3.6-35B-A3B による契約レビューは `VERDICT: PASS`。proof level は `method_contract_present`。
- 2026-06-21: PR2 Method schema をadditive拡張。旧 `forge.v1` payload互換、strict DTO、新radar表現を検証（focused 28 passed、回帰31 passed、syntax成功）。localhost:8080 LLMレビューは `VERDICT: PASS`。
- 2026-06-21: PR3 構造化adapter 3種とcontent-addressed artifact store、deterministic `atlas_file_changes.v1` compilerを実装。focused 27 passed、Safe Apply/Forge回帰60 passed。localhost:8080実モデル出力をedit intentから安全な非適用patchへ変換成功。
- 2026-06-21: PR4 AnchoredEditBlock / UnifiedDiff / DeterministicTextPatch / ReviewOnly / RepairCompass adaptersを実装。focused 36 passed、回帰60 passed。localhost:8080実モデルのanchored blockを非適用patchへ変換成功。
- 2026-06-21: PR5 MethodPipelineを実装。trigger fallback、attempt履歴、unavailable、bounded retry、authority hard-failを検証（focused 34 passed、回帰49 passed）。forced schema failureからlocalhost:8080実モデルedit intentへのfallback成功。
- 2026-06-21: PR6 MethodRouterをExecutionPolicySelectorへ添付。RouteMatrix権限を維持し、弱点・失敗回数に応じたmethod/policyを選択（focused 23 passed、回帰50 passed）。localhost:8080実モデルでweak-profile route→method→pipeline成功。
- 2026-06-21: PR7 method/abstraction/fallback/safety評価8軸と通常/adversarialケースを追加。focused 19 passed、回帰34 passed。localhost:8080単一structured fidelityケースはsemantic不一致でfailed（正式dimension scoreは未算出）。
- 2026-06-21: PR8 evaluation cases/run/rerun/optimize/model-profile APIとrun永続化を実装。focused 18 passed、回帰40 passed。PR7のlocalhost:8080実case failureをAPI投入し、failed profileと非適用method previewを確認。
- 2026-06-21: PR9 Forge Twin facadeを追加。既存reversible settings/profileとread-only context/impact inspectorを再利用（focused 11 passed、回帰32 passed）。localhost:8080 advisory reviewは境界明示後 `VERDICT: PASS`。
- 2026-06-21: PR10 OpenAI-compatible real Method runnerと`evaluation/run-live`を追加。focused 17 passed、provider/API回帰49 passed。localhost:8080 run `forge_eval_ad0e5883f8ce` は実行・証跡保存に成功し、edit-intent品質2ケースはfailed/score 0.0と正直に記録。
- 2026-06-21: PR11 evidence-backed optimizerとRoleAssignment、method-aware Loadoutを追加。focused 14 passed、回帰32 passed。実run profileからedit-intent/anchored/review-only構成の非適用previewを生成。
- 2026-06-21: PR12 Arena candidate drawerと外部ライブラリ無しSVG radar（5 filter、unavailable専用表示）を追加。Node render 11 passed、API/optimizer回帰23 passed。実ブラウザ制御はunavailable。
