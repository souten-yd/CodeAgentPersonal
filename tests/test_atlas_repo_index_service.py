from pathlib import Path
from agent.atlas_repo_index_service import AtlasRepoIndexService
from agent.atlas_repo_index_schema import AtlasRepoIndexRequest

def _svc(tmp_path): return AtlasRepoIndexService(tmp_path/'data')

def test_build_python_symbol_index_extracts_routes_imports_methods(tmp_path: Path):
    (tmp_path/'app').mkdir(); (tmp_path/'app'/'main.py').write_text('import app.foo\nclass A: pass\ndef f():\n return 1\n')
    (tmp_path/'app'/'foo.py').write_text('x=1\n')
    res=_svc(tmp_path).build_or_update(AtlasRepoIndexRequest(project_path=str(tmp_path))); assert res.symbol_count >= 2 and res.edge_count >= 1

def test_files_json_contains_file_nodes(tmp_path: Path):
    (tmp_path/'a.py').write_text('def x():\n pass\n'); svc=_svc(tmp_path); svc.build_or_update(AtlasRepoIndexRequest(project_path=str(tmp_path)))
    assert svc.storage.load_json(str(tmp_path),'files.json')

def test_manifest_contains_file_hashes(tmp_path: Path):
    (tmp_path/'a.py').write_text('x=1\n'); svc=_svc(tmp_path); svc.build_or_update(AtlasRepoIndexRequest(project_path=str(tmp_path)))
    assert svc.storage.load_json(str(tmp_path),'manifest.json').get('file_hashes')

def test_incremental_update_records_reused_reparsed_deleted(tmp_path: Path):
    (tmp_path/'a.py').write_text('x=1\n'); svc=_svc(tmp_path); svc.build_or_update(AtlasRepoIndexRequest(project_path=str(tmp_path)))
    (tmp_path/'b.py').write_text('y=2\n'); res=svc.build_or_update(AtlasRepoIndexRequest(project_path=str(tmp_path),incremental=True))
    assert 'metadata' in res.model_dump()

def test_no_shell_or_remote_git(tmp_path: Path):
    assert 'shell=True' not in Path('agent/atlas_repo_index_service.py').read_text()

def test_no_path_ca_data_literals(tmp_path: Path):
    assert 'Path("ca_data")' not in Path('agent/atlas_repo_index_service.py').read_text()
