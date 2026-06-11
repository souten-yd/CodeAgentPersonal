from pathlib import Path

from agent.atlas_code_intel_schema import AtlasDependencyGraphRequest, AtlasRelatedTestsRequest, AtlasSymbolIndexRequest
from agent.project_intelligence.adapters.code_intel import ProjectIntelligenceCodeIntelAdapter


def test_symbol_index_single_file_and_python_visitor(tmp_path: Path):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'app.py').write_text('import os\nfrom x import y\nclass A:\n    def m(self):\n        return 1\nasync def af():\n    return 1\ndef f(x):\n    return x\n', encoding='utf-8')
    (repo / 'other.py').write_text('def g():\n    return 0\n', encoding='utf-8')
    svc = ProjectIntelligenceCodeIntelAdapter()
    out = svc.build_symbol_index(AtlasSymbolIndexRequest(project_path=str(repo), relative_path='app.py'))
    assert {s.file_path for s in out.symbols} == {'app.py'}
    method = next(s for s in out.symbols if s.name == 'm')
    assert method.kind == 'method' and method.parent == 'A'
    assert any(s.name == 'f' and s.kind == 'function' and s.parent == '' for s in out.symbols)
    assert any(s.name == 'af' and s.kind == 'function' for s in out.symbols)
    assert any(s.kind == 'import' for s in out.symbols)


def test_relative_path_directory_and_missing_error(tmp_path: Path):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'src').mkdir(); (repo / 'src' / 'foo.py').write_text('import os\n', encoding='utf-8')
    svc = ProjectIntelligenceCodeIntelAdapter()
    dep = svc.build_dependency_graph(AtlasDependencyGraphRequest(project_path=str(repo), relative_path='src'))
    assert all(e.source.startswith('src/') for e in dep.edges)
    try:
        svc.build_symbol_index(AtlasSymbolIndexRequest(project_path=str(repo), relative_path='nope.py'))
    except ValueError as exc:
        assert 'path_not_found' in str(exc)
    else:
        raise AssertionError('expected ValueError')


def test_read_error_skips_file(tmp_path: Path, monkeypatch):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'a.py').write_text('import os\n', encoding='utf-8')
    svc = ProjectIntelligenceCodeIntelAdapter()

    orig = Path.read_bytes
    def flaky(self: Path):
        if self.name == 'a.py':
            raise OSError('boom')
        return orig(self)

    monkeypatch.setattr(Path, 'read_bytes', flaky)
    s = svc.build_symbol_index(AtlasSymbolIndexRequest(project_path=str(repo)))
    d = svc.build_dependency_graph(AtlasDependencyGraphRequest(project_path=str(repo)))
    assert any(x['path'] == 'a.py' and 'read error' in x['reason'] for x in s.skipped_files)
    assert any(x['path'] == 'a.py' and 'read error' in x['reason'] for x in d.skipped_files)


def test_dependency_resolution_metadata(tmp_path: Path):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'src').mkdir(); (repo / 'src' / 'util.js').write_text('export const x=1\n', encoding='utf-8')
    (repo / 'src' / 'main.ts').write_text('import {x} from "./util"\nimport React from "react"\n', encoding='utf-8')
    (repo / 'app.js').write_text('console.log(1)\n', encoding='utf-8')
    (repo / 'base.css').write_text('body{}\n', encoding='utf-8')
    (repo / 'i.html').write_text('<script src="app.js"></script>', encoding='utf-8')
    (repo / 's.css').write_text('@import "./base.css";\n', encoding='utf-8')
    svc = ProjectIntelligenceCodeIntelAdapter()
    out = svc.build_dependency_graph(AtlasDependencyGraphRequest(project_path=str(repo)))
    js_edge = next(e for e in out.edges if e.kind == 'js_import' and e.target == './util')
    assert js_edge.metadata['resolved_target_path'] == 'src/util.js'
    assert js_edge.metadata['resolution'] == 'resolved'
    html_edge = next(e for e in out.edges if e.kind == 'html_script')
    assert html_edge.metadata['resolved_target_path'] == 'app.js'
    css_edge = next(e for e in out.edges if e.kind == 'css_import')
    assert css_edge.metadata['resolved_target_path'] == 'base.css'
    external = next(e for e in out.edges if e.target == 'react')
    assert external.metadata['resolution'] == 'external'


def test_related_tests_verification_hint_and_no_command_hint(tmp_path: Path):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'src').mkdir(); (repo / 'tests').mkdir()
    (repo / 'src' / 'foo.py').write_text('def foo():\n    pass\n', encoding='utf-8')
    (repo / 'src' / 'bar.ts').write_text('export const bar=1\n', encoding='utf-8')
    (repo / 'tests' / 'test_foo.py').write_text('from src.foo import foo\n', encoding='utf-8')
    (repo / 'src' / 'bar.test.ts').write_text('import { bar } from "./bar"\n', encoding='utf-8')
    svc = ProjectIntelligenceCodeIntelAdapter()
    out = svc.find_related_tests(AtlasRelatedTestsRequest(project_path=str(repo), changed_files=['src/foo.py', 'src/bar.ts']))
    py_item = next(x for x in out.related_tests if x['path'].endswith('.py'))
    js_item = next(x for x in out.related_tests if x['path'].endswith('.ts'))
    assert py_item['verification_hint']['command_id'] == 'pytest_selected'
    assert js_item['verification_hint']['command_id'] == ''
    assert 'node_test_runner' not in str(out.related_tests)
    assert all('command_hint' not in x for x in out.related_tests)


def test_truncation_metadata(tmp_path: Path):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'a.py').write_text('def a():\n    pass\n', encoding='utf-8')
    (repo / 'b.py').write_text('def b():\n    pass\n', encoding='utf-8')
    svc = ProjectIntelligenceCodeIntelAdapter()
    s = svc.build_symbol_index(AtlasSymbolIndexRequest(project_path=str(repo), max_symbols=1, max_files=1))
    assert s.metadata['truncated'] is True
    assert 'max_files limit reached' in s.warnings
    d = svc.build_dependency_graph(AtlasDependencyGraphRequest(project_path=str(repo), max_edges=0, max_files=1))
    assert d.metadata['truncated'] is True


def test_unsafe_path_rejected(tmp_path: Path):
    svc = ProjectIntelligenceCodeIntelAdapter()
    try:
        svc.build_symbol_index(AtlasSymbolIndexRequest(project_path=str(tmp_path), relative_path='../x'))
    except ValueError:
        pass
    else:
        raise AssertionError('expected ValueError')
