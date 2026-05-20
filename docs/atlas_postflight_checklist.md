# Atlas Implementation Postflight Checklist

Must run before PR completion.

## 1. Required Tests

Run targeted pytest for changed area.

Examples:
- Repo Context:
  pytest -q tests/test_atlas_repo_context_*.py
- UI:
  pytest -q tests/test_atlas_ui_script_contract.py
- Guarded Loop:
  pytest -q tests/test_atlas_guarded_operator_loop_service.py
- Docs:
  pytest -q tests/test_atlas_docs_roadmap_contract.py

## 2. JS Checks

If JS changed:
- node --check web/js/atlas_pipeline_api.js
- node --check web/js/atlas_dashboard.js

## 3. Grep Safety Checks

Run where relevant:

grep -R 'Path("ca_data")' agent app tests | cat
grep -R 'shell=True' agent app tests | cat
grep -R 'subprocess.run' agent app tests | cat
grep -R 'git push\|git pull\|git clone' agent app tests | cat
grep -R 'type="module"' ui.html web/js tests | cat

Note:
- grep hits are not always failures, but must be reviewed and explained.

## 4. UI Wiring Checks

If UI changed:
- grep DOM ID in ui.html
- grep API helper in web/js/atlas_pipeline_api.js
- grep binding in web/js/atlas_dashboard.js
- grep endpoint in app/api
- verify cache bust updated

## 5. Docs Updates

Every PR must update checkpoint docs:
- docs/atlas_unified_autopilot_checkpoint.md
- docs/atlas_autopilot_current_status.md
- docs/atlas_autopilot_scale_master_plan.md
- docs/atlas_development_handoff.md if current/next PR changes

## 6. Required PR Final Report

Every PR report must include:
- Completed PR
- Current PR
- Next PR
- Files changed
- Tests run
- Grep/safety checks
- Known limitations
- Safety confirmation
- Whether follow-up PR is required
