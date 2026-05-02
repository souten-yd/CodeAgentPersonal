import tempfile
import unittest
from pathlib import Path

from agent.patch_schema import PatchProposal
from agent.patch_storage import PatchStorage


class Phase12PatchChainTests(unittest.TestCase):
    def test_chain_summary_parent_child(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            ps.save_patch_proposal(PatchProposal(patch_id='a', run_id='r', plan_id='p', step_id='s', target_file='a.py', verification_status='failed'))
            ps.save_patch_proposal(PatchProposal(patch_id='b', run_id='r', plan_id='p', step_id='s', target_file='a.py', reproposal_of_patch_id='a'))
            s1 = ps.get_patch_chain_summary('r', 'a')
            self.assertEqual(s1['children'], ['b'])
            s2 = ps.get_patch_chain_summary('r', 'b')
            self.assertEqual(s2['parent_patch_id'], 'a')
            self.assertEqual(s2['root_patch_id'], 'a')
            self.assertEqual(s2['reproposal_count_total'], 1)

    def test_missing_patch_raises(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            with self.assertRaises(ValueError):
                ps.get_patch_chain_summary('r', 'nope')

    def test_cycle_no_infinite_loop(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            ps.save_patch_proposal(PatchProposal(patch_id='a', run_id='r', plan_id='p', step_id='s', target_file='a.py', reproposal_of_patch_id='b'))
            ps.save_patch_proposal(PatchProposal(patch_id='b', run_id='r', plan_id='p', step_id='s', target_file='a.py', reproposal_of_patch_id='a'))
            s = ps.get_patch_chain_summary('r', 'a')
            self.assertGreaterEqual(len(s['chain']), 1)


if __name__ == '__main__':
    unittest.main()
