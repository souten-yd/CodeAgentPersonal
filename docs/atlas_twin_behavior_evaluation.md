# Atlas Digital Twin / Deep Behavioral Graph — Behavior Evaluation & Remediation Plan

## Purpose

PIBIH-2 (Impact Analysis Core) and PIBIH-3 (Deep Behavioral Graph V3) are complete. This document
records a behavior evaluation of the Digital Twin (static graph + behavioral graph + impact analysis)
against a realistic **virtual project**, and a prioritized remediation plan to make the remaining
behavior appropriate.

## Methodology

Harness: `scripts/twin_behavior_eval.py`. It builds a self-contained virtual project, projects it into
an in-memory `SqliteProjectTwinStore` (static + behavioral delta), and runs PASS/FAIL behavior checks.
Re-run with:

```powershell
$env:PYTHONPATH="."; .\venv_sys\Scripts\python.exe scripts\twin_behavior_eval.py
```

Exit code = number of failing checks (0 = all appropriate).

### Virtual project shape

A small web app exercising the twin's relationships end to end:

```text
app/config.py    os.environ.get / os.getenv  -> config resources
app/db.py        sqlite execute/commit/cursor/fetchall -> db resources (read/write)
app/services.py  from-import db + config; create_item/list_items
app/api.py       FastAPI @router.post/get -> routes handled_by services
web/app.js       click events -> fetch('/items') -> routes
tests/           test_create_item, test_get_items cover services/handlers
app/models.py    class ItemRepo with self._validate() method call   (edge case)
app/legacy.py    os.environ['LEGACY_FLAG'] subscript read            (edge case)
```

## Evaluation result

**20 / 20 checks appropriate** (after remediations R1–R3 below; was 16/20 before R1).

Appropriate (PASS) behavior confirmed:

- cross-file transitive impact: `db.save_item` change → `services.create_item` → `POST /items` route → `test_create_item`;
- route change → backend handler + UI caller event + recommended test;
- config change (`APP_MODE`) → reader `get_mode` → transitive `create_item`;
- resource-effect direction + identity (db `write`, config `read`; `resource://config:APP_MODE`, `:DATABASE_URL`);
- UI click event traces to a route (UI → API → route path discoverable);
- import-aware call resolution (`services.create_item` → `db.save_item` resolved to canonical ref);
- resolved project calls are not falsely flagged ambiguous; builtins not flagged;
- no behavioral fact is marked verified (all `inferred` / `heuristic_static`).

## Findings (inappropriate behavior observed)

| ID | Finding | Severity | Status |
| --- | --- | --- | --- |
| F1 | Impact results were polluted with structural container nodes (`dir://`, `file://`, `module://`) reached via `defines`/`contains` reverse edges — noise that hurts planner usefulness. | High | **Fixed (R1)** |
| F2 | `os.environ['X']` **subscript** config reads are not modeled (only `os.getenv` / `os.environ.get` Call forms are). A config change to a subscript-only var would not surface its readers. | Medium | **Fixed (R2)** |
| F3 | `self.method()` / class-method calls do not resolve to the concrete method canonical ref (only the name-based `pyname://` edge exists), so intra-class impact precision is reduced. | Medium | **Fixed (R3)** |
| F4 | DB effect direction is coarse: every `execute(...)` is classified `write`, so a read-only `execute('SELECT ...')` is mislabeled. | Low | Planned (R4) |

## Remediation plan

### R1 — Exclude structural containers from impact results — DONE

- Change: `agent/project_twin/analysis.py` skips `repository/directory/file/module/package` node types
  when building impact items (they are reached via containment edges but are not behavioral impacts).
- Test: `tests/test_project_twin_impact_analysis.py::test_impact_excludes_structural_container_nodes`.
- Result: virtual-project checks 9 & 12 now PASS; container noise eliminated.

### R2 — Model config reads beyond the `.get()` Call form — DONE

- Change: `agent/project_twin/behavioral_graph.py` adds `_config_subscript_identity` + a `Subscript`
  branch (via the shared `_emit_resource_effect` helper) so `os.environ['X']` / `environ["X"]` reads
  model `resource://config:<X>` with read direction. `ANALYZER_VERSION` -> `behavioral_graph.v4`.
- Test: `tests/test_project_twin_behavioral_graph_v3.py::test_config_env_subscript_read_is_modeled`.
- Result: virtual-project check 10 now PASS.

### R3 — Resolve self/class-method calls to concrete refs — DONE

- Change: `agent/project_twin/static_graph.py` builds a per-class method table and resolves `self.m()`
  inside a class to `py://<rel>#<Class>.m` (resolution `self_method`) when `m` is defined on the same
  class; the name-based edge is kept. `PARSER_VERSION` -> `static_graph.v3`.
- Test: `tests/test_project_twin_call_resolution.py::test_self_method_call_resolves_to_concrete_method`.
- Result: virtual-project check 11 now PASS.

### R4 — DB effect direction precision — PLANNED

- Target: `agent/project_twin/behavioral_graph.py` `_resource_direction` for `kind == "database"`.
- Scope: inspect the first string arg of `execute/executemany` — `SELECT` → `read`, `INSERT/UPDATE/DELETE`
  → `write`/`delete`; default `write` when unknown. Keep heuristic.
- Acceptance: `execute('SELECT ...')` → read; `execute('INSERT ...')` → write.
- Priority: low (direction is already advisory).

## Sequencing

R1, R2, and R3 are landed — the virtual-project evaluation is now **20/20 appropriate**. R4 (DB
`execute` direction precision) remains opportunistic and does not block PIBIH-4. Next planned package:
PIBIH-4 (Project Intelligence Planning and Generation Injection).

## Safety / invariants

All twin facts remain `inferred` / `heuristic_static`; impact analysis reads the snapshot and never
mutates; no Proposal / Safe Apply / Verification boundary is touched by evaluation or R1.
