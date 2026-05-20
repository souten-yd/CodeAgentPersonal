# Atlas Implementation Preflight Checklist

Must run before implementation.

## 1. Required Docs to Read

- docs/atlas_development_handoff.md
- docs/atlas_scale_master_roadmap.md
- docs/atlas_unified_autopilot_checkpoint.md
- docs/atlas_autopilot_current_status.md
- docs/atlas_autopilot_scale_master_plan.md
- docs/atlas_development_constitution.md
- docs/atlas_preflight_checklist.md

## 2. GitHub State Verification

必須:
- Confirm latest merged PR on GitHub.
- Compare GitHub latest PR with checkpoint docs.
- Inspect actual main branch files.
- Do not trust PR body text alone.

## 3. Main File Inspection

必須:
- Inspect files that will be changed.
- Inspect related tests.
- Inspect API registration.
- Inspect UI script loading.
- Inspect cache bust.
- Inspect data_root usage.
- Inspect helper existence / UI binding / endpoint chain.

## 4. Runtime Wiring Checklist

For every new UI feature:
- ui.html DOM exists
- AtlasPipelineAPI helper exists
- atlas_dashboard.js binding exists
- backend endpoint exists
- backend router is registered
- test checks actual main files

For every new API:
- router registered
- Request-aware root used
- validation exists
- response shape tested
- missing resource behavior defined

For every new service:
- data_root injected
- no Path("ca_data")
- no shell=True
- no remote git
- no unintended project file modification

## 5. Safety Checklist

Confirm:
- no execution semantics change unless explicitly requested
- no execute all
- no auto continue
- no automatic safe_apply
- no automatic verification
- no automatic retry
- no automatic patch generation
- no automatic test execution
- no shell=True
- no remote git


## Runtime Chain Test Design Preflight

Required before implementation:

1. Identify the exact runtime chain that must work.
2. List at least 3 broken cases that the PR tests must catch.
3. Write or update tests so those broken cases would fail.
4. Do not rely on token/string presence alone.
5. For UI changes, identify:
   - DOM ID
   - API helper
   - dashboard function
   - bind/init attachment point
   - endpoint
   - response unwrap
   - render target
   - cache bust
6. For backend/API changes, identify:
   - service constructor and injected data_root
   - API endpoint
   - router registration
   - validation path
   - missing resource behavior
   - response metadata flags
7. Stop implementation if the tests cannot distinguish a working runtime chain from a string-only placeholder.

## 6. Test Design Checklist

Tests must not be placeholder-only.

Required:
- positive path
- missing/non-blocking path
- validation failure path
- safety flags
- root/data_root behavior
- actual main file contract for UI/helper/binding
