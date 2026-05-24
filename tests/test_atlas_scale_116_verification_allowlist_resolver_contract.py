from agent.atlas_verification_allowlist import resolve_verification_allowlist_target


def test_allowed_id_resolves_deterministically():
    first = resolve_verification_allowlist_target("pytest_file")
    second = resolve_verification_allowlist_target("pytest_file")

    assert first.model_dump() == second.model_dump()
    assert first.allowed is True
    assert first.reason == "allowlisted"
    assert first.runtime_level == "level_0_manual_only"
    assert first.resolver_only is True
    assert first.execution_enabled is False
    assert first.advisory_only is True
    assert first.authoritative_source == "backend"
    assert first.vue_authoritative is False
    assert first.command_metadata["command_id"] == "pytest_file"


def test_unknown_id_is_not_allowed():
    payload = resolve_verification_allowlist_target("totally_unknown_target")

    assert payload.allowed is False
    assert payload.reason == "unknown_target_id"


def test_shell_metacharacters_rejected():
    payload = resolve_verification_allowlist_target("pytest_file && rm -rf /")

    assert payload.allowed is False
    assert payload.reason == "shell_metacharacter_rejected"


def test_install_remote_git_and_destructive_commands_rejected():
    for target in ["pip install requests", "git clone https://example.com/repo.git", "rm -rf /tmp/demo"]:
        payload = resolve_verification_allowlist_target(target)
        assert payload.allowed is False
        assert payload.reason == "disallowed_command_pattern"


def test_no_shell_or_subprocess_or_route_tokens_introduced():
    allowed = resolve_verification_allowlist_target("pytest_selected")
    dumped = str(allowed.model_dump())
    forbidden = ["subprocess", "shell=", "@router.post", "@router.put", "@router.patch", "@router.delete"]

    assert not any(token in dumped for token in forbidden)
