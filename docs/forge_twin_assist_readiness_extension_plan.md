# Forge Twin Assist Evaluation — 追加強化設計（TA9〜TA12）

作成日: 2026-06-21 / Owner: souten

この文書は `docs/forge_twin_assist_evaluation_plan.md` の **TA1〜TA8 完了後に続けて実行する追加強化計画**。前回計画で「Atlas実生成経路におけるTwin注入補助の効果」を評価できるようにした後、さらに以下を評価可能にする。

1. Twin本体の実装度合い・信頼度
2. route × method × assist の組み合わせ最適化
3. Twin slot / deterministic anchor の品質
4. proposal生成後の Safe Apply dry-run / focused tests / post-apply Twin gate まで含むE2E評価

この追加計画は、単に「Twinが効いたか」ではなく、**なぜ効いたか / Twinのどの部分が足りないか / どの経路と補助の組み合わせが最適か / 適用後も壊れないか** を評価するためのもの。

---

## 0. 前提

先行計画:

```text
docs/forge_twin_assist_evaluation_plan.md
```

先行TA1〜TA8で期待される状態:

- Twin Assist Mode taxonomy / DTO が存在する。
- baseline vs assisted 評価が可能。
- AtlasPatchProposalService実経路を通した評価が可能。
- Twin-localized slot / deterministic anchor MVP がある。
- ProfileStoreへ推奨 Twin assist mode / injection level を保存できる。
- Forge UIで baseline / assisted / lift / harm を確認できる。
- 8080実モデル評価の証跡が保存されている。

この文書のTA9〜TA12は、その後に続く強化項目である。

---

## 1. 追加PR一覧

| # | ブランチ | 内容 | 依存 | 状態 |
|---|---|---|---|---|
| TA9 | `feat/forge-twin-readiness-score` | Twin本体の実装度・信頼度を評価する Readiness Score | TA1〜TA8 | ☐ pending |
| TA10 | `feat/forge-route-method-assist-matrix` | route × method × assist × fallback の組み合わせ評価 | TA1〜TA9 | ☐ pending |
| TA11 | `feat/forge-twin-slot-quality-gates` | Twin slot / deterministic anchor の品質ゲート・confidence calibration | TA4, TA9 | ☐ pending |
| TA12 | `feat/forge-twin-assist-postapply-e2e` | proposal→Safe Apply dry-run→focused tests→post-apply Twin gate のE2E評価 | TA1〜TA11 | ☐ pending |

---

## 2. TA9 — Twin Readiness Score

### 2.1 目的

Twin Assist Evaluationは「Twin補助が効いたか」を測る。一方で、Twin本体がどの程度実装・信頼できる状態かは別軸で測る必要がある。

TA9では、Project Twin / Safe-Edit Briefing / impact / symbol resolution / staleness / prompt delivery の実装度合いを数値化する。

### 2.2 新規評価軸

新規ファイル候補:

```text
agent/model_forge/twin_readiness.py
agent/model_forge/twin_readiness_contracts.py
```

追加dimension:

```python
TWIN_READINESS_DIMENSIONS = [
    "twin_snapshot_availability",
    "twin_snapshot_freshness",
    "symbol_resolution_rate",
    "impact_precision",
    "impact_budget_fit",
    "safe_edit_briefing_availability",
    "dependent_file_relevance",
    "recommended_test_relevance",
    "twin_instruction_delivery",
    "twin_instruction_utilization",
    "twin_staleness_detection",
    "twin_harm_rate",
]
```

### 2.3 DTO

```python
class TwinReadinessRequest(ForgeModel):
    project_id: str
    project_path: str
    changed_refs: list[str] = []
    task_category: str = "codegen"
    change_class: ChangeClass = ChangeClass.MEDIUM
    max_depth: int | None = None
    budget: int = 60
    metadata: dict = {}
```

```python
class TwinReadinessSignal(ForgeModel):
    name: str
    status: str  # passed | failed | unavailable | warning
    score: float | None = None
    detail: str = ""
    evidence_refs: list[str] = []
```

```python
class TwinReadinessReport(ForgeModel):
    report_id: str
    project_id: str
    project_path: str
    overall_score: float | None = None
    readiness_level: str  # unavailable | low | medium | high | trusted
    signals: list[TwinReadinessSignal] = []
    recommended_max_assist_mode: str = ""
    recommended_injection_cap: int | None = None
    blocked_reasons: list[str] = []
    warnings: list[str] = []
    evidence_refs: list[str] = []
    created_at: str
```

### 2.4 評価内容

#### twin_snapshot_availability

- Project Twin DB / snapshot が存在するか。
- 存在しない場合は `unavailable`。passedにしない。

#### twin_snapshot_freshness

- ソースmtimeとTwin DB mtimeを比較する。
- ソースの方が新しい場合は stale。
- stale検出できれば warningまたはfailed。

#### symbol_resolution_rate

- target files / changed_refs を symbol refs に展開できた割合。
- `expand_changed_refs_to_symbols` の出力を利用。

#### impact_precision

- impact direct/transitive が0件でも過大でもないか。
- expected dependent filesがfixtureにある場合は一致率を測る。

#### impact_budget_fit

- impactがbudget内に収まるか。
- budget超過時は「広すぎるTwin注入」としてwarning。

#### safe_edit_briefing_availability

- Safe-Edit Briefingが生成できるか。
- emptyの場合は理由を記録。

#### dependent_file_relevance

- dependent files が実際に存在し、target goalと関連するか。
- 初期MVPではfixture期待値ベースでよい。

#### recommended_test_relevance

- recommended tests が実在し、対象変更と関連するか。

#### twin_instruction_delivery

- compiled instructionがpatch生成payload/system promptに届いた証跡があるか。
- `instruction_id`, `brief_id`, `policy_id`, prompt section hash を保存する。

#### twin_instruction_utilization

- 生成proposalがallowed_refs / required_tests / contractsを実際に参照したか。
- 初期MVPではsemantic inspectionでよい。

#### twin_staleness_detection

- 古いTwinをあえて用意したfixtureで、staleを検知しrefreshまたはwarningできるか。

#### twin_harm_rate

- Twin assistありでbaselineより悪化した割合。
- Twinそのものの過剰注入・誤impactの危険信号として保存。

### 2.5 Readiness level

```text
unavailable: snapshotなし / evidenceなし
low: score < 0.4
medium: 0.4 <= score < 0.7
high: 0.7 <= score < 0.9
trusted: score >= 0.9 and no critical warnings
```

### 2.6 推奨制御

Twin readinessが低い場合:

- `TWIN_LOCALIZED_SLOT` を使わない。
- `STRICT_TWIN_BRIEF` をcapする。
- `POLICY_ONLY` または `CONSTRAINTS_AND_REFS` までに留める。
- `review_only` fallbackを厚くする。

Twin readinessが高い場合:

- `IMPACT_AND_SAFE_EDIT` / `TWIN_LOCALIZED_SLOT` / `TWIN_DETERMINISTIC_ANCHOR` を許可。

### 2.7 API

```http
POST /api/forge/twin-readiness/run
GET /api/forge/twin-readiness/reports/{report_id}
```

MVPではTwin Assist API配下でもよい:

```http
POST /api/forge/twin-assist/readiness
```

### 2.8 UI

Forge > Twin Assist detail drawerに追加:

- Twin Readiness Score
- readiness level
- snapshot freshness
- symbol resolution rate
- impact budget
- safe edit briefing availability
- prompt delivery audit
- warnings

### 2.9 Tests

```text
tests/test_forge_twin_readiness.py
```

必須:

- snapshot missing => unavailable, not passed
- stale snapshot => warning/failed
- symbol expansion success rate算出
- impact過大時warning
- compiled instruction delivery証跡あり
- readiness lowならassist mode cap

---

## 3. TA10 — Route × Method × Assist Matrix

### 3.1 目的

TA1〜TA8ではassist modeごとの改善量を測る。TA10ではさらに、route / method / assist / fallback の組み合わせを比較し、タスク種別ごとに最適構成を推定する。

### 3.2 評価単位

```text
route × method_variant × twin_assist_mode × injection_level × fallback_chain
```

全組み合わせ総当たりは重いため、候補生成を行う。

候補例:

```text
patch_dsl_json + impact_and_safe_edit
patch_dsl_json + twin_localized_slot
anchored_edit_block + strict_twin_brief
twin_localized_slot_patch + deterministic_anchor
review_only fallback
```

### 3.3 DTO

```python
class AssistMatrixCandidate(ForgeModel):
    candidate_id: str
    route: ForgeRoute
    method_variant: MethodVariant
    twin_assist_mode: TwinAssistMode
    twin_injection_level: int
    fallback_chain: list[MethodVariant] = []
    context_package_mode: ContextPackageMode
    task_decomposition_policy: TaskDecompositionPolicy
    verification_mode: VerificationMode
    metadata: dict = {}
```

```python
class AssistMatrixResult(ForgeModel):
    candidate_id: str
    case_id: str
    status: str
    score: float | None = None
    lift_vs_baseline: float | None = None
    harm_detected: bool = False
    latency_ms: int = 0
    token_usage: dict = {}
    touched_files: list[str] = []
    blocked_reasons: list[str] = []
    failed_reasons: list[str] = []
    evidence_refs: list[str] = []
```

```python
class AssistMatrixReport(ForgeModel):
    report_id: str
    provider_id: str
    model_id: str
    task_category: str
    change_class: str
    candidates: list[AssistMatrixCandidate]
    results: list[AssistMatrixResult]
    best_candidate_id: str = ""
    recommended_policy_patch: dict = {}
    evidence_refs: list[str] = []
    created_at: str
```

### 3.4 Candidate生成

新規ファイル:

```text
agent/model_forge/assist_matrix.py
```

Candidate生成ルール:

1. RouteMatrixのsafe candidatesのみ使う。
2. MethodRouterの推奨primary/fallbackを候補に含める。
3. TwinAssistEvaluationのbest assist modeを候補に含める。
4. high risk / criticalではreview_only fallback必須。
5. TwinReadiness lowならslot/deterministic anchor候補を除外またはdeprioritize。
6. external providerはlocal_onlyでは除外。

### 3.5 score

```text
final_score = quality_score
            + lift_bonus
            - harm_penalty
            - latency_penalty
            - token_penalty
            - safety_penalty
```

ただし safety violation はscore調整ではなくblocked。

### 3.6 ProfileStore反映

モデル単位だけでなく、以下単位で保存する。

```text
model_id × provider_id × task_category × change_class
```

保存例:

```json
{
  "task_category": "large_existing_file_edit",
  "change_class": "large",
  "best_route": "patch_dsl",
  "best_method_variant": "twin_localized_slot_patch",
  "best_twin_assist_mode": "twin_localized_slot",
  "best_injection_level": 4,
  "fallback_chain": ["twin_deterministic_anchor_patch", "review_only"],
  "evidence_refs": ["assist_matrix_..."]
}
```

### 3.7 API

```http
POST /api/forge/twin-assist/matrix/run
GET /api/forge/twin-assist/matrix/reports/{report_id}
POST /api/forge/twin-assist/matrix/reports/{report_id}/record-profile
```

### 3.8 UI

Forge > Twin Assist > Matrix:

- rows: candidates
- columns: score / lift / harm / latency / tokens / touched files / gates
- best candidate highlighted
- compare drawer: route/method/assist/fallback differences

### 3.9 Tests

```text
tests/test_forge_assist_matrix.py
```

必須:

- RouteMatrix safe candidates以外を使わない
- local_onlyでexternal provider候補を作らない
- harm candidateがbestにならない
- readiness lowならslot系候補がcapされる
- task_category/change_class別にrecommendationが保存される

---

## 4. TA11 — Twin Slot Quality Gates

### 4.1 目的

Twin-localized slotは弱LLM救済の中核だが、slot自体が間違っていると誤編集を誘導する。TA11では slot品質・anchor一意性・範囲妥当性・confidence calibration を評価し、品質が低いslotを実行候補から除外する。

### 4.2 新規評価軸

```python
TWIN_SLOT_QUALITY_DIMENSIONS = [
    "slot_target_correctness",
    "slot_boundary_correctness",
    "anchor_uniqueness",
    "slot_scope_minimality",
    "slot_confidence_calibration",
    "slot_fallback_correctness",
    "slot_mutation_boundary_integrity",
]
```

### 4.3 DTO

```python
class TwinSlotQualityReport(ForgeModel):
    report_id: str
    slot_id: str
    file: str
    symbol_ref: str = ""
    accepted: bool
    score: float | None = None
    findings: list[dict] = []
    blocked_reasons: list[str] = []
    warnings: list[str] = []
    evidence_refs: list[str] = []
```

### 4.4 Gate rules

block:

- `anchor_occurrences != 1`
- target file does not exist
- start_line/end_line outside file bounds
- slot crosses unrelated top-level symbol boundary
- slot overlaps forbidden_refs
- confidence < threshold and no fallback
- slot operation would delete/replace too broad a range
- slot requires direct apply or bypasses Safe Apply

warning:

- slot too large but still within boundary
- no recommended tests
- impact unavailable
- symbol_ref absent but target file unique

### 4.5 Confidence calibration

保存する:

```text
predicted_confidence vs actual_success
```

case単位でslot confidenceが高いのに失敗した場合は calibration gap として記録。

### 4.6 Integration

- `TwinEditSlotResolver` は必ず `TwinSlotQualityGate` を通す。
- gate failedなら `review_only` または non-slot fallback。
- MethodRouterは slot quality report を見てslot系methodを許可/禁止する。

### 4.7 API/UI

API:

```http
POST /api/forge/twin-assist/slots/evaluate
```

UI:

- slot id
- file/symbol
- anchor occurrences
- boundary
- score
- accepted/blocked
- blocked reasons

### 4.8 Tests

```text
tests/test_forge_twin_slot_quality.py
```

必須:

- ambiguous anchor blocks
- duplicate anchor blocks
- out-of-range slot blocks
- too broad range blocks
- forbidden ref overlap blocks
- low confidence without fallback blocks
- safe slot passes
- failed slot falls back to review_only

---

## 5. TA12 — Post-Apply E2E Evaluation

### 5.1 目的

TA1〜TA11では主にproposal生成品質を評価する。TA12では、実生成されたproposalを隔離workspaceでSafe Apply dry-run / isolated applyし、focused testsとpost-apply Twin gateまで通す。

これにより、「生成proposalは良さそう」ではなく、**適用後に本当に壊れていないか** をForge評価で確認する。

### 5.2 評価フロー

```text
Twin Assist candidate selection
  ↓
AtlasPatchProposalService.propose_for_item
  ↓
Safe Apply dry-run / isolated workspace apply
  ↓
focused tests / static checks
  ↓
Twin post-apply gate
  ↓
Proof Ledger entry
  ↓
baseline vs assisted E2E comparison
```

### 5.3 DTO

```python
class PostApplyE2ERequest(ForgeModel):
    provider_id: str
    model_id: str
    base_url: str
    case_ids: list[str] = []
    assist_matrix_report_id: str | None = None
    apply_mode: str = "isolated"  # isolated only for MVP
    run_tests: bool = True
    timeout_seconds: float = 180.0
```

```python
class PostApplyE2EAttempt(ForgeModel):
    case_id: str
    candidate_id: str
    assist_mode: str
    status: str  # passed | failed | unavailable | blocked
    proposal_score: float | None = None
    apply_status: str = ""
    changed_files: list[str] = []
    focused_tests: list[str] = []
    test_status: str = ""
    post_apply_twin_status: str = ""
    proof_ledger_ref: str = ""
    rollback_available: bool = False
    blocked_reasons: list[str] = []
    failed_reasons: list[str] = []
    unavailable_reasons: list[str] = []
    evidence_refs: list[str] = []
```

```python
class PostApplyE2EReport(ForgeModel):
    report_id: str
    provider_id: str
    model_id: str
    attempts: list[PostApplyE2EAttempt]
    aggregate_scores: dict[str, float]
    recommended_policy_patch: dict = {}
    evidence_refs: list[str] = []
    created_at: str
```

### 5.4 Safety

- 実projectへ直接applyしない。
- isolated workspace / temp copyのみ。
- remote publishしない。
- destructive actionは禁止。
- Safe Apply executorのdry-runまたはsnapshot/rollbackを必須にする。
- tests unavailableはunavailableでありpassedではない。

### 5.5 Post-apply gate

既存 `evaluate_twin_post_apply` / Proof Ledger系を再利用する。

記録:

- changed_files
- verification evidence
- blocked reasons
- repair reasons
- proof requirements
- unavailable evidence

### 5.6 API

```http
POST /api/forge/twin-assist/e2e/run
GET /api/forge/twin-assist/e2e/reports/{report_id}
POST /api/forge/twin-assist/e2e/reports/{report_id}/record-profile
```

### 5.7 UI

Forge > Twin Assist > E2E:

- candidate
- proposal score
- apply status
- focused tests
- post-apply Twin gate
- proof ledger
- rollback
- final status

### 5.8 Tests

```text
tests/test_forge_twin_assist_postapply_e2e.py
```

必須:

- isolated applyのみ許可
- direct workspace apply拒否
- Safe Apply bypass拒否
- unavailable tests not passed
- post-apply gate failure recorded
- rollback evidence recorded
- baseline vs assisted E2E score computed

---

## 6. 実装順序詳細

### TA9 実装順

1. `twin_readiness_contracts.py`
2. `twin_readiness.py`
3. unit tests
4. API minimal endpoint
5. UI read-only display
6. status doc更新

### TA10 実装順

1. `assist_matrix.py` DTO / candidate generator
2. RouteMatrix safe candidate integration
3. TwinReadiness cap integration
4. matrix scoring
5. ProfileStore recommendation persistence
6. API + tests
7. UI table

### TA11 実装順

1. `twin_slot_quality.py`
2. gate rules
3. TwinEditSlotResolver接続
4. MethodRouter slot permission接続
5. tests
6. UI detail

### TA12 実装順

1. isolated workspace apply harness
2. Safe Apply dry-run / snapshot/rollback接続
3. focused tests runner MVP
4. post-apply Twin gate接続
5. Proof Ledger evidence
6. E2E report / API / UI
7. 8080 real model evidence

---

## 7. 追加Acceptance Criteria

TA9完了:

- Twin snapshot / freshness / symbol resolution / impact / Safe-Edit / prompt delivery を評価できる。
- readiness lowではslot系assistがcapされる。
- unavailableをpassedにしない。

TA10完了:

- route × method × assist の候補比較ができる。
- RouteMatrix安全候補外を使わない。
- model × task_category × change_class の推奨を保存できる。

TA11完了:

- slot / anchor / range の品質ゲートがある。
- ambiguous anchor / broad slot / forbidden overlap をblockする。
- slotが危険な時はreview_only/fallbackへ落ちる。

TA12完了:

- isolated apply / focused tests / post-apply Twin gate までE2E評価できる。
- rollback evidenceを保存する。
- 実projectへ直接applyしない。
- baseline vs assistedのE2E lift/harmが記録される。

---

## 8. 完了後の期待状態

TA1〜TA12完了後、Forgeは以下を評価・推薦できる。

```text
model × task_category × change_class
  -> best route
  -> best method
  -> best twin assist mode
  -> injection level
  -> fallback chain
  -> readiness constraints
  -> slot quality constraints
  -> post-apply E2E evidence
```

つまり、単に「弱LLMが使えるか」ではなく、

```text
この弱LLMは通常のlarge-file editは弱いが、
Twin readinessがhighで、slot qualityがpassし、
twin_localized_slot_patch + deterministic_anchor + focused tests まで通るなら、
Atlas実生成ではこの範囲で安全に使える。
```

という判断ができるようになる。

---

## 9. 証跡フォーマット追加

TA9〜TA12完了時は、既存Evidence Rulesに加えて以下を記録する。

```text
Twin readiness score:
Readiness level:
Symbol resolution rate:
Impact precision:
Safe-Edit Briefing availability:
Prompt delivery audit:
Route-method-assist matrix best candidate:
Slot quality score:
Slot blocked reasons:
Post-apply apply status:
Focused tests:
Post-apply Twin gate:
Proof ledger ref:
Rollback evidence:
E2E lift:
E2E harm:
Recommended policy patch:
```

---

## 10. Stop Conditions

TA9〜TA12では以下もstop条件とする。

- readinessがunavailableなのにslot系assistをtrusted扱いしようとした場合。
- anchor一意性が確認できないslotを適用候補にしようとした場合。
- isolated applyではなく実projectへ直接applyしようとした場合。
- focused tests unavailableをpassed扱いしようとした場合。
- post-apply Twin gate NGを補助成功として記録しようとした場合。
- RouteMatrix安全候補外をmatrix winnerにしようとした場合。
