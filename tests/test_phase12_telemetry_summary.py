import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.llm_telemetry_schema import LLMCallTelemetry
from agent.llm_telemetry_storage import LLMTelemetryStorage


class Phase12TelemetrySummaryTests(unittest.TestCase):
    def test_detail_includes_summary(self):
        with tempfile.TemporaryDirectory() as td:
            ts = LLMTelemetryStorage(Path(td))
            rec = LLMCallTelemetry(
                telemetry_id='t1', run_id='r1', plan_id='p1', patch_id='x', step_id='s',
                purpose='patch_generation', success=True, duration_ms=12,
                prompt_chars=10, response_chars=20, validation_reason='no_match',
                apply_allowed_after_validation=False,
                metadata={'llm_call_success': True, 'validation_success': False, 'rejected_by_validation': True, 'api_key': 'SECRET'}
            )
            ts.save_telemetry(rec)
            old = main._phase6_run_storage.base_dir
            main._phase6_run_storage.base_dir = Path(td)
            try:
                c = TestClient(main.app)
                r = c.get('/api/runs/r1/llm-telemetry/t1')
                self.assertEqual(r.status_code, 200)
                d = r.json()
                self.assertIn('summary', d)
                s = d['summary']
                self.assertTrue(s['success'])
                self.assertTrue(s['llm_call_success'])
                self.assertFalse(s['validation_success'])
                self.assertTrue(s['rejected_by_validation'])
                self.assertNotIn('api_key', s)
                r2 = c.get('/api/runs/r1/llm-telemetry')
                self.assertEqual(r2.status_code, 200)
            finally:
                main._phase6_run_storage.base_dir = old


if __name__ == '__main__':
    unittest.main()
