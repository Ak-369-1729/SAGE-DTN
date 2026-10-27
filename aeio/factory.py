"""Construction of AEIOs from human reports, sensors and ECP."""
from __future__ import annotations

from typing import Any

from core.geo import cell_of_latlon
from core.hashing import h64
from evidence.commitment import EvidenceLocator, IntegrityCommitment
from spl.registry import InvariantRegistry, default_registry

from .model import AEIO, make_event_id
from .types import EventType, Fidelity, SourceClass

BASE_CRITICALITY = {
    EventType.TRAPPED_PERSON: 1.0, EventType.MEDICATION_NEED: 0.8, EventType.WATER_REQUEST: 0.25,
    EventType.SAFE_STATUS: 0.1, EventType.WATER_LEVEL: 0.3, EventType.SMOKE_DENSITY: 0.3,
    EventType.COLLAPSE_RISK: 0.2, EventType.WATER_SHORTAGE: 0.9, EventType.POTENTIAL_FIRE_CLUSTER: 0.9,
}


def criticality_of(event_type: EventType, payload: dict) -> float:
    c = BASE_CRITICALITY[event_type]
    if event_type == EventType.MEDICATION_NEED:
        c = 0.6 + 0.15 * (int(payload.get("urgency", 1)) - 1)
    elif event_type == EventType.COLLAPSE_RISK:
        c = {"LOW": 0.1, "ELEVATED": 0.6, "HIGH": 0.95}.get(payload.get("risk_state"), 0.2)
    elif event_type == EventType.WATER_LEVEL:
        c = 0.2 + 0.15 * int(payload.get("level_bucket", 0))
    elif event_type == EventType.SMOKE_DENSITY:
        c = 0.2 + 0.15 * int(payload.get("density_bucket", 0))
    return min(1.0, c)


def make_aeio(event_type: EventType, payload: dict[str, Any], observed_at: float, *,
              source_class: SourceClass, observation_key: str, origin_node: str,
              reporter: str | None = None, evidence: bytes | None = None,
              sensor_metadata: dict | None = None, confidence: float = 1.0, corroboration: int = 0,
              geo_cell: str | None = None, registry: InvariantRegistry | None = None,
              extra_provenance: dict | None = None) -> AEIO:
    reg = registry or default_registry()
    event_type = EventType(event_type)
    rule = reg.rule_for(event_type, payload)
    if geo_cell is None and payload.get("lat") is not None:
        geo_cell = cell_of_latlon(payload["lat"], payload["lon"])
    event_id = make_event_id(observation_key)
    commitment = locator = None
    if evidence is not None:
        salt = h64(event_id + ":salt").to_bytes(8, "big")
        c = IntegrityCommitment.commit(evidence, salt)
        commitment = c.to_dict()
        locator = EvidenceLocator.for_evidence(event_id, c, len(evidence)).to_dict()
    prov = {"observation_key": observation_key, "origin_node": origin_node, "reporter": reporter}
    if extra_provenance:
        prov.update(extra_provenance)
    return AEIO(
        event_id=event_id, event_type=event_type, source_class=SourceClass(source_class),
        criticality=criticality_of(event_type, payload), utility=0.0, fidelity_level=Fidelity.F0,
        geo_cell=geo_cell, freshness={"observed_at": float(observed_at), "quantum_s": reg.freshness_quantum_s},
        confidence=float(confidence), corroboration=int(corroboration),
        preservation_class=rule.preservation_class, minimum_fidelity=rule.min_fidelity,
        semantic_invariants=rule.invariants, aggregation_class=rule.aggregation_class,
        evidence_locator=locator, integrity_commitment=commitment, provenance=prov,
        sensor_metadata=sensor_metadata, policy_version=reg.policy_version,
        payload=dict(payload), evidence=evidence)
