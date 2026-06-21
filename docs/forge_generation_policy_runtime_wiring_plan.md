# Forge / Atlas Generation Policy Runtime Wiring — 追加計画（TA13〜TA16）

作成日: 2026-06-21 / Owner: souten

この文書は、以下の既存計画の続きとして実行する。

```text
docs/forge_twin_assist_evaluation_plan.md          # TA1〜TA8
docs/forge_twin_assist_readiness_extension_plan.md # TA9〜TA12
```

前回までに `agent/model_forge/atlas_generation_policy.py` が追加され、ベンチ済みprofile・未ベンチprofile・Forge最適ルーティングOFF時の安全fallbackを解決できるようになった。しかし、現時点ではこのresolverは **まだ `pipeline_integration.build_twin_pipeline_evidence()` に本接続されていない**。

本計画は、その未反映部分を実生成経路へ接続し、実際のAtlasコード生成時に **Twin注入度 / route / method / fallback chain がベンチマーク結果または安全fallbackに従って切り替わったことを証跡化する** ための詳細設計である。

---

## 0. 現状評価

### 0.1 すでにあるもの

- `agent/model_forge/atlas_generation_policy.py`
  - `resolve_atlas_generation_policy()`
  - `resolve_forge_optimal_routing()`
  - `AtlasGenerationPolicyResolution`
  - `ATLAS_FORGE_OPTIMAL_ROUTING`
- `tests/test_forge_atlas_generation_policy.py`
  - 未ベンチ時のsafe default
  - benchmark route fitnessによるsafe候補内reorder
  - optimal routing OFF時のfallback
  - critical gate維持
  - weak large-file profile時のmethod/injection調整

### 0.2 既存実生成経路の土台

`agent/twin_control_plane/pipeline_integration.py` は既に以下を行う。

1. `resolve_capability_profile()` で ProfileStore から capability profile / route_preferences を読む。
2. `_build_policy_and_brief()` で `ExecutionPolicySelector.select()` を呼ぶ。
3. `build_twin_pipeline_evidence()` が policy.route / instruction_style / twin_injection_level / route_fitness / benchmark_route_selected / compiled_instruction をevidenceに入れる。
4. `patch_injection.py` が `twin_generation_hints` を作る。
5. `AtlasPatchProposalService` が `twin_control_section` を生成promptへ入れる。

### 0.3 未反映・不足

1. `atlas_generation_policy.py` のresolverが `pipeline_integration.py` に未接続。
2. `selection_mode` が実生成evidenceに出ない。
3. `optimal_routing_enabled` が実生成evidenceに出ない。
4. `fallback_recommendation` が実生成evidenceに出ない。
5. 未ベンチ / profileありroute_fitnessなし / OFF / benchmark_optimized の違いが実生成時に明確に監査できない。
6. UI/APIで「今回の生成はなぜこのroute/method/Twin注入度になったか」を確認できない。
7. 実コード生成時に `atlas_generation_policy` がprompt metadataへ届いたことのテストがない。

---

## 1. 追加PR一覧

| # | ブランチ | 内容 | 依存 | 状態 |
|---|---|---|---|---|
| TA13 | `feat/forge-runtime-policy-wiring` | `atlas_generation_policy` resolverを `pipeline_integration` に本接続 | `atlas_generation_policy.py` | ☐ pending |
| TA14 | `feat/forge-runtime-policy-preview-api` | 実生成policy preview API / evidence schema / UI表示 | TA13 | ☐ pending |
| TA15 | `feat/forge-default-routing-presets` | 未ベンチ・OFF時の推奨fallback presetsを明文化/設定化 | TA13 | ☐ pending |
| TA16 | `feat/forge-runtime-policy-e2e-proof` | 実patch生成payloadまで route/method/injection が届くE2E証跡 | TA13〜TA15 | ☐ pending |

---

## 2. TA13 — Runtime Policy Wiring

### 2.1 目的

`build_twin_pipeline_evidence()` が、既存の直接 `ExecutionPolicySelector` 呼び出しではなく、`resolve_atlas_generation_policy()` を通してpolicyを取得するようにする。

これにより、実生成evidenceに以下が必ず残る。

```json
{
  "atlas_generation_policy": {
    "selection_mode": "benchmark_optimized | unbenchmarked_default | forge_optimal_routing_off | profile_without_route_fitness_default | benchmark_profile_kept_default",
    "optimal_routing_enabled": true,
    "profile_available": true,
    "route_fitness_available": true,
    "route_fitness_applied": true,
    "fallback_recommendation": {
      "route": "sliced_impact",
      "method_variant": "patch_dsl_json",
      "method_fallbacks": ["edit_intent_list", "anchored_edit_block", "review_only"],
      "twin_injection_level": 3,
      "instruction_style": "constrained_patch",
      "task_decomposition_policy": "micro_patch_only",
      "context_package_mode": "impact_slice",
      "verification_mode": "affected_tests",
      "reason": "benchmark_optimized",
      "production_routing_changed": false
    }
  }
}
```

### 2.2 変更対象

```text
agent/twin_control_plane/pipeline_integration.py
tests/test_twin_pipeline_integration.py
```

### 2.3 実装方針

#### Step 1: `resolve_capability_profile()` を維持する

既存API互換のため、`resolve_capability_profile()` は残す。外部テストや他モジュールが使っている可能性があるため削除しない。

#### Step 2: `_build_policy_and_brief()` を拡張する

現状:

```python
policy = selector.select(..., route_preferences=route_preferences or None)
return policy, brief
```

変更後:

```python
from agent.model_forge.atlas_generation_policy import resolve_atlas_generation_policy

resolution = resolve_atlas_generation_policy(
    change_class=ChangeClass(change_class),
    task_category=task_category,
    provider_id=getattr(capability_profile, "provider_id", ""),
    model_id=getattr(capability_profile, "model_id", ""),
    capability_profile=capability_profile,
    profile_available=profile_available,
    route_preferences=route_preferences,
)
policy = resolution.policy
return policy, brief, resolution
```

ただし既存呼び出し互換を壊さないため、関数名を変えずに内部変更する場合は返却値変更の影響に注意する。安全策として、新関数を追加する。

```python
def _build_policy_brief_and_resolution(...):
    return policy, brief, resolution
```

そして `build_twin_pipeline_evidence()` だけが新関数を使う。

#### Step 3: `build_twin_pipeline_evidence()` に証跡を追加

既存top-level fieldsは維持する。

追加:

```python
"atlas_generation_policy": resolution.model_dump(mode="json"),
"selection_mode": resolution.selection_mode,
"optimal_routing_enabled": resolution.optimal_routing_enabled,
"route_fitness_applied": resolution.route_fitness_applied,
"fallback_recommendation": resolution.fallback_recommendation,
```

互換のため、既存の以下は残す。

```python
"route"
"instruction_style"
"twin_injection_level"
"route_fitness"
"benchmark_route_selected"
```

#### Step 4: OFF時の挙動

`ATLAS_FORGE_OPTIMAL_ROUTING=off` の場合:

- `selection_mode == "forge_optimal_routing_off"`
- routeはRouteMatrix default
- route_fitnessはevidenceとして表示してよいが、`route_fitness_applied=False`
- method/injectionはcapability profileに基づいてよい
- `production_routing_changed=False`

#### Step 5: 未ベンチ時の挙動

profileなし:

- `selection_mode == "unbenchmarked_default"`
- routeはRouteMatrix default
- profile weaknessは捏造しない
- default method/injectionを返す
- evidenceに `profile_available=False` を出す

#### Step 6: profileありroute_fitnessなし

capability profileはあるがbenchmark route fitnessが空:

- `selection_mode == "profile_without_route_fitness_default"`
- routeはRouteMatrix default
- method/injectionはcapability profileに基づく

### 2.4 Tests

`tests/test_twin_pipeline_integration.py` に追加。

必須:

1. `test_runtime_policy_evidence_present`
   - active evidenceに `atlas_generation_policy` がある。
   - route/method/injection/fallback_recommendationが入る。

2. `test_unbenchmarked_generation_policy_uses_default_route`
   - profileなしで `selection_mode=unbenchmarked_default`。
   - mediumなら `route=patch_dsl`。

3. `test_optimal_routing_off_is_recorded_in_pipeline_evidence`
   - env `ATLAS_FORGE_OPTIMAL_ROUTING=off`
   - route_fitnessがあっても `route_fitness_applied=False`
   - `selection_mode=forge_optimal_routing_off`

4. `test_benchmark_optimized_policy_flows_into_pipeline_evidence`
   - temp ProfileStoreにroute fitnessが出るdimensionを保存。
   - safe候補内でdefault以外のrouteが選ばれたら `benchmark_optimized`。

5. `test_critical_policy_keeps_critical_gate_even_with_benchmark_preference`
   - critical changeでは `critical_gate`。

6. `test_policy_resolution_never_changes_execution_authority`
   - `shadow_report.changes_execution=False`
   - `changes_production_routing=False`

---

## 3. TA14 — Runtime Policy Preview API / UI

### 3.1 目的

実生成前に「このモデル・タスク・変更規模なら、route/method/Twin注入度は何になるか」をForge UI/APIから確認できるようにする。

### 3.2 API

追加候補:

```http
POST /api/forge/atlas-generation-policy/preview
```

Request:

```json
{
  "provider_id": "local",
  "model_id": "Qwen3.6-35B-A3B",
  "change_class": "large",
  "task_category": "autonomous_codegen",
  "optimal_routing": true
}
```

Response:

```json
{
  "selection_mode": "benchmark_optimized",
  "policy": {...},
  "fallback_recommendation": {...},
  "route_fitness": {...},
  "reasons": [...]
}
```

### 3.3 UI

Forge UIに追加:

- Advanced > Runtime Policy Preview
- Model profile drawer > Runtime Generation Policy
- Twin Assist result drawer > Applied Runtime Policy

表示項目:

- selection_mode
- optimal_routing_enabled
- profile_available
- route_fitness_available
- route_fitness_applied
- selected route
- method variant
- method fallbacks
- twin injection level
- instruction style
- context package mode
- verification mode
- why selected
- safe fallback when OFF/unbenchmarked

### 3.4 Tests

```text
tests/test_forge_runtime_policy_preview_api.py
tests/test_forge_runtime_policy_ui_render.py
```

---

## 4. TA15 — Default Routing Presets

### 4.1 目的

未ベンチマーク時やForge最適ルーティングOFF時の推奨経路を、RouteMatrixに依存するだけでなく、UI/APIで明示的に確認できるpresetとして定義する。

### 4.2 新規ファイル

```text
agent/model_forge/default_generation_presets.py
```

### 4.3 Preset

```python
DEFAULT_GENERATION_PRESETS = {
    "unbenchmarked_safe": {
        "trivial": {"route": "deterministic", "method": "deterministic_text_patch", "injection": 0},
        "micro": {"route": "micro_patch", "method": "structured_patch_json", "injection": 1},
        "small": {"route": "direct_patch", "method": "structured_patch_json", "injection": 2},
        "medium": {"route": "patch_dsl", "method": "patch_dsl_json", "injection": 2},
        "large": {"route": "sliced_impact", "method": "structured_patch_json", "injection": 3},
        "critical": {"route": "critical_gate", "method": "review_only", "injection": 4},
        "greenfield": {"route": "greenfield_skeleton", "method": "structured_patch_json", "injection": 4}
    },
    "optimal_routing_off": "same_as_route_matrix_default_but_profile_can_adjust_method_and_injection"
}
```

注意:

- presetは説明用・preview用。
- 実行権限はRouteMatrix / ExecutionPolicySelectorが保持。
- criticalはreview_only推奨を明示してもよいが、既存MethodRouterとの互換が必要。既存実装が別methodを返す場合、presetはadvisoryとして扱う。

### 4.4 API/UI

```http
GET /api/forge/atlas-generation-policy/default-presets
```

UIで表示:

- no benchmark fallback
- optimal routing off fallback
- critical safety fallback

### 4.5 Tests

- RouteMatrix defaultとpresetが矛盾しない。
- criticalはcritical_gateを必ず示す。
- large/criticalにunsafe micro routeを出さない。

---

## 5. TA16 — Runtime Policy E2E Proof

### 5.1 目的

`pipeline_integration` にpolicy resolverが接続されただけでは不十分。実際にAtlas patch生成payloadに以下が届くことを確認する。

- selected route
- method variant
- method fallback chain
- twin injection level
- compiled instruction
- fallback recommendation
- selection mode

### 5.2 変更対象

```text
agent/atlas_patch_proposal_service.py
tests/test_atlas_patch_proposal_twin_policy_injection.py
```

### 5.3 実装方針

`AtlasPatchProposalService.propose_for_item()` は既に `twin_generation_hints` を読む。ここに `atlas_generation_policy` を含める。

期待metadata:

```json
{
  "twin_generation_hints": {
    "twin_instruction": "...",
    "twin_route": "sliced_impact",
    "twin_instruction_style": "constrained_patch",
    "twin_injection_level": 3,
    "atlas_generation_policy": {
      "selection_mode": "benchmark_optimized",
      "method_variant": "patch_dsl_json",
      "method_fallbacks": [...]
    }
  }
}
```

### 5.4 Prompt audit

`generate_proposal_with_llm()` のpayload/evidenceに以下を残す。

```json
{
  "runtime_policy_delivery": {
    "policy_id": "...",
    "selection_mode": "benchmark_optimized",
    "route": "sliced_impact",
    "method_variant": "patch_dsl_json",
    "twin_injection_level": 3,
    "compiled_instruction_present": true,
    "prompt_section_hash": "..."
  }
}
```

### 5.5 Tests

1. `test_runtime_policy_reaches_patch_proposal_payload`
   - metadataに `atlas_generation_policy` が含まれる。

2. `test_runtime_policy_prompt_contains_selected_instruction`
   - compiled instructionがsystem promptに入る。

3. `test_off_policy_prompt_uses_safe_default_without_benchmark_claim`
   - optimal routing off時、benchmark_optimizedを名乗らない。

4. `test_unbenchmarked_policy_prompt_uses_default_recommendation`
   - unbenchmarked_defaultがpayloadに残る。

5. `test_policy_delivery_does_not_apply_files`
   - proposal生成だけ。Safe Apply bypassなし。

---

## 6. Acceptance Criteria

TA13完了:

- `build_twin_pipeline_evidence()` が `atlas_generation_policy` を含む。
- selection_mode / optimal_routing_enabled / route_fitness_applied / fallback_recommendation がevidenceにある。
- 既存top-level route / injection / benchmark_route_selected は互換維持。
- OFF / 未ベンチ / benchmark_optimized がテスト済み。

TA14完了:

- Forge APIからruntime policy previewができる。
- UIでselection_modeとfallback recommendationを確認できる。

TA15完了:

- 未ベンチ/OFF時のdefault presetsが明文化される。
- RouteMatrixと矛盾しないことをテストで確認する。

TA16完了:

- 実patch生成payloadまでpolicy summaryが届く。
- compiled instruction / selection_mode / route / method / injection のprompt delivery auditが残る。
- 直接applyしない。

---

## 7. Safety Invariants

- Benchmark結果はRouteMatrix safe候補内のreorderにしか使わない。
- critical changeは常にcritical_gate。
- optimal routing OFF時はRouteMatrix defaultを使う。
- unbenchmarked profileを弱点扱いしない。
- profile unavailableをpassedやtrusted扱いしない。
- runtime policy previewはadvisoryであり、production routingを変更しない。
- promptへpolicyを渡しても、Proposal / Safe Apply / Verificationの権限は変えない。
- remote publish / PR / push / mergeは行わない。

---

## 8. 完了後の期待状態

TA13〜TA16完了後、実際のAtlasコード生成時に以下が証跡として確認できる。

```text
model/profile benchmark evidence
  ↓
AtlasGenerationPolicyResolution
  ↓
ExecutionPolicy(route, method, injection, fallback)
  ↓
TwinBrief / compiled instruction / Safe-Edit Briefing
  ↓
patch proposal payload
  ↓
runtime_policy_delivery evidence
```

これにより、以下の問いにyes/noで答えられる。

1. ベンチ結果がrouteに反映されたか。
2. MethodRouterのmethod/fallbackが実生成に反映されたか。
3. Twin injection levelがpromptに入ったか。
4. 未ベンチ時は安全defaultになったか。
5. optimal routing OFF時はベンチ結果を無視したか。
6. criticalではbenchmark preferenceを無視してcritical_gateになったか。
7. その判断理由がevidenceに残ったか。
