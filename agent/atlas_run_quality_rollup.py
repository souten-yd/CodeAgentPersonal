from __future__ import annotations

from pathlib import Path

from agent.atlas_integration_checker import AtlasIntegrationChecker
from agent.atlas_automation_features import KEY_REQUIREMENT_COVERAGE_ENFORCEMENT
from agent.atlas_placeholder_detector import detect_placeholders, is_placeholder_only_content
from agent.atlas_repair_intent_classifier import is_test_only_repair_plan
from agent.atlas_requirement_tracer import AtlasRequirementTracer

_HTML_EXT = (".html",)
_JS_CSS_EXT = (".js", ".css", ".mjs", ".ts")
_IMPL_EXT = (".py", ".js", ".ts", ".mjs", ".html", ".css")
_TEST_MARKERS = ("/test/", "/tests/", "/spec/", "test_", "_test.", ".spec.", ".test.")


def _is_test_path(path: str) -> bool:
    p = path.lower().replace("\\", "/")
    return any(m in p for m in _TEST_MARKERS)


def _read(project_path: str, rel: str) -> str | None:
    try:
        fp = Path(project_path) / rel
        if not fp.exists():
            return None
        return fp.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _requirement_coverage(
    requirements: list[dict],
    changed_files: list[str],
    any_completed: bool,
    *,
    verified_files: list[str] | None = None,
    done_definitions: list[str] | None = None,
    file_contents: dict[str, str] | None = None,
) -> dict:
    """Map requirements to evidence (changed/verified files, done_definition) — conservative.

    - No implementation evidence at all (no changed files / nothing completed) → every
      requirement is 'missing' and the run is not success-eligible.
    - Otherwise map each requirement to changed/verified files via keyword overlap:
      matched+verified → verified, matched → implemented, unmapped → partial.
    - requirement_checked is only achievable when ALL requirements are 'verified'.
    """
    total = len(requirements)
    no_evidence = (not changed_files) or (not any_completed)
    if total == 0:
        return {"total": 0, "by_status": {}, "mapped": [], "no_implementation_evidence": False,
                "all_verified": False, "success_eligible": True}
    if no_evidence:
        return {
            "total": total,
            "by_status": {"missing": total},
            "mapped": [{**r, "status": "missing"} for r in requirements],
            "no_implementation_evidence": True,
            "all_verified": False,
            "success_eligible": False,
        }
    mapped = AtlasRequirementTracer().map_requirements_to_evidence(
        requirements, changed_files=changed_files, verified_files=verified_files,
        done_definitions=done_definitions, file_contents=file_contents,
    )
    by_status: dict[str, int] = {}
    for r in mapped:
        s = str(r.get("status") or "partial")
        by_status[s] = by_status.get(s, 0) + 1
    all_verified = by_status.get("verified", 0) == total and total > 0
    return {
        "total": total,
        "by_status": by_status,
        "mapped": mapped,
        "no_implementation_evidence": False,
        "all_verified": all_verified,
        # partial/implemented do not hard-fail a completed run (see PR-8d notes); only the
        # no-implementation-evidence case degrades.
        "success_eligible": True,
    }


def _integration_scan(project_path: str, changed_files: list[str]) -> tuple[list[dict], bool]:
    """Check that changed JS/CSS modules are referenced from a changed HTML entrypoint."""
    if not project_path:
        return [], False
    html_files = [f for f in changed_files if str(f).lower().endswith(_HTML_EXT)]
    js_css = [f for f in changed_files if str(f).lower().endswith(_JS_CSS_EXT) and not _is_test_path(f)]
    if not html_files or not js_css:
        return [], False
    checker = AtlasIntegrationChecker()
    warnings: list[dict] = []
    failed = False
    for html in html_files:
        html_path = Path(project_path) / html
        # Use import-graph traversal when JS modules present (catches transitive imports).
        js_files = [f for f in js_css if str(f).lower().endswith((".js", ".mjs", ".ts"))]
        css_files = [f for f in js_css if str(f).lower().endswith(".css")]
        if js_files:
            result = checker.check_entrypoint_import_graph(
                html_path, project_root=project_path, generated_files=js_css
            )
        else:
            result = checker.check_html_entrypoint(html_path, generated_files=css_files)
        for finding in result.get("findings", []):
            if finding.get("type") == "unused_export":
                warnings.append(finding)
                continue
            warnings.append(finding)
            if str(finding.get("severity")) == "failed":
                failed = True
    return warnings, failed


def _is_placeholder_only(content: str) -> bool:
    """Delegates to the shared helper so pre-apply and post-apply judge stubs identically."""
    return is_placeholder_only_content(content)


def _placeholder_scan(project_path: str, changed_files: list[str]) -> tuple[list[dict], bool]:
    if not project_path:
        return [], False
    warnings: list[dict] = []
    placeholder_only_files = 0
    impl_files = 0
    for rel in changed_files:
        if not str(rel).lower().endswith(_IMPL_EXT) or _is_test_path(rel):
            continue
        content = _read(project_path, rel)
        if content is None:
            continue
        impl_files += 1
        findings = detect_placeholders(content, file_path=rel)
        if findings:
            warnings.append({"path": rel, "findings": findings})
        if _is_placeholder_only(content):
            placeholder_only_files += 1
    # If every changed implementation file is placeholder-only, the change is a stub.
    placeholder_failed = impl_files > 0 and placeholder_only_files == impl_files and placeholder_only_files > 0
    return warnings, placeholder_failed


def compute_run_quality_rollup(pool, item_results, *, project_path: str = "") -> dict:
    """Aggregate final-status quality signals for an autopilot run.

    Returns a rollup with requirement coverage, integration/placeholder warnings, repair
    warning, and a `degraded` flag with reasons. The caller degrades a would-be-success
    terminal status when `degraded` is True.
    """
    changed: list[str] = []
    verified_files: list[str] = []
    for r in item_results:
        files = list(getattr(r, "changed_files", []) or [])
        changed += files
        # Files are "verified" only when the item completed with a passing verification.
        vr = getattr(r, "verification_result", {}) or {}
        if str(getattr(r, "status", "")) == "completed" and str(vr.get("status") or "") == "passed":
            verified_files += files
    changed = list(dict.fromkeys(changed))
    verified_files = list(dict.fromkeys(verified_files))
    any_completed = any(str(getattr(r, "status", "")) == "completed" for r in item_results)

    pool_meta = getattr(pool, "metadata", {}) or {}
    requirements = pool_meta.get("requirement_trace") or []
    done_definitions: list[str] = []
    for it in (getattr(pool, "items", []) or []):
        done_definitions += list(getattr(it, "done_definition", []) or [])
    file_contents = {
        rel: text for rel in changed
        if str(rel).lower().endswith(_IMPL_EXT) and (text := _read(project_path, rel)) is not None
    }
    coverage = _requirement_coverage(
        requirements, changed, any_completed,
        verified_files=verified_files, done_definitions=done_definitions, file_contents=file_contents,
    )
    features = (pool_meta.get("automation_features") or {}) if isinstance(pool_meta.get("automation_features"), dict) else {}
    coverage_enforcement = str(features.get(KEY_REQUIREMENT_COVERAGE_ENFORCEMENT) or "warn").strip().lower()
    if coverage_enforcement not in {"warn", "enforce"}:
        coverage_enforcement = "warn"
    coverage["enforcement"] = coverage_enforcement

    integration_warnings, integration_failed = _integration_scan(project_path, changed)
    placeholder_warnings, placeholder_failed = _placeholder_scan(project_path, changed)

    # Repair warning: user reported a repair but the plan only touched tests.
    repair_warning = ""
    repair_intent = (getattr(pool, "metadata", {}) or {}).get("repair_intent") or {}
    if repair_intent.get("is_repair"):
        plan_items = [
            {
                "item_type": getattr(it, "item_type", ""),
                "target_files": list(getattr(it, "target_files", []) or []),
                "file_changes": list((getattr(it, "metadata", {}) or {}).get("file_changes") or []),
            }
            for it in (getattr(pool, "items", []) or [])
        ]
        if is_test_only_repair_plan(plan_items):
            repair_warning = "test_only_repair_plan"

    degrade_reasons: list[str] = []
    warnings: list[str] = []
    if coverage.get("no_implementation_evidence"):
        warnings.append("requirement_coverage_incomplete")
    if coverage.get("no_implementation_evidence") and coverage_enforcement == "enforce":
        degrade_reasons.append("requirement_coverage_incomplete")
    if integration_failed:
        degrade_reasons.append("integration_failed")
    if placeholder_failed:
        degrade_reasons.append("placeholder_only")
    if repair_warning:
        degrade_reasons.append(repair_warning)

    return {
        "requirement_coverage": coverage,
        "integration_warnings": integration_warnings,
        "placeholder_warnings": placeholder_warnings,
        "repair_warning": repair_warning,
        "warnings": warnings,
        "degraded": bool(degrade_reasons),
        "degrade_reasons": degrade_reasons,
        "changed_files": changed,
    }
