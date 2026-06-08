from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.patch_transaction import read_patch_transaction_manifest

SCHEMA_VERSION = "atlas.risk_classification.v1"


STRICT_GATE_EXACT = {
    "main.py", "start.bat", "start.sh", "dockerfile", "pyproject.toml", "package.json", "ui.html",
    "web/atlas_ui_surface_manifest.json", "app/atlas/workspace_snapshot.py", "app/atlas/patch_transaction.py",
    "app/atlas/risk_classification.py", "docs/atlas_autonomous_execution_readiness_policy.md",
    "docs/atlas_development_constitution.md", "docs/atlas_self_development_rules.md",
    "docs/atlas_preflight_checklist.md", "docs/atlas_postflight_checklist.md",
}
STRICT_GATE_PREFIX = (
    ".github/workflows/", "app/api/", "agent/atlas_safe_apply", "agent/atlas_auto_safe_apply",
    "agent/atlas_auto_verification", "agent/atlas_automation_gate", "agent/atlas_verification",
    "agent/debug_loop_runner", "agent/atlas_change_snapshot_restore", "web/js/atlas_dashboard.js",
    "web/js/atlas_pipeline_api.js", "scripts/", "launcher/",
)

# Recognised project source / web / asset / config file types. A change to one of these is an
# ordinary development change whose risk follows the *change type* (create = additive = low,
# modify = could break behaviour = medium) rather than being dumped into "unknown". This keeps the
# classifier from over-escalating ordinary external-project work (e.g. a root-level script.js /
# index.html game) while the strict-gate exact/prefix rules above still protect sensitive paths.
ORDINARY_SOURCE_SUFFIXES = frozenset({
    ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".vue", ".svelte",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".py", ".rb", ".php", ".go", ".rs", ".java", ".kt", ".swift",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".lua", ".sh",
    ".json", ".md", ".txt", ".csv", ".xml", ".svg", ".yml", ".yaml", ".toml",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _safe_relpath(value: str) -> str:
    if not value:
        raise ValueError("empty_path_forbidden")
    p = Path(value)
    if p.is_absolute():
        raise ValueError("absolute_paths_forbidden")
    if any(part in ("", ".", "..") for part in p.parts):
        raise ValueError("path_traversal_forbidden")
    return p.as_posix()


def _risk_flags(level: str) -> dict[str, Any]:
    human = level in {"medium", "high", "strict_gate"}
    return {
        "strict_gate_required": level == "strict_gate",
        "human_approval_required": human,
        "autonomous_allowed": False,
        "automatic_apply_allowed": False,
        "automatic_rollback_allowed": False,
        "verification_required": human,
    }


def classify_change_risk(*, project_path: str | Path, proposed_files: list[dict[str, Any]] | list[str] | None, reason: str = "") -> dict[str, Any]:
    project_root = Path(project_path).expanduser().resolve()
    warnings: list[str] = []
    matched_rules: list[dict[str, Any]] = []
    categories: set[str] = set()
    normalized: list[dict[str, Any]] = []

    raw_files = proposed_files or []
    if not raw_files:
        level = "unknown"
        matched_rules.append({"rule_id": "unknown.empty_files", "level": level, "reason": "No proposed files", "paths": []})
        categories.add("unknown")
    else:
        for item in raw_files:
            entry = item if isinstance(item, dict) else {"relative_path": str(item), "change_type": "unknown"}
            rel_raw = str(entry.get("relative_path", "") or "")
            change_type = str(entry.get("change_type", "unknown") or "unknown")
            record = {"relative_path": rel_raw, "change_type": change_type, "path_valid": False, "warnings": []}
            try:
                rel = _safe_relpath(rel_raw)
                _ensure_under(project_root, project_root / rel, "project_escape")
                record["relative_path"] = rel
                record["path_valid"] = True
            except ValueError as exc:
                record["warnings"].append(str(exc))
                warnings.append(f"invalid_path:{rel_raw}:{exc}")
            normalized.append(record)

        level_rank = {"unknown": 0, "low": 1, "medium": 2, "high": 3, "strict_gate": 4}
        level = "low"

        for rec in normalized:
            if not rec["path_valid"]:
                categories.add("unknown")
                matched_rules.append({"rule_id": "unknown.invalid_path", "level": "unknown", "reason": "Invalid path", "paths": [rec["relative_path"]]})
                if level != "strict_gate":
                    level = "unknown"
                continue
            rp = rec["relative_path"].lower()
            ct = rec["change_type"]
            if rp in STRICT_GATE_EXACT or rp.startswith(STRICT_GATE_PREFIX) or rp.startswith("docker-compose") or rp.startswith("requirements") or rp.endswith(".lock"):
                categories.update({"execution_semantics", "self_improvement"})
                matched_rules.append({"rule_id": "strict.path", "level": "strict_gate", "reason": "Strict-gate path", "paths": [rec["relative_path"]]})
                level = "strict_gate"
                continue
            if rp.startswith("app/api/"):
                categories.add("api_surface")
                matched_rules.append({"rule_id": "strict.api", "level": "strict_gate", "reason": "Execution API path", "paths": [rec["relative_path"]]})
                level = "strict_gate"
                continue
            if ct in {"delete", "rename"}:
                categories.add("rollback")
                matched_rules.append({"rule_id": "high.change_type", "level": "high", "reason": "Delete/rename risk", "paths": [rec["relative_path"]]})
                if level != "strict_gate":
                    level = "high"
                continue
            if rp.startswith("docs/"):
                categories.add("docs_only")
                matched_rules.append({"rule_id": "low.docs", "level": "low", "reason": "Non-policy docs path", "paths": [rec["relative_path"]]})
                continue
            if rp.startswith("tests/"):
                categories.add("tests_only")
                matched_rules.append({"rule_id": "low.tests", "level": "low", "reason": "Tests-only change", "paths": [rec["relative_path"]]})
                continue
            if rp.startswith(("app/", "agent/", "web/")):
                categories.add("execution_semantics")
                matched_rules.append({"rule_id": "medium.impl", "level": "medium", "reason": "Implementation change", "paths": [rec["relative_path"]]})
                if level in {"low", "unknown"}:
                    level = "medium"
                continue
            if Path(rp).suffix in ORDINARY_SOURCE_SUFFIXES:
                # Ordinary project source/asset file outside the strict-gate set: classify by change
                # type instead of "unknown". Creating a new file is additive (low); modifying an
                # existing one can break behaviour (medium); delete/rename was already handled above.
                if ct == "create":
                    categories.add("additive_source")
                    matched_rules.append({"rule_id": "low.new_source_file", "level": "low", "reason": "New project source/asset file", "paths": [rec["relative_path"]]})
                else:
                    categories.add("execution_semantics")
                    matched_rules.append({"rule_id": "medium.modify_source_file", "level": "medium", "reason": "Modify existing project source/asset file", "paths": [rec["relative_path"]]})
                    if level in {"low", "unknown"}:
                        level = "medium"
                continue
            categories.add("unknown")
            matched_rules.append({"rule_id": "unknown.unclassified", "level": "unknown", "reason": "Unclassified path", "paths": [rec["relative_path"]]})
            level = "unknown" if level != "strict_gate" else level

        if len(normalized) > 25 and level != "strict_gate":
            matched_rules.append({"rule_id": "high.too_many_files", "level": "high", "reason": "Too many files changed", "paths": [r["relative_path"] for r in normalized]})
            level = "high" if level != "strict_gate" else level

    scores = {"unknown": 0, "low": 20, "medium": 50, "high": 75, "strict_gate": 95}
    flags = _risk_flags(level)
    return {
        "schema_version": SCHEMA_VERSION,
        "project_path": str(project_root),
        "reason": reason,
        "proposed_files": normalized,
        "risk_level": level,
        "risk_score": scores[level],
        "risk_categories": sorted(categories) if categories else ["unknown"],
        "matched_rules": matched_rules,
        "warnings": warnings,
        **flags,
        "policy_notes": [
            "Risk classification is metadata-only and does not authorize execution.",
            "Unknown risk is not low risk.",
            "Atlas runtime remains level_0_manual_only.",
        ],
    }


def create_risk_classification_record(*, project_path: str | Path, data_root: str | Path, proposed_files: list[dict[str, Any]] | list[str] | None = None, workspace_id: str = "", pool_id: str = "", item_id: str = "", run_id: str = "", reason: str = "", transaction_id: str = "", transaction_manifest_path: str = "", dry_run: bool = False) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    risk_id = f"risk_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    risk_dir = root / "atlas" / "risk_classifications" / risk_id
    result = classify_change_risk(project_path=project_path, proposed_files=proposed_files, reason=reason)
    created_at = _utc_now()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "risk_id": risk_id,
        "created_at": created_at,
        "project_path": result["project_path"],
        "data_root": str(root),
        "workspace_id": workspace_id,
        "pool_id": pool_id,
        "item_id": item_id,
        "run_id": run_id,
        "reason": reason,
        "transaction_id": transaction_id,
        "transaction_manifest_path": transaction_manifest_path,
        "proposed_files": result["proposed_files"],
        "risk_level": result["risk_level"],
        "risk_score": result["risk_score"],
        "risk_categories": result["risk_categories"],
        "matched_rules": result["matched_rules"],
        "strict_gate_required": result["strict_gate_required"],
        "human_approval_required": result["human_approval_required"],
        "autonomous_allowed": False,
        "automatic_apply_allowed": False,
        "automatic_rollback_allowed": False,
        "verification_required": result["verification_required"],
        "policy_notes": result["policy_notes"],
        "warnings": result["warnings"],
        "summary": summarize_risk_classification(result),
    }
    manifest_path = risk_dir / "manifest.json"
    if not dry_run:
        risk_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"status": "planned" if dry_run else "created", "risk_id": risk_id, "risk_dir": str(risk_dir), "manifest_path": str(manifest_path), "manifest": manifest, "dry_run": dry_run}


def read_risk_classification_record(*, manifest_path: str | Path | None = None, risk_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    if manifest_path is None:
        if not risk_id or data_root is None:
            raise ValueError("manifest_locator_required")
        manifest = Path(data_root).resolve() / "atlas" / "risk_classifications" / risk_id / "manifest.json"
    else:
        manifest = Path(manifest_path).expanduser().resolve()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    root = Path(data_root if data_root is not None else payload.get("data_root", "")).expanduser().resolve()
    _ensure_under(root, manifest, "manifest_outside_data_root")
    return {"manifest": payload, "warnings": []}


def classify_patch_transaction_risk(*, data_root: str | Path, transaction_manifest_path: str | Path | None = None, transaction_id: str = "", project_path: str | Path | None = None, workspace_id: str = "", pool_id: str = "", item_id: str = "", run_id: str = "", reason: str = "", dry_run: bool = False) -> dict[str, Any]:
    tx = read_patch_transaction_manifest(manifest_path=transaction_manifest_path, transaction_id=transaction_id, data_root=data_root)["manifest"]
    tx_path = str(Path(transaction_manifest_path).resolve()) if transaction_manifest_path else str(Path(data_root).resolve() / "atlas" / "patch_transactions" / tx["transaction_id"] / "manifest.json")
    warnings = []
    if not tx.get("snapshot_id"):
        warnings.append("snapshot_id_missing")
    if not tx.get("snapshot_manifest_path"):
        warnings.append("snapshot_manifest_path_missing")
    rec = create_risk_classification_record(
        project_path=project_path or tx["project_path"],
        data_root=data_root,
        proposed_files=tx.get("proposed_files") or [],
        workspace_id=workspace_id or tx.get("workspace_id", ""),
        pool_id=pool_id or tx.get("pool_id", ""),
        item_id=item_id or tx.get("item_id", ""),
        run_id=run_id or tx.get("run_id", ""),
        reason=reason or tx.get("reason", ""),
        transaction_id=tx.get("transaction_id", ""),
        transaction_manifest_path=tx_path,
        dry_run=dry_run,
    )
    rec["manifest"]["warnings"] = sorted(set(rec["manifest"].get("warnings", []) + warnings))
    return rec


def summarize_risk_classification(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "risk_level": payload.get("risk_level", "unknown"),
        "risk_score": payload.get("risk_score", 0),
        "strict_gate_required": bool(payload.get("strict_gate_required", False)),
        "human_approval_required": bool(payload.get("human_approval_required", False)),
        "autonomous_allowed": False,
        "automatic_apply_allowed": False,
        "automatic_rollback_allowed": False,
        "verification_required": bool(payload.get("verification_required", False)),
        "matched_rule_count": len(payload.get("matched_rules", [])),
        "warnings_count": len(payload.get("warnings", [])),
    }
