from pathlib import Path

from agent.atlas_code_intel_schema import AtlasDependencyGraphRequest, AtlasRelatedTestsRequest, AtlasSymbolIndexRequest
from agent.atlas_code_intel_service import AtlasCodeIntelService


def test_symbol_index_python_and_syntax_skip(tmp_path: Path):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'a.py').write_text('import os\nfrom x import y\nclass A:\n    def m(self):\n        return 1\ndef f(x):\n    return x\n', encoding='utf-8')
    (repo / 'bad.py').write_text('def oops(:\n', encoding='utf-8')
    svc = AtlasCodeIntelService()
    out = svc.build_symbol_index(AtlasSymbolIndexRequest(project_path=str(repo)))
    kinds = {s.kind for s in out.symbols}
    assert {'class', 'function', 'method', 'import'} <= kinds
    assert any(s['reason'] == 'syntax error' for s in out.skipped_files)


def test_symbol_index_js_html_css_and_limits(tmp_path: Path):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'x.ts').write_text("import z from './z'\nexport function run(){}\nclass C{}\nconst fx = () => 1\n", encoding='utf-8')
    (repo / 'i.html').write_text('<div id="main"></div>\n<script src="a.js"></script>\n<link rel="stylesheet" href="a.css"/>', encoding='utf-8')
    (repo / 's.css').write_text('@import "base.css";\n.foo { color: red; }\n', encoding='utf-8')
    (repo / 'big.js').write_bytes(b'x' * 300000)
    (repo / 'bin.dat').write_bytes(b'\x00\x01')
    svc = AtlasCodeIntelService()
    out = svc.build_symbol_index(AtlasSymbolIndexRequest(project_path=str(repo), max_symbols=3))
    assert len(out.symbols) == 3
    assert 'max_symbols limit reached' in out.warnings


def test_dependency_graph_python_js_html_css_and_max_edges(tmp_path: Path):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'a.py').write_text('import os\nfrom x.y import z\n', encoding='utf-8')
    (repo / 'a.ts').write_text('import {x} from "./m"\n', encoding='utf-8')
    (repo / 'i.html').write_text('<script src="a.js"></script><link rel="stylesheet" href="a.css"/>', encoding='utf-8')
    (repo / 's.css').write_text('@import "base.css";\n', encoding='utf-8')
    svc = AtlasCodeIntelService()
    out = svc.build_dependency_graph(AtlasDependencyGraphRequest(project_path=str(repo), max_edges=2))
    assert len(out.edges) == 2
    assert 'max_edges limit reached' in out.warnings


def test_related_tests_heuristics_and_fallback(tmp_path: Path):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'app').mkdir(); (repo / 'src').mkdir(); (repo / 'tests').mkdir()
    (repo / 'app' / 'foo.py').write_text('def foo():\n    pass\n', encoding='utf-8')
    (repo / 'src' / 'bar.ts').write_text('export const bar = 1\n', encoding='utf-8')
    (repo / 'tests' / 'test_foo.py').write_text('from app.foo import foo\n', encoding='utf-8')
    (repo / 'src' / 'bar.test.ts').write_text('import { bar } from "./bar"\n', encoding='utf-8')
    svc = AtlasCodeIntelService()
    out = svc.find_related_tests(AtlasRelatedTestsRequest(project_path=str(repo), changed_files=['app/foo.py', 'src/bar.ts']))
    paths = {x['path'] for x in out.related_tests}
    assert 'tests/test_foo.py' in paths
    assert 'src/bar.test.ts' in paths

    out2 = svc.find_related_tests(AtlasRelatedTestsRequest(project_path=str(repo), changed_files=['app/none.py'], max_tests=1))
    assert len(out2.related_tests) == 1


def test_unsafe_path_rejected(tmp_path: Path):
    svc = AtlasCodeIntelService()
    try:
        svc.build_symbol_index(AtlasSymbolIndexRequest(project_path=str(tmp_path), relative_path='../x'))
    except ValueError:
        pass
    else:
        raise AssertionError('expected ValueError')
