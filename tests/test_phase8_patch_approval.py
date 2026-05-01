from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.patch_approval_manager import PatchApprovalManager
from agent.patch_schema import PatchProposal
from agent.patch_storage import PatchStorage


class Phase8PatchApprovalTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.storage = PatchStorage(self.root / "ca_data")

    def tearDown(self):
        self.td.cleanup()

    def _save_patch(self, **kwargs):
        p = PatchProposal(
            patch_id="p1", run_id="r1", plan_id="pl1", step_id="s1", target_file="a.py",
            apply_allowed=True, risk_level="low", safety_warnings=[], proposed_content="\n# note\n", unified_diff="+note"
        )
        for k,v in kwargs.items():
            setattr(p,k,v)
        self.storage.save_patch_proposal(p)

    def test_apply_disallowed_cannot_approve(self):
        self._save_patch(apply_allowed=False)
        pm = PatchApprovalManager(self.storage)
        with self.assertRaises(ValueError):
            pm.decide("r1","p1","approve")

    def test_warnings_need_ack(self):
        self._save_patch(safety_warnings=["warn"])
        pm = PatchApprovalManager(self.storage)
        with self.assertRaises(ValueError):
            pm.decide("r1","p1","approve")

    def test_medium_need_risk_ack(self):
        self._save_patch(risk_level="medium")
        pm = PatchApprovalManager(self.storage)
        with self.assertRaises(ValueError):
            pm.decide("r1","p1","approve")

    def test_approve_and_reject(self):
        self._save_patch()
        pm = PatchApprovalManager(self.storage)
        ok = pm.decide("r1","p1","approve", user_comment="日本語", risk_acknowledged=False)
        self.assertEqual(ok["approval"]["status"], "approved")
        with self.assertRaises(ValueError):
            pm.decide("r1","p1","reject", user_comment="不要")

    def test_rejected_patch_cannot_be_reapproved(self):
        self._save_patch()
        pm = PatchApprovalManager(self.storage)
        rej = pm.decide("r1", "p1", "reject", user_comment="不要")
        self.assertEqual(rej["approval"]["status"], "rejected")
        with self.assertRaises(ValueError):
            pm.decide("r1", "p1", "approve", safety_warnings_acknowledged=True, risk_acknowledged=True)

    def test_warning_ack_and_medium_risk_ack_can_approve(self):
        self._save_patch(safety_warnings=["warn"], risk_level="medium")
        pm = PatchApprovalManager(self.storage)
        ok = pm.decide(
            "r1",
            "p1",
            "approve",
            user_comment="日本語コメント",
            safety_warnings_acknowledged=True,
            risk_acknowledged=True,
        )
        self.assertEqual(ok["approval"]["status"], "approved")
        self.assertEqual(ok["approval"]["user_comment"], "日本語コメント")

if __name__ == "__main__":
    unittest.main()
