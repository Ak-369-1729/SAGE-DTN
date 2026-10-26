"""IntegrityCommitment and EvidenceLocator."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import asdict, dataclass

from core.hashing import short_id


@dataclass(frozen=True)
class IntegrityCommitment:
    alg: str
    salt_hex: str
    digest_hex: str

    @staticmethod
    def commit(plaintext: bytes, salt: bytes) -> "IntegrityCommitment":
        return IntegrityCommitment("sha256-salted", salt.hex(), hashlib.sha256(salt + plaintext).hexdigest())

    def verify(self, plaintext: bytes) -> bool:
        exp = hashlib.sha256(bytes.fromhex(self.salt_hex) + plaintext).hexdigest()
        return hmac.compare_digest(exp, self.digest_hex)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "IntegrityCommitment":
        return IntegrityCommitment(**d)


@dataclass(frozen=True)
class EvidenceLocator:
    evidence_id: str
    event_id: str
    size: int
    commitment_digest: str
    policy_id: str = "EVIDENCE-ACCESS-1"

    @staticmethod
    def for_evidence(event_id: str, commitment: IntegrityCommitment, size: int) -> "EvidenceLocator":
        return EvidenceLocator(short_id("evidence", event_id, commitment.digest_hex), event_id, size,
                               commitment.digest_hex)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "EvidenceLocator":
        return EvidenceLocator(**d)
