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


def test_resume_latest_research_job_prefers_server_active_then_latest_then_localstorage() -> None:
    html = _ui()
    assert 'async function resumeLatestNexusResearchJob() {' in html
    assert "const activeUrl = API + '/nexus/jobs/active?limit=20';" in html
    assert "const latestUrl = API + '/nexus/jobs/latest?project=' + encodeURIComponent(currentProject || 'default') + '&limit=1&include_terminal=true';" in html
    assert "const storageKey = 'nexus.deepResearch.lastJobId';" in html


def test_resume_non_blocking_uses_timeout_and_all_settled() -> None:
    html = _ui()
    assert 'fetchWithTimeout(activeUrl, {}, 2200);' in html
    assert 'fetchWithTimeout(latestUrl, {}, 2200);' in html
    assert 'Promise.allSettled([' in html and 'resumeLatestNexusResearchJob(),' in html


def test_terminal_latest_job_is_routed_to_previous_runs() -> None:
    html = _ui()
    assert 'if (isNexusResearchTerminalStatus(job)) {' in html
    assert 'pushNexusDeepPreviousRun(normalized);' in html


def test_advanced_settings_remains_inside_details() -> None:
    html = _ui()
    assert '<details id="nexus-research-advanced"' in html
    assert '<summary>Advanced Settings</summary>' in html


def test_auto_settings_resolver_contains_depth_mapping_and_adaptive_fields() -> None:
    html = _ui()
    assert 'function resolveNexusResearchAutoSettings({ searchType, depth } = {}) {' in html
    assert 'quick:' in html
    assert 'standard:' in html
    assert 'deep:' in html
    assert 'exhaustive:' in html
    assert 'deep: { max_queries:' in html and 'adaptive_retrieval_enabled: true' in html
    assert 'exhaustive: { max_queries:' in html and 'adaptive_retrieval_enabled: true' in html


def test_collect_advanced_overrides_returns_empty_when_details_closed() -> None:
    html = _ui()
    assert 'if (!isNexusAdvancedSettingsOpen()) return {};' in html


def test_run_payload_merges_auto_settings_then_advanced_overrides() -> None:
    html = _ui()
    assert '...autoSettings,' in html
    assert '...advancedOverrides,' in html


def test_hidden_advanced_values_not_mixed_when_advanced_details_closed() -> None:
    html = _ui()
    assert "const advancedOverrides = (typeof collectNexusAdvancedOverrides === 'function')" in html
    assert 'if (Object.keys(advancedOverrides).length === 0) window.__nexusAdvancedOverridesEnabled = false;' in html


def test_compact_status_helper_handles_no_sources_no_evidence_and_fallback_notice() -> None:
    html = _ui()
    assert "if (reason === 'no_sources') title = '検索結果を取得できませんでした';" in html
    assert "else if (reason === 'no_evidence') title = '根拠を抽出できませんでした';" in html
    assert "const fallbackNotice = generationMode === 'template_fallback' ? '回答生成はfallbackです。根拠付き回答ではありません。' : '';" in html


def test_reason_precedence_wins_over_state_precedence() -> None:
    html = _ui()
    assert "if (reason === 'no_sources') title = '検索結果を取得できませんでした';" in html
    assert "else if (state === 'failed') title = '失敗しました';" in html


def test_answer_notice_classifier_does_not_warn_on_finish_reason_stop_without_truncation() -> None:
    html = _ui()
    assert "if (finishReason === 'stop' && !outputTruncated && !error && hasAnswer) {" in html
    assert "return { severity: 'none', message: '', showToUser: false };" in html


def test_role_model_search_warning_not_rendered_in_normal_ui() -> None:
    html = _ui()
    assert 'role_model_search' not in html
