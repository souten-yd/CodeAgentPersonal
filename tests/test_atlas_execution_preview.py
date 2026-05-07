from pathlib import Path

from agent.atlas_execution_preview import AtlasExecutionPreview


class FakePlanStorage:
    def load_plan(self, plan_id: str):
        return {
            "plan_id": plan_id,
            "implementation_steps": [{"title": "Update", "description": "small change"}],
            "target_files": ["agent/atlas_autopilot.py"],
            "risks": ["low"],
            "verification_plan": ["pytest"],
        }


class FakeImplementationExecutor:
    called = False

    def execute(self, *args, **kwargs):
        self.called = True


def test_prepare_preview_is_preview_only(tmp_path: Path):
    before = sorted(p.name for p in tmp_path.iterdir())
    impl = FakeImplementationExecutor()
    previewer = AtlasExecutionPreview(plan_storage=FakePlanStorage(), implementation_executor=impl)
    out = previewer.prepare_preview(plan_id="plan_x", requirement_id="req_x")
    assert isinstance(out, dict)
    assert out["status"] in {"execution_preview_ready", "blocked"}
    assert out["plan_id"] == "plan_x"
    assert out["requirement_id"] == "req_x"
    safety = " ".join(out.get("safety_constraints") or []).lower()
    assert "no file changes" in safety
    assert "no patch apply" in safety
    assert impl.called is False
    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == after
