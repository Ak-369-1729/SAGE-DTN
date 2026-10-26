"""Authorization abstraction for evidence access.

An authority issues HMAC-signed capability tokens (role, subject, expiry).
Replica holders verify the token before releasing sealed evidence. In the
simulator the verification key is pre-distributed; a deployment would use
asymmetric signatures (e.g. Ed25519) so holders cannot mint tokens.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

ALLOWED_ROLES = ("RESPONDER", "COORDINATOR")


@dataclass(frozen=True)
class AuthToken:
    role: str
    subject: str
    expires_at: float
    mac: str

    def body(self) -> bytes:
        return f"{self.role}|{self.subject}|{self.expires_at}".encode()


class Authority:
    def __init__(self, key: bytes):
        self._key = key

    def issue(self, role: str, subject: str, expires_at: float) -> AuthToken:
        t = AuthToken(role, subject, expires_at, "")
        return AuthToken(role, subject, expires_at, hmac.new(self._key, t.body(), hashlib.sha256).hexdigest())

    def verify(self, token: AuthToken, now: float) -> bool:
        exp = hmac.new(self._key, token.body(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(exp, token.mac) and token.role in ALLOWED_ROLES and now <= token.expires_at
