import random

from hypothesis import given, settings
from hypothesis import strategies as st

from aeio.types import EventType, Fidelity
from spl.lock import SemanticPreservationLock, permit, permit_levels
from spl.oracle import is_legal

from .strategies import MUTATIONS, aeios, mutate


@settings(max_examples=600, deadline=None)
@given(aeios(), st.sampled_from(MUTATIONS), st.integers(0, 4), st.integers(0, 2**31))
def test_permit_agrees_with_independent_oracle(a, kind, target, seed):
    cand = mutate(a, kind, random.Random(seed), target)
    assert permit(a, cand).allowed == is_legal(a.to_dict(), cand.to_dict())


@settings(max_examples=400, deadline=None)
@given(aeios(), st.integers(0, 4))
def test_transition_never_commits_forbidden(a, target):
    lock = SemanticPreservationLock()
    out = lock.transition(a, target)
    assert out is a or is_legal(a.to_dict(), out.to_dict())


def test_required_registry_semantics():
    assert not permit_levels(EventType.TRAPPED_PERSON, 0, 2)      # F2 drops usable location
    assert not permit_levels(EventType.TRAPPED_PERSON, 0, 3)
    assert permit_levels(EventType.TRAPPED_PERSON, 0, 1)
    assert permit_levels(EventType.SAFE_STATUS, 0, 3)               # sketch aggregation keeps count semantics
    assert not permit_levels(EventType.SAFE_STATUS, 0, 3, aggregator="naive")
    assert not permit_levels(EventType.SAFE_STATUS, 0, 4)           # F4 loses geo_cell
    assert permit_levels(EventType.WATER_LEVEL, 0, 3)
    assert not permit_levels(EventType.WATER_LEVEL, 0, 3, aggregator="naive")  # loses freshness
    assert not permit_levels(EventType.COLLAPSE_RISK, 0, 3)          # HIGH is protected (min F2)
    assert permit_levels(EventType.COLLAPSE_RISK, 0, 3, payload={"lat": 26.1, "lon": 91.7, "risk_state": "LOW"})


def test_extreme_pressure_cannot_destroy_trapped_location():
    from aeio.factory import make_aeio
    from aeio.types import SourceClass
    from utility.engine import UtilityEngine
    a = make_aeio(EventType.TRAPPED_PERSON, {"trapped_status": "TRAPPED", "lat": 26.12, "lon": 91.73},
                  100.0, source_class=SourceClass.SURVIVOR, observation_key="x", origin_node="n")
    ue = UtilityEngine()
    prop = ue.propose(a, U=0.0, P=1.0)       # utility asks for maximal reduction
    assert prop.target_fidelity == Fidelity.F4
    out = SemanticPreservationLock().transition(a, prop.target_fidelity)
    assert out.fidelity_level == Fidelity.F1
    assert out.payload["lat"] == a.payload["lat"] and out.payload["trapped_status"] == "TRAPPED"
