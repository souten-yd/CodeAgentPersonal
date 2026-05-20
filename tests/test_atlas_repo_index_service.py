from pathlib import Path
from agent.atlas_repo_index_service import AtlasRepoIndexService
from agent.atlas_repo_index_schema import AtlasRepoIndexRequest

def test_build_python_symbol_index(tmp_path: Path):
    (tmp_path/'app').mkdir(); (tmp_path/'tests').mkdir()
    (tmp_path/'app'/'main.py').write_text('import os\nclass A: pass\ndef f():\n return 1\n')
    svc=AtlasRepoIndexService(tmp_path/'data')
    res=svc.build_or_update(AtlasRepoIndexRequest(project_path=str(tmp_path)))
    assert res.symbol_count >= 2
    assert res.edge_count >= 1
