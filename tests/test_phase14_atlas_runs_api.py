import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.patch_schema import PatchProposal
from agent.patch_storage import PatchStorage


class TestPhase14AtlasRunsApi(unittest.TestCase):
    def test_runs_api_and_limit(self):
        with tempfile.TemporaryDirectory() as td:
            old = main._phase6_run_storage.base_dir
            main._phase6_run_storage.base_dir = Path(td)
            try:
                ps = PatchStorage(Path(td))
                for i in range(3):
                    run_id = f'r{i}'
                    rd = Path(td) / 'runs' / run_id
                    rd.mkdir(parents=True, exist_ok=True)
                    (rd / 'run.json').write_text('{"run_id":"%s","status":"completed"}' % run_id, encoding='utf-8')
                    ps.save_patch_proposal(PatchProposal(patch_id=f'p{i}', run_id=run_id, plan_id='pl', step_id='s', target_file='a.py'))
                c = TestClient(main.app)
                r = c.get('/api/atlas/runs?limit=2')
                self.assertEqual(r.status_code, 200)
                runs = r.json().get('runs', [])
                self.assertEqual(len(runs), 2)
                self.assertIn('run_id', runs[0])
                self.assertIn('patch_count', runs[0])
                self.assertIn('blocked_count', runs[0])
                self.assertIn('verification_failed_count', runs[0])
            finally:
                main._phase6_run_storage.base_dir = old

    def test_empty_runs_dir_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as td:
            old = main._phase6_run_storage.base_dir
            main._phase6_run_storage.base_dir = Path(td)
            try:
                c = TestClient(main.app)
                r = c.get('/api/atlas/runs')
                self.assertEqual(r.status_code, 200)
                runs = r.json().get('runs', [])
                self.assertEqual(runs, [])
            finally:
                main._phase6_run_storage.base_dir = old

    def test_broken_run_has_summary_error(self):
        with tempfile.TemporaryDirectory() as td:
            old = main._phase6_run_storage.base_dir
            main._phase6_run_storage.base_dir = Path(td)
            try:
                bad = Path(td) / 'runs' / 'broken'
                bad.mkdir(parents=True, exist_ok=True)
                (bad / 'run.json').write_text('{bad json', encoding='utf-8')
                c = TestClient(main.app)
                r = c.get('/api/atlas/runs')
                self.assertEqual(r.status_code, 200)
                runs = r.json().get('runs', [])
                self.assertTrue(isinstance(runs, list))
                broken = next((x for x in runs if x.get('run_id') == 'broken'), None)
                self.assertIsNotNone(broken)
                self.assertIn('summary_error', broken)
                self.assertTrue(broken['summary_error'])
            finally:
                main._phase6_run_storage.base_dir = old


if __name__ == '__main__':
    unittest.main()
