from __future__ import annotations

import json
from pathlib import Path

from agent.patch_schema import PatchApplyResult, PatchProposal
from agent.verification_schema import VerificationResult


class PatchStorage:
    def __init__(self, ca_data_dir: str | Path) -> None:
        self.base_dir = Path(ca_data_dir)

    def _run_dir(self, run_id: str) -> Path:
        return self.base_dir / "runs" / run_id

    def _patches_dir(self, run_id: str) -> Path:
        p = self._run_dir(run_id) / "patches"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _verification_dir(self, run_id: str) -> Path:
        p = self._run_dir(run_id) / "verification"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save_patch_proposal(self, proposal: PatchProposal) -> None:
        pd = self._patches_dir(proposal.run_id)
        (pd / f"{proposal.patch_id}.patch.json").write_text(json.dumps(proposal.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (pd / f"{proposal.patch_id}.diff").write_text(proposal.unified_diff, encoding="utf-8")
        (pd / f"{proposal.patch_id}.md").write_text(f"# Patch {proposal.patch_id}\n\n- target: {proposal.target_file}\n- status: {proposal.status}\n", encoding="utf-8")

    def save_apply_result(self, run_id: str, result: PatchApplyResult) -> None:
        pd = self._patches_dir(run_id)
        (pd / f"{result.patch_id}.apply.json").write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    def save_verification_result(self, result: VerificationResult) -> None:
        vd = self._verification_dir(result.run_id)
        (vd / f"{result.verification_id}.verification.json").write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (vd / f"{result.verification_id}.md").write_text(f"# Verification {result.verification_id}\n\n- status: {result.status}\n- summary: {result.summary}\n", encoding="utf-8")

    def list_patches(self, run_id: str) -> list[dict]:
        pd = self._patches_dir(run_id)
        out: list[dict] = []
        for path in sorted(pd.glob("*.patch.json")):
            out.append(json.loads(path.read_text(encoding="utf-8")))
        return out

    def load_patch(self, run_id: str, patch_id: str) -> dict:
        path = self._patches_dir(run_id) / f"{patch_id}.patch.json"
        return json.loads(path.read_text(encoding="utf-8"))
