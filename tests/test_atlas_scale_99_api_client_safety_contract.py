from pathlib import Path
import re


def test_api_client_readiness_stays_get_only():
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert '/api/atlas/level1/readiness' in text
    m = re.search(r"export async function fetchLevel1ReadinessDiagnostics\(\).*?\n}\n", text, re.S)
    assert m
    block = m.group(0)
    assert "method: 'GET'" in block
    assert '/api/atlas/level1/execute' not in block
    assert "method: 'POST'" not in block
    assert "method: 'PUT'" not in block
    assert "method: 'PATCH'" not in block
    assert "method: 'DELETE'" not in block
