from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.atlas_journal import AtlasJournal
from agent.atlas_nexus_research_schema import (
    AtlasContextFinding,
    AtlasNexusContextPack,
    AtlasNexusResearchRequest,
    AtlasResearchPurpose,
    AtlasResearchStatus,
)
from agent.atlas_plan_pool_schema import AtlasPlanItem


_ALLOWED_PURPOSES = {
    "codebase_context",
    "memory_context",
    "log_context",
    "web_research",
    "ui_design_research",
    "technical_research",
    "math_reasoning_support",
    "intent_disambiguation",
    "support_data_collection",
}

_ALLOWED_STATUSES = {
    "pending",
    "running",
    "completed",
    "completed_with_warnings",
    "failed",
    "skipped",
}


class AtlasNexusResearchAdapter:
    def __init__(
        self,
        nexus_client: object | None = None,
        journal: AtlasJournal | None = None,
    ):
        self.nexus_client = nexus_client
        self.journal = journal

    def run_research(self, request: AtlasNexusResearchRequest) -> AtlasNexusContextPack:
        if not request.query.strip():
            context_pack = self.build_empty_context_pack(request, "empty_query")
            self.save_context_pack(context_pack, pool_id=request.pool_id)
            return context_pack

        if self.nexus_client is None:
            context_pack = self.build_empty_context_pack(request, "nexus_client_unavailable")
            self.save_context_pack(context_pack, pool_id=request.pool_id)
            return context_pack

        try:
            if hasattr(self.nexus_client, "run_research"):
                result = self._call_with_request(getattr(self.nexus_client, "run_research"), request)
            elif hasattr(self.nexus_client, "search"):
                result = self._call_search(getattr(self.nexus_client, "search"), request)
            elif hasattr(self.nexus_client, "context_pack"):
                result = self._call_with_request(getattr(self.nexus_client, "context_pack"), request)
            else:
                context_pack = self.build_empty_context_pack(request, "nexus_client_has_no_supported_method")
                self.save_context_pack(context_pack, pool_id=request.pool_id)
                return context_pack
            context_pack = self.build_context_pack_from_result(request, result)
        except Exception as exc:
            context_pack = self.build_empty_context_pack(request, f"nexus_research_failed: {exc}")

        self.save_context_pack(context_pack, pool_id=request.pool_id)
        return context_pack

    def build_empty_context_pack(
        self,
        request: AtlasNexusResearchRequest,
        warning: str = "",
    ) -> AtlasNexusContextPack:
        warnings = [warning] if warning else []
        return AtlasNexusContextPack(
            request_id=request.request_id,
            purpose=request.purpose,
            status="completed_with_warnings" if warning else "completed",
            summary="No context returned from Nexus.",
            constraints=list(request.constraints),
            confidence=0.0,
            insufficient_context=True,
            warnings=warnings,
            metadata=self._context_pack_metadata(request),
        )

    def build_context_pack_from_result(
        self,
        request: AtlasNexusResearchRequest,
        result: object | dict,
    ) -> AtlasNexusContextPack:
        if isinstance(result, AtlasNexusContextPack):
            return result

        payload = self._payload_from_result(result)
        warnings = self._string_list(payload.get("warnings"))
        findings = self._findings_from_result(payload.get("findings"), warnings)
        summary = str(payload.get("summary") or "").strip()
        if not summary:
            summary = self._summary_from_findings(findings) or "No summary returned from Nexus."

        status = payload.get("status") or "completed"
        if status not in _ALLOWED_STATUSES:
            warnings.append(f"unsupported_status: {status}")
            status = "completed_with_warnings"

        metadata = self._context_pack_metadata(request)
        result_metadata = payload.get("metadata")
        if isinstance(result_metadata, dict):
            metadata.update(result_metadata)

        return AtlasNexusContextPack(
            request_id=str(payload.get("request_id") or request.request_id),
            purpose=self._coerce_purpose(payload.get("purpose") or request.purpose),
            status=status,
            summary=summary,
            findings=findings,
            constraints=self._string_list(payload.get("constraints")) or list(request.constraints),
            recommendations=self._string_list(payload.get("recommendations")),
            risks=self._string_list(payload.get("risks")),
            sources=self._dict_list(payload.get("sources")),
            confidence=self._float_value(payload.get("confidence"), default=0.0),
            freshness=str(payload.get("freshness") or ""),
            insufficient_context=bool(payload.get("insufficient_context", False)),
            warnings=warnings,
            errors=self._string_list(payload.get("errors")),
            metadata=metadata,
        )

    def save_context_pack(self, context_pack: AtlasNexusContextPack, pool_id: str = "") -> None:
        if self.journal is None:
            return

        resolved_pool_id = pool_id or str(context_pack.metadata.get("pool_id") or "")
        if not resolved_pool_id:
            return

        json_path = self._context_pack_path(resolved_pool_id, context_pack.context_pack_id, ".json")
        markdown_path = self._context_pack_path(resolved_pool_id, context_pack.context_pack_id, ".md")
        json_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(self._model_dump(context_pack), ensure_ascii=False, indent=2), encoding="utf-8")
        markdown_path.write_text(self._context_pack_markdown(context_pack), encoding="utf-8")

    def request_from_plan_item(
        self,
        item: AtlasPlanItem,
        purpose: str = "codebase_context",
        query: str = "",
    ) -> AtlasNexusResearchRequest:
        resolved_query = query.strip() or item.goal.strip() or item.description.strip() or item.title.strip()
        constraints = list(item.done_definition[:5]) + list(item.rollback_plan[:5])
        metadata = {
            "item_type": item.item_type,
            "risk_level": item.risk_level,
            "target_files": list(item.target_files),
            "linked_plan_id": item.linked_plan_id,
            "linked_requirement_id": item.linked_requirement_id,
        }
        return AtlasNexusResearchRequest(
            pool_id=item.pool_id,
            item_id=item.item_id,
            run_id=item.linked_run_id,
            source="planner",
            purpose=self._coerce_purpose(purpose),
            query=resolved_query,
            constraints=constraints,
            metadata=metadata,
        )

    def _call_with_request(self, method: Any, request: AtlasNexusResearchRequest) -> object:
        try:
            return method(request)
        except TypeError:
            return method(self._model_dump(request))

    def _call_search(self, method: Any, request: AtlasNexusResearchRequest) -> object:
        try:
            return method(query=request.query, max_sources=request.max_sources)
        except TypeError:
            try:
                return method(request.query, request.max_sources)
            except TypeError:
                return method(request.query)

    def _payload_from_result(self, result: object | dict) -> dict[str, Any]:
        if result is None:
            return {}
        if isinstance(result, dict):
            return dict(result)
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if hasattr(result, "dict"):
            return result.dict()
        payload: dict[str, Any] = {}
        for key in [
            "summary",
            "findings",
            "constraints",
            "recommendations",
            "risks",
            "sources",
            "confidence",
            "freshness",
            "insufficient_context",
            "warnings",
            "errors",
            "status",
            "metadata",
            "purpose",
            "request_id",
        ]:
            if hasattr(result, key):
                payload[key] = getattr(result, key)
        return payload

    def _findings_from_result(self, raw_findings: Any, warnings: list[str]) -> list[AtlasContextFinding]:
        if raw_findings is None:
            return []
        if not isinstance(raw_findings, list):
            raw_findings = [raw_findings]

        findings: list[AtlasContextFinding] = []
        for index, raw_finding in enumerate(raw_findings):
            if isinstance(raw_finding, AtlasContextFinding):
                findings.append(raw_finding)
                continue
            if isinstance(raw_finding, dict):
                try:
                    findings.append(AtlasContextFinding(**raw_finding))
                except Exception as exc:
                    warnings.append(f"invalid_finding_{index}: {exc}")
                continue
            if isinstance(raw_finding, str):
                findings.append(
                    AtlasContextFinding(
                        finding_type="other",
                        title=self._short_title(raw_finding),
                        content=raw_finding,
                    )
                )
                continue
            warnings.append(f"invalid_finding_{index}: unsupported finding type")
        return findings

    def _context_pack_path(self, pool_id: str, context_pack_id: str, suffix: str) -> Path:
        path_getter = getattr(self.journal, "context_pack_path", None)
        if callable(path_getter):
            return Path(path_getter(pool_id, context_pack_id, suffix))
        return self.journal.plan_pool_dir(pool_id) / "context_packs" / f"{context_pack_id}{suffix}"

    def _context_pack_markdown(self, context_pack: AtlasNexusContextPack) -> str:
        findings = [f"{finding.title}: {finding.content}" if finding.content else finding.title for finding in context_pack.findings]
        return f"""# Atlas Nexus Context Pack

- Context Pack ID: {context_pack.context_pack_id}
- Request ID: {context_pack.request_id}
- Purpose: {context_pack.purpose}
- Status: {context_pack.status}

## Summary

{context_pack.summary}

## Findings

{self._markdown_list(findings)}

## Recommendations

{self._markdown_list(context_pack.recommendations)}

## Risks

{self._markdown_list(context_pack.risks)}

## Warnings

{self._markdown_list(context_pack.warnings)}

## Errors

{self._markdown_list(context_pack.errors)}
"""

    def _context_pack_metadata(self, request: AtlasNexusResearchRequest) -> dict[str, Any]:
        return {
            "pool_id": request.pool_id,
            "item_id": request.item_id,
            "run_id": request.run_id,
            "request": self._model_dump(request),
        }

    def _summary_from_findings(self, findings: list[AtlasContextFinding]) -> str:
        if not findings:
            return ""
        titles = [finding.title for finding in findings[:3] if finding.title]
        return "; ".join(titles)

    def _short_title(self, value: str, limit: int = 80) -> str:
        compact = " ".join(value.split())
        if len(compact) <= limit:
            return compact or "Untitled finding"
        return compact[: limit - 1].rstrip() + "…"

    def _coerce_purpose(self, value: Any) -> AtlasResearchPurpose:
        text = str(value or "codebase_context")
        if text in _ALLOWED_PURPOSES:
            return text  # type: ignore[return-value]
        return "codebase_context"

    def _string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _dict_list(self, value: Any) -> list[dict]:
        if value is None:
            return []
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [dict(value)]
        return []

    def _float_value(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _model_dump(self, model: Any) -> dict[str, Any]:
        if hasattr(model, "model_dump"):
            return model.model_dump()
        return model.dict()

    def _markdown_list(self, values: list[str]) -> str:
        if not values:
            return "- None"
        return "\n".join(f"- {value}" for value in values)
