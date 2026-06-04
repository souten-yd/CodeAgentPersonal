#!/usr/bin/env python3
"""End-to-end smoke: clarification -> apply-time safety block -> human override -> dispatch.

Exercises the real HTTP surface (no browser, no LLM required) and asserts the exit path that the
"silent Patch 0/N spinner" bug lacked:

  1. Answering the last clarification question reruns the gates and lands the pool at
     ``blocked_safety_review`` WITH a visible block reason (not approval_required, not a spinner).
  2. Autonomous codegen on that pool reports ``blocked_safety_review`` (an explicit, reasoned stop)
     instead of silently dispatching 0/N.
  3. Granting a human safety override flips the pool to ``ready`` and records the override.
  4. Re-running codegen now advances PAST the apply-time safety gate (the override is honored) —
     the run is no longer blocked_safety_review.

Run: python scripts/smoke_clarification_safety_block_override_e2e.py
Exits non-zero on the first failed expectation.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.server import create_app
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage

POOL_ID = "pool_smoke_safety_block"


def _seed_pool(tmp_path: Path) -> None:
    pool = AtlasPlanPool(
        pool_id=POOL_ID,
        root_goal="Build a multi-file feature",
        status="needs_scope_confirmation",
        project_path=str(tmp_path / "ws"),
        items=[
            AtlasPlanItem(
                item_id="i1", pool_id=POOL_ID, title="Item", goal="Do the work",
                item_type="implementation", status="approval_required",
                # medium risk is blocked by guarded_low_risk at apply time -> a real safety block.
                risk_level="medium", target_files=["src/i1.py"], metadata={"action_type": "create"},
            )
        ],
        metadata={
            "clarification_required": True,
            "clarification_questions": [
                {
                    "question_id": "clar_q_1", "index": 1, "total": 1,
                    "prompt": "Pick scope", "reason": "scope unclear",
                    "options": [{"option_id": "minimal_scope", "label": "Minimal"}],
                    "status": "pending",
                }
            ],
        },
    )
    AtlasPlanPoolStorage(tmp_path).save_pool(pool)


def _check(label: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        raise SystemExit(1)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        _seed_pool(tmp_path)
        app = create_app()
        app.state.atlas_ca_data_root = str(tmp_path)
        client = TestClient(app)

        # 1) Answer the last clarification -> rerun gates -> blocked_safety_review with a reason.
        r = client.post(
            f"/api/atlas/plan-pools/{POOL_ID}/clarify",
            json={"question_id": "clar_q_1", "option_id": "minimal_scope", "answer_text": "one file"},
        )
        _check("clarify returns 200", r.status_code == 200, r.text)
        body = r.json()
        _check("status is blocked_safety_review", body["status"] == "blocked_safety_review", body["status"])
        reason = (body.get("clarification_replanning") or {}).get("safety_gate_block_reason_after_clarification", "")
        _check("safety block reason is visible", bool(reason), reason)

        # 2) Codegen reports the block explicitly (no silent 0/N dispatch).
        r = client.post("/api/atlas/autonomous-codegen/run", json={"pool_id": POOL_ID})
        _check("codegen run returns 200", r.status_code == 200, r.text)
        run_body = r.json()
        _check("codegen is blocked_safety_review (not 0/N spinner)", run_body["status"] == "blocked_safety_review", run_body.get("status", ""))
        _check("codegen generated 0 patches while blocked", int(run_body.get("generated_count", 0)) == 0)

        # 3) Human override -> ready, recorded.
        r = client.post(f"/api/atlas/plan-pools/{POOL_ID}/safety-override", json={"reason": "reviewed by operator", "approver": "operator"})
        _check("override returns 200", r.status_code == 200, r.text)
        ovr = r.json()
        _check("override flips pool to ready", ovr["status"] == "ready", ovr["status"])
        _check("override is recorded", ovr["safety_override_granted_after_clarification"] is True)

        # 4) Re-run codegen: the apply-time gate now honors the override (no longer blocked).
        r = client.post("/api/atlas/autonomous-codegen/run", json={"pool_id": POOL_ID})
        _check("codegen run returns 200 after override", r.status_code == 200, r.text)
        after = r.json()
        _check(
            "codegen advances past safety gate after override",
            after["status"] != "blocked_safety_review",
            f"status={after.get('status')} stop_reason={after.get('stop_reason')}",
        )

    print("\nSMOKE OK: clarification safety block -> override -> dispatch exit path works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
