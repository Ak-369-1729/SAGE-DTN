"""CPMM nodes used by modes G-J: NodeState = ProtectedMap ∪ BoundedAggregateState ∪ EvidenceStore."""
from __future__ import annotations

import math

from aeio.model import AEIO
from aeio.types import Fidelity
from core.hashing import h64
from cpmm.evidence_store import EvidenceRecord
from cpmm.node_state import NodeState
from cpmm.protected_map import order_key
from evidence.commitment import EvidenceLocator, IntegrityCommitment
from evidence.crypto import Sealed
from evidence.recovery import REQUEST_BYTES, RecoveryRequest
from spl.lock import SemanticPreservationLock
from utility.engine import ResourceState, UtilityContext

OFFER_BYTES = 8
TYPE_PRIORITY = {"COLLAPSE_RISK": 0, "SMOKE_DENSITY": 1, "WATER_LEVEL": 1, "WATER_REQUEST": 2, "SAFE_STATUS": 3}


class CPMMNode:
    kind = "cpmm"

    def __init__(self, spec, mode: dict, sim):
        cfg = sim.cfg
        self.id, self.role, self.village = spec.node_id, spec.role, spec.village
        self.spec = spec
        self.mode = mode
        self.sim = sim
        self.cap = spec.storage_B
        self.battery = spec.battery_J
        self.state = NodeState(cfg.hll_p, cfg.window_s, cfg.windows_kept)
        self.key_mod: dict = {}
        self.ctr = 0
        self.synced: dict[str, dict] = {}
        self.spl = SemanticPreservationLock(sim.registry, aggregator="sketch")
        self.energy = 0.0
        self.alive = True
        self.last_resp = math.inf if self.role == "RESPONDER" else -math.inf
        self.rx_human = self.rx_sensor = 0
        self.prev_used = 0
        self.replicas: dict[str, set] = {}       # evidence originated here -> replica holders
        self.requests: dict[str, RecoveryRequest] = {}
        self.responses: dict[tuple, EvidenceRecord] = {}
        self.protected_overflow = 0
        self.spl_fallback = 0
        self._rep_cache: dict = {}
        self.ecp_fired: set = set()

    # ------------------------------------------------------------------
    def _mod(self, key):
        self.ctr += 1
        self.key_mod[key] = self.ctr

    def storage_used(self) -> int:
        return (self.state.protected.storage_bytes() if self.role != "RESPONDER" else 0) \
            + self.state.aggregate.storage_bytes() + self.state.evidence.used_bytes()

    def put_protected(self, a: AEIO, t: float, from_peer: str | None = None) -> bool:
        changed = self.state.protected.put(a)
        if changed:
            self._mod(a.event_id)
            if self.role == "RESPONDER":
                self.sim.rlog.note(a, t)
            if self.cap is not None and self.storage_used() > self.cap:
                self.protected_overflow += 1
        return changed

    def pressure(self, t: float) -> float:
        cfg = self.sim.cfg
        used = self._used_cache if hasattr(self, "_used_cache") else self.storage_used()
        rs = ResourceState(queue_bytes=used, queue_capacity=self.cap or 1, storage_used=used,
                           storage_capacity=self.cap or 1,
                           queue_growth_Bps=(used - self.prev_used) / cfg.step_s,
                           bandwidth_Bps=cfg.bandwidth_Bps, battery_frac=1 - self.energy / self.battery,
                           expected_contact_s=cfg.contact_dwell_s,
                           human_rate_per_min=self.rx_human * 60 / cfg.step_s,
                           sensor_rate_per_min=self.rx_sensor * 60 / cfg.step_s)
        return self.sim.ue.pressure(rs)

    def utility_of(self, a: AEIO, now: float) -> float:
        return self.sim.ue.utility(a, UtilityContext(now=now))

    # ------------------------------------------------------------------
    def ingest(self, a: AEIO, msg_id: str, t: float):
        sim = self.sim
        if a.source_class.value in ("ENV_SENSOR", "STRUCT_SENSOR"):
            self.rx_sensor += 1
        else:
            self.rx_human += 1
        if a.evidence is not None and a.evidence_locator and not self.state.evidence.has(a.evidence_locator["evidence_id"]):
            loc = EvidenceLocator.from_dict(a.evidence_locator)
            free = (self.cap or 1 << 62) - self.storage_used()
            if free >= len(a.evidence) + 48:
                self.state.evidence.put_plaintext(sim.master_key, loc, IntegrityCommitment.from_dict(a.integrity_commitment),
                                                  a.evidence, self.id, h64(loc.evidence_id).to_bytes(8, "big"))
                self.replicas.setdefault(loc.evidence_id, set())
        rule = sim.registry.rule_for(a.event_type, a.payload)
        if rule.protected:
            # Raw evidence lives in the EvidenceStore; the propagated ProtectedMap entry is at most F1.
            P = self.pressure(t)
            U = self.utility_of(a, t)
            cand = sim.ue.propose(a, U, P)
            rep = self.spl.transition(a, max(Fidelity.F1, cand.target_fidelity))
            self.put_protected(rep, t)
            return
        rep = self.spl.transition(a, Fidelity.F3)
        if rep.fidelity_level != Fidelity.F3:
            self.spl_fallback += 1
            self.put_protected(rep, t)
            return
        bucket = rep.payload.get("level_bucket", rep.payload.get("density_bucket", rep.payload.get("risk_state")))
        ingest = a.provenance.get("ingest_node") or a.provenance.get("origin_node")
        for k in self.state.aggregate.add(a.event_type.value, rep.geo_cell, rep.observed_at,
                                          rep.payload["sketch_key"], bucket,
                                          device=a.provenance.get("reporter"), ingest=ingest):
            self._mod(k)

    # ------------------------------------------------------------------
    def maintain(self, t: float, step: int):
        if not self.alive:
            return
        sim = self.sim
        self._used_cache = self.storage_used()
        if self.mode.get("ecp") and step % 2 == 0:
            thr = sim.ecp_thresholds_for(self, t)
            for rule, m in sim.ecp.evaluate(self.state.aggregate, t, self.id, thr):
                d = sim.ecp.derived_event(rule, m, t, self.id, sim.cfg.window_s)
                cur = self.state.protected.best(d.event_id)
                if cur is None or cur.payload.get("magnitude") != d.payload["magnitude"]:
                    if cur is not None:
                        d = d.replace(provenance={**d.provenance, "logical_ts": max(
                            d.provenance["logical_ts"], cur.provenance.get("logical_ts", 0) + sim.cfg.window_s)})
                    if self.put_protected(d, t):
                        sim.ecp_promotions += 1
        if self.mode.get("sensor_adapt") and self.role == "SENSOR":
            P = self.pressure(t)
            act, mult = sim.ue.sensor_action(P, self.rx_sensor * 60 / sim.cfg.step_s)
            for s in sim.sensors_by_node.get(self.id, []):
                if s.publish_multiplier != mult:
                    sim.sensor_adapt_changes += 1
                s.publish_multiplier = mult
        self.prev_used = self._used_cache
        del self._used_cache
        self.rx_human = self.rx_sensor = 0

    def forward_rep(self, best: AEIO, P: float, t: float) -> AEIO:
        cfg = self.sim.cfg
        target = best.fidelity_level
        if cfg.protected_forward_max_fidelity is not None:
            target = max(target, Fidelity(cfg.protected_forward_max_fidelity))
        if best.evidence is not None and P >= self.sim.ue.cfg.actions.adapt_min_pressure:
            U = self.utility_of(best, t)
            target = max(target, self.sim.ue.propose(best, U, P).target_fidelity)
        if target == best.fidelity_level:
            return best
        ck = (best.digest, int(target))
        r = self._rep_cache.get(ck)
        if r is None:
            r = self._rep_cache[ck] = self.spl.transition(best, target)
        return r

    def wipe(self):
        self.alive = False
        self.state = NodeState(self.sim.cfg.hll_p, self.sim.cfg.window_s, self.sim.cfg.windows_kept)
        self.requests.clear()
        self.responses.clear()


def exchange_cpmm(a: CPMMNode, b: CPMMNode, budget: float, t: float) -> int:
    sim = a.sim
    if b.role == "SENSOR":  # sensor nodes are producer-only (same rule in every mode)
        return _evidence_phase(a, b, budget, t) if a.mode.get("recovery") else 0
    syn = a.synced.setdefault(b.id, {})
    bsyn = b.synced.setdefault(a.id, {})
    spent = 0
    P = a.pressure(t)
    # ---- protected entries -------------------------------------------------
    pm = a.state.protected
    keys = [k for k in pm.entries if a.key_mod.get(k, 0) > syn.get(k, -1)]
    if keys:
        us = {k: a.utility_of(pm.best(k), t) for k in keys}
        keys.sort(key=lambda k: (-us[k], k))
    misfit = 0
    for k in keys:
        if spent + OFFER_BYTES > budget:
            break
        best = pm.best(k)
        rep = a.forward_rep(best, P, t)
        if (a.mode.get("defer") and b.role == a.role and b.role in ("FIELD", "SENSOR")
                and sim.ue.propose(best, us[k], P).defer):
            sim.deferred += 1
            continue
        spent += OFFER_BYTES
        sim.bytes_by["offer"] += OFFER_BYTES
        bk = b.state.protected.best_key(k)
        if bk is not None and bk >= order_key(rep):
            syn[k] = a.key_mod[k]
            continue
        size = rep.wire_bytes
        if spent + size > budget:
            misfit += 1
            if misfit > 25:
                break
            continue
        spent += size
        sim.bytes_by["protected"] += size
        if rep.sensor_metadata is not None:
            sim.bytes_by["sensor"] += size
        b.put_protected(rep, t, a.id)
        syn[k] = a.key_mod[k]
        if rep.digest in b.state.protected.entries.get(k, {}) and len(b.state.protected.entries[k]) == 1 \
                and rep is best:
            bsyn[k] = b.key_mod.get(k, 0)
    # ---- aggregate sketches -----------------------------------------------
    ag = a.state.aggregate
    akeys = [k for k in ag.sketches if a.key_mod.get(k, 0) > syn.get(k, -1)]
    akeys.sort(key=lambda k: (TYPE_PRIORITY.get(k[0], 9), -k[2], k[1], k[3]))
    for k in akeys:
        if spent + OFFER_BYTES > budget:
            break
        spent += OFFER_BYTES
        sim.bytes_by["offer"] += OFFER_BYTES
        sk = ag.sketches[k]
        bs = b.state.aggregate.sketches.get(k)
        if bs is not None and bs.dominates(sk):
            syn[k] = a.key_mod[k]
            continue
        size = ag.wire_bytes(k)
        if spent + size > budget:
            break
        spent += size
        sim.bytes_by["aggregate"] += size
        if k[0] in TYPE_PRIORITY and k[0] not in ("WATER_REQUEST", "SAFE_STATUS"):
            sim.bytes_by["sensor"] += size
        if b.state.aggregate.merge_key(k, sk):
            b._mod(k)
        syn[k] = a.key_mod[k]
        if b.state.aggregate.sketches.get(k) is not None and b.state.aggregate.sketches[k].key() == sk.key():
            bsyn[k] = b.key_mod.get(k, 0)
    # ---- utility-driven eager evidence forwarding (PRESERVE_FULL/REPLICATE) ----
    spent += _evidence_forward(a, b, budget - spent, P, t)
    # ---- evidence replication / recovery (I, J) ----------------------------
    if a.mode.get("recovery"):
        spent += _evidence_phase(a, b, budget - spent, t)
    return spent


def _evidence_forward(a: CPMMNode, b: CPMMNode, budget: float, P: float, t: float) -> int:
    sim, cfg = a.sim, a.sim.cfg
    if cfg.protected_forward_max_fidelity is not None or b.role not in ("FERRY", "RESPONDER"):
        return 0
    ap = sim.ue.cfg.actions
    if P >= ap.adapt_min_pressure or (b.role != "RESPONDER" and b.pressure(t) >= ap.adapt_min_pressure):
        return 0
    spent = 0
    cands = []
    for eid, rec in a.state.evidence.records.items():
        if b.state.evidence.has(eid):
            continue
        best = a.state.protected.best(rec.locator.event_id)
        if best is None:
            continue
        u = a.utility_of(best, t)
        if u >= ap.replicate_min_utility:
            cands.append((-u, eid, rec))
    for _, eid, rec in sorted(cands):
        size = rec.sealed.size + 64
        if spent + size > budget:
            break
        if b.state.evidence.put_record(rec):
            spent += size
            sim.bytes_by["evidence_forward"] += size
            if b.role == "RESPONDER" and b.state.evidence.verify_and_open(sim.master_key, rec) is not None:
                sim.rlog.evidence_delivered.add(rec.locator.event_id)
    return spent


def _evidence_phase(a: CPMMNode, b: CPMMNode, budget: float, t: float) -> int:
    sim, cfg = a.sim, a.sim.cfg
    spent = 0
    # replica placement by the origin
    if b.role != "RESPONDER" and cfg.evidence_replicas > 0:
        for eid, holders in a.replicas.items():
            if len(holders) >= cfg.evidence_replicas or b.id in holders or b.state.evidence.has(eid):
                continue
            rec = a.state.evidence.get(eid)
            if rec is None:
                continue
            size = rec.sealed.size + 64
            free = (b.cap or 1 << 62) - b.storage_used()
            if spent + size > budget or free < size:
                continue
            stored = rec
            if cfg.replica_corrupt_prob > 0 and (h64(f"corrupt:{cfg.seed}:{eid}:{b.id}") % 10_000) < cfg.replica_corrupt_prob * 10_000:
                ct = bytearray(rec.sealed.ciphertext)
                ct[0] ^= 0xFF
                stored = EvidenceRecord(rec.locator, rec.commitment, Sealed(rec.sealed.nonce, bytes(ct), rec.sealed.tag), rec.origin)
            if b.state.evidence.put_record(stored):
                holders.add(b.id)
                spent += size
                sim.bytes_by["evidence_replica"] += size
    # recovery requests (epidemic)
    for rid, req in list(a.requests.items()):
        if rid in b.requests or spent + REQUEST_BYTES > budget:
            continue
        b.requests[rid] = req
        spent += REQUEST_BYTES
        sim.bytes_by["recovery"] += REQUEST_BYTES
        _maybe_respond(b, req, t)
    # responses travel back epidemically toward the requester
    for key, rec in list(a.responses.items()):
        if key in b.responses:
            continue
        req_ids = [r for r in b.requests.values() if r.locator.evidence_id == key[0]] or \
                  [r for r in a.requests.values() if r.locator.evidence_id == key[0]]
        if not req_ids:
            continue
        out = sim.recovery.get(key[0])
        if out is not None and out.recovered_at is not None:
            continue
        size = rec.sealed.size + 64
        if spent + size > budget:
            continue
        b.responses[key] = rec
        spent += size
        sim.bytes_by["recovery"] += size
        if b.role == "RESPONDER" and any(r.requester == b.id for r in req_ids):
            sim.verify_recovery(b, key, rec, t)
    return spent


def _maybe_respond(node: CPMMNode, req: RecoveryRequest, t: float):
    eid = req.locator.evidence_id
    rec = node.state.evidence.get(eid)
    if rec is None or not node.alive:
        return
    if not node.sim.authority.verify(req.token, t):
        node.sim.auth_rejections += 1
        return
    node.responses[(eid, node.id)] = rec
