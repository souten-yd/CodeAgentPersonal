from pathlib import Path


def test_scale_95_no_public_level1_execution_route_exposed() -> None:
    text = Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')
    assert '/api/atlas/level1/execute' not in text
    assert '@router.post("/level1/execute")' not in text
    assert '@router.post("/level1/dry-run")' not in text
    assert '@router.post("/level1/approve")' not in text
    assert '@router.post("/level1/apply")' not in text
    assert '@router.post("/level1/verify")' not in text
    assert '@router.post("/level1/rollback")' not in text
    assert '@router.post("/level1/retry")' not in text
    assert '@router.post("/level1/continue")' not in text
