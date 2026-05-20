from __future__ import annotations

from pathlib import Path

from agent.atlas_context_refresh_v2_schema import AtlasContextRefreshV2Bundle, AtlasContextRefreshV2Request
from agent.atlas_plan_item_impact_map_schema import AtlasPlanItemImpactMapRequest
from agent.atlas_plan_item_impact_map_service import AtlasPlanItemImpactMapService


class AtlasContextRefreshV2Service:
    def __init__(self, data_root: Path | str):
        self.data_root = Path(data_root).expanduser().resolve()
        self.impact_service = AtlasPlanItemImpactMapService(data_root=self.data_root)

    def refresh(self, req: AtlasContextRefreshV2Request) -> AtlasContextRefreshV2Bundle:
        plan_pool = dict(req.plan_pool or {})
        items = list(plan_pool.get("items") or [])
        warnings: list[str] = []
        status = "available"
        if not items:
            status = "empty_plan_pool" if "items" in plan_pool else "missing"
            warnings.append("plan_pool_items_missing_non_blocking")

        impact = dict(req.impact_map or {})
        if not impact and req.include_plan_item_impact_map:
            try:
                built = self.impact_service.build_map(AtlasPlanItemImpactMapRequest(
                    workspace_id=req.workspace_id,
                    project_path=req.project_path,
                    pool_id=req.pool_id,
                    goal=req.goal,
                    changed_files=list(req.changed_files or []),
                    target_files=list(req.target_files or []),
                    plan_pool=plan_pool,
                    allow_build_if_missing=False,
                )).model_dump()
                impact = built
                warnings.append("impact_map_built_advisory")
            except Exception as err:
                impact = {"status": "missing", "impacts": []}
                warnings.append("impact_map_build_failed_non_blocking")
                warnings.append(f"impact_map_build_error:{type(err).__name__}")

        impacts = list(impact.get("impacts") or [])
        selected = []
        if req.item_id:
            selected = [i for i in impacts if str(i.get("item_id") or "") == req.item_id]
            if not selected:
                warnings.append("item_id_not_found_in_impact_map")
        else:
            selected = impacts

        impacted_files: list[str] = []
        related_tests: list[str] = []
        commands: list[str] = []
        manual: list[str] = []
        ci: list[dict] = []
        evidence: list[dict] = []
        confidence = "unknown"
        for it in selected:
            confidence = it.get("confidence") or confidence
            impacted_files.extend(list(it.get("impacted_files") or []))
            related_tests.extend(list(it.get("related_tests") or []))
            commands.extend(list(it.get("recommended_commands") or []))
            manual.extend(list(it.get("manual_verification_steps") or []))
            ci.extend(list(it.get("ci_selection_hints") or []))
            for p in list(it.get("impacted_files") or []):
                evidence.append({"type": "impact", "source": "plan_item_impact_map", "item_id": it.get("item_id", ""), "path": p, "reason": ",".join(list(it.get("reasons") or [])), "confidence": it.get("confidence", "unknown")})

        dedup = lambda xs: list(dict.fromkeys(xs))
        return AtlasContextRefreshV2Bundle(
            status=status if selected or status != "available" else "missing",
            workspace_id=req.workspace_id,
            project_path=req.project_path,
            pool_id=req.pool_id,
            item_id=req.item_id,
            goal=req.goal,
            scope={"item_scoped": bool(req.item_id), "item_count": len(selected)},
            plan_item_impact={"status": impact.get("status", "missing"), "item_count": len(impacts)},
            impacted_files=dedup(impacted_files)[:50],
            related_tests=dedup(related_tests)[:30],
            recommended_commands=dedup(commands)[:5],
            manual_verification_steps=dedup(manual)[:10],
            ci_selection_hints=ci[:10],
            evidence=evidence[:50],
            context_notes=warnings[:30],
            confidence=confidence,
            warnings=warnings[:30],
        )
