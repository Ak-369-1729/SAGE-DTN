import random

from hypothesis import given, settings
from hypothesis import strategies as st

from aeio import codec
from aeio.factory import make_aeio
from aeio.types import EventType, SourceClass
from cpmm.hll import HLL
from cpmm.node_state import NodeState, merge


def _ops(seed: int, n: int):
    rng = random.Random(seed)
    ops = []
    for i in range(n):
        k = rng.randrange(40)
        if rng.random() < 0.4:
            t = rng.choice([EventType.TRAPPED_PERSON, EventType.MEDICATION_NEED])
            p = {"trapped_status": "TRAPPED"} if t == EventType.TRAPPED_PERSON else {"medication_label": "INSULIN", "urgency": 2}
            p.update(lat=26.1 + k * 1e-3, lon=91.7)
            a = make_aeio(t, p, 100.0 + k, source_class=SourceClass.SURVIVOR, observation_key=f"o{k}", origin_node="n")
            ops.append(("p", codec.reduce(a, rng.choice([1, 1, 0]))))
        else:
            ops.append(("a", ("SAFE_STATUS", f"C{k % 4}_0", rng.uniform(0, 7200), f"s{rng.randrange(500)}", None)))
    return ops


def _state(ops, idxs):
    s = NodeState(p=6, window_s=300, windows_kept=12)
    for i in idxs:
        kind, x = ops[i]
        if kind == "p":
            s.protected.put(x)
        else:
            s.aggregate.add(*x[:4], bucket=x[4])
    return s


@settings(max_examples=150, deadline=None)
@given(st.integers(0, 10**9))
def test_merge_laws(seed):
    rng = random.Random(seed)
    ops = _ops(seed, 60)
    A, B, C = (_state(ops, rng.sample(range(60), 25)) for _ in range(3))
    d = lambda s: s.logical_digest()
    assert d(merge(A, B)) == d(merge(B, A))                                  # commutativity
    assert d(merge(merge(A, B), C)) == d(merge(A, merge(B, C)))              # associativity
    assert d(merge(A, A)) == d(A)                                            # idempotence
    AB = merge(A, B)
    assert d(merge(AB, B)) == d(AB)                                          # duplicate delivery


@settings(max_examples=60, deadline=None)
@given(st.integers(0, 10**9))
def test_gossip_convergence_any_order_with_partitions(seed):
    rng = random.Random(seed)
    ops = _ops(seed, 80)
    n = 6
    nodes = [_state(ops, [i for i in range(80) if i % n == j]) for j in range(n)]
    full = _state(ops, range(80))
    # partitioned phase: two islands gossip internally in random order with duplicates
    for _ in range(30):
        isl = rng.choice([[0, 1, 2], [3, 4, 5]])
        a, b = rng.sample(isl, 2)
        nodes[b].merge_in(nodes[a])
        if rng.random() < 0.3:
            nodes[b].merge_in(nodes[a])
    # reconnection: random pairwise encounters until convergence
    for _ in range(200):
        a, b = rng.sample(range(n), 2)
        nodes[b].merge_in(nodes[a])
        nodes[a].merge_in(nodes[b])
    digests = {s.logical_digest() for s in nodes}
    assert digests == {full.logical_digest()}


def test_hll_duplicate_insensitive_and_bounded():
    h = HLL(8)
    for rep in range(50):
        for i in range(100):
            h.add(f"k{i}")
    assert abs(h.estimate() - 100) / 100 < 0.15
    assert len(h.reg) == 256


def test_protected_conflicts_are_explicit():
    s1, s2 = NodeState(), NodeState()
    base = dict(lat=26.1, lon=91.7)
    a = make_aeio(EventType.MEDICATION_NEED, {**base, "medication_label": "INSULIN", "urgency": 3}, 50.0,
                  source_class=SourceClass.SURVIVOR, observation_key="same", origin_node="n")
    b = a.replace(payload={**a.payload, "urgency": 1})
    s1.protected.put(a)
    s2.protected.put(b)
    m = merge(s1, s2)
    assert m.protected.conflicts() == [a.event_id]
    assert len(m.protected.get(a.event_id)) == 2
