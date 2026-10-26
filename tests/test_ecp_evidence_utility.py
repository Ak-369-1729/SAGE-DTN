from aeio.factory import make_aeio
from aeio.types import EventType, Fidelity, SourceClass
from cpmm.aggregate_state import BoundedAggregateState
from cpmm.evidence_store import EvidenceStore
from ecp.engine import ECPEngine
from evidence.auth import Authority
from evidence.commitment import EvidenceLocator, IntegrityCommitment
from evidence.crypto import Sealed
from utility.engine import ResourceState, UtilityContext, UtilityEngine


def _water(st, n, t0=0.0, dt=20.0, replay=1, nodes=("F0", "F1")):
    for r in range(replay):
        for i in range(n):
            st.add("WATER_REQUEST", "C1_1", t0 + i * dt, f"sk{i}", device=f"P{i}", ingest=nodes[i % len(nodes)])


def test_ecp_replay_does_not_fire():
    st = BoundedAggregateState(p=8)
    _water(st, 10, replay=100)
    assert ECPEngine().evaluate(st, 200.0) == []


def test_ecp_fires_on_true_population():
    st = BoundedAggregateState(p=8)
    _water(st, 60, dt=10)
    fired = ECPEngine().evaluate(st, 600.0)
    assert [r.rule_id for r, _ in fired] == ["ECP-WATER-1"]
    d = ECPEngine.derived_event(fired[0][0], fired[0][1], 600.0, "x", 300)
    d2 = ECPEngine.derived_event(fired[0][0], fired[0][1], 600.0, "y", 300)
    assert d.event_id == d2.event_id and d.digest == d2.digest   # same logical event on every node


def test_evidence_seal_verify_and_tamper():
    key = b"k" * 32
    pt = b"raw-evidence" * 20
    c = IntegrityCommitment.commit(pt, b"salt0001")
    loc = EvidenceLocator.for_evidence("e1", c, len(pt))
    es = EvidenceStore()
    rec = es.put_plaintext(key, loc, c, pt, "n0", b"nonce001")
    assert EvidenceStore.verify_and_open(key, rec) == pt
    bad = bytearray(rec.sealed.ciphertext)
    bad[3] ^= 1
    rec.sealed = Sealed(rec.sealed.nonce, bytes(bad), rec.sealed.tag)
    assert EvidenceStore.verify_and_open(key, rec) is None


def test_authorization():
    auth = Authority(b"secret")
    tok = auth.issue("RESPONDER", "R0", 1000)
    assert auth.verify(tok, 10)
    assert not auth.verify(tok, 2000)
    assert not auth.verify(auth.issue("SURVIVOR", "x", 1000), 10)
    forged = type(tok)("RESPONDER", "R9", 1000, tok.mac)
    assert not auth.verify(forged, 10)


def test_utility_monotone_and_pressure_bounds():
    ue = UtilityEngine()
    mk = lambda t, p: make_aeio(t, {**p, "lat": 26.1, "lon": 91.7}, 0.0, source_class=SourceClass.SURVIVOR,
                                observation_key=str(t), origin_node="n")
    trapped = mk(EventType.TRAPPED_PERSON, {"trapped_status": "TRAPPED"})
    safe = mk(EventType.SAFE_STATUS, {"persons": 1})
    ctx = UtilityContext(now=60)
    assert ue.utility(trapped, ctx) > ue.utility(safe, ctx)
    assert ue.utility(trapped, UtilityContext(now=60)) > ue.utility(trapped, UtilityContext(now=20000))
    assert ue.utility(trapped, ctx) > ue.utility(trapped, UtilityContext(now=60, duplicate=True))
    assert 0 <= ue.pressure(ResourceState()) <= 1
    assert ue.pressure(ResourceState(storage_used=1, storage_capacity=1)) == 1.0
    lo = ue.propose(safe, 0.01, 0.1).target_fidelity
    hi = ue.propose(safe, 0.01, 0.9).target_fidelity
    assert hi >= lo and hi >= Fidelity.F3
