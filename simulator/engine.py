"""Discrete-time DTN simulation engine shared by all system modes."""
from __future__ import annotations

import bisect
import math
import time
from collections import defaultdict

import numpy as np

from aeio.model import AEIO
from aeio.types import EventType, Fidelity
from core.hashing import h64
from core.version import code_version
from cpmm.exact import ExactAggregateState
from ecp.engine import ECPEngine, ECPRule
from evidence.auth import Authority
from evidence.commitment import EvidenceLocator
from evidence.recovery import RecoveryOutcome, RecoveryRequest
from sensors.virtual import FloodGaugeSensor, SensorConfig, SmokeSensor, VibrationSensor
from spl.invariants import extract
from spl.registry import default_registry
from utility.config import UtilityConfig
from utility.engine import UtilityContext, UtilityEngine

from .cpmm_node import CPMMNode, exchange_cpmm
from .modes import MODES
from .record_node import RecordNode, exchange_record
from .scenario import Environment, FerryMobility, ScenarioConfig, build_nodes, generate_human_workload

SA_THRESHOLD = 0.6
SA_WEIGHTS = (0.5, 0.3, 0.2)  # critical usable, human aggregate accuracy, fresh sensor picture
AGG_TYPES = ("SAFE_STATUS", "WATER_REQUEST")
SENSOR_TYPES = ("WATER_LEVEL", "SMOKE_DENSITY", "COLLAPSE_RISK")


class ResponderLog:
    """Union view of everything that reached any responder (used for metrics only)."""

    def __init__(self, sim):
        self.sim = sim
        self.crit: dict[str, list] = {}          # event_id -> [t_any, t_usable]
        self.obs_by_cell: dict[tuple, set] = defaultdict(set)
        self.latest_obs: dict[tuple, float] = {}
        self.windows: dict[tuple, set] = defaultdict(set)
        self.derived: dict[tuple, float] = {}    # (rule_id, cell) -> first time at responder
        self.absorbed_critical: set = set()
        self.central = ExactAggregateState(8, sim.cfg.window_s, sim.cfg.windows_kept)
        self.corrupt_delivered = 0
        self.evidence_delivered: set = set()
        self.sensor_state_bytes = 0

    def usable(self, a: AEIO, orig: AEIO) -> bool:
        rule = self.sim.registry.rule_for(orig.event_type, orig.payload)
        return all(extract(i, a) is not None and extract(i, a) == extract(i, orig) for i in rule.invariants)

    def note(self, a: AEIO, t: float):
        tr = self.sim.truth.get(a.event_id)
        if a.event_type.value in ("WATER_SHORTAGE", "POTENTIAL_FIRE_CLUSTER"):
            k = (a.payload.get("rule_id"), a.geo_cell)
            if k not in self.derived:
                self.derived[k] = t
                self.sim.events_log.append({"t": t, "type": "ECP_AT_RESPONDER", "rule": k[0], "cell": k[1],
                                            "derived_type": a.event_type.value, "magnitude": a.payload.get("magnitude")})
            return
        if a.evidence is not None and tr is not None:
            self.evidence_delivered.add(a.event_id)
        if a.sensor_metadata is not None and self.sim.mode["kind"] == "record":
            self.sensor_state_bytes += a.wire_bytes
        if tr is not None and tr["critical"]:
            rec = self.crit.setdefault(a.event_id, [t, None])
            if rec[1] is None and self.usable(a, tr["aeio"]):
                rec[1] = t
        ok = a.observation_key
        if a.geo_cell and ok and a.fidelity_level <= Fidelity.F2:
            k = (a.event_type.value, a.geo_cell)
            self.obs_by_cell[k].add(ok)
            if a.observed_at is not None:
                self.latest_obs[k] = max(self.latest_obs.get(k, -1), a.observed_at)
                self.windows[k].add(int(a.observed_at // self.sim.cfg.window_s))
                if a.event_type.value in ("WATER_REQUEST", "SMOKE_DENSITY"):
                    b = a.payload.get("density_bucket")
                    self.central.add(a.event_type.value, a.geo_cell, a.observed_at, ok,
                                     b if b is not None else None, device=a.provenance.get("reporter"),
                                     ingest=a.provenance.get("ingest_node") or a.provenance.get("origin_node"))

    def absorbed_crit(self, new: AEIO, old: AEIO):
        tr = self.sim.truth.get(old.event_id)
        if tr is not None and tr["critical"]:
            self.absorbed_critical.add(old.event_id)


class Simulation:
    def __init__(self, cfg: ScenarioConfig, mode: str, ml_gate=None, timeline: bool = False):
        self.cfg = cfg
        self.mode_name = mode
        self.mode = MODES[mode]
        self.registry = default_registry()
        self.ue = UtilityEngine(UtilityConfig.from_dict(cfg.utility))
        self.ecp = ECPEngine()
        for r in self.ecp.rules:
            for k, v in cfg.ecp_thresholds.get(r.rule_id, {}).items():
                setattr(r, k, v)
        self.ml_gate = ml_gate if self.mode.get("ml") else None
        self.env = Environment(cfg)
        self.mob = FerryMobility(cfg)
        self.master_key = h64(f"master:{cfg.seed}").to_bytes(8, "big") * 4
        self.authority = Authority(b"authority-key-" + str(cfg.seed).encode())
        self.timeline_on = timeline
        self.timeline: list[dict] = []
        self.events_log: list[dict] = []
        rng_nodes = np.random.default_rng([cfg.seed, 1])
        rng_work = np.random.default_rng([cfg.seed, 2])
        self.specs = build_nodes(cfg, rng_nodes)
        self.subs = generate_human_workload(cfg, self.specs, rng_work)
        cls = RecordNode if self.mode["kind"] == "record" else CPMMNode
        self.nodes = {s.node_id: cls(s, self.mode, self) for s in self.specs}
        self.order = [s.node_id for s in self.specs]
        self.sensors_by_node: dict[str, list] = defaultdict(list)
        for s in self.specs:
            if s.role != "SENSOR":
                continue
            for j, (S, sd) in enumerate(((FloodGaugeSensor, 2.0), (SmokeSensor, 8.0), (VibrationSensor, 0.004))):
                sc = SensorConfig(sample_hz=cfg.sensor_sample_hz, publish_period_s=cfg.sensor_publish_s, noise_sd=sd,
                                  failure_time_s=cfg.sensor_failure_s)
                self.sensors_by_node[s.node_id].append(
                    S(f"{s.node_id}.{j}", s.node_id, s.x, s.y, sc, np.random.default_rng([cfg.seed, 3, h64(s.node_id) % 10_000, j])))
        self.truth: dict[str, dict] = {}
        self.truth_times: dict[tuple, list] = defaultdict(list)
        self.truth_sensor: dict[tuple, list] = defaultdict(list)
        self.truth_u: dict[tuple, float] = defaultdict(float)
        self.oracle = ExactAggregateState(8, cfg.window_s, cfg.windows_kept)
        self.oracle_fired: dict[tuple, float] = {}
        self.rlog = ResponderLog(self)
        self.bytes_by = defaultdict(int)
        self.tbt = 0
        self.unchecked_reductions = 0
        self.deferred = 0
        self.ecp_promotions = 0
        self.sensor_adapt_changes = 0
        self.auth_rejections = 0
        self.pressure_samples: list[float] = []
        self.recovery: dict[str, RecoveryOutcome] = {}
        self.sa_series: list[tuple] = []
        self.peak_storage = 0
        self.peak_storage_items = 0
        self.storage_series: list[int] = []
        self.sensor_energy = 0.0

    # ------------------------------------------------------------------
    def ecp_thresholds_for(self, node, t):
        if self.ml_gate is None:
            return None
        return self.ml_gate.thresholds(node.state.aggregate, self.ecp.rules, t)

    def _register_truth(self, a: AEIO, t: float):
        if a.event_id in self.truth:
            return
        rule = self.registry.rule_for(a.event_type, a.payload)
        # sensor-originated critical events are counted at their triggering transition, so the
        # denominator is identical for every mode even when sensor publish rates adapt.
        critical = rule.critical and (a.sensor_metadata is None or bool(a.sensor_metadata.get("triggered")))
        self.truth[a.event_id] = {"aeio": a, "t": t, "critical": critical}
        et = a.event_type.value
        if et in AGG_TYPES:
            bisect.insort(self.truth_times[(et, a.geo_cell)], t)
            self.truth_u[(et, a.geo_cell)] += self.ue.utility(a, UtilityContext(now=t))
        if et in SENSOR_TYPES:
            self.truth_sensor[(et, a.geo_cell)].append(t)
        if et in ("WATER_REQUEST", "SMOKE_DENSITY"):
            b = a.payload.get("density_bucket")
            self.oracle.add(et, a.geo_cell, a.observed_at, a.observation_key, b,
                            device=a.provenance.get("reporter"),
                            ingest=a.provenance.get("ingest_node") or a.provenance.get("origin_node"))

    def _oracle_ecp(self, t):
        for rule, m in self.ecp.evaluate(self.oracle, t):
            self.oracle_fired.setdefault((rule.rule_id, m.cell), t)

    def _central_ecp(self, t):
        for rule, m in self.ecp.evaluate(self.rlog.central, t):
            self.rlog.derived.setdefault((rule.rule_id, m.cell), t)

    # ------------------------------------------------------------------
    def run(self) -> dict:
        cfg = self.cfg
        t0 = time.time()
        n_steps = int(cfg.horizon_s // cfg.step_s)
        si = 0
        nodes = self.nodes
        ferries = [n for n in self.order if nodes[n].role == "FERRY"]
        pos = {s.node_id: (s.x, s.y) for s in self.specs}
        for step in range(n_steps):
            t = step * cfg.step_s
            for k, fid in enumerate(ferries):
                pos[fid] = self.mob.position(k, t)
            if cfg.source_loss_s is not None and t <= cfg.source_loss_s < t + cfg.step_s:
                for nid in cfg.source_loss_nodes:
                    n = nodes[nid]
                    if n.kind == "cpmm":
                        n.wipe()
                    else:
                        n.alive = False
                        n.store.clear()
                    self.events_log.append({"t": t, "type": "SOURCE_LOSS", "node": nid})
            # human workload
            while si < len(self.subs) and self.subs[si].t < t + cfg.step_s:
                s = self.subs[si]
                si += 1
                self._register_truth(s.aeio, s.t)
                n = nodes[s.node_id]
                if n.alive:
                    n.ingest(s.aeio, s.msg_id, s.t)
            # sensors
            for nid, sens in self.sensors_by_node.items():
                n = nodes[nid]
                if not n.alive:
                    continue
                for sensor in sens:
                    e0 = sensor.energy_used
                    # sub-step so publish periods shorter than the simulation tick take effect
                    k = max(1, int(np.ceil(cfg.step_s / max(1.0, sensor.cfg.publish_period_s * sensor.publish_multiplier))))
                    sub = cfg.step_s / k
                    for i in range(k):
                        for a in sensor.step(self.env, t + i * sub, sub):
                            self._register_truth(a, a.observed_at)
                            n.ingest(a, f"msg:{a.event_id}", a.observed_at)
                    self.sensor_energy += sensor.energy_used - e0
            # node maintenance
            for nid in self.order:
                n = nodes[nid]
                if n.kind == "cpmm":
                    n.maintain(t, step)
                else:
                    n.maintain(t)
            if step % 2 == 0:
                self._oracle_ecp(t)
                if self.mode["kind"] == "record":
                    self._central_ecp(t)
            # contacts
            self._contacts(pos, t)
            if cfg.recovery_request_s is not None and t <= cfg.recovery_request_s < t + cfg.step_s and self.mode.get("recovery"):
                self._issue_recovery(t)
            # storage
            st = [nodes[n].storage_used() for n in self.order if nodes[n].role != "RESPONDER" and nodes[n].alive]
            if st:
                self.peak_storage = max(self.peak_storage, max(st))
                self.storage_series.append(int(np.mean(st)))
            if step % cfg.sample_every_steps == 0 or step == n_steps - 1:
                self.sa_series.append((t + cfg.step_s, *self._sa(t + cfg.step_s)))
                if self.timeline_on:
                    self.timeline.append(self._frame(t, pos))
        return self._final(time.time() - t0)

    def _contacts(self, pos, t):
        cfg, nodes = self.cfg, self.nodes
        ids = [n for n in self.order if nodes[n].alive]
        xy = np.array([pos[n] for n in ids])
        d = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
        budget = cfg.bandwidth_Bps * cfg.step_s
        ex = exchange_record if self.mode["kind"] == "record" else exchange_cpmm
        self.contacts_now = []
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if d[i, j] > cfg.radio_range_m:
                    continue
                a, b = nodes[ids[i]], nodes[ids[j]]
                if a.role == "RESPONDER" and b.role == "RESPONDER" and a.kind == "record":
                    continue
                self.contacts_now.append((a.id, b.id))
                if b.role == "RESPONDER":
                    a.last_resp = t
                if a.role == "RESPONDER":
                    b.last_resp = t
                used = ex(a, b, budget / 2, t) + ex(b, a, budget / 2, t)
                self.tbt += used
                for n in (a, b):
                    n.energy += used * (cfg.energy_tx_J_per_B + cfg.energy_rx_J_per_B) / 2

    # ------------------------------------------------------------------
    def _issue_recovery(self, t):
        lost = set(self.cfg.source_loss_nodes)
        for r in [n for n in self.nodes.values() if n.role == "RESPONDER"]:
            tok = self.authority.issue("RESPONDER", r.id, t + 10 * 3600)
            for eid, vs in r.state.protected.entries.items():
                a = next(iter(vs.values()))
                if not a.evidence_locator or a.fidelity_level == Fidelity.F0:
                    continue
                if lost and a.provenance.get("origin_node") not in lost:
                    continue
                loc = EvidenceLocator.from_dict(a.evidence_locator)
                if r.state.evidence.has(loc.evidence_id) or loc.evidence_id in self.recovery:
                    continue
                req = RecoveryRequest(loc, tok, r.id, t)
                r.requests[req.rid] = req
                self.recovery[loc.evidence_id] = RecoveryOutcome(loc.evidence_id, t)
                self.events_log.append({"t": t, "type": "RECOVERY_REQUEST", "evidence_id": loc.evidence_id, "node": r.id})
            break  # one requesting responder

    def verify_recovery(self, node, key, rec, t):
        out = self.recovery.get(key[0])
        if out is None or out.recovered_at is not None:
            return
        out.attempts.append(key[1])
        pt = node.state.evidence.verify_and_open(self.master_key, rec)
        if pt is None:
            out.integrity_failures += 1
            self.events_log.append({"t": t, "type": "INTEGRITY_FAILURE", "evidence_id": key[0], "holder": key[1]})
            return
        tr = self.truth.get(rec.locator.event_id)
        if tr is not None and tr["aeio"].evidence != pt:
            self.rlog.corrupt_delivered += 1
            return
        out.recovered_at = t
        out.holder = key[1]
        node.state.evidence.put_record(rec)
        if tr is not None:
            node.put_protected(tr["aeio"].replace(provenance={**tr["aeio"].provenance, "recovered_by": key[1]}), t)
        self.events_log.append({"t": t, "type": "RECOVERED", "evidence_id": key[0], "holder": key[1]})

    # ------------------------------------------------------------------
    def responder_estimate(self, et: str, cell: str) -> float:
        if self.mode["kind"] == "record":
            e = float(len(self.rlog.obs_by_cell.get((et, cell), ())))
            best: dict = {}
            for n in self.nodes.values():
                if n.role == "RESPONDER":
                    for k, (v, c) in n.summaries.items():
                        if k[1] == et and k[2] == cell and best.get(k, (-1, 0))[0] < v:
                            best[k] = (v, c)
            return e + sum(c for _, c in best.values())
        return self._resp_agg().estimate(et, cell)

    def _resp_agg(self):
        rs = [n for n in self.nodes.values() if n.role == "RESPONDER"]
        agg = rs[0].state.aggregate.copy()
        for r in rs[1:]:
            agg.merge_in(r.state.aggregate)
        return agg

    def _sa(self, t: float) -> tuple[float, float, float, float]:
        crit_gen = [e for e, v in self.truth.items() if v["critical"] and v["t"] <= t]
        crit_ok = sum(1 for e in crit_gen if (self.rlog.crit.get(e) or [None, None])[1] is not None)
        c = crit_ok / len(crit_gen) if crit_gen else 0.0  # empty denominators score 0 (no awareness yet)
        agg = self._resp_agg() if self.mode["kind"] == "cpmm" else None
        oks = tot = 0
        for (et, cell), ts in self.truth_times.items():
            n = bisect.bisect_right(ts, t)
            if n < 3:
                continue
            tot += 1
            e = agg.estimate(et, cell) if agg is not None else self.responder_estimate(et, cell)
            oks += abs(e - n) / n <= 0.25
        h = oks / tot if tot else 0.0
        fresh = tot_s = 0
        for (et, cell), ts in self.truth_sensor.items():
            tot_s += 1
            if agg is not None:
                lw = agg.latest_window(et, cell)
                lt = -1 if lw is None else (lw + 1) * self.cfg.window_s
            else:
                lt = self.rlog.latest_obs.get((et, cell), -1)
            fresh += lt >= t - 900
        s = fresh / tot_s if tot_s else 0.0
        w = SA_WEIGHTS
        return (w[0] * c + w[1] * h + w[2] * s, c, h, s)

    def _frame(self, t, pos) -> dict:
        fr = {"t": t, "nodes": [], "contacts": list(self.contacts_now), "tbt": self.tbt}
        for nid in self.order:
            n = self.nodes[nid]
            d = {"id": nid, "role": n.role, "x": round(pos[nid][0]), "y": round(pos[nid][1]), "alive": n.alive,
                 "storage": n.storage_used(), "battery": round(1 - n.energy / n.battery, 4)}
            if n.kind == "cpmm":
                d.update(protected=len(n.state.protected), aggregates=len(n.state.aggregate.sketches),
                         evidence=len(n.state.evidence.records), conflicts=len(n.state.protected.conflicts()))
            else:
                d.update(queue=len(n.store), summaries=len(n.summaries))
            fr["nodes"].append(d)
        fr["sa"] = self.sa_series[-1][1:] if self.sa_series else None
        fr["spl_rejected"] = sum(n.spl.stats.rejected for n in self.nodes.values() if getattr(n, "spl", None))
        fr["spl_permitted"] = sum(n.spl.stats.permitted for n in self.nodes.values() if getattr(n, "spl", None))
        fr["ecp_promotions"] = self.ecp_promotions
        fr["replicas"] = sum(len(h) for n in self.nodes.values() if n.kind == "cpmm" for h in n.replicas.values())
        return fr

    def _final(self, wall: float) -> dict:
        cfg = self.cfg
        H = cfg.horizon_s
        crit = [e for e, v in self.truth.items() if v["critical"]]
        any_ = [e for e in crit if e in self.rlog.crit]
        usable = [e for e in crit if (self.rlog.crit.get(e) or [None, None])[1] is not None]
        lat = [self.rlog.crit[e][1] - self.truth[e]["t"] for e in usable]
        usable_s = set(usable)
        hcrit = [e for e in crit if self.truth[e]["aeio"].sensor_metadata is None]
        sat = next((s[0] for s in self.sa_series if s[1] >= SA_THRESHOLD), None)
        # aggregate error at end
        errs = []
        for (et, cell), ts in self.truth_times.items():
            if len(ts) >= 3:
                errs.append(abs(self.responder_estimate(et, cell) - len(ts)) / len(ts))
        # ECP vs oracle
        fired = set(self.oracle_fired)
        det = {k: v for k, v in self.rlog.derived.items()}
        false_ecp = sorted(k for k in det if k not in fired)
        missed = sorted(k for k in fired if k not in det)
        ecp_lat = [det[k] - self.oracle_fired[k] for k in fired if k in det]
        # utility delivered (utility at generation, credited when information is usable at a responder)
        u_del = 0.0
        for e, v in self.truth.items():
            a = v["aeio"]
            if v["critical"]:
                if e in usable:
                    u_del += self.ue.utility(a, UtilityContext(now=v["t"]))
        for (et, cell), ts in self.truth_times.items():
            est = self.responder_estimate(et, cell)
            u_del += self.truth_u[(et, cell)] * min(1.0, est / len(ts))  # no credit for over-counting
        storage = [self.nodes[n].storage_used() for n in self.order if self.nodes[n].role != "RESPONDER"]
        rec = list(self.recovery.values())
        m = {
            "mode": self.mode_name, "seed": cfg.seed, "scenario": cfg.name, "human_load": cfg.human_load,
            "sensor_publish_s": cfg.sensor_publish_s, "evidence_replicas": cfg.evidence_replicas,
            "critical_generated": len(crit), "critical_delivered_any": len(any_),
            "critical_delivered_usable": len(usable),
            "CDR": len(usable) / len(crit) if crit else float("nan"),
            "CDR_any": len(any_) / len(crit) if crit else float("nan"),
            "critical_human_generated": len(hcrit),
            "CDR_human": (sum(1 for e in hcrit if e in usable_s) / len(hcrit)) if hcrit else float("nan"),
            "responder_sensor_state_B": int(self.rlog.sensor_state_bytes if self.mode["kind"] == "record" else
                                            sum(sk.wire_bytes() + 24 for k, sk in self._resp_agg().sketches.items() if k[0] in SENSOR_TYPES)),
            "sensor_observations": sum(1 for v in self.truth.values() if v["aeio"].sensor_metadata is not None),
            "critical_info_loss": (len(set(any_) - set(usable)) + len(self.rlog.absorbed_critical - set(usable))) / len(crit) if crit else float("nan"),
            "critical_evidence_at_responder": (sum(1 for e in crit if e in self.rlog.evidence_delivered) /
                                               max(1, sum(1 for e in crit if self.truth[e]["aeio"].evidence is not None))),
            "critical_latency_mean_s": float(np.mean(lat)) if lat else float("nan"),
            "critical_latency_p50_s": float(np.median(lat)) if lat else float("nan"),
            "TBT_bytes": int(self.tbt), **{f"bytes_{k}": int(v) for k, v in self.bytes_by.items()},
            "SAT_s": sat if sat is not None else float("nan"), "SAT_censored": sat is None,
            "SA_mean": float(np.mean([s[1] for s in self.sa_series])),
            "SA_final": self.sa_series[-1][1], "SA_crit_final": self.sa_series[-1][2],
            "SA_agg_final": self.sa_series[-1][3], "SA_sensor_final": self.sa_series[-1][4],
            "peak_storage_B": int(self.peak_storage), "mean_storage_B": float(np.mean(self.storage_series)) if self.storage_series else 0.0,
            "final_max_storage_B": int(max(storage) if storage else 0),
            "summary_error": float(np.mean(errs)) if errs else float("nan"),
            "utility_per_kB": u_del / (self.tbt / 1024) if self.tbt else float("nan"),
            "energy_proxy_J": float(sum(n.energy for n in self.nodes.values()) + self.sensor_energy),
            "ecp_oracle_fired": len(fired), "ecp_detected": len(det), "ecp_false": len(false_ecp),
            "ecp_missed": len(missed), "ecp_latency_mean_s": float(np.mean(ecp_lat)) if ecp_lat else float("nan"),
            "ecp_mechanism": "distributed_sketch" if self.mode.get("ecp") else ("central_exact_at_responder" if self.mode["kind"] == "record" else "none"),
            "unchecked_reductions": self.unchecked_reductions, "deferred": self.deferred,
            "sensor_adapt_changes": self.sensor_adapt_changes,
            "observations_generated": len(self.truth), "human_submissions": len(self.subs),
            "wall_s": round(wall, 2),
        }
        if self.mode["kind"] == "cpmm":
            m["protected_overflow"] = sum(n.protected_overflow for n in self.nodes.values())
            m["conflicts_at_responder"] = sum(len(n.state.protected.conflicts()) for n in self.nodes.values() if n.role == "RESPONDER")
            m["spl_rejected"] = sum(n.spl.stats.rejected for n in self.nodes.values())
            m["spl_clamped"] = sum(n.spl.stats.clamped for n in self.nodes.values())
            m["aggregate_sketches_responder"] = len(self._resp_agg().sketches)
        else:
            m["dropped"] = sum(n.dropped for n in self.nodes.values())
            if self.mode.get("adapt") == "spl":
                m["spl_rejected"] = sum(n.spl.stats.rejected for n in self.nodes.values() if n.spl)
                m["spl_clamped"] = sum(n.spl.stats.clamped for n in self.nodes.values() if n.spl)
        if rec:
            ok = [r for r in rec if r.recovered_at is not None]
            m.update(recovery_requests=len(rec), recovery_success=len(ok),
                     recovery_probability=len(ok) / len(rec),
                     recovery_latency_mean_s=float(np.mean([r.recovered_at - r.requested_at for r in ok])) if ok else float("nan"),
                     recovery_bytes=int(self.bytes_by.get("recovery", 0)),
                     recovery_integrity_failures_detected=sum(r.integrity_failures for r in rec),
                     recovery_corrupt_accepted=self.rlog.corrupt_delivered)
        m["config"] = cfg.to_dict()
        m["code_version"] = code_version()
        m["policy_version"] = self.registry.policy_version
        m["registry_digest"] = self.registry.digest
        m["timestamp_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return m


def run(cfg: ScenarioConfig, mode: str, **kw) -> dict:
    return Simulation(cfg, mode, **kw).run()
