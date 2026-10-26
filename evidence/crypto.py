"""Simulated authenticated encryption for evidence payloads.

PROTOTYPE ONLY. Uses HMAC-SHA256 as a PRF in counter mode for the keystream and
HMAC-SHA256 over (nonce || ciphertext) as the tag (encrypt-then-MAC). It is a
standard construction, but this code is not audited, not constant-time and is
labelled *simulated encryption*. A deployment must use AES-GCM or
ChaCha20-Poly1305 from a vetted library.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass


def _keystream(key: bytes, nonce: bytes, n: int) -> bytes:
    out = bytearray()
    ctr = 0
    while len(out) < n:
        out += hmac.new(key, nonce + ctr.to_bytes(8, "big"), hashlib.sha256).digest()
        ctr += 1
    return bytes(out[:n])


@dataclass(frozen=True)
class Sealed:
    nonce: bytes
    ciphertext: bytes
    tag: bytes

    @property
    def size(self) -> int:
        return len(self.nonce) + len(self.ciphertext) + len(self.tag)


def seal(key: bytes, nonce: bytes, plaintext: bytes) -> Sealed:
    ct = bytes(a ^ b for a, b in zip(plaintext, _keystream(key, nonce, len(plaintext))))
    tag = hmac.new(key, b"tag" + nonce + ct, hashlib.sha256).digest()[:16]
    return Sealed(nonce, ct, tag)


def open_sealed(key: bytes, s: Sealed) -> bytes | None:
    exp = hmac.new(key, b"tag" + s.nonce + s.ciphertext, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(exp, s.tag):
        return None
    return bytes(a ^ b for a, b in zip(s.ciphertext, _keystream(key, s.nonce, len(s.ciphertext))))


def derive_key(master: bytes, evidence_id: str) -> bytes:
    return hmac.new(master, b"evidence-key:" + evidence_id.encode(), hashlib.sha256).digest()
