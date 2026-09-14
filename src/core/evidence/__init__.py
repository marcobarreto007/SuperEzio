"""Evidence Mode helpers for auditable analysis artifacts."""

from .arch_flags import (
    is_arch_c1_enabled,
    is_arch_c2_enabled,
    is_arch_c3_enabled,
    is_arch_c4_enabled,
)
from .pack import save_evidence_pack, seal_pack, verify_pack_seal
from .pack_builder import build_evidence_pack_from_state
from .report import generate_html_report
from .run import EVIDENCE_DIR, EvidenceRun
from .snapshot import (
    NumberClaim,
    bind_answer_to_snapshot,
    freeze_snapshot,
    number_claims,
    number_ledger,
    save_snapshot,
    unbound_number_claims,
    verify_snapshot_seal,
)
from .storage import save_evidence

__all__ = [
    "EVIDENCE_DIR",
    "EvidenceRun",
    "NumberClaim",
    "bind_answer_to_snapshot",
    "build_evidence_pack_from_state",
    "freeze_snapshot",
    "generate_html_report",
    "is_arch_c1_enabled",
    "is_arch_c2_enabled",
    "is_arch_c3_enabled",
    "is_arch_c4_enabled",
    "number_claims",
    "number_ledger",
    "save_evidence",
    "save_evidence_pack",
    "save_snapshot",
    "seal_pack",
    "unbound_number_claims",
    "verify_pack_seal",
    "verify_snapshot_seal",
]
