from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProjectContract:
    contract_id: str
    contract_type: str
    path: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResourceContract(ProjectContract):
    contract_type: str = "resource"


@dataclass(frozen=True)
class InterfaceContract(ProjectContract):
    contract_type: str = "interface"


@dataclass(frozen=True)
class DataContract(ProjectContract):
    contract_type: str = "data"


@dataclass(frozen=True)
class StateContract(ProjectContract):
    contract_type: str = "state"


@dataclass(frozen=True)
class BusinessRuleContract(ProjectContract):
    contract_type: str = "business_rule"


@dataclass(frozen=True)
class ContractViolation:
    code: str
    contract_type: str
    path: str
    severity: str = "error"
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "contract_type": self.contract_type,
            "path": self.path,
            "severity": self.severity,
            "evidence": dict(self.evidence),
        }


def violation(
    *,
    code: str,
    contract_type: str,
    path: str,
    severity: str = "error",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ContractViolation(
        code=code,
        contract_type=contract_type,
        path=path,
        severity=severity,
        evidence=evidence or {},
    ).to_dict()
