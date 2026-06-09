"""Core enums, literals and the contract-version constant (PDT-1).

No storage, network or framework dependency. Readers must be tolerant of additive
enum members per the compatibility rules in
`docs/atlas_project_digital_twin_contracts.md`.
"""

from __future__ import annotations

from typing import Literal

#: Initial public contract version. All persisted payloads and APIs carry this value.
CONTRACT_VERSION = "atlas.project_twin.v1"

TwinNodeStatus = Literal[
    "declared",
    "inferred",
    "observed",
    "verified",
    "user_approved",
    "contradicted",
    "superseded",
    "invalidated",
]

TwinDerivation = Literal[
    "canonical_projection",
    "deterministic_static",
    "heuristic_static",
    "llm_inference",
    "runtime_observation",
    "verification",
    "user_decision",
]

TwinDomain = Literal[
    "structural",
    "behavioral",
    "runtime",
    "intent_delivery",
    "learning",
]

#: Result discriminator for a runtime observation. `unavailable` must never be
#: silently converted into success.
ObservationResult = Literal["passed", "failed", "observed", "unavailable"]

AtlasPhase = Literal[
    "requirement_analysis",
    "project_investigation",
    "planning",
    "generation",
    "review",
    "verification",
    "repair",
    "final_rollup",
]

#: Typed error codes for API/port responses.
TwinErrorCode = Literal[
    "project_not_found",
    "revision_not_found",
    "stale_base_revision",
    "invalid_contract_version",
    "query_limit_exceeded",
    "collector_unavailable",
    "context_budget_too_small",
    "project_scope_violation",
    "twin_store_unavailable",
    "migration_required",
]

#: Statuses that represent the current, non-historical view of a fact.
CURRENT_STATUSES: frozenset[str] = frozenset(
    {"declared", "inferred", "observed", "verified", "user_approved"}
)

#: Statuses that represent retired/historical facts (kept queryable, excluded from current).
HISTORICAL_STATUSES: frozenset[str] = frozenset(
    {"contradicted", "superseded", "invalidated"}
)

#: Derivations that may never be presented or consumed as a verified runtime fact.
NON_VERIFIED_DERIVATIONS: frozenset[str] = frozenset(
    {"heuristic_static", "llm_inference"}
)
