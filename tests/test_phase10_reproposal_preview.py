import tempfile, unittest
from pathlib import Path
from agent.implementation_executor import ImplementationExecutor
from agent.patch_schema import PatchProposal
from agent.plan_storage import PlanStorage
from agent.run_storage import RunStorage

class T(unittest.TestCase):
    def test_reproposal_requires_failed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); ps=PlanStorage(root/'ca'); rs=RunStorage(root/'ca')
            ex=ImplementationExecutor(ps,rs,llm_patch_fn=lambda **k:'{"original_block":"x=1","replacement_block":"x=2"}')
            run_id='run_x'; (root/'proj').mkdir(); tf=root/'proj'/'a.py'; tf.write_text('x=1\n',encoding='utf-8')
            rs.save_run(type('R',(),{'run_id':run_id,'model_dump':lambda self:{'run_id':run_id,'project_path':str(root/'proj')}})())
            p=PatchProposal(patch_id='p1',run_id=run_id,plan_id='pl',step_id='s1',target_file=str(tf),patch_type='replace_block',verification_status='passed')
            ex.patch_storage.save_patch_proposal(p)
            with self.assertRaises(ValueError): ex.generate_reproposal(run_id,'p1')

if __name__=='__main__':unittest.main()
