"""Evidence contract for financial data consumed by agents."""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, Field, computed_field


class EvidenceContractError(ValueError):
    """Raised when a payload cannot satisfy the evidence contract."""


class EvidenceSection(BaseModel):
    name: str
    evidence_id: str
    source: str = "unknown"
    timestamp: str | None = None
    status: str = "ok"
    payload: dict[str, Any] = Field(default_factory=dict)


class EvidenceContract(BaseModel):
    ticker: str
    analysis_id: str
    required_sections: list[str] = Field(default_factory=list)
    sections: dict[str, EvidenceSection] = Field(default_factory=dict)
    missing_required: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def ready(self) -> bool:
        return not self.missing_required

    def assert_ready(self) -> None:
        if self.missing_required:
            missing = ", ".join(self.missing_required)
            raise EvidenceContractError(
                f"missing evidence for required sections: {missing}"
            )


def _is_valid_section(section: Any) -> bool:
    return (
        isinstance(section, dict)
        and bool(section)
        and bool(str(section.get("evidence_id") or "").strip())
    )


def build_evidence_contract(
    data: dict[str, Any],
    required_sections: Iterable[str],
) -> EvidenceContract:
    """Build a contract from collector output and mark missing required evidence."""
    required = list(required_sections)
    sections: dict[str, EvidenceSection] = {}
    missing: list[str] = []

    for name, payload in data.items():
        if not _is_valid_section(payload):
            continue
        sections[name] = EvidenceSection(
            name=name,
            evidence_id=str(payload["evidence_id"]),
            source=str(payload.get("source") or "unknown"),
            timestamp=payload.get("timestamp"),
            status=str(payload.get("data_quality") or "ok"),
            payload=dict(payload),
        )

    for name in required:
        if name not in sections:
            missing.append(name)

    return EvidenceContract(
        ticker=str(data.get("ticker") or "UNKNOWN"),
        analysis_id=str(data.get("analysis_id") or "N/D"),
        required_sections=required,
        sections=sections,
        missing_required=missing,
    )


def format_evidence_contract(contract: EvidenceContract) -> str:
    """Return a concise prompt block listing allowed evidence IDs."""
    lines = [
        "=== EVIDENCE CONTRACT ===",
        f"analysis_id={contract.analysis_id}",
        f"ticker={contract.ticker}",
        f"ready={str(contract.ready).lower()}",
    ]
    if contract.missing_required:
        lines.append("missing_required=" + ", ".join(contract.missing_required))
    lines.append("allowed_sections:")
    for name in sorted(contract.sections):
        section = contract.sections[name]
        lines.append(
            f"- {name}: evidence_id={section.evidence_id}, source={section.source}"
        )
    lines.append(
        "rule: agents and CEO may cite current financial data only from these evidence_id values."
    )
    return "\n".join(lines)
