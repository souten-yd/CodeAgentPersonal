import tempfile
import unittest
from pathlib import Path

from agent.llm_patch_generator import generate_replace_block_patch
from agent.implementation_executor import ImplementationExecutor
from agent.patch_context_selector import PatchContextSelector
from agent.patch_storage import PatchStorage
from agent.plan_storage import PlanStorage
from agent.run_storage import RunStorage


class T(unittest.TestCase):
    def test_quality_and_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); proj=root/'p'; proj.mkdir(); f=proj/'a.py'; f.write_text('def x():\n    return 1\n',encoding='utf-8')
            def llm(**kwargs):
                assert 'CANDIDATE BLOCKS' in kwargs['prompt']
                return '{"candidate_id":"cand_1","original_block":"return 1","replacement_block":"return 2","confidence":0.9}'
            p=generate_replace_block_patch('r','p','s','update return','change logic','low',f,f.read_text(encoding='utf-8'),llm_fn=llm)
            self.assertGreaterEqual(p.quality_score,0.4)
            self.assertGreaterEqual(p.candidate_block_count,1)

    def test_backup_contains_patch_id(self):
        ex=ImplementationExecutor(PlanStorage('/tmp/none'), RunStorage('/tmp/none'))
        b=ex._backup_path_for(Path('/tmp/a.py'),'pid1')
        self.assertIn('pid1', str(b))

    def test_quality_fields_saved_to_patch_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proj = root / 'p'; proj.mkdir()
            f = proj / 'a.py'
            f.write_text('def x():\n    return 1\n', encoding='utf-8')

            p = generate_replace_block_patch(
                'run1', 'plan1', 's1', 'update return', 'change logic', 'low', f,
                f.read_text(encoding='utf-8'),
                llm_fn=lambda **k: '{"candidate_id":"cand_1","original_block":"return 1","replacement_block":"return 2","confidence":0.8}'
            )
            storage = PatchStorage(root / 'ca')
            storage.save_patch_proposal(p)
            loaded = storage.load_patch('run1', p.patch_id)
            self.assertIn('quality_score', loaded)
            self.assertIn('quality_summary', loaded)
            self.assertIsInstance(loaded.get('quality_warnings', []), list)
            self.assertGreaterEqual(int(loaded.get('candidate_block_count', 0)), 1)
            self.assertIn('selected_candidate_reason', loaded)
            self.assertIn('candidates_summary', (loaded.get('metadata') or {}))

    def test_context_selector_basics(self):
        sel = PatchContextSelector()
        content = '\n'.join([f'line {i}' for i in range(1, 120)]) + '\n# verify keyword\n最後は日本語の行\n'
        cands = sel.select_candidates(content, 'verify behavior', 'keyword line を確認する', max_candidates=3, target_file='a.py')
        self.assertLessEqual(len(cands), 3)
        self.assertTrue(any('verify keyword' in c.text for c in cands))
        jp = sel.select_candidates('これは日本語テキストです\n関数の置換を確認\n' * 30, '日本語確認', '置換候補を選ぶ', max_candidates=2, target_file='b.py')
        self.assertGreaterEqual(len(jp), 1)


if __name__=='__main__':unittest.main()
