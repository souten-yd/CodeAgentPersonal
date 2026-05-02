import tempfile
import unittest
from pathlib import Path

from agent.patch_schema import PatchProposal
from agent.patch_storage import PatchStorage


class T(unittest.TestCase):
    def test_tracking_fields(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            ps.save_patch_proposal(PatchProposal(patch_id='p1', run_id='r', plan_id='pl', step_id='s', target_file='a.py', verification_status='failed'))
            ps.save_patch_proposal(PatchProposal(patch_id='p2', run_id='r', plan_id='pl', step_id='s', target_file='a.py', reproposal_of_patch_id='p1'))
            lst = {x['patch_id']: x for x in ps.list_patches('r')}
            self.assertTrue(lst['p1']['verification_failed'])
            self.assertTrue(lst['p1']['has_reproposal'])
            self.assertEqual(lst['p1']['reproposal_count'], 1)
            self.assertEqual(lst['p1']['latest_reproposal_patch_id'], 'p2')

if __name__ == '__main__':
    unittest.main()
