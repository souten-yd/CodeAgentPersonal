import tempfile
import unittest
from pathlib import Path

from agent.manual_check_schema import ManualLLMCheckResult
from agent.manual_check_storage import ManualCheckStorage


class T(unittest.TestCase):
    def test_manual_check_storage(self):
        with tempfile.TemporaryDirectory() as td:
            st = ManualCheckStorage(Path(td))
            rec = ManualLLMCheckResult(check_id='c1', run_id='r1', patch_id='p1', notes='日本語メモ')
            st.save_manual_check(rec)
            self.assertEqual(st.load_manual_check('r1', 'c1')['notes'], '日本語メモ')
            self.assertEqual(len(st.list_manual_checks('r1')), 1)

if __name__ == '__main__':
    unittest.main()
