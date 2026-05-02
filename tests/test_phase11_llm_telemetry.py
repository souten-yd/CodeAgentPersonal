import tempfile
import unittest
from pathlib import Path

from agent.llm_telemetry_schema import LLMCallTelemetry
from agent.llm_telemetry_storage import LLMTelemetryStorage


class T(unittest.TestCase):
    def test_storage(self):
        with tempfile.TemporaryDirectory() as td:
            st = LLMTelemetryStorage(Path(td))
            rec = LLMCallTelemetry(telemetry_id='t1', run_id='r1', purpose='patch_generation', prompt_chars=10, response_chars=20, success=True, validation_reason='ok', apply_allowed_after_validation=True)
            st.save_telemetry(rec)
            one = st.load_telemetry('r1', 't1')
            self.assertEqual(one['prompt_chars'], 10)
            self.assertEqual(len(st.list_telemetry('r1')), 1)

if __name__ == '__main__':
    unittest.main()
