from __future__ import annotations

# Indicators that a requirement or plan item is ambiguous and needs clarification
_AMBIGUITY_MARKERS = [
    "unclear",
    "ambiguous",
    "multiple interpretations",
    "could be interpreted",
    "scope not defined",
    "conflicting",
    "unknown dependency",
    "requires user decision",
    "which approach",
    "どちら",
    "明確でない",
    "複数の解釈",
    "スコープ不明",
]


class AtlasClarificationGateService:
    """Gate that requires user clarification before Patch/Apply when requirements are ambiguous.

    Callers supply a list of ambiguity signals detected during planning.
    If any signals are present, the gate returns clarification_required=True
    along with structured options for the user.

    Safe, obvious default assumptions bypass this gate and are recorded in
    the final summary as explicit_assumptions.
    """

    def evaluate(
        self,
        ambiguity_signals: list[str],
        *,
        options: list[dict] | None = None,
        safe_default_assumption: str = "",
    ) -> dict:
        """Evaluate whether clarification is needed.

        Args:
            ambiguity_signals: List of ambiguity descriptions detected by the planner.
            options: If provided, structured options to present to the user.
                     Each: {option_id, label, description, merit, risk}.
            safe_default_assumption: If non-empty and the risk is clearly low, proceed
                                      with this assumption instead of blocking.

        Returns:
            {
                clarification_required: bool,
                gate_status: "passed" | "clarification_required" | "proceeded_with_assumption",
                ambiguity_signals: list,
                options: list,
                assumption: str,
            }
        """
        if not ambiguity_signals:
            return self._passed()

        # Safety-sensitive signals must never use a safe default — always require clarification
        safety_sensitive = any(
            kw in sig.lower() for sig in ambiguity_signals
            for kw in ("execution", "capability", "safety policy", "runtime", "external access",
                       "network", "permission", "security", "credential")
        )

        if safe_default_assumption and not safety_sensitive:
            return {
                "clarification_required": False,
                "gate_status": "proceeded_with_assumption",
                "ambiguity_signals": ambiguity_signals,
                "options": [],
                "assumption": safe_default_assumption,
            }

        return {
            "clarification_required": True,
            "gate_status": "clarification_required",
            "ambiguity_signals": ambiguity_signals,
            "options": list(options or []),
            "assumption": "",
        }

    def detect_ambiguities(self, plan_text: str) -> list[str]:
        """Scan plan text for ambiguity markers and return found signals."""
        found: list[str] = []
        text_lower = plan_text.lower()
        for marker in _AMBIGUITY_MARKERS:
            if marker.lower() in text_lower:
                found.append(marker)
        return found

    @staticmethod
    def _passed() -> dict:
        return {
            "clarification_required": False,
            "gate_status": "passed",
            "ambiguity_signals": [],
            "options": [],
            "assumption": "",
        }
