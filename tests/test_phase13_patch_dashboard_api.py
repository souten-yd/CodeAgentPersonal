import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.patch_schema import PatchProposal
from agent.patch_storage import PatchStorage


class TestPhase13PatchDashboardApi(unittest.TestCase):
    def test_dashboard_api(self):
        with tempfile.TemporaryDirectory() as td:
            old = main._phase6_run_storage.base_dir
            main._phase6_run_storage.base_dir = Path(td)
            try:
                ps = PatchStorage(Path(td))
                ps.save_patch_proposal(PatchProposal(patch_id='p1', run_id='r1', plan_id='pl', step_id='s', target_file='a.py'))
                c = TestClient(main.app)
                r = c.get('/api/runs/r1/patch-dashboard')
                self.assertEqual(r.status_code, 200)
                d = r.json()['dashboard']
                self.assertIn('counts', d)
                self.assertIn('attention', d)
                self.assertIn('patches', d)
            finally:
                main._phase6_run_storage.base_dir = old


if __name__ == '__main__':
    unittest.main()
