from __future__ import annotations

import re
from pathlib import PurePosixPath

from agent.atlas_ci_failure_repair_schema import (
    AtlasCIFailureEvidence,
    AtlasCIFailureRepairRequest,
    AtlasCIRepairPlan,
)


_PYTEST_FAILED_RE = re.compile(r"^FAILED\s+([^\s:]+(?:::?[^\s]+)*)", re.MULTILINE)
_PYTEST_PATH_RE = re.compile(r"([\w./-]*tests?[\w./-]*\.py)(?:::[\w\[\].-]+)?")


class AtlasCIFailureRepairService:
    """Convert supplied CI/test failure text into bounded advisory repair metadata."""

    def build(self, request: AtlasCIFailureRepairRequest) -> dict:
        failing_tests = self._unique(list(request.failing_test_names) + self._pytest_failures(request.log_text))
        affected_files = self._unique(list(request.affected_files) + [self._test_to_path(name) for name in failing_tests])
        affected_files = [path for path in affected_files if path]
        mapped_items = self._mapped_plan_items(affected_files, request.plan_items)
        allowed, blocked = self._split_allowed(affected_files, request.allowed_paths)
        confidence = self._confidence(failing_tests=failing_tests, affected_files=affected_files)
        failure_class = "pytest_failure" if failing_tests else ("ci_failure_unclassified" if request.log_text.strip() else "unknown")
        evidence = AtlasCIFailureEvidence(
            source=request.source or "manual",
            run_id=request.run_id,
            job_id=request.job_id,
            failing_command=request.failing_command,
            failing_test_names=failing_tests,
            log_excerpt=self._excerpt(request.log_text),
            affected_files=affected_files,
            confidence=confidence,
            bounded_repair_recommendation=self._recommendation(allowed, confidence),
            metadata=self._no_execution_metadata(),
        )
        planned = bool(allowed and confidence != "unknown")
        warnings = []
        if not failing_tests:
            warnings.append("no_failing_tests_detected")
        if blocked:
            warnings.append("affected_files_outside_allowed_paths")
        if not allowed:
            warnings.append("no_allowed_repair_files")
        plan = AtlasCIRepairPlan(
            status="planned" if planned else "blocked",
            failure_class=failure_class,
            mapped_plan_item_ids=mapped_items,
            affected_files=affected_files,
            allowed_repair_files=allowed,
            blocked_files=blocked,
            post_repair_verification_required=planned,
            recommended_verification_commands=self._recommended_commands(request.failing_command, failing_tests),
            confidence=confidence,
            warnings=warnings,
            metadata=self._no_execution_metadata(),
        )
        return {
            "ci_failure_evidence": evidence.model_dump(),
            "ci_repair_plan": plan.model_dump(),
            "post_ci_repair_verification_required": plan.post_repair_verification_required,
            "ci_failure_ingestion": {
                "status": "available" if request.log_text.strip() or failing_tests or affected_files else "missing",
                **self._no_execution_metadata(),
            },
        }

    @staticmethod
    def _pytest_failures(text: str) -> list[str]:
        failures = [match.group(1).strip() for match in _PYTEST_FAILED_RE.finditer(text or "")]
        if failures:
            return failures
        return [match.group(0).strip() for match in _PYTEST_PATH_RE.finditer(text or "")]

    @staticmethod
    def _test_to_path(name: str) -> str:
        return str(name or "").split("::", 1)[0].replace("\\", "/")

    @staticmethod
    def _mapped_plan_items(paths: list[str], plan_items: list[dict]) -> list[str]:
        mapped: list[str] = []
        path_set = set(paths)
        for raw in plan_items or []:
            item = raw if isinstance(raw, dict) else {}
            targets = {str(path).replace("\\", "/") for path in item.get("target_files") or []}
            if targets & path_set:
                item_id = str(item.get("item_id") or item.get("id") or "")
                if item_id:
                    mapped.append(item_id)
        return AtlasCIFailureRepairService._unique(mapped)

    @staticmethod
    def _split_allowed(paths: list[str], allowed_paths: list[str]) -> tuple[list[str], list[str]]:
        allowed_roots = [str(path).replace("\\", "/").rstrip("/") for path in allowed_paths or [] if str(path).strip()]
        if not allowed_roots:
            return list(paths), []
        allowed: list[str] = []
        blocked: list[str] = []
        for path in paths:
            normalized = str(PurePosixPath(path.replace("\\", "/")))
            if any(normalized == root or normalized.startswith(root + "/") for root in allowed_roots):
                allowed.append(normalized)
            else:
                blocked.append(normalized)
        return allowed, blocked

    @staticmethod
    def _confidence(*, failing_tests: list[str], affected_files: list[str]) -> str:
        if failing_tests and affected_files:
            return "high"
        if failing_tests:
            return "medium"
        return "unknown"

    @staticmethod
    def _excerpt(text: str) -> str:
        clean = "\n".join(line.rstrip() for line in str(text or "").splitlines() if line.strip())
        return clean[:1200]

    @staticmethod
    def _recommendation(allowed_files: list[str], confidence: str) -> str:
        if confidence == "unknown" or not allowed_files:
            return "Manual CI review required; no bounded repair file scope was inferred."
        return "Repair only the allowed affected files and rerun the failing CI command or tests after repair."

    @staticmethod
    def _recommended_commands(command: str, failing_tests: list[str]) -> list[str]:
        if command:
            return [command]
        if failing_tests:
            return ["python -m pytest -q " + " ".join(failing_tests[:5])]
        return []

    @staticmethod
    def _no_execution_metadata() -> dict:
        return {
            "advisory_only": True,
            "executed": False,
            "remote_ci_fetched": False,
            "shell_executed": False,
            "remote_git_push_executed": False,
            "draft_pr_updated": False,
            "auto_repair_executed": False,
        }

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for value in values:
            text = str(value or "").replace("\\", "/").strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return out
