# Twin repo-scale evaluation — KasaneCore — 2026-06-16

A full Project Twin was built over the entire KasaneCore repository and used to triage the test
suite (impact-based test selection) with the TwinProof test-management plan. This records the
measured scale, the benchmark, the bugs the run exposed, and the effectiveness verdict, so the result
can be referenced later.

## 1. Build — full repository

| Metric | Value |
|---|---|
| Builder | `DigitalTwinModuleImpl(db_path=…).refresh(full_rebuild=True)` over repo root (`.`) |
| Excluded dirs | `.git`, `__pycache__`, `node_modules`, `venv*`, `tts_envs`, `third_party`, `ca_data`, build/dist caches |
| **Full build time** | **359.2 s** (~6 min) |
| **Nodes** | **417,484** |
| **Edges** | **736,507** |
| Persisted DB size | **689.6 MB** (SQLite) |
| Snapshot load time (warm DB) | **95 s** to materialize the full graph into memory |
| Python files in graph | 3,210 |
| Test files in graph | **1,027** |
| Test symbol nodes | 7,056 |

### Node-type distribution (417,484)

| node_type | count | | node_type | count |
|---|---:|---|---|---:|
| cfg_block | 225,352 | | method | 7,012 |
| definition | 75,637 | | file | 3,316 |
| variable | 36,520 | | module | 3,284 |
| return | 20,453 | | class | 2,755 |
| function | 17,446 | | recovery | 824 |
| side_effect | 12,546 | | state | 575 |
| **test** | **10,435** | | resource | 553 |
| api_route | 440 | | … | … |

Observation: **control-flow nodes (`cfg_block` 225k, `return` 20k) are ~59% of the graph.** Impact
("who depends on this") does not need them — this is the lever for the P1 performance fix (load only
the dependency-relevant slice).

### Edge-type distribution (736,507)

| edge_type | count | | edge_type | count |
|---|---:|---|---|---:|
| calls | 143,109 | | imports | 16,136 |
| defines | 139,370 | | interprocedural_argument_flow | 15,740 |
| cfg_next | 133,028 | | performs_side_effect | 12,546 |
| flows_to | 78,133 | | **covers_symbol** | **10,435** |
| cfg_condition_true/false | 27,337 ×2 | | inherits | 1,677 |
| flows_to_return | 25,818 | | handled_by | 1,000 |
| cfg_entry/exit | 24,458 ×2 | | … | … |

The dependency-relevant edges for impact/test-triage are `calls` (143k), `defines` (139k), `imports`
(16k), `covers_symbol` (10k, **test → subject-under-test**), `performs_side_effect` (12k), `inherits`
(1.7k). The CFG/dataflow edges (`cfg_*` ~370k, `flows_to*` ~104k) — over half the edges — are not
needed for impact.

## 2. Triage — impact-based test selection

Query: `store.assess_impact(changed_refs = expand_changed_refs_to_symbols(<file>), max_depth=4,
min_confidence=0.0)`, counting impacted files under `tests/` out of 1,027.

| Changed module | Query time | Impacted test files | Selectivity |
|---|---:|---:|---:|
| `agent/model_forge/decomposition_policy.py` (leaf, 6 symbols) | **351 s** | **353 / 1027** | 34% |

`recommended_tests` (runtime-observation channel): 222 — a static approximation, since no runtime
test-execution observations were ingested.

## 3. Bugs / limitations the run exposed

**P1 — assess_impact is unusably slow at repo scale (~351 s/query).** Root cause: every call
materializes the entire 417k-node / 736k-edge graph (95 s each), and a single triage does it more than
once (`expand_changed_refs_to_symbols` + `assess_impact` each load). There is no snapshot cache and no
scoped load. Over half the loaded graph (CFG/dataflow) is irrelevant to impact.
→ Fix direction: (a) in-process snapshot cache keyed by revision; (b) scoped load of only
dependency-relevant node/edge types.

**P2 — impact over-selects at depth=4 / min_confidence=0 (353/1027 ≈ 34%).** Transitive reachability
with no confidence floor connects a leaf module to a third of the suite through shared utilities — not
selective enough to replace "run everything."
→ Fix direction: confidence-weighted **top-K** selection (rank tests by weakest-edge path confidence,
bound depth), not a raw reachability set.

## 4. Effectiveness for a weak model — verdict

- **Scoped dependency awareness is effective** and is already proven: in the controlled evaluation
  (`docs/twin_dependency_evaluation_2026-06-16.md`) the Twin Safe-Edit Briefing lifted the weak 8080
  model from **0% to 100%** recall of cross-file dependents.
- **Raw repo-scale impact is not yet usable** for test triage: at 351 s/query and 34% selectivity it
  is both too slow and too broad. It needs the P1 (performance) and P2 (precision) fixes before it can
  drive the 1,027-test suite selection a weak model would rely on.
- Net: the mechanism is sound and high-value when scoped; making it useful at KasaneCore scale is a
  performance + ranking problem, now tracked as P1/P2.

Meta note: this evaluation is itself an instance of the target loop — **the Twin was used to find bugs
in the Twin.**

## 5. Reproduction

```python
from agent.project_twin.module import DigitalTwinModuleImpl
from agent.project_twin.facade import ProjectIdentity, RefreshTwinRequest
from agent.project_twin.contracts import ImpactRequest
from agent.twin_control_plane.pipeline_integration import expand_changed_refs_to_symbols

mod = DigitalTwinModuleImpl(db_path="twin_repo.sqlite")
mod.refresh(RefreshTwinRequest(project=ProjectIdentity(
    project_id="kasane", workspace_id="default", project_path="."), full_rebuild=True))  # ~359 s

store = mod._store
pid = "kasane\x1fdefault"
refs = expand_changed_refs_to_symbols(store, pid, ["agent/model_forge/decomposition_policy.py"])
impact = store.assess_impact(ImpactRequest(project_id=pid, changed_refs=refs,
                                           change_kind="modify", max_depth=4, min_confidence=0.0))
test_files = {i.canonical_ref[len('py://'):].split('#')[0]
              for i in impact.direct_impacts + impact.transitive_impacts
              if i.canonical_ref.startswith('py://tests/')}
```

## 6. Follow-up work (agreed: fix P1 → P2 first)

1. **P1 performance**: snapshot cache + scoped (dependency-only) load for `assess_impact`.
2. **P2 precision**: confidence-weighted top-K impacted-test selection.
3. Then resume C4 (graph-verified cross-file consistency), F3 (closed self-improvement acceptance),
   G3 (autonomous goal generation — details to be agreed before implementation).
