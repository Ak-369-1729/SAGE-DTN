from __future__ import annotations

from enum import Enum, IntEnum


class EventType(str, Enum):
    TRAPPED_PERSON = "TRAPPED_PERSON"
    MEDICATION_NEED = "MEDICATION_NEED"
    WATER_REQUEST = "WATER_REQUEST"
    SAFE_STATUS = "SAFE_STATUS"
    WATER_LEVEL = "WATER_LEVEL"
    SMOKE_DENSITY = "SMOKE_DENSITY"
    COLLAPSE_RISK = "COLLAPSE_RISK"
    WATER_SHORTAGE = "WATER_SHORTAGE"
    POTENTIAL_FIRE_CLUSTER = "POTENTIAL_FIRE_CLUSTER"


HUMAN_TYPES = (EventType.TRAPPED_PERSON, EventType.MEDICATION_NEED,
               EventType.WATER_REQUEST, EventType.SAFE_STATUS)
SENSOR_TYPES = (EventType.WATER_LEVEL, EventType.SMOKE_DENSITY, EventType.COLLAPSE_RISK)
DERIVED_TYPES = (EventType.WATER_SHORTAGE, EventType.POTENTIAL_FIRE_CLUSTER)


class SourceClass(str, Enum):
    SURVIVOR = "SURVIVOR"
    RESPONDER = "RESPONDER"
    ENV_SENSOR = "ENV_SENSOR"
    STRUCT_SENSOR = "STRUCT_SENSOR"
    GATEWAY = "GATEWAY"
    AGGREGATE_DERIVED = "AGGREGATE_DERIVED"


class Fidelity(IntEnum):
    """Lower number = higher fidelity. "Fj >= Fmin" in the PRD means level(Fj) <= level(Fmin)."""
    F0 = 0  # full evidence / authoritative observation
    F1 = 1  # reduced individual record (no raw evidence, no free text)
    F2 = 2  # compact individual summary (cell-level location, bucketed values)
    F3 = 3  # geo-cell aggregate contribution
    F4 = 4  # regional bounded sketch contribution


class PreservationClass(str, Enum):
    PROTECTED = "PROTECTED"
    AGGREGATABLE = "AGGREGATABLE"
    DERIVED_PROTECTED = "DERIVED_PROTECTED"


class AggregationClass(str, Enum):
    NONE = "NONE"
    DISTINCT_COUNT = "DISTINCT_COUNT"
    BUCKET_DISTRIBUTION = "BUCKET_DISTRIBUTION"
    NAIVE_COUNTER = "NAIVE_COUNTER"  # used only by non-CPMM baselines
