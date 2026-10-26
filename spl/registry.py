"""Versioned deterministic invariant registry."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aeio.types import AggregationClass, EventType, Fidelity, PreservationClass
from core.hashing import canonical_json, sha256_hex

DEFAULT_REGISTRY_PATH = Path(__file__).with_name("registry_v1.json")


@dataclass(frozen=True)
class Rule:
    event_type: EventType
    preservation_class: PreservationClass
    min_fidelity: Fidelity
    aggregation_class: AggregationClass
    invariants: tuple[str, ...]
    critical: bool

    @property
    def protected(self) -> bool:
        return self.preservation_class in (PreservationClass.PROTECTED, PreservationClass.DERIVED_PROTECTED)


class InvariantRegistry:
    def __init__(self, spec: dict[str, Any]):
        self.spec = spec
        self.policy_version: str = spec["policy_version"]
        self.freshness_quantum_s: int = int(spec["freshness_quantum_s"])
        self.digest = sha256_hex(canonical_json(spec))[:16]

    @classmethod
    def load(cls, path: str | Path = DEFAULT_REGISTRY_PATH) -> "InvariantRegistry":
        return cls(json.loads(Path(path).read_text()))

    def rule_for(self, event_type: EventType, payload: dict | None = None) -> Rule:
        r = self.spec["rules"][EventType(event_type).value]
        pc, minf, agg, crit = r["preservation_class"], r["min_fidelity"], r["aggregation_class"], r["critical"]
        cond = r.get("protect_if")
        if cond and payload is not None and payload.get(cond["field"]) in cond["in"]:
            pc, minf, agg = "PROTECTED", cond["min_fidelity"], "NONE"
            crit = payload.get(cond["field"]) in cond.get("critical_if_in", [])
        return Rule(EventType(event_type), PreservationClass(pc), Fidelity(minf), AggregationClass(agg),
                    tuple(r["invariants"]), bool(crit))

    def event_types(self) -> list[EventType]:
        return [EventType(k) for k in self.spec["rules"]]


_DEFAULT: InvariantRegistry | None = None


def default_registry() -> InvariantRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = InvariantRegistry.load()
    return _DEFAULT
