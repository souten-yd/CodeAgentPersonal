# Capability assessment — weak model self-improving a large codebase — 2026-06-16

Question: from the angle of "what does a **weak model** need in order to autonomously **self-improve a
large codebase** (KasaneCore itself)", enumerate the required capabilities, rate each from the actual
code, and extract the gaps.

Legend: ✅ implemented · 🟡 partial · 🔴 missing/insufficient. Levels are graded from real files, not
intent.

## A. Understand the codebase at scale

| # | Capability | Level | Evidence / notes |
|---|---|---|---|
| A1 | Symbol/structure extraction | ✅ | `project_intelligence/adapters/code_explorer.py` (`extract_symbols`, AST). |
| A2 | Dependency / impact graph (who calls what) | ✅ | `project_twin` static+behavioral analyzers; `store.assess_impact`. Evaluated accurate vs frontier ground truth (`docs/twin_dependency_evaluation_2026-06-16.md`). |
| A3 | Twin built & used **in the live loop** | ✅ (new) | Auto-build before generation, default-on in active mode; file→symbol expansion. `pipeline_integration.ensure_project_twin` / `expand_changed_refs_to_symbols`; orchestrator Phase 0. (Was 🔴 until #1894.) |
| A4 | Dependent-aware "safe-edit" guidance to the model | ✅ | `project_twin/safe_edit_briefing.py` injected via `build_twin_pipeline_evidence`. |
| A5 | Read-before-edit grounding | ✅ | `atlas_patch_proposal_service` reads current file (≤60 KB), sibling files (≤28 KB). |
| A6 | **Relevance/impact-ranked context selection** across a huge repo | 🔴 | `patch_context_selector.py` (53 lines) ranks by **keyword** within one file; `code_explorer.extract_symbols` takes the **first 40** symbols, not impact-ranked. The Twin knows the relevant set but does **not** drive *which files/symbols to load* — only the advisory briefing. **Key gap for large-repo generation.** |

## B. Plan & decompose

| # | Capability | Level | Evidence |
|---|---|---|---|
| B1 | Goal → plan | ✅ | `task_planning_runner`, `planner_phase1`, `deep_planner`. |
| B2 | Requirement analysis / clarification | ✅ | `requirement_analyzer`, `clarification_service`. |
| B3 | Adversarial plan critique | ✅ | `adversarial_plan_critic`. |
| B4 | File decomposition, **capability-tuned** | ✅ | `agent_prompts` + `model_forge/decomposition_policy` (#1889/#1890/#1891). |

## C. Generate

| # | Capability | Level | Evidence |
|---|---|---|---|
| C1 | Patch generation | ✅ | `atlas_patch_proposal_service`. |
| C2 | Large-file edit reliability (anchored placement) | ✅ | anchor recovery (#1888). |
| C3 | Capability-aware route / injection | ✅ | `model_forge/execution_policy`, Twin instruction compiler. |
| C4 | Cross-file interface consistency | 🟡 | `atlas_interface_contract` injects a shared contract by **prompt**; not graph-verified across many files. |

## D. Apply & verify safely

| # | Capability | Level | Evidence |
|---|---|---|---|
| D1 | Safe Apply (no blind disk writes) | ✅ | `atlas_file_safe_apply_executor`, `atlas_safe_apply_adapter`. |
| D2 | Forbidden-op / protected-path gates | ✅ | `safe_apply_adapter` (`protected_path`, `delete_forbidden`, `run_command_forbidden`). |
| D3 | Verification (real tests / browser smoke / visual) | ✅ | `verification_runner`, `atlas_auto_verification_service`, allowlisted commands; honest about env gaps (pytest-missing ≠ code failure). |
| D4 | Rollback / snapshot | ✅ | `atlas_change_snapshot_service` / `_restore_service`. |
| D5 | Remote-publication approval (PR/merge gating) | ✅ | `git_steward.classify_git_operation` (push/PR/merge require approval). |
| D6 | **Impact-selected regression tests** | 🔴 | Twin produces `recommended_tests`, but verification runs allowlisted commands and does **not** select *which* tests to run from the change's blast radius. |

## E. Repair & learn

| # | Capability | Level | Evidence |
|---|---|---|---|
| E1 | Self-correction / repair loop | ✅ | `atlas_self_correction_service`, `correction_router_service`, `bounded_retry_service`. |
| E2 | CI-failure repair | ✅ | `atlas_ci_failure_repair_service`. |
| E3 | Cross-run memory (anti-pattern / golden / proof ledger) | ✅ | wired into the orchestrator (`_load_anti_pattern_memory`, `_load_golden_index`, proof ledger). |
| E4 | Capability auto-update from production runs | ✅ | `_update_capability_profile_from_run`. |

## F. Autonomy & closure

| # | Capability | Level | Evidence |
|---|---|---|---|
| F1 | Autonomous codegen orchestrator | ✅ | `atlas_autonomous_codegen_orchestrator_service`. |
| F2 | Guarded operator loop (step + confirmation token) | ✅ (human-in-loop) | `atlas_guarded_operator_loop_service`. |
| F3 | Acceptance / convergence ("are we done?") | 🟡 | `twin_control_plane/acceptance_harness`, `project_convergence`; not a closed self-improvement acceptance. |
| F4 | Observability (status / token breakdown / evidence) | ✅ | status panel + `llm_usage` (#1886/#1887). |
| F5 | Model + system evaluation / benchmarking | ✅ | `model_forge/eval_packs` incl. `large_file_editing`, `real_llm_eval`; Twin eval doc. |

## G. Self-improvement–specific (editing **its own** repo)

| # | Capability | Level | Evidence / gap |
|---|---|---|---|
| G1 | Target its own repo as the project | 🟡 | Possible via `project_path`; no dedicated self-improvement orchestrator/profile. |
| G2 | **Self-guardrail protection** (don't let an autonomous run edit its own safety / approval / git-steward / Twin code) | 🔴 | `PROTECTED_PATH_PREFIXES` only covers `.git/.hg/.svn`. No denylist of the system's own safety-critical modules. **Important risk for autonomous self-modification.** |
| G3 | **Autonomous goal generation** (pick its own improvement backlog) | 🔴 | `continuation_service` continues a given run; nothing proposes self-improvement goals. Everything is user-initiated. |
| G4 | Always-fresh Twin during self-edit | ✅ (new) | Auto-build + post-apply refresh (#1894). |

## Gaps, prioritized for autonomous self-improvement

1. **🔴 Impact-ranked context selection (A6)** — generation still loads the first-N symbols + the single
   target file, not the Twin-impact-relevant files. The Twin *knows* the relevant set; wire it to pick
   *which* files/symbols to load. The evaluation showed a weak model is blind (and hallucinates) on a
   large repo without exactly this. **Highest leverage.**
2. **🔴 Self-guardrail protection (G2)** — a denylist (or approval gate) for the system's own
   safety-critical modules (`agent/atlas_safe_apply*`, `approval*`, `git_steward/*`, `twin_control_plane/*`,
   `full_auto_gate`, this assessment's guardrails) so an autonomous run cannot weaken its own controls.
3. **🔴 Autonomous goal generation (G3)** — a component that mines failing tests / TODOs / Twin health /
   coverage to propose a ranked self-improvement backlog, turning the supervised loop into a self-directed one.
4. **🔴 Impact-selected regression tests (D6)** — run the Twin's `recommended_tests` for a change instead
   of a fixed allowlist, so verification scales to a large suite.
5. **🟡 Graph-verified cross-file consistency (C4)** — verify multi-file interface coherence from the Twin
   graph, not only via the prompt-injected contract.
6. **🟡 Closed acceptance for self-improvement (F3/G1)** — a self-improvement acceptance that proves the
   change improved a measured property (a metric/benchmark) and regressed nothing.

## One-line verdict

The build/apply/verify/repair/learn spine and the Forge capability + Twin dependency machinery are
**implemented and, as of #1894, live by default**. The remaining blockers to *autonomous* self-improvement
on a large codebase are: (1) impact-**ranked context selection**, (2) **self-guardrail protection**, and
(3) **autonomous goal generation** — in that priority.
