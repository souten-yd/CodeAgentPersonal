import tempfile, unittest
from pathlib import Path
from agent.llm_patch_generator import generate_replace_block_patch
from agent.implementation_executor import ImplementationExecutor
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

if __name__=='__main__':unittest.main()
