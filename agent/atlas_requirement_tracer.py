from __future__ import annotations

import re

# Requirement status values
REQ_STATUS_PLANNED = "planned"
REQ_STATUS_IMPLEMENTED = "implemented"
REQ_STATUS_VERIFIED = "verified"
REQ_STATUS_MISSING = "missing"
REQ_STATUS_PARTIAL = "partial"

_SENTENCE_SPLIT = re.compile(r'[。.!?！？\n]+')
_REQ_PREFIXES = re.compile(
    r'^(?:must|should|shall|needs?\s+to|required?\s+to|'
    r'please|add|create|implement|make|ensure|fix|update|show|display|'
    r'する|してください|すること|必要|追加|実装|表示|修正)',
    re.IGNORECASE,
)


class AtlasRequirementTracer:
    """Extract atomic requirements from a user request and track their implementation status.

    Each requirement has:
        requirement_id, description, planned_files, implementation_evidence,
        verification_method, status
    """

    def extract_requirements(self, user_request: str) -> list[dict]:
        """Split user request into atomic requirements."""
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(user_request) if s.strip()]
        requirements: list[dict] = []
        for i, sentence in enumerate(sentences, start=1):
            if len(sentence) < 5:
                continue
            req_id = f"req_{i:03d}"
            requirements.append({
                "requirement_id": req_id,
                "description": sentence,
                "planned_files": [],
                "implementation_evidence": [],
                "verification_method": "",
                "status": REQ_STATUS_PLANNED,
            })
        return requirements

    def update_status(self, requirement: dict, *, implemented_files: list[str] | None = None,
                      verification_passed: bool = False) -> dict:
        """Update a requirement's status based on implementation evidence."""
        req = dict(requirement)
        if implemented_files:
            req["implementation_evidence"] = list(implemented_files)
        if verification_passed and req["implementation_evidence"]:
            req["status"] = REQ_STATUS_VERIFIED
        elif req["implementation_evidence"]:
            req["status"] = REQ_STATUS_IMPLEMENTED
        else:
            req["status"] = REQ_STATUS_MISSING
        return req

    def coverage_summary(self, requirements: list[dict]) -> dict:
        """Return a summary of requirement coverage."""
        total = len(requirements)
        by_status: dict[str, int] = {}
        for req in requirements:
            s = str(req.get("status") or REQ_STATUS_PLANNED)
            by_status[s] = by_status.get(s, 0) + 1

        missing_or_partial = (
            by_status.get(REQ_STATUS_MISSING, 0)
            + by_status.get(REQ_STATUS_PARTIAL, 0)
            + by_status.get(REQ_STATUS_PLANNED, 0)  # unprocessed = not success eligible
        )
        all_verified = by_status.get(REQ_STATUS_VERIFIED, 0) == total and total > 0
        success_eligible = missing_or_partial == 0 and total > 0

        return {
            "total": total,
            "by_status": by_status,
            "missing_or_partial_count": missing_or_partial,
            "all_verified": all_verified,
            "success_eligible": success_eligible,
        }
