from pathlib import Path

from agent.atlas_project_inspection_service import AtlasProjectInspectionService


def test_project_tree_and_list_max_and_excludes(tmp_path: Path):
    repo = tmp_path / 'repo'
    (repo / '.git').mkdir(parents=True)
    (repo / 'node_modules').mkdir(parents=True)
    (repo / 'src').mkdir(parents=True)
    (repo / '.git' / 'x').write_text('x', encoding='utf-8')
    (repo / 'node_modules' / 'x.js').write_text('x', encoding='utf-8')
    for i in range(5):
        (repo / 'src' / f'f{i}.py').write_text('def a():\n    pass\n', encoding='utf-8')
    svc = AtlasProjectInspectionService()
    tree = svc.project_tree(str(repo), max_files=3)
    assert len(tree.tree) == 3
    assert all('.git/' not in p and 'node_modules/' not in p for p in tree.tree)


def test_file_outline_and_large_binary_skip(tmp_path: Path):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo/'a.py').write_text('import os\nclass A:\n    pass\ndef f():\n    pass\n', encoding='utf-8')
    (repo/'b.md').write_text('# T\n## S\n', encoding='utf-8')
    (repo/'big.py').write_bytes(b'x' * 300000)
    (repo/'bin.dat').write_bytes(b'\x00\x01\x02')
    svc = AtlasProjectInspectionService()
    assert any('class A' in x for x in svc.file_outline(str(repo), 'a.py').outline)
    assert any('# T' in x for x in svc.file_outline(str(repo), 'b.md').outline)
    assert 'large file skipped' in svc.file_outline(str(repo), 'big.py').warnings
    assert 'binary file skipped' in svc.file_outline(str(repo), 'bin.dat').warnings
