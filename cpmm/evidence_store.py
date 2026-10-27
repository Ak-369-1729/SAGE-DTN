"""EvidenceStore: encrypted (simulated) high-fidelity evidence kept apart from propagated state."""
from __future__ import annotations

from dataclasses import dataclass

from evidence.commitment import EvidenceLocator, IntegrityCommitment
from evidence.crypto import Sealed, derive_key, open_sealed, seal


@dataclass
class EvidenceRecord:
    locator: EvidenceLocator
    commitment: IntegrityCommitment
    sealed: Sealed
    origin: str


class EvidenceStore:
    def __init__(self, capacity_bytes: int | None = None):
        self.records: dict[str, EvidenceRecord] = {}
        self.capacity_bytes = capacity_bytes

    def used_bytes(self) -> int:
        return sum(r.sealed.size for r in self.records.values())

    def put_plaintext(self, master_key: bytes, locator: EvidenceLocator, commitment: IntegrityCommitment,
                      plaintext: bytes, origin: str, nonce: bytes) -> EvidenceRecord:
        rec = EvidenceRecord(locator, commitment, seal(derive_key(master_key, locator.evidence_id), nonce,
                                                       plaintext), origin)
        self.records[locator.evidence_id] = rec
        return rec

    def put_record(self, rec: EvidenceRecord) -> bool:
        if rec.locator.evidence_id in self.records:
            return False
        if self.capacity_bytes is not None and self.used_bytes() + rec.sealed.size > self.capacity_bytes:
            return False
        self.records[rec.locator.evidence_id] = rec
        return True

    def has(self, evidence_id: str) -> bool:
        return evidence_id in self.records

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        return self.records.get(evidence_id)

    @staticmethod
    def verify_and_open(master_key: bytes, rec: EvidenceRecord) -> bytes | None:
        pt = open_sealed(derive_key(master_key, rec.locator.evidence_id), rec.sealed)
        if pt is None or not rec.commitment.verify(pt):
            return None
        if rec.commitment.digest_hex != rec.locator.commitment_digest:
            return None
        return pt
