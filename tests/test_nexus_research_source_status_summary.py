from pathlib import Path


def test_research_status_summary_separates_download_limit_and_problem_counts():
    text = Path("web/js/nexus.js").read_text(encoding="utf-8")
    assert "skipped_due_to_download_limit_count" in text
    assert "取得上限で未取得" in text
    assert "取得問題" in text


def test_research_agent_summary_tracks_candidate_and_attempted_download_counts():
    text = Path("app/nexus/research_agent.py").read_text(encoding="utf-8")
    assert "candidate_count" in text
    assert "attempted_download_count" in text
    assert "skipped_due_to_download_limit_count" in text
