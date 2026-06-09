"""Contract version constant and compatibility helpers (PDT-1).

Compatibility rules (`docs/atlas_project_digital_twin_contracts.md` section 10):
- additive optional fields are backward compatible;
- enum additions require tolerant readers;
- field removal/rename requires a new contract version;
- API clients send a supported version or use the current default.

No storage dependency.
"""

from __future__ import annotations

from agent.project_twin.types import CONTRACT_VERSION

_PREFIX = "atlas.project_twin."

#: Versions this build can read/write. Additive minor changes stay within v1.
SUPPORTED_CONTRACT_VERSIONS: frozenset[str] = frozenset({CONTRACT_VERSION})


def parse_contract_version(version: str) -> int:
    """Return the integer major version from an ``atlas.project_twin.v<N>`` string.

    Raises ``ValueError`` for any value that is not a well-formed contract version.
    """

    if not isinstance(version, str) or not version.startswith(_PREFIX):
        raise ValueError(f"invalid_contract_version: {version!r}")
    suffix = version[len(_PREFIX):]
    if not suffix.startswith("v") or not suffix[1:].isdigit():
        raise ValueError(f"invalid_contract_version: {version!r}")
    return int(suffix[1:])


def is_compatible_version(version: str) -> bool:
    """True when ``version`` shares the current major version and is parseable."""

    try:
        return parse_contract_version(version) == parse_contract_version(CONTRACT_VERSION)
    except ValueError:
        return False


def assert_supported_version(version: str) -> None:
    """Raise ``ValueError`` when ``version`` is not compatible with this build."""

    if not is_compatible_version(version):
        raise ValueError(f"invalid_contract_version: {version!r}")
