from tests.helpers.ui_contract import load_ui_contract_text


def _ui() -> str:
    return load_ui_contract_text()


def test_resume_filters_active_and_latest_to_research_jobs() -> None:
    html = _ui()
    assert ".filter((job) => isNexusResearchJobLike(job) && ['queued', 'running'].includes" in html
    assert "if (!isNexusResearchJobLike(job)) return false;" in html


def test_resume_uses_metadata_query_priority() -> None:
    html = _ui()
    assert "query: String(job?.metadata?.query || job?.title || job?.query || job?.message || id).trim()," in html


def test_resume_guard_reset_and_single_retry_on_active_timeout() -> None:
    html = _ui()
    assert "nexusDeepResearchResumeStarted = false;" in html
    assert "if (activeTimedOut && !nexusDeepResearchResumeRetryScheduled) {" in html
    assert "setTimeout(() => {" in html and "resumeLatestNexusResearchJob();" in html


def test_terminal_latest_job_hydrates_bundle_and_answer() -> None:
    html = _ui()
    assert "async function hydrateNexusDeepTerminalLatest(jobId) {" in html
    assert "await refreshNexusDeepBundle(id);" in html
    assert "await refreshNexusDeepAnswer(id);" in html
    assert "pushNexusDeepPreviousRun(normalized);" in html
