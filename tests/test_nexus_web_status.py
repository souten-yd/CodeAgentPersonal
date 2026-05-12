from pathlib import Path

def test_nexus_web_status_contract_file_exists():
    assert Path("tests/test_nexus_web_status_contract.py").exists()
