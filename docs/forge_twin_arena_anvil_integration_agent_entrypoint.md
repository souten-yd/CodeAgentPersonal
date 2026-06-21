# Forge / Twin / Arena / Anvil 統合改修 — Agent Entrypoint（Codex 引き継ぎ）

このファイルだけ読めば着手できる。`AGENTS.md` の Active Goal がここを指している。

## 0. これは何か

Forge を「モデル評価・実行経路選択・MethodVariant 選択・Loadout 管理」の司令塔にする統合改修トラック。中核は欠落している **Method 層**（`MethodVariant` / `MethodAdapter` / `MethodRouter` / `MethodPipeline`）の新設と、Arena radar・弱 LLM 補強・Anvil 実評価。

元指示書の要点: **Route と MethodVariant を分離する**／**Arena にレーダーチャート**／**構造化出力が苦手なモデルを切り捨てず `edit_intent_list` に逃がす**。

## 1. まず読む順番

1. 本ファイル
2. `docs/forge_twin_arena_anvil_integration_plan.md` — 16 PR 項目の分割・依存・受け入れ基準・進捗テーブル（**着手前後に必ず更新**）
3. `docs/forge_twin_arena_anvil_integration_current_status.md` — Phase 0 棚卸し（既存実装の分類、削除禁止リスト、命名衝突）

## 2. 作業フロー（項目=1PR）

ユーザーはこのトラックで **項目ごとの PR 作成・マージを承認済み**（2026-06-21、PR #1960 で計画をマージ）。

各項目について:

1. `plan.md` の次の pending 項目を選ぶ（依存が満たされた最小 ID）。
2. 実コードを確認（置き換えず統合・拡張）。
3. ブランチ `feat/forge-method-<slug>` を切る。
4. 最小の垂直スライスを実装 + テスト追加。
5. テスト実行（下記コマンド）。
6. `plan.md` 進捗テーブルと進捗ログを更新。current_status も該当箇所を更新。
7. 該当ファイルのみ `git add`（**`git add -A` 禁止**: `venv_sys/` `ca_data/` は数 GB の未追跡ディレクトリ。blanket add すると push が remote に拒否される）。
8. commit → push → `gh pr create` → `gh pr merge --merge --delete-branch`。
9. main に戻り `git pull --ff-only`。

## 3. テスト実行

```bash
venv_sys/Scripts/python.exe -m pytest -q tests/<file>.py
```

確認済み: `venv_sys/Scripts/python.exe -m pytest -q tests/test_execution_policy_route_preference.py` → 4 passed。Python 3.11.9。pytest はリポジトリルートから実行。

新規テストは `tests/test_forge_method_*.py` 等の命名で `tests/` に置く。

## 4. 守る不変条件（hard）

- `unavailable` は `passed` ではない／score 平均にも混ぜない（`eval_packs.py` / `candidate_evaluator.py` / `profile_store.py` が一貫してこれを守っている。新コードも踏襲）。
- strict schema（`extra="forbid"`）。DTO 拡張は**正式フィールド追加 + デフォルト値 + 後方互換テスト**。既存 JSON が読めること。
- Safe Apply 境界を壊さない。Arena は非適用・raw 保存のみ・`adoption_state=not_applied` 固定。
- remote publish / PR / push / merge は承認必須（このトラックは承認済み）。test・gate 弱体化禁止、stale test 自動削除禁止。
- mock / synthetic を real evidence と主張しない。focused テストのみで `acceptance_complete` としない。

## 5. ⚠ 命名衝突（最重要の落とし穴）

`agent/model_forge/decomposition_policy.py` は**既存・production 接続済み**で、意味は「**ファイル分割サイズ**ポリシー」（`DecompositionPolicy(tier, max_file_lines, prefer_split, max_source_files)`、tier=frontier/standard/weak、planner プロンプトに反映）。

元指示書の `DecompositionPolicy`（`none|light|narrow_slice|micro_patch_only|...` という**タスク分解戦略 enum**）とは**別物**。新規 enum は `TaskDecompositionPolicy` 等の別名で新設し、既存ファイルを破壊しない。

## 6. 既存の土台（再利用する。新規作成しない）

| 既存 | 役割 |
|---|---|
| `agent/model_forge/route_taxonomy.py` | `ForgeRoute`(11種) — 開発経路。MethodVariant とは別軸 |
| `agent/model_forge/route_matrix.py` | `ChangeClass`→safe候補→route。**安全上位権限。MethodRouter は override しない** |
| `agent/model_forge/execution_policy.py` | `ExecutionPolicySelector` — ここに method 添付を統合（PR6） |
| `agent/model_forge/schema.py` | Forge DTO（strict）。`ForgeExecutionRequest/Result` `ArenaCandidate` `CandidateScore` 拡張（PR2） |
| `agent/model_forge/arena_runner.py` | 非適用 model×route 実行 + raw 保存。method metadata 追加（PR2/12） |
| `agent/model_forge/eval_packs.py` | capability 8軸の機械採点。新軸/ケース追加（PR7） |
| `agent/model_forge/capability_scoring.py` | pack→ProfileStore→`ModelCapabilityProfile` |
| `agent/twin_control_plane/contracts.py` | `ExecutionPolicy` `TwinInjectionLevel` `InstructionStyle` `ModelCapabilityMode` — method 拡張（PR2） |
| `app/api/forge.py` | Forge API。`/api/forge/evaluation/*`(PR8) `/api/forge/twin/*`(PR9) 追加 |
| `web/js/forge.js` | Forge UI。radar / fallback graph / method 比較 / Advanced 統合（PR12-14） |
| providers: `local_openai_compatible.py`(llama.cpp:8080/LM Studio:1234) `openrouter_*` | 実 LLM source（PR10） |

capability 既存8軸: impact_analysis, contract_preservation, test_generation, stale_test_judgment, flag_reasoning, repair_discipline, evidence_discipline, large_file_editing。

## 7. PR 一覧（plan.md と同期。PR1〜15 マージ済み。次の着手 = PR16）

1〜15 はマージ済み: method 契約 DTO → schema 拡張 → adapters → MethodPipeline → MethodRouter 統合 → 評価軸/ケース → 評価 API → Twin facade → 実 LLM runner → optimizer/loadout → UI(radar/fallback/Advanced) → 実行統合(shadow)。

**Phase 2（残作業、次の着手 = PR16）**: 16. Anvil 正式 acceptance → 17. 自然 fallback パック → 18. MethodRouter v2 → 19. Multi-model RoleAssignment → 20. Active gated 統合 → 21. 全評価軸の弱 LLM 結果をフロンティア検証 + ベンチマーク健全性 → 22. Atlas 経路妥当性検証。

依存・受け入れ基準・詳細は `plan.md` の「拡張 PR 一覧（弱 LLM 補強の完成形 — Phase 2）」参照。§8 は PR1 の歴史的スペック（着手済み）。

## 8. PR1 着手スペック（feat/forge-method-contracts）

最初の一手を曖昧さなく示す。**pure DTO のみ。実行ロジック・配線なし**（proof level = `method_contract_present`）。

新規 `agent/model_forge/method_taxonomy.py`:
- `MethodVariant(StrEnum)`: `structured_patch_json` / `patch_dsl_json` / `edit_intent_list` / `anchored_edit_block` / `unified_diff` / `tool_call_patch` / `deterministic_text_patch` / `deterministic_ast_patch` / `review_only` / `test_plan_only` / `repair_compass_steps`

新規 `agent/model_forge/method_contracts.py`（pydantic、`model_config = ConfigDict(extra="forbid")`、`schema.py` の `ForgeModel` を踏襲）:
- `MethodRequest`: request_id, route(ForgeRoute), method_variant(MethodVariant), model_id, provider_id, task_category, change_class, goal, context_package_ref, twin_brief_ref, allowed_refs, forbidden_refs, output_contract, verification_contract, abstraction_level="concrete_steps", decomposition_policy="narrow_slice", risk_level="medium", metadata
- `MethodResult`: request_id, method_variant, status(Literal["passed","failed","unavailable","blocked"]), raw_output_ref, parsed_output_ref, patch_ref, edit_intent_ref, proposal_ref, evidence_refs, errors, blocked_reasons, unavailable_reasons, latency_ms, token_usage, contract_valid=False, safe_apply_ready=False, requires_human_review=False
- `MethodAdapter(Protocol)`: `variant`; `prepare_prompt(request)->CompiledPrompt`; `parse_output(request, raw_output)->MethodResult`; `compile_patch(request, result)->MethodResult`; `verify_contract(request, result)->MethodResult`（`CompiledPrompt` は最小 DTO として本 PR で定義: prompt_text, system_text="", metadata）
- `MethodRegistry`: `register(adapter)`, `get(variant)->MethodAdapter`, `supports(variant)->bool`
- `FallbackStep`: method_variant, reason="", max_attempts=1, trigger_on(list[str]), modifies_request(dict)
- `MethodChain`: chain_id, primary(MethodVariant), fallbacks(list[FallbackStep]), stop_on=["passed"], hard_fail_on(list[str])
- `MethodPipelineResult`: chain_id, final_status, selected_method(MethodVariant), attempts(list[MethodResult]), final_patch_ref, final_proposal_ref, evidence_refs, blocked_reasons, fallback_reasons

新規テスト `tests/test_forge_method_contracts.py`:
- MethodVariant enum 値テスト
- 各 DTO の構築 + `extra="forbid"` 拒否テスト
- MethodRegistry の register/get/supports dispatch
- `MethodResult(status="unavailable")` が passed と区別される（不変条件）

受け入れ: 上記テストが通る。既存テスト無回帰（`pytest -q tests/test_forge_api.py tests/test_execution_policy_route_preference.py`）。配線・API 変更なし。

完了したら plan.md の PR1 行を ☑ merged にし、進捗ログへ追記。

## 9. 完了報告フォーマット

`AGENTS.md` の Evidence Rules 形式 + 本トラック proof level: `contract_present` → `method_contract_present` → `method_pipeline_component_complete` → `method_router_shadow_connected` → `real_llm_evaluated` → `anvil_real_eval_passed` → `fallback_real_eval_passed` → `acceptance_complete`。Anvil 未評価なら `anvil_real_eval_pending`、`acceptance_complete` にしない。
