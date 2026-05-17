from __future__ import annotations

from agent.atlas_context_refresh_schema import AtlasContextRefreshPolicy

_CONTEXT_REFRESH_POLICIES = {
    "local_first_bounded": AtlasContextRefreshPolicy(
        policy_id="local_first_bounded",
        name="Local-first bounded",
        description="Use local repo and code-intel context only within bounded budgets.",
    ),
    "web_allowed_manual": AtlasContextRefreshPolicy(
        policy_id="web_allowed_manual",
        name="Web allowed (manual)",
        description="Allow web search only when explicitly requested in manual trigger.",
        allow_nexus_web_search=True,
        max_sources=12,
        max_context_chars=32000,
    ),
    "deep_research_manual": AtlasContextRefreshPolicy(
        policy_id="deep_research_manual",
        name="Deep research (manual)",
        description="Allow deep research only for manual trigger with explicit include flag.",
        allow_nexus_web_search=True,
        allow_deep_research=True,
        max_sources=20,
        max_context_chars=64000,
        timeout_seconds=300,
    ),
}


def get_context_refresh_policy(policy_id: str) -> AtlasContextRefreshPolicy:
    return _CONTEXT_REFRESH_POLICIES.get(policy_id, _CONTEXT_REFRESH_POLICIES["local_first_bounded"])


def list_context_refresh_policies() -> list[AtlasContextRefreshPolicy]:
    return list(_CONTEXT_REFRESH_POLICIES.values())
