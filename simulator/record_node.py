"""Record-based nodes used by baselines A-F (each observation travels as an individual bundle)."""
from __future__ import annotations

import heapq
import math
from collections import Counter
from dataclasses import dataclass

from aeio import codec
from aeio.model import AEIO
from aeio.types import Fidelity
from spl.lock import SemanticPreservationLock
from utility.engine import ResourceState, UtilityContext

SUMMARY_BYTES = 48
OFFER_BYTES = 8


@dataclass
class Bundle:
    msg_id: str
    a: AEIO
    created: float
    prio: float
    u0: float
    pmark: float = -1.0


class RecordNode:
    kind = "record"

    def __init__(self, spec, mode: dict, sim):
        self.id, self.role, self.village = spec.node_id, spec.role, spec.village
        self.spec = spec
        self.mode = mode
        self.sim = sim
        self.cap = spec.storage_B
        self.battery = spec.battery_J
        self.store: dict[str, Bundle] = {}
        self.used = 0
        self.prev_used = 0
        self.seen: set[str] = set()
        self.offered: dict[str, set] = {}
        self.summaries: dict[tuple, tuple[int, int]] = {}
        self.local_counts: Counter = Counter()
        self.cell_count: Counter = Counter()
        self.obs_count: Counter = Counter()
        self.heap: list = []
        self.last_resp = math.inf if self.role == "RESPONDER" else -math.inf
        self.energy = 0.0
        self.alive = True
        self.rx_human = self.rx_sensor = 0
        self.dropped = 0
        self.spl = SemanticPreservationLock(sim.registry, aggregator="naive") if mode.get("adapt") == "spl" else None

    # ------------------------------------------------------------------
    def storage_used(self) -> int:
        return self.used

    def utility_of(self, a: AEIO, now: float) -> float:
        ctx = UtilityContext(now=now, similar_in_cell=self.cell_count[(a.event_type, a.geo_cell)],
                             duplicate=self.obs_count[a.observation_key] > 1)
        return self.sim.ue.utility(a, ctx)

    def evict_key(self, b: Bundle) -> float:
        return b.prio if self.mode["evict"] == "priority" else b.u0

    def _index(self, b: Bundle, sign: int):
        self.cell_count[(b.a.event_type, b.a.geo_cell)] += sign
        if b.a.observation_key:
            self.obs_count[b.a.observation_key] += sign

    def _insert(self, b: Bundle):
        self.store[b.msg_id] = b
        self.used += b.a.wire_bytes
        self._index(b, +1)
        if self.mode["evict"] in ("priority", "utility"):
            heapq.heappush(self.heap, (self.evict_key(b), b.created, b.msg_id))

    def remove(self, mid: str):
        b = self.store.pop(mid, None)
        if b is not None:
            self.used -= b.a.wire_bytes
            self._index(b, -1)

    def make_room(self, size: int, key: float) -> bool:
        if self.cap is None or self.used + size <= self.cap:
            return True
        ev = self.mode["evict"]
        if ev == "drop_new":
            return False
        if ev == "drop_oldest":
            while self.store and self.used + size > self.cap:
                self.remove(next(iter(self.store)))
                self.dropped += 1
            return self.used + size <= self.cap
        while self.heap and self.used + size > self.cap:
            k, _, mid = self.heap[0]
            if mid not in self.store:
                heapq.heappop(self.heap)
                continue
            if k >= key:
                return False
            heapq.heappop(self.heap)
            self.remove(mid)
            self.dropped += 1
        return self.used + size <= self.cap

    def can_accept(self, size: int, key: float) -> bool:
        if self.cap is None or self.used + size <= self.cap:
            return True
        return self.mode["evict"] != "drop_new"

    def receive(self, b: Bundle, t: float) -> bool:
        if b.msg_id in self.seen:
            return False
        if self.role == "RESPONDER":
            self.seen.add(b.msg_id)
            self.sim.rlog.note(b.a, t)
            return True
        nb = Bundle(b.msg_id, b.a, b.created, b.prio, self.utility_of(b.a, t) if self.mode["evict"] == "utility" else b.u0)
        if not self.make_room(b.a.wire_bytes, self.evict_key(nb)):
            self.dropped += 1
            return False
        self.seen.add(b.msg_id)
        self._insert(nb)
        return True

    def ingest(self, a: AEIO, msg_id: str, t: float):
        if a.source_class.value in ("ENV_SENSOR", "STRUCT_SENSOR"):
            self.rx_sensor += 1
        else:
            self.rx_human += 1
        b = Bundle(msg_id, a, t, a.criticality, 0.0)
        self.receive(b, t)

    # ------------------------------------------------------------------
    def pressure(self, t: float) -> float:
        s = self.sim
        rs = ResourceState(queue_bytes=self.used, queue_capacity=self.cap or 1, storage_used=self.used,
                           storage_capacity=self.cap or 1,
                           queue_growth_Bps=(self.used - self.prev_used) / s.cfg.step_s,
                           bandwidth_Bps=s.cfg.bandwidth_Bps, battery_frac=1 - self.energy / self.battery,
                           expected_contact_s=s.cfg.contact_dwell_s,
                           human_rate_per_min=self.rx_human * 60 / s.cfg.step_s,
                           sensor_rate_per_min=self.rx_sensor * 60 / s.cfg.step_s)
        return s.ue.pressure(rs)

    def maintain(self, t: float):
        adapt = self.mode.get("adapt")
        if adapt and self.role != "RESPONDER" and self.alive:
            P = self.pressure(t)
            self.sim.pressure_samples.append(P)
            if P >= self.sim.ue.cfg.actions.adapt_min_pressure:
                self._adapt(P, t)
        self.prev_used = self.used
        self.rx_human = self.rx_sensor = 0

    def _adapt(self, P: float, t: float):
        ue = self.sim.ue
        for mid in list(self.store):
            b = self.store[mid]
            if P - b.pmark < 0.1:
                continue
            b.pmark = P
            U = self.utility_of(b.a, t)
            cand = ue.propose(b.a, U, P)
            if cand.target_fidelity <= b.a.fidelity_level:
                continue
            if self.spl is None:
                new = codec.reduce(b.a, cand.target_fidelity, "naive")
                self.sim.unchecked_reductions += 1
            else:
                new = self.spl.transition(b.a, cand.target_fidelity)
            if new is b.a:
                continue
            self.remove(mid)
            if new.fidelity_level >= Fidelity.F3:
                cell = new.geo_cell or "R0"
                k = (new.event_type.value, cell)
                self.local_counts[k] += 1
                ver = self.summaries.get((self.id,) + k, (0, 0))[0] + 1
                self.summaries[(self.id,) + k] = (ver, self.local_counts[k])
                self.sim.rlog.absorbed_crit(new, b.a)
            else:
                self._insert(Bundle(mid, new, b.created, b.prio, b.u0, P))


def exchange_record(a: RecordNode, b: RecordNode, budget: float, t: float) -> int:
    """a sends to b within `budget` bytes. Returns bytes used."""
    sim = a.sim
    if b.role == "RESPONDER":
        for mid in [m for m in a.store if m in b.seen]:
            a.remove(mid)
    if a.role == "RESPONDER" or b.role == "SENSOR":
        return 0  # responders are sinks; sensor nodes are producer-only (same rule in every mode)
    mode = a.mode
    off = a.offered.setdefault(b.id, set())
    cand = [a.store[m] for m in a.store if m not in off]
    rep = mode["replicate"]
    if rep == "never" or rep == "utility":
        grad_ok = b.last_resp > a.last_resp
    if mode["order"] == "priority":
        cand.sort(key=lambda x: (-x.prio, x.created))
    elif mode["order"] == "utility":
        us = {x.msg_id: a.utility_of(x.a, t) for x in cand}
        cand.sort(key=lambda x: (-us[x.msg_id], x.created))
    spent = 0
    misfit = 0
    for x in cand:
        if spent + OFFER_BYTES > budget:
            break
        replicate = rep == "always" or (rep == "utility" and us[x.msg_id] >= sim.ue.cfg.actions.replicate_min_utility)
        if not replicate and not grad_ok:
            continue
        spent += OFFER_BYTES
        sim.bytes_by["offer"] += OFFER_BYTES
        off.add(x.msg_id)
        if x.msg_id in b.seen:
            continue
        size = x.a.wire_bytes
        if spent + size > budget or not b.can_accept(size, x.prio):
            off.discard(x.msg_id)
            misfit += 1
            if misfit > 25:
                break
            continue
        spent += size
        sim.bytes_by["record"] += size
        if x.a.sensor_metadata is not None:
            sim.bytes_by["sensor"] += size
        ok = b.receive(x, t)
        if ok and not replicate:
            a.remove(x.msg_id)
    # naive summaries (E/F)
    for k, (ver, cnt) in list(a.summaries.items()):
        if spent + SUMMARY_BYTES > budget:
            break
        if b.summaries.get(k, (-1, 0))[0] < ver:
            b.summaries[k] = (ver, cnt)
            spent += SUMMARY_BYTES
            sim.bytes_by["summary"] += SUMMARY_BYTES
    return spent
