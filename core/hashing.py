"""Deterministic hashing and canonical encoding helpers.

All identifiers and digests in SAGE-DTN are derived from canonical JSON so that
two nodes that hold the same logical information compute the same digest,
independent of insertion order or Python hash randomisation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default).encode()


def _default(o: Any):
    if isinstance(o, (bytes, bytearray)):
        return {"__bytes__": bytes(o).hex()}
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if hasattr(o, "value"):
        return o.value
    raise TypeError(f"not serialisable: {type(o)}")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def h64(data: bytes | str) -> int:
    """64-bit deterministic hash (BLAKE2b-64)."""
    if isinstance(data, str):
        data = data.encode()
    return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")


def short_id(*parts: Any, n: int = 16) -> str:
    return sha256_hex(canonical_json(list(parts)))[:n]
