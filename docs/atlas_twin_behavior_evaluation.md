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

**18 / 20 checks appropriate** (after remediation R1 below).

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
| F2 | `os.environ['X']` **subscript** config reads are not modeled (only `os.getenv` / `os.environ.get` Call forms are). A config change to a subscript-only var would not surface its readers. | Medium | Planned (R2) |
| F3 | `self.method()` / class-method calls do not resolve to the concrete method canonical ref (only the name-based `pyname://` edge exists), so intra-class impact precision is reduced. | Medium | Planned (R3) |
| F4 | DB effect direction is coarse: every `execute(...)` is classified `write`, so a read-only `execute('SELECT ...')` is mislabeled. | Low | Planned (R4) |

## Remediation plan

### R1 — Exclude structural containers from impact results — DONE

- Change: `agent/project_twin/analysis.py` skips `repository/directory/file/module/package` node types
  when building impact items (they are reached via containment edges but are not behavioral impacts).
- Test: `tests/test_project_twin_impact_analysis.py::test_impact_excludes_structural_container_nodes`.
- Result: virtual-project checks 9 & 12 now PASS; container noise eliminated.

### R2 — Model config reads beyond the `.get()` Call form — PLANNED

- Target: `agent/project_twin/behavioral_graph.py` (`_config_identity` + a Subscript branch in
  `_emit_behavior_facts`).
- Scope: detect `os.environ['X']` / `os.environ["X"]` subscript reads (and optionally `settings.X` /
  `config.get('X')` patterns behind a conservative allowlist) as `resource://config:<X>` with read
  direction. Keep heuristic; do not flag arbitrary dict subscripts.
- Acceptance: `os.environ['LEGACY_FLAG']` yields `resource://config:LEGACY_FLAG`; a config-change
  ImpactRequest returns the reader; existing config tests still pass.
- Priority: medium (config-impact completeness).

### R3 — Resolve self/class-method calls to concrete refs — PLANNED

- Target: `agent/project_twin/static_graph.py` call-resolution (`handle_function` / a per-class method
  table) and/or `behavioral_graph.py` local resolution.
- Scope: within a class body, resolve `self.m()` to `py://<rel>#<Class>.m` when `m` is defined on the
  same class; keep the name-based edge; leave cross-class/duck-typed calls name-based + ambiguous.
- Acceptance: `self._validate()` produces a `calls` edge to `py://app/models.py#ItemRepo._validate`;
  no regression to module-level resolution.
- Priority: medium (intra-class impact precision).

### R4 — DB effect direction precision — PLANNED

- Target: `agent/project_twin/behavioral_graph.py` `_resource_direction` for `kind == "database"`.
- Scope: inspect the first string arg of `execute/executemany` — `SELECT` → `read`, `INSERT/UPDATE/DELETE`
  → `write`/`delete`; default `write` when unknown. Keep heuristic.
- Acceptance: `execute('SELECT ...')` → read; `execute('INSERT ...')` → write.
- Priority: low (direction is already advisory).

## Sequencing

R1 is landed. R2 and R3 are natural PIBIH-3 follow-on deepening (already listed as PIBIH-3 deferred
gaps) and can be taken before or alongside PIBIH-4. R4 is opportunistic. None block PIBIH-4.

## Safety / invariants

All twin facts remain `inferred` / `heuristic_static`; impact analysis reads the snapshot and never
mutates; no Proposal / Safe Apply / Verification boundary is touched by evaluation or R1.
