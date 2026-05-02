import tempfile
import unittest
from pathlib import Path

from agent.patch_schema import PatchProposal
from agent.patch_storage import PatchStorage


class Phase12PatchChainTests(unittest.TestCase):
    def test_chain_summary_root_child_count_reflected(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            ps.save_patch_proposal(PatchProposal(patch_id='a', run_id='r', plan_id='p', step_id='s', target_file='a.py', verification_status='failed'))
            ps.save_patch_proposal(PatchProposal(patch_id='b', run_id='r', plan_id='p', step_id='s', target_file='a.py', reproposal_of_patch_id='a'))
            s1 = ps.get_patch_chain_summary('r', 'a')
            self.assertEqual(s1['children'], ['b'])
            self.assertEqual(s1['ancestor_reproposal_count'], 0)
            self.assertEqual(s1['child_reproposal_count'], 1)
            self.assertEqual(s1['related_reproposal_count'], 1)
            self.assertEqual(s1['reproposal_count_total'], 1)
            self.assertIn('reproposal_count_total_semantics', s1)

    def test_chain_summary_child_ancestor_count_reflected(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            ps.save_patch_proposal(PatchProposal(patch_id='a', run_id='r', plan_id='p', step_id='s', target_file='a.py', verification_status='failed'))
            ps.save_patch_proposal(PatchProposal(patch_id='b', run_id='r', plan_id='p', step_id='s', target_file='a.py', reproposal_of_patch_id='a'))
            s2 = ps.get_patch_chain_summary('r', 'b')
            self.assertEqual(s2['parent_patch_id'], 'a')
            self.assertEqual(s2['root_patch_id'], 'a')
            self.assertEqual(s2['ancestor_reproposal_count'], 1)
            self.assertEqual(s2['child_reproposal_count'], 0)
            self.assertEqual(s2['related_reproposal_count'], 1)
            self.assertEqual(s2['reproposal_count_total'], 1)

    def test_chain_summary_parent_with_two_direct_children(self):
        with tempfile.TemporaryDirectory() as td:
            ps = PatchStorage(Path(td))
            ps.save_patch_proposal(PatchProposal(patch_id='a', run_id='r', plan_id='p', step_id='s', target_file='a.py'))
            ps.save_patch_proposal(PatchProposal(patch_id='b', run_id='r', plan_id='p', step_id='s', target_file='a.py', reproposal_of_patch_id='a'))
            ps.save_patch_proposal(PatchProposal(patch_id='c', run_id='r', plan_id='p', step_id='s', target_file='a.py', reproposal_of_patch_id='a'))
            s = ps.get_patch_chain_summary('r', 'a')
            self.assertCountEqual(s['children'], ['b', 'c'])
            self.assertEqual(s['child_reproposal_count'], 2)
            self.assertEqual(s['related_reproposal_count'], 2)

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
            self.assertIn('ancestor_reproposal_count', s)
            self.assertIn('child_reproposal_count', s)
            self.assertIn('related_reproposal_count', s)


if __name__ == '__main__':
    unittest.main()
