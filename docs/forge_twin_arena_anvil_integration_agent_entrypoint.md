# Forge / Twin / Arena / Anvil 統合改修 — Agent Entrypoint

このファイルだけ読めば着手できる。`AGENTS.md` の Active Goal がここを指している。

## 0. 現在のActive Goal

現在のActive Goalは **Forge Twin Assist Evaluation — Atlas実生成補助評価・弱LLM補助レベル最適化**。

既存トラックでは PR16〜PR22 と H1〜H4 まで完了し、Method層・Anvil実評価・自然fallback・MethodRouter v2・multi-model role assignment・active gate・Atlas route validation・semantic hardening・全軸frontier verification・capability rescue policy が揃った。

次の不足は、**Forge評価をモデル単体評価から、Atlas実生成経路込みの実効評価へ拡張すること**。つまり、Twin注入なしbaselineと、Twin注入あり生成をA/B比較し、弱LLMがTwin補助でどれだけ救えるかを定量化する。

さらにTA9〜TA12では、Twin本体の実装度合い・信頼度、route/method/assist組み合わせ最適化、slot品質、post-apply E2Eまで評価対象に拡張する。

## 1. まず読む順番

1. 本ファイル
2. `docs/forge_twin_assist_evaluation_plan.md` — TA1〜TA8: baseline vs assisted Twin Assist評価。
3. `docs/forge_twin_assist_readiness_extension_plan.md` — TA9〜TA12: Twin readiness / route-method-assist matrix / slot quality / post-apply E2E。
4. `docs/forge_twin_arena_anvil_integration_plan.md` — 既存計画。PR16〜22 / H1〜H4 までの完了状態を確認する。
5. `docs/forge_twin_arena_anvil_integration_current_status.md` — component inventory / per-PR completion proofs / 残gap。

## 2. 現状評価

実装済みの重要土台:

| 既存 | 役割 |
|---|---|
| `agent/model_forge/method_taxonomy.py` | MethodVariant定義 |
| `agent/model_forge/method_router.py` | モデルprofileに応じたMethodVariant/fallback/context/decomposition選択 |
| `agent/model_forge/execution_policy.py` | route / method / Twin injection / gates を組む |
| `agent/twin_control_plane/pipeline_integration.py` | ExecutionPolicy + TwinBrief + compiled instruction + Safe-Edit Briefing |
| `agent/twin_control_plane/patch_injection.py` | Atlas patch生成へ `twin_generation_hints` を渡す |
| `agent/atlas_patch_proposal_service.py` | `twin_control_section` を生成promptに合成する |
| `agent/model_forge/real_method_runner.py` | MethodAdapter単体の実LLM評価 |
| `agent/model_forge/capability_rescue.py` | 全NG時の救出ラダー |

不足:

1. Forge評価はまだ MethodAdapter単体寄りで、Atlas実生成経路のTwin注入効果を直接測っていない。
2. Twin注入なし/ありの baseline・assisted・lift・harm がProfileStoreやUIに記録されない。
3. large_file_editing / edit_intent_quality が弱いモデルに対して、Twinがslot/anchor/rangeを先に決め、LLMにはslot内コードだけ返させる手法がまだない。
4. H4のrescue planはあるが、ExecutionPolicySelector / MethodRouter / Atlas実生成経路への本接続は後続。
5. Twin本体のreadiness、symbol resolution、impact精度、prompt delivery、slot品質、post-apply E2Eまでは評価されていない。

## 3. 実装パッケージ

| # | Branch | Goal | Status |
|---|---|---|---|
| TA1 | `feat/forge-twin-assist-contracts` | TwinAssistMode taxonomy, DTO, strict schema tests | completed |
| TA2 | `feat/forge-twin-assist-packs` | case packs, fixtures, scoring, harm detection | completed |
| TA3 | `feat/forge-twin-assist-runner` | `AtlasPatchProposalService.propose_for_item` 実経路でbaseline vs assisted評価 | completed |
| TA4 | `feat/forge-twin-localized-slot` | TwinEditSlot resolver / slot patch adapter MVP | completed |
| TA5 | `feat/forge-twin-assist-policy` | MethodRouter / ExecutionPolicy / ProfileStore接続 | completed |
| TA6 | `feat/forge-twin-assist-api` | `/api/forge/twin-assist/*` API | completed |
| TA7 | `feat/forge-twin-assist-ui` | Forge UI Twin Assist tab / result drawer / profile recommendation | pending |
| TA8 | `feat/forge-twin-assist-real-eval` | 8080実モデル評価・evidence保存・status更新 | pending |
| TA9 | `feat/forge-twin-readiness-score` | Twin snapshot/freshness/symbol/impact/Safe-Edit/prompt delivery readiness | pending |
| TA10 | `feat/forge-route-method-assist-matrix` | route × method × assist × fallback matrix | pending |
| TA11 | `feat/forge-twin-slot-quality-gates` | slot/anchor/range quality gates and confidence calibration | pending |
| TA12 | `feat/forge-twin-assist-postapply-e2e` | proposal→Safe Apply dry-run→focused tests→post-apply Twin gate | pending |

## 4. 作業フロー（項目=1PR）

各項目について:

1. TA1〜TA8は `docs/forge_twin_assist_evaluation_plan.md`、TA9〜TA12は `docs/forge_twin_assist_readiness_extension_plan.md` の次のpending項目を選ぶ。
2. 実コードを確認し、置き換えず統合・拡張する。
3. ブランチ `feat/forge-twin-assist-<slug>` または表のBranchを切る。
4. 最小の垂直スライスを実装する。
5. focused tests / affected tests / syntax checks / available real model evidence を実行する。
6. 該当plan docと `docs/forge_twin_arena_anvil_integration_current_status.md` を更新する。
7. `git add -A` は禁止。対象ファイルのみaddする。
8. PR作成・mergeはユーザー承認済み範囲または明示承認に従う。

## 5. テスト実行

```bash
venv_sys/Scripts/python.exe -m pytest -q tests/<file>.py
```

新規テスト候補:

```text
tests/test_forge_twin_assist_contracts.py
tests/test_forge_twin_assist_packs.py
tests/test_forge_twin_assist_runner.py
tests/test_forge_twin_localized_slot.py
tests/test_forge_twin_assist_api.py
tests/test_forge_twin_assist_ui_render.py
tests/test_forge_twin_readiness.py
tests/test_forge_assist_matrix.py
tests/test_forge_twin_slot_quality.py
tests/test_forge_twin_assist_postapply_e2e.py
```

## 6. 守る不変条件

- `unavailable` は `passed` ではない。
- mock / synthetic は real evidence ではない。
- Twin Assist Evaluation は直接ファイル適用しない。
- Safe Apply / Proposal / Verification を迂回しない。
- production routing を自動変更しない。
- ProfileStoreへの保存は observation / recommendation。active切替は既存gateに従う。
- Twin注入で悪化した場合はharmとして記録する。
- readinessが低いTwinにslot/deterministic anchorをtrusted扱いしない。
- non-unique anchorや広すぎるslotを許可しない。
- post-apply E2Eはisolated workspace / dry-run / rollback-capable flowのみ。
- remote publish / PR / push / merge は承認必須。
- test・gate弱体化禁止、stale test自動削除禁止。

## 7. 実装上の注意

### 7.1 評価はAtlas実生成経路を通す

`RealMethodRunner` のようなMethodAdapter単体評価だけでは不十分。Twin Assist Evaluation は、可能な限り `AtlasPatchProposalService.propose_for_item` を呼び、実際のpatch生成prompt / `twin_control_section` / current file content / Project Twin hints を通して評価する。

### 7.2 Twin slotではLLMにanchorを選ばせない

large_file_editing / edit_intent_quality が弱いモデルでは、old_string/new_stringやinsert_after anchorをLLMに作らせるのが失敗源。TA4/TA11では Twin/AST/Atlas が `TwinEditSlot` と deterministic anchor を決め、LLMにはslot内のコード断片だけ返させる。

### 7.3 baseline vs assistedを必ず比較する

Twinありの単体スコアだけでは不十分。必ず同じcaseでbaseline score、assisted score、lift、harmを保存する。

### 7.4 Twin readinessでassist modeをcapする

TA9以降、Twin snapshotがstale/unavailable、symbol resolutionが低い、impactが過大、prompt deliveryが不明な場合は、`TWIN_LOCALIZED_SLOT` や `TWIN_DETERMINISTIC_ANCHOR` を推奨しない。

### 7.5 推奨は自動適用しない

`recommended_twin_assist_mode` や `recommended_twin_injection_level` はProfileStoreへ保存してよいが、production routing / active executionへの反映は既存gateに従う。

## 8. 完了報告フォーマット

`AGENTS.md` の Evidence Rules に従い、Twin Assist固有項目を必ず含める。

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
Profile recommendation:
Atlas UI evidence:
Unavailable checks:
Safety invariants:
Remaining gaps:
Next package:
Blocker:
Proof level:
```

## 9. 期待される最終挙動

例: 8080 weak model が以下のprofileの場合:

```text
structured_output_fidelity=1.0
patch_protocol_fidelity=1.0
anchor_selection_quality=1.0
edit_intent_quality=0.0
large_file_editing=0.4
```

Forgeは以下を推奨できること。

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
  "readiness_required": "high",
  "slot_quality_required": "accepted",
  "post_apply_e2e_required": true
}
```

## 10. Completion

このActive Goalは、以下が揃うまでcompleteにしない。

- baseline/assisted/lift/harmがForgeで評価できる。
- Atlas実生成経路を通した評価である。
- Twin slot / deterministic anchor の改善効果が測れる。
- Twin readiness scoreがある。
- route × method × assist matrixがある。
- slot quality gatesがある。
- post-apply E2E評価がある。
- ProfileStoreに推奨assist mode / injection level / matrix recommendationが保存される。
- MethodRouter / ExecutionPolicy が推奨を利用できる。
- Forge UIにTwin Assist結果とprofile recommendationが表示される。
- 8080実モデルで最低ケースを評価し、evidence refsを保存する。
