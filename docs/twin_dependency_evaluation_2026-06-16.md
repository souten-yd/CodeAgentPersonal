# Twin dependency-awareness evaluation — 2026-06-16

Goal: measure whether the Project Twin gives accurate "who depends on this symbol" information for a
real codebase (KasaneCore), and how much that information **augments a weak local model** toward a
frontier model's understanding — the prerequisite for safely editing a large codebase
(self-improvement).

Three sources are compared:

- **Frontier (ground truth)**: a frontier model's reading of the repo, operationalized as `grep` over
  the actual call sites — the verifiable set of direct callers.
- **Twin**: `SqliteProjectTwinStore.assess_impact()` over a Twin built from the source
  (`DigitalTwinModuleImpl.refresh(full_rebuild=True)`).
- **Weak model (8080)**: `Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf` via the local
  OpenAI-compatible server, with and without the Twin's Safe-Edit Briefing injected.

## Part 1 — Twin accuracy vs the frontier ground truth

### Scope `agent/model_forge` (Twin: 9.3 s, 4 495 nodes, 7 867 edges)

| Target symbol | Frontier (grep) direct callers, in-scope | Twin `assess_impact` | Verdict |
|---|---|---|---|
| `eval_packs.py#score_pack` | `capability_scoring.py` (`score_dimensions`, scorer methods) | `score_dimensions` + `CapabilityScorer.record_pack_result` + `CapabilityScorer.record_eval_run` | ✅ match, down to method granularity |
| `capability_scoring.py#build_capability_profile` | `capability_scoring.py` (`load_capability_profile`) | `load_capability_profile` | ✅ match |
| `decomposition_policy.py#derive_decomposition_policy` | none in-scope (caller is outside `model_forge`) | none | ✅ no false positive |
| `route_fitness.py#derive_route_fitness` | none in-scope | none | ✅ no false positive |
| `eval_packs.py#load_eval_packs` | none in-scope | none | ✅ no false positive |

### Scope `agent/twin_control_plane` (Twin: 6.0 s, 2 714 nodes, 5 115 edges)

Target `instruction_compiler.py#compile_model_instruction` (a ~40-file module):

- **Frontier (grep) direct callers (ground truth):** `active_integration.py`,
  `pipeline_integration.py`, `real_llm_eval.py`.
- **Twin:** all 3 direct callers (100 % recall) **plus** two transitive dependents
  (`acceptance_harness.py`, `evaluation_harness.py`) reached through the call graph.

**Finding:** the Twin reproduces the direct callers with no misses and no false positives, and
additionally surfaces the transitive blast radius. One precision wrinkle was observed — impact
traversal occasionally returns a caller's internal `var://`/`def://` nodes (local variables / nested
defs) — which the Safe-Edit Briefing now filters to real source symbols.

## Part 2 — How much does the Twin augment the weak model?

The Twin only matters when the codebase is too large to fit in context. Two regimes:

### Small scope (both files fit in context)

Target `score_pack`, both `eval_packs.py` and `capability_scoring.py` given to the model.

| Source | Recall of true callers |
|---|---|
| Weak model (8080), no Twin | 100 % |
| Weak model (8080), + Twin briefing | 100 % |

When everything fits, the weak model already finds the callers; the Twin is a no-op benefit.

### Large-repo regime (cannot fit the module — only the definition file is given)

Target `compile_model_instruction`; the model is given **only** `instruction_compiler.py` (simulating
that a ~40-file module / a KasaneCore-scale repo cannot be loaded wholesale), then asked which other
files call it.

| Source | Recall of true callers | Behavior |
|---|---|---|
| Frontier (grep) | 100 % | ground truth: 3 files |
| **Weak model (8080), no Twin** | **0 %** | found none; **hallucinated 80+ non-existent files** (`twin_model_dicing.py`, `twin_model_pivoting.py`, …) |
| **Weak model (8080), + Twin briefing** | **100 %** | named all 3 real callers (+ the 2 transitive), in ~2 s |

**Augmentation: 0 % → 100 % (+100 points).**

## Conclusions

1. The Twin's dependency information is **accurate** against a frontier reading of the real repo:
   full recall of direct callers, no false positives, plus transitive reach.
2. In the regime that matters for self-improvement — a codebase too large to fit in context — the
   weak local model is **not just weak but dangerous on its own**: it cannot see the dependents and
   fabricates non-existent files, so it would "update" files that do not exist and miss the real call
   sites it must preserve.
3. Injecting the Twin's Safe-Edit Briefing lifts the weak model from **0 % to frontier-level (100 %)**
   dependency awareness. "Weak model × Twin" therefore achieves frontier-grade safe-edit context on a
   large codebase, which is exactly what autonomous self-improvement requires.

## Reproduction

- Build a Twin: `DigitalTwinModuleImpl(db_path=...).refresh(RefreshTwinRequest(project=ProjectIdentity(project_id=..., workspace_id="default", project_path=<dir>), full_rebuild=True))`.
- Query impact: `store.assess_impact(ImpactRequest(project_id="<project_id>\x1f<workspace_id>", changed_refs=["py://<rel>#<symbol>"], change_kind="modify", max_depth=3, min_confidence=0.0))`.
- Ground truth: `grep -rn "<symbol>(" <dir>` minus the definition.
- Weak model: `AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf")`.

Wiring under test: the Safe-Edit Briefing (`agent/project_twin/safe_edit_briefing.py`) is injected into
the generation instruction by `build_twin_pipeline_evidence`
(`agent/twin_control_plane/pipeline_integration.py`).
