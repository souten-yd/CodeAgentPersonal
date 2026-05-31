from __future__ import annotations

# Severity levels that block Patch/Apply
_BLOCKING_SEVERITIES = frozenset({"high", "critical"})


class AtlasCritiqueGateService:
    """Gate that prevents Patch/Apply when high/critical critique findings exist.

    Callers should call evaluate() before proceeding with patch generation or
    safe apply. If the gate returns blocked=True, the plan must be revised or
    the finding overridden with an explicit reason.
    """

    def evaluate(
        self,
        critique_result: dict | None,
        *,
        override_reason: str = "",
    ) -> dict:
        """Evaluate critique findings against the blocking threshold.

        Args:
            critique_result: dict from AdversarialCritiqueResult.model_dump() or equivalent.
            override_reason: If provided, allows proceeding despite high findings.
                             Must be non-empty to override.

        Returns:
            {
                blocked: bool,
                blocking_findings: list[dict],
                override_applied: bool,
                override_reason: str,
                gate_status: "passed" | "blocked" | "overridden",
            }
        """
        if not critique_result:
            return self._passed()

        findings = list(critique_result.get("findings") or [])
        blocking = [
            f if isinstance(f, dict) else f.model_dump() if hasattr(f, "model_dump") else {}
            for f in findings
            if _is_blocking(f)
        ]
        consensus_risk = str(critique_result.get("consensus_risk") or "low").lower()
        requires_revision = bool(critique_result.get("requires_revision"))

        if not blocking and consensus_risk not in _BLOCKING_SEVERITIES and not requires_revision:
            return self._passed()

        # High/critical findings present
        if override_reason:
            return {
                "blocked": False,
                "blocking_findings": blocking,
                "override_applied": True,
                "override_reason": override_reason,
                "gate_status": "overridden",
            }

        return {
            "blocked": True,
            "blocking_findings": blocking,
            "override_applied": False,
            "override_reason": "",
            "gate_status": "blocked",
        }

    @staticmethod
    def _passed() -> dict:
        return {
            "blocked": False,
            "blocking_findings": [],
            "override_applied": False,
            "override_reason": "",
            "gate_status": "passed",
        }


def _is_blocking(finding) -> bool:
    if isinstance(finding, dict):
        return str(finding.get("severity") or "").lower() in _BLOCKING_SEVERITIES
    sev = getattr(finding, "severity", "")
    return str(sev).lower() in _BLOCKING_SEVERITIES
