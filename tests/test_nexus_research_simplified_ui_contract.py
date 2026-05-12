from tests.helpers.ui_contract import load_ui_contract_text


def _ui() -> str:
    return load_ui_contract_text()


def test_research_default_view_hides_job_provider_current_run_and_job_id() -> None:
    html = _ui()
    assert 'id="nexus-deep-job-status"' not in html
    assert 'id="nexus-deep-provider-health"' not in html
    assert 'Current Run' not in html
    assert 'id="nexus-deep-current-run"' not in html


def test_debug_details_can_still_contain_job_id() -> None:
    html = _ui()
    assert 'Debug Details' in html
    assert 'job:${id}' in html


def test_previous_runs_starts_collapsed_and_not_eager_loaded() -> None:
    html = _ui()
    assert 'Show previous runs' in html
    assert "if (!nexusDeepPreviousRunsLoaded) refreshNexusDeepPreviousRuns();" in html


def test_nexus_init_does_not_block_on_single_promise_all() -> None:
    html = _ui()
    assert 'Promise.allSettled([' in html
    assert 'setTimeout(() => fn(), timeout);' in html


def test_jobs_active_polling_not_started_only_by_nexus_tab_open() -> None:
    html = _ui()
    assert 'if (nexusDeepResearchJobId) {' in html
    assert 'nexusJobsPollTimer = setInterval(refreshNexusJobs, NEXUS_POLL_MS);' in html
