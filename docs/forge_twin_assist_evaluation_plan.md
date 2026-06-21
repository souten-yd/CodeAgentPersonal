# Forge Twin Assist Evaluation — Atlas実生成補助評価・追加計画

作成日: 2026-06-21 / Owner: souten

この文書は `docs/forge_twin_arena_anvil_integration_plan.md` の **Phase 3 / H4 完了後に続けて実行する追加計画**。`AGENTS.md` の Active Goal から参照される。既存の Forge / Twin / Arena / Anvil 統合トラックは PR16〜PR22 および H1〜H4 まで進んでおり、次の未解決テーマは「モデル単体評価ではNGでも、Atlas実生成経路に入る Twin 注入補助でどれだけ救えるか」を定量評価し、モデルごとに補助レベルを変えることである。

---

## 0. 現状評価

### 実装済み・再利用する土台

- `agent/model_forge/method_taxonomy.py`: MethodVariant / Method層は存在する。
- `agent/model_forge/method_router.py`: profileに応じて MethodVariant / fallback / decomposition / context_package を選ぶ。
- `agent/model_forge/execution_policy.py`: ExecutionPolicySelector が route / method / Twin injection / gates を組み立てる。
- `agent/twin_control_plane/pipeline_integration.py`: ExecutionPolicy + TwinBrief + compiled instruction + Safe-Edit Briefing を組み立てる。
- `agent/twin_control_plane/patch_injection.py`: Atlas patch生成へ `twin_generation_hints` を注入する。
- `agent/atlas_patch_proposal_service.py`: `twin_control_section` を生成system promptへ合成し、既存ファイルにはsurgical editsを促す。
- `agent/model_forge/real_method_runner.py`: 実LLMに対するMethodAdapter単体評価ができる。
- `agent/model_forge/capability_rescue.py`: 全NG時の救出ラダーがある。

### 現状の不足

1. Forge評価は主に **MethodAdapter単体** の能力評価であり、Atlas実生成経路における Twin注入効果を直接測っていない。
2. 実生成では Twin instruction / Safe-Edit Briefing / impact / current file content が入るが、baselineとの差分、lift、harmを保存していない。
3. `large_file_editing` が弱いモデルに対して、Twinが編集箇所をslot化し、LLMにanchor生成をさせない手法は未実装。
4. `edit_intent_quality` が弱いモデルでも、現状promptやfallbackには old_string/new_string / insert_after anchor をLLMに返させる箇所が残る。
5. H4の rescue plan は計画判断としては存在するが、ExecutionPolicySelector / MethodRouter / Atlas実生成経路への本接続は後続。
6. モデルごとに「Twin注入なしではNGだが、Twin補助ありなら使える」かをForge UI/Arenaで見える形にできていない。

### 判断

この追加計画では、Forgeを「モデル単体評価」から一段進め、**Atlas実生成経路込みの実効コード生成性能** を評価する。特に弱LLMについて、Twin注入レベルごとの改善量を測り、ProfileStoreに推奨補助レベルを保存し、MethodRouter / ExecutionPolicy がそれを利用できるようにする。

---

## 1. 目的

同一モデル・同一課題に対して以下をA/B評価する。

1. Twin注入なし baseline
2. Twin policy only
3. constraints + refs
4. impact + Safe-Edit Briefing
5. strict TwinBrief
6. Twin-localized slot
7. Twin deterministic anchor

評価結果から、モデルごとに以下を決める。

- 推奨 `twin_injection_level`
- 推奨 `TwinAssistMode`
- 避けるべき `MethodVariant`
- 推奨 fallback chain
- large file / edit intent / cross-file / contract preservation での補助効果
- Twin注入が逆効果になるharm条件

---

## 2. 新規taxonomy

新規ファイル:

```text
agent/model_forge/twin_assist_taxonomy.py
```

追加:

```python
from enum import StrEnum

class TwinAssistMode(StrEnum):
    NONE = "none"
    POLICY_ONLY = "policy_only"
    CONSTRAINTS_AND_REFS = "constraints_and_refs"
    IMPACT_AND_SAFE_EDIT = "impact_and_safe_edit"
    STRICT_TWIN_BRIEF = "strict_twin_brief"
    TWIN_LOCALIZED_SLOT = "twin_localized_slot"
    TWIN_DETERMINISTIC_ANCHOR = "twin_deterministic_anchor"
```

意味:

- `NONE`: baseline。Twin注入なし。
- `POLICY_ONLY`: route / method / hard constraintsのみ。
- `CONSTRAINTS_AND_REFS`: allowed_refs / forbidden_refs / contracts / required_testsまで。
- `IMPACT_AND_SAFE_EDIT`: Project Twin impact / Safe-Edit Briefing / dependent files / recommended testsを含む。
- `STRICT_TWIN_BRIEF`: 弱LLM向けに編集許可範囲・禁止範囲・証跡・テスト・出力形式を強制。
- `TWIN_LOCALIZED_SLOT`: Twin/ASTで編集slotを決め、LLMはslot内コードだけ返す。
- `TWIN_DETERMINISTIC_ANCHOR`: anchor/rangeはAtlas側が決め、LLMにanchorを選ばせない。

---

## 3. 新規評価軸

新規ファイル候補:

```text
agent/model_forge/twin_assist_eval_packs.py
```

追加dimension:

```python
TWIN_ASSIST_DIMENSIONS = [
    "twin_assist_lift",
    "twin_instruction_compliance",
    "safe_edit_briefing_utilization",
    "twin_localization_fit",
    "slot_fill_quality",
    "deterministic_anchor_compliance",
    "large_file_rescue_success",
    "cross_file_consistency_with_twin",
    "contract_preservation_with_twin",
    "test_targeting_with_twin",
]
```

評価方針:

- `twin_assist_lift`: assisted_score - baseline_score。
- `twin_instruction_compliance`: hard constraints / allowed_refs / forbidden_refs / required_tests を守るか。
- `safe_edit_briefing_utilization`: dependent files / impacted refs / recommended tests を反映できるか。
- `twin_localization_fit`: Twinが指定した file/symbol/slot を使えるか。
- `slot_fill_quality`: slot内の必要コードだけを返せるか。
- `deterministic_anchor_compliance`: Atlasが決めたanchor/rangeに従い、勝手に別anchorへ逸脱しないか。
- `large_file_rescue_success`: large_file_editingが弱いモデルをTwin slotで救えるか。
- `cross_file_consistency_with_twin`: 存在しない関数・ファイル名・exportを捏造しないか。
- `contract_preservation_with_twin`: public interface / API / UI state / schema を壊さないか。
- `test_targeting_with_twin`: TwinProof / Safe-Edit Briefing の recommended tests をverification planに反映するか。

---

## 4. 新規DTO

新規ファイル:

```text
agent/model_forge/twin_assist_contracts.py
```

### TwinAssistCase

```python
class TwinAssistCase(ForgeModel):
    case_id: str
    title: str
    dimension: str
    task_category: str = "codegen"
    change_class: ChangeClass = ChangeClass.MEDIUM
    target_files: list[str] = []
    project_fixture_id: str = ""
    user_goal: str
    expected_behavior: str = ""
    baseline_allowed: bool = True
    assist_modes: list[TwinAssistMode] = []
    required_refs: list[str] = []
    forbidden_refs: list[str] = []
    expected_symbols: list[str] = []
    expected_tests: list[str] = []
    metadata: dict = {}
```

### TwinAssistRunRequest

```python
class TwinAssistRunRequest(ForgeModel):
    provider_id: str
    model_id: str
    base_url: str = "http://127.0.0.1:8080"
    case_ids: list[str] = []
    assist_modes: list[TwinAssistMode] = []
    run_baseline: bool = True
    project_fixture_root: str = "ca_data/model_forge/twin_assist_fixtures"
    timeout_seconds: float = 120.0
    source_mode: SourceMode = SourceMode.LOCAL_ONLY
    privacy_sensitive: bool = True
```

### TwinAssistAttemptResult

```python
class TwinAssistAttemptResult(ForgeModel):
    case_id: str
    assist_mode: TwinAssistMode
    provider_id: str
    model_id: str
    status: str  # passed | failed | unavailable | blocked
    score: float | None = None
    patch_content_available: bool = False
    semantic_passed: bool = False
    verification_passed: bool = False
    touched_files: list[str] = []
    forbidden_touched: list[str] = []
    implemented_symbols: list[str] = []
    verification_cases: list[str] = []
    latency_ms: int = 0
    token_usage: dict = {}
    raw_output_ref: str = ""
    proposal_ref: str = ""
    evidence_refs: list[str] = []
    blocked_reasons: list[str] = []
    failed_reasons: list[str] = []
    unavailable_reasons: list[str] = []
```

### TwinAssistCaseComparison

```python
class TwinAssistCaseComparison(ForgeModel):
    case_id: str
    baseline: TwinAssistAttemptResult | None = None
    assisted: list[TwinAssistAttemptResult] = []
    best_assist_mode: TwinAssistMode | None = None
    best_score: float | None = None
    lift: float | None = None
    harm_detected: bool = False
    recommendation: str = ""
    reasons: list[str] = []
```

### TwinAssistEvaluationReport

```python
class TwinAssistEvaluationReport(ForgeModel):
    run_id: str
    provider_id: str
    model_id: str
    status: str
    comparisons: list[TwinAssistCaseComparison]
    aggregate_scores: dict[str, float]
    recommended_twin_injection_level: int
    recommended_assist_modes: list[TwinAssistMode]
    recommended_method_overrides: dict[str, str]
    recommended_fallback_chain: list[str]
    evidence_refs: list[str]
    created_at: str
```

---

## 5. 評価fixture

追加場所:

```text
tests/fixtures/twin_assist/
ca_data/model_forge/twin_assist_fixtures/  # 実行時生成物はgitignore前提
```

最低ケース:

1. `large_existing_file_insert`
   - 200行以上の既存ファイルに小機能を追加。
   - baselineではanchor_not_found / broad rewrite / no contentが起きやすい。
   - Twin slotありで改善するか確認。

2. `cross_file_api_consistency`
   - 実装ファイルとテストファイルを用意。
   - 存在しない関数やファイル名を捏造しないか。

3. `public_contract_preservation`
   - 既存関数signature/exportを変えず内部だけ修正。

4. `edit_intent_rescue`
   - edit_intent_qualityが弱いモデルに、old/new anchorを書かせずslot fillで改善できるか。

5. `dependency_aware_test_selection`
   - dependent tests / recommended tests をverification planに反映するか。

---

## 6. Runner

新規ファイル:

```text
agent/model_forge/twin_assist_runner.py
```

責務:

1. fixture projectを一時workspaceへコピーする。
2. assist_modeごとにTwin注入量を変える。
3. `AtlasPatchProposalService.propose_for_item` を呼び、**実際のAtlas patch生成経路**を評価する。
4. 生成proposalを解析する。
5. patch content / semantic_validation / verification_plan / touched_files を評価する。
6. baselineとassistedの差分を比較する。
7. evidenceを `ca_data/model_forge/twin_assist_runs/<run_id>/` に保存する。

重要:

- MethodAdapter単体ではなくAtlas実生成経路を通す。
- 実ファイル適用はしない。Safe Apply前のproposal評価まで。
- unavailableをpassedにしない。
- mockだけでacceptance_completeにしない。
- Twinで悪化した場合はharmとして記録する。

疑似コード:

```python
class TwinAssistRunner:
    def run(self, request: TwinAssistRunRequest) -> TwinAssistEvaluationReport:
        run_id = "twin_assist_" + uuid4().hex[:12]
        cases = load_twin_assist_cases(request.case_ids)
        comparisons = []
        for case in cases:
            baseline = self._run_one(case, TwinAssistMode.NONE, request, run_id) if request.run_baseline else None
            assisted = [self._run_one(case, mode, request, run_id) for mode in selected_modes(request)]
            comparisons.append(compare_case(case, baseline, assisted))
        return aggregate_report(run_id, request, comparisons)
```

---

## 7. Twin Assist Compiler

新規ファイル:

```text
agent/model_forge/twin_assist_compiler.py
```

目的:

既存 `build_twin_pipeline_evidence` / `compile_model_instruction` の出力を、AssistModeごとに絞る。

```python
def compile_assist_metadata(*, assist_mode: TwinAssistMode, evidence: dict, case: TwinAssistCase) -> dict:
    ...
```

- `NONE`: `{}`
- `POLICY_ONLY`: route / method / hard constraintsのみ
- `CONSTRAINTS_AND_REFS`: allowed_refs / forbidden_refs / contracts / required_tests
- `IMPACT_AND_SAFE_EDIT`: Safe-Edit Briefing / dependent files / impacted refs / tests
- `STRICT_TWIN_BRIEF`: 弱LLM向け明示制約
- `TWIN_LOCALIZED_SLOT`: TwinEditSlotをmetadataへ入れる
- `TWIN_DETERMINISTIC_ANCHOR`: deterministic anchor resolverの結果をmetadataへ入れる

---

## 8. Twin-localized slot patch

新規ファイル:

```text
agent/model_forge/twin_edit_slots.py
agent/model_forge/twin_slot_adapter.py
```

### TwinEditSlot

```python
class TwinEditSlot(ForgeModel):
    slot_id: str
    file: str
    symbol_ref: str = ""
    operation: str  # replace_range | insert_after | insert_before | replace_symbol_body
    start_line: int | None = None
    end_line: int | None = None
    anchor_text: str = ""
    anchor_occurrences: int = 0
    max_new_lines: int = 80
    required_behavior: str = ""
    forbidden_behavior: list[str] = []
    required_tests: list[str] = []
    confidence: float = 0.0
    evidence_refs: list[str] = []
```

### TwinEditSlotResolver MVP

- target_filesが1つなら対象。
- PythonはASTで関数/class範囲を抽出。
- JS/TSは簡易正規表現でfunction/class/export範囲を抽出。
- goalとsymbol名のキーワード一致で候補を出す。
- 見つからない場合は安全な挿入点候補をslot化。
- `anchor_text` は `current_content.count(anchor_text) == 1` の場合のみ採用。
- occurrence != 1ならLLMへ使わせず、review_onlyまたはfallback。

### TwinLocalizedSlotPatchAdapter

- MethodAdapterとして追加。
- LLMにはold_string/new_string/anchorを作らせない。
- LLMはslot内のコード断片だけを返す。
- patch化はdeterministic compilerが行う。
- 直接applyしない。Proposal / Safe Apply境界を維持。

---

## 9. MethodRouter / ExecutionPolicy接続

`agent/model_forge/method_taxonomy.py` に追加:

```python
TWIN_LOCALIZED_SLOT_PATCH = "twin_localized_slot_patch"
TWIN_SYMBOL_WINDOW_PATCH = "twin_symbol_window_patch"
TWIN_DETERMINISTIC_ANCHOR_PATCH = "twin_deterministic_anchor_patch"
TWIN_SLOT_FILL_ONLY = "twin_slot_fill_only"
```

`agent/model_forge/method_router.py` ルール追加:

```python
large_weak = score("large_file_editing") < 0.55
edit_intent_weak = score("edit_intent_quality") < 0.55
structured_strong = score("structured_output_fidelity") >= 0.7
patch_protocol_strong = score("patch_protocol_fidelity") >= 0.7
anchor_strong = score("anchor_selection_quality") >= 0.7

if change_class in {LARGE, CRITICAL} and large_weak:
    if structured_strong or patch_protocol_strong:
        primary = TWIN_LOCALIZED_SLOT_PATCH
    else:
        primary = TWIN_SLOT_FILL_ONLY
    avoid EDIT_INTENT_LIST when edit_intent_weak
```

推奨fallback:

```text
patch_dsl_json
  -> twin_localized_slot_patch
  -> twin_deterministic_anchor_patch
  -> review_only
```

大規模編集では:

```text
twin_localized_slot_patch
  -> twin_deterministic_anchor_patch
  -> review_only
```

`ExecutionPolicy` に追加候補:

```python
twin_assist_mode: TwinAssistMode | None = None
twin_assist_reason: list[str] = Field(default_factory=list)
twin_assist_expected_lift: float | None = None
twin_slot_required: bool = False
deterministic_anchor_required: bool = False
avoid_method_variants: list[MethodVariant] = Field(default_factory=list)
```

---

## 10. ProfileStore拡張

モデルごとにTwin補助効果を保存する。

候補フィールド:

```python
twin_assist_scores: dict[str, float] = Field(default_factory=dict)
twin_assist_lift: dict[str, float] = Field(default_factory=dict)
recommended_twin_assist_mode: str = ""
recommended_twin_injection_level: int | None = None
twin_assist_evidence_refs: list[str] = Field(default_factory=list)
```

保存例:

```json
{
  "model_id": "Qwen3.6-35B-A3B",
  "dimension_scores": {
    "large_file_editing": 0.4,
    "edit_intent_quality": 0.0
  },
  "twin_assist_scores": {
    "large_file_rescue_success": 0.85,
    "slot_fill_quality": 0.9,
    "deterministic_anchor_compliance": 1.0
  },
  "twin_assist_lift": {
    "large_existing_file_insert": 0.45
  },
  "recommended_twin_assist_mode": "twin_localized_slot",
  "recommended_twin_injection_level": 4
}
```

---

## 11. API

`app/api/forge.py` に追加:

```http
GET /api/forge/twin-assist/cases
POST /api/forge/twin-assist/run
GET /api/forge/twin-assist/runs/{run_id}
POST /api/forge/twin-assist/runs/{run_id}/record-profile
```

注意:

- `record-profile` はProfileStoreへ観測として記録するだけ。
- production routingへ自動反映しない。
- active利用は既存gateに従う。

---

## 12. UI

`web/js/forge.js` に `Twin Assist` セクションを追加する。

表示:

- Provider / Model / Base URL
- Case pack: Quick / Large-file / Cross-file / Contract / Full
- Assist modes checkbox
- Run Twin Assist Eval
- Results table:
  - case
  - baseline score
  - best assisted score
  - lift
  - best assist mode
  - harm
  - latency
  - tokens
  - recommendation
- Detail drawer:
  - baseline raw output
  - assisted raw output
  - touched files
  - forbidden touched
  - Twin instruction snippet
  - Safe-Edit Briefing summary
  - slot info
  - evidence refs

Model profile cardには以下を表示:

```text
Recommended Twin Assist:
- injection_level
- assist_mode
- avoid methods
- fallback chain
- reasons
```

---

## 13. 実装順序

| # | ブランチ | 内容 | 状態 |
|---|---|---|---|
| TA1 | feat/forge-twin-assist-contracts | taxonomy / DTO / strict schema tests | ☑ completed |
| TA2 | feat/forge-twin-assist-packs | case packs / fixtures / scoring | ☑ completed |
| TA3 | feat/forge-twin-assist-runner | AtlasPatchProposalService実経路を使うbaseline vs assisted runner | ☑ completed |
| TA4 | feat/forge-twin-localized-slot | TwinEditSlot / resolver / slot patch adapter MVP | ☑ completed |
| TA5 | feat/forge-twin-assist-policy | MethodRouter / ExecutionPolicy / ProfileStore連携 | ☐ pending |
| TA6 | feat/forge-twin-assist-api | `/api/forge/twin-assist/*` API | ☐ pending |
| TA7 | feat/forge-twin-assist-ui | Forge UI: Twin Assist tab / result table / drawer / profile recommendation | ☐ pending |
| TA8 | feat/forge-twin-assist-real-eval | 8080実モデルで最低4ケース評価、evidence保存、current_status更新 | ☐ pending |

---

## 14. Acceptance Criteria

- ForgeでTwin Assist Evaluationを実行できる。
- baseline / assisted / lift / harm が保存・表示される。
- 評価はMethodAdapter単体だけでなく `AtlasPatchProposalService.propose_for_item` 実経路を通す。
- Twin注入レベルごとの差が記録される。
- `large_file_editing` / `edit_intent_quality` 弱点に対し、Twin slot / deterministic anchor の改善効果を測れる。
- ProfileStoreに推奨assist mode / injection levelが保存される。
- MethodRouter / ExecutionPolicy が推奨を利用できる。
- Anvil/8080実モデルで最低ケースを評価し、証跡を保存する。
- Safe Apply / approval / unavailable honesty を維持する。
- Twinありで悪化した場合はharmとして記録する。

---

## 15. Safety Invariants

- 評価実行で直接ファイル適用しない。
- Safe Applyを迂回しない。
- remote publish / PR作成 / push はしない。
- unavailableをpassedにしない。
- mockだけでacceptance_completeにしない。
- TwinなしよりTwinありで悪化した場合はharmとして記録する。
- ProfileStore反映はobservation/recommendationであり、active切替は既存gateに従う。
- review_only / human_review_required は「成功」ではなく degraded safe outcome として扱う。

---

## 16. 完了後の期待状態

今回のようなモデルプロファイル:

```text
structured_output_fidelity=1.0
patch_protocol_fidelity=1.0
anchor_selection_quality=1.0
edit_intent_quality=0.0
large_file_editing=0.4
```

に対して、Forgeは以下のように推奨できる。

```json
{
  "recommended_twin_injection_level": 4,
  "recommended_assist_mode": "twin_localized_slot",
  "avoid_method_variants": ["edit_intent_list"],
  "recommended_fallback_chain": [
    "patch_dsl_json",
    "twin_localized_slot_patch",
    "twin_deterministic_anchor_patch",
    "review_only"
  ],
  "reason": [
    "structured and patch protocol are strong",
    "edit intent generation is weak",
    "large file editing is weak",
    "Twin slot localization improves large-file success",
    "deterministic anchors avoid LLM anchor selection"
  ]
}
```

---

## 17. 証跡フォーマット

各TA完了時は `AGENTS.md` の Evidence Rules に加え、以下を current_status に記録する。

```text
Completed package:
Status:
Changed modules/files:
Behavior implemented:
Focused tests:
Syntax checks:
Affected tests:
Real model evidence:
Baseline score:
Assisted score:
Lift:
Harm cases:
Best assist mode:
Profile recommendation:
Atlas UI evidence:
Unavailable checks:
Safety invariants:
Remaining gaps:
Next package:
Blocker:
Proof level:
```

Proof level候補:

```text
twin_assist_contract_present
→ twin_assist_runner_component_complete
→ twin_slot_patch_component_complete
→ twin_assist_profile_recommendation_ready
→ twin_assist_real_eval_passed
→ twin_assist_policy_connected
```
