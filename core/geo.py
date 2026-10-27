"""Local tangent-plane geometry and geographic cells.

Simulation positions are metres in a local plane. Latitude/longitude are derived
from a fixed reference origin so that AEIOs carry realistic coordinates.
geo_cell = 500 m grid cell (the aggregation unit, "F3" granularity).
region   = whole deployment area ("F4" granularity).
"""
from __future__ import annotations

import math

ORIGIN_LAT = 26.1000
ORIGIN_LON = 91.7000
M_PER_DEG_LAT = 111_320.0
CELL_M = 500.0
REGION_ID = "R0"


def xy_to_latlon(x: float, y: float) -> tuple[float, float]:
    lat = ORIGIN_LAT + y / M_PER_DEG_LAT
    lon = ORIGIN_LON + x / (M_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT)))
    return lat, lon


def latlon_to_xy(lat: float, lon: float) -> tuple[float, float]:
    y = (lat - ORIGIN_LAT) * M_PER_DEG_LAT
    x = (lon - ORIGIN_LON) * M_PER_DEG_LAT * math.cos(math.radians(ORIGIN_LAT))
    return x, y


def cell_of_xy(x: float, y: float, cell_m: float = CELL_M) -> str:
    return f"C{int(math.floor(x / cell_m))}_{int(math.floor(y / cell_m))}"


def cell_of_latlon(lat: float, lon: float) -> str:
    return cell_of_xy(*latlon_to_xy(lat, lon))
