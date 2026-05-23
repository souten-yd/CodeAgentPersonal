from pathlib import Path


def test_no_level1_execution_route_exposed() -> None:
    content = Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')
    forbidden = [
        '/api/atlas/level1/execute', '/api/atlas/execute', '/dry-run/start',
    ]
    for item in forbidden:
        assert item not in content
