from __future__ import annotations

import re

# Requirement status values
REQ_STATUS_PLANNED = "planned"
REQ_STATUS_IMPLEMENTED = "implemented"
REQ_STATUS_VERIFIED = "verified"
REQ_STATUS_VERIFIED_STATIC = "verified_static"
REQ_STATUS_MISSING = "missing"
REQ_STATUS_PARTIAL = "partial"
REQ_STATUS_UNVERIFIED = "unverified"
SUCCESS_STATUSES = {REQ_STATUS_VERIFIED, REQ_STATUS_VERIFIED_STATIC}

_SENTENCE_SPLIT = re.compile(r'[。.!?！？\n]+')
_TOKEN_RE = re.compile(r'[a-zA-Z][a-zA-Z0-9]+')
# Common words that carry no mapping signal.
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "should", "must", "shall", "need", "needs",
    "please", "add", "create", "make", "ensure", "show", "display", "update", "page", "code",
    "implement", "implementation", "from", "into", "when", "where", "which", "have", "has",
    "will", "your", "use", "using", "value", "values", "file", "files", "user", "users",
})

_PHRASE_SYNONYMS: dict[str, set[str]] = {
    "レインボー": {"rainbow", "hsl", "hue", "gradient", "color"},
    "虹": {"rainbow", "hsl", "hue", "gradient", "color"},
    "アニメ": {"animation", "animate", "keyframes", "requestanimationframe"},
    "動き": {"animation", "animate", "keyframes", "requestanimationframe"},
    "表示": {"display", "show", "render", "text"},
    "色": {"color", "hsl", "hue", "rgb", "gradient"},
}

_BEHAVIOR_SIGNALS: dict[str, tuple[str, ...]] = {
    "rainbow": ("rainbow", "hsl(", "hue-rotate", "linear-gradient", "@keyframes", "color:"),
    "hsl": ("hsl(",),
    "hue": ("hue-rotate", "hsl(",),
    "gradient": ("linear-gradient", "radial-gradient"),
    "animation": ("requestanimationframe", "@keyframes", "setinterval", "animation:"),
    "animate": ("requestanimationframe", "@keyframes", "setinterval", "animation:"),
    "keyframes": ("@keyframes",),
    "requestanimationframe": ("requestanimationframe",),
    "display": ("<body", "textcontent", "innerhtml", "display:"),
    "render": ("<canvas", "render", "draw", "textcontent", "innerhtml"),
    "color": ("color:", "background", "hsl(", "rgb(", "linear-gradient"),
}


def _keywords(text: str) -> set[str]:
    """Meaningful lowercase tokens (len>=4, not stopwords) used for requirement↔file mapping."""
    raw = text or ""
    out = {t.lower() for t in _TOKEN_RE.findall(raw) if len(t) >= 4 and t.lower() not in _STOPWORDS}
    lowered = raw.lower()
    for phrase, synonyms in _PHRASE_SYNONYMS.items():
        if phrase in raw:
            out |= synonyms
    # Keep common short CSS/code tokens only when they are semantically meaningful.
    for token in ("hsl", "rgb", "hue"):
        if token in lowered:
            out.add(token)
    return out


def _file_matches(path: str, keywords: set[str]) -> bool:
    """A file matches a requirement when its path tokens overlap the requirement keywords."""
    if not keywords:
        return False
    file_tokens = {t.lower() for t in _TOKEN_RE.findall(str(path) or "")}
    return bool(file_tokens & keywords)


def _content_matches(content: str, keywords: set[str]) -> bool:
    if not content or not keywords:
        return False
    lowered = content.lower()
    for kw in keywords:
        signals = _BEHAVIOR_SIGNALS.get(kw)
        if signals and any(sig in lowered for sig in signals):
            return True
        if len(kw) >= 4 and kw in lowered:
            return True
    return False



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

    def map_requirements_to_evidence(
        self,
        requirements: list[dict],
        *,
        changed_files: list[str],
        verified_files: list[str] | None = None,
        verified_static_files: list[str] | None = None,
        done_definitions: list[str] | None = None,
        file_contents: dict[str, str] | None = None,
        requirement_evidence: dict[str, dict] | None = None,
    ) -> list[dict]:
        """Map each requirement to evidence.

        Explicit requirement IDs are authoritative. Keyword matching is fallback
        advisory evidence only and never verifies an unrelated requirement.
        """
        changed = list(changed_files or [])
        verified = set(verified_files or [])
        verified_static = set(verified_static_files or [])
        done_text = " ".join(done_definitions or []).lower()
        contents = dict(file_contents or {})
        explicit = dict(requirement_evidence or {})
        out: list[dict] = []
        for req in requirements:
            req_id = str(req.get("requirement_id") or "")
            evidence = dict(explicit.get(req_id) or {}) if req_id else {}
            if evidence:
                changed_for_req = list(dict.fromkeys(evidence.get("changed_files") or []))
                planned_files = list(dict.fromkeys(evidence.get("planned_files") or req.get("planned_files") or []))
                planned_items = list(dict.fromkeys(evidence.get("planned_items") or []))
                status = _status_from_explicit_evidence(evidence, changed_for_req, planned_files, planned_items)
                out.append({
                    **req,
                    "planned_files": planned_files,
                    "planned_items": planned_items,
                    "changed_files": changed_for_req,
                    "implementation_evidence": changed_for_req,
                    "implemented_symbols": list(dict.fromkeys(evidence.get("implemented_symbols") or [])),
                    "implemented_signals": list(dict.fromkeys(evidence.get("implemented_signals") or [])),
                    "verification_method": str(evidence.get("verification_method") or ""),
                    "verification_status": str(evidence.get("verification_status") or ""),
                    "evidence_path": str(evidence.get("evidence_path") or ""),
                    "status": status,
                    "evidence_source": "explicit_requirement_id",
                })
                continue

            kw = _keywords(str(req.get("description") or ""))
            # done_definition keywords reinforce the requirement's vocabulary
            kw |= (_keywords(done_text) & kw) if done_text else set()
            matched = [
                f for f in changed
                if _file_matches(f, kw) or _content_matches(str(contents.get(f) or ""), kw)
            ]
            if matched:
                if any(f in verified for f in matched):
                    status = REQ_STATUS_VERIFIED
                elif any(f in verified_static for f in matched):
                    status = REQ_STATUS_VERIFIED_STATIC
                else:
                    status = REQ_STATUS_IMPLEMENTED
                evidence = list(matched)
            elif changed:
                status = REQ_STATUS_PARTIAL
                evidence = []
            else:
                status = REQ_STATUS_MISSING
                evidence = []
            verification_method = "verification_passed" if status in SUCCESS_STATUSES else ""
            out.append({
                **req,
                "planned_files": list(req.get("planned_files") or []),
                "planned_items": list(req.get("planned_items") or []),
                "changed_files": evidence,
                "implementation_evidence": evidence,
                "verification_method": verification_method,
                "verification_status": "passed" if status in SUCCESS_STATUSES else "",
                "evidence_path": "",
                "status": status,
                "evidence_source": "keyword_fallback",
            })
        return out

    def coverage_summary(self, requirements: list[dict]) -> dict:
        """Return a summary of requirement coverage."""
        mandatory = [r for r in requirements if bool(r.get("required", True))]
        total = len(requirements)
        mandatory_total = len(mandatory)
        by_status: dict[str, int] = {}
        for req in requirements:
            s = str(req.get("status") or REQ_STATUS_PLANNED)
            by_status[s] = by_status.get(s, 0) + 1

        mandatory_by_status: dict[str, int] = {}
        for req in mandatory:
            s = str(req.get("status") or REQ_STATUS_PLANNED)
            mandatory_by_status[s] = mandatory_by_status.get(s, 0) + 1

        incomplete = [
            req for req in mandatory
            if str(req.get("status") or REQ_STATUS_PLANNED) not in SUCCESS_STATUSES
        ]
        all_verified = mandatory_total > 0 and not incomplete
        success_eligible = all_verified

        return {
            "total": total,
            "mandatory_total": mandatory_total,
            "by_status": by_status,
            "mandatory_by_status": mandatory_by_status,
            "missing_or_partial_count": len(incomplete),
            "incomplete_requirement_ids": [str(req.get("requirement_id") or "") for req in incomplete],
            "all_verified": all_verified,
            "success_eligible": success_eligible,
        }


def _status_from_explicit_evidence(evidence: dict, changed_files: list[str], planned_files: list[str], planned_items: list[str]) -> str:
    verification_status = str(evidence.get("verification_status") or "").strip().lower()
    verification_method = str(evidence.get("verification_method") or "").strip().lower()
    if changed_files and verification_status == "passed":
        if verification_method in {"static_checked", "verified_static", "static"}:
            return REQ_STATUS_VERIFIED_STATIC
        return REQ_STATUS_VERIFIED
    if changed_files and verification_status in {"blocked", "skipped", "unavailable"}:
        return REQ_STATUS_UNVERIFIED
    if changed_files and verification_status == "failed":
        return REQ_STATUS_PARTIAL
    if changed_files:
        return REQ_STATUS_IMPLEMENTED
    if planned_files or planned_items:
        return REQ_STATUS_PLANNED
    return REQ_STATUS_MISSING
