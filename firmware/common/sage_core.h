// SAGE-DTN portable node core (ESP32 / Arduino / host C++17).
// Mirrors the Python reference: AEIO fields, fidelity levels, SPL registry
// (policy SPL-1.0.0), bounded HyperLogLog, ring buffer, sensor buckets.
// NOTE: the 64-bit hash here is FNV-1a + splitmix finaliser (cheap on MCUs);
// the Python simulator uses BLAKE2b-64, so sketches are not bit-compatible
// across the two implementations. A gateway must re-hash observation keys.
#pragma once
#include <stdint.h>
#include <string.h>
#include <math.h>

namespace sage {

[[maybe_unused]] static const char* POLICY_VERSION = "SPL-1.0.0";

enum EventType : uint8_t { TRAPPED_PERSON, MEDICATION_NEED, WATER_REQUEST, SAFE_STATUS, WATER_LEVEL,
                           SMOKE_DENSITY, COLLAPSE_RISK, WATER_SHORTAGE, POTENTIAL_FIRE_CLUSTER, N_TYPES };
[[maybe_unused]] static const char* TYPE_NAMES[N_TYPES] = {"TRAPPED_PERSON", "MEDICATION_NEED", "WATER_REQUEST", "SAFE_STATUS",
  "WATER_LEVEL", "SMOKE_DENSITY", "COLLAPSE_RISK", "WATER_SHORTAGE", "POTENTIAL_FIRE_CLUSTER"};

// Field presence bits used by the SPL check.
enum Field : uint16_t { F_TRAPPED = 1, F_LATLON = 2, F_FRESH = 4, F_MED = 8, F_URGENCY = 16, F_CELL = 32,
                        F_SKETCHKEY = 64, F_LEVELB = 128, F_SMOKEB = 256, F_RISK = 512, F_RULE = 1024 };

struct Rule { uint8_t min_fidelity; uint16_t required; };
// SPL-1.0.0 registry (see spl/registry_v1.json). COLLAPSE_RISK HIGH/ELEVATED -> min F2 handled in minFidelity().
static const Rule REGISTRY[N_TYPES] = {
  {1, F_TRAPPED | F_LATLON | F_FRESH}, {1, F_MED | F_URGENCY | F_LATLON}, {3, F_CELL | F_SKETCHKEY | F_FRESH},
  {3, F_CELL | F_SKETCHKEY}, {3, F_LEVELB | F_CELL | F_FRESH}, {3, F_SMOKEB | F_CELL | F_FRESH},
  {3, F_RISK | F_CELL | F_FRESH}, {2, F_RULE | F_CELL | F_FRESH}, {2, F_RULE | F_CELL | F_FRESH}};

enum Risk : uint8_t { RISK_LOW = 0, RISK_ELEVATED = 1, RISK_HIGH = 2 };

struct AEIO {
  uint64_t event_id;        // H(observation key)
  EventType type;
  uint8_t fidelity;         // 0..4, lower = higher fidelity
  uint16_t fields;          // presence bits
  int32_t lat_e5, lon_e5;   // usable location (1e-5 deg)
  char geo_cell[12];
  uint32_t observed_at;     // seconds since deployment epoch
  uint8_t bucket;           // level/smoke bucket or risk state
  uint8_t urgency;
  char label[16];           // medication label / rule id
  uint64_t sketch_key;
  uint32_t evidence_len;    // >0 when ring-buffer evidence was frozen
  uint8_t commitment[32];   // SHA-256 commitment (computed by mbedTLS on ESP32)
};

inline uint64_t hash64(const void* data, size_t n) {
  const uint8_t* p = (const uint8_t*)data; uint64_t h = 1469598103934665603ULL;
  for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
  h ^= h >> 30; h *= 0xbf58476d1ce4e5b9ULL; h ^= h >> 27; h *= 0x94d049bb133111ebULL; h ^= h >> 31;
  return h;
}
inline uint64_t hashStr(const char* s) { return hash64(s, strlen(s)); }

inline uint8_t minFidelity(const AEIO& a) {
  if (a.type == COLLAPSE_RISK && a.bucket >= RISK_ELEVATED) return 2;
  return REGISTRY[a.type].min_fidelity;
}

// Permit(source -> candidate): deterministic SPL check on concrete representations.
inline bool permit(const AEIO& src, const AEIO& cand) {
  if (cand.type != src.type || cand.fidelity < src.fidelity || cand.fidelity > minFidelity(src)) return false;
  uint16_t req = REGISTRY[src.type].required;
  if ((src.fields & req) != req || (cand.fields & req) != req) return false;
  if ((req & F_LATLON) && (cand.lat_e5 / 10 != src.lat_e5 / 10 || cand.lon_e5 / 10 != src.lon_e5 / 10)) return false;
  if ((req & F_FRESH) && cand.observed_at / 300 != src.observed_at / 300) return false;
  if ((req & F_CELL) && strcmp(cand.geo_cell, src.geo_cell) != 0) return false;
  if ((req & (F_LEVELB | F_SMOKEB | F_RISK)) && cand.bucket != src.bucket) return false;
  if ((req & F_URGENCY) && cand.urgency != src.urgency) return false;
  if ((req & (F_MED | F_RULE)) && strcmp(cand.label, src.label) != 0) return false;
  if ((req & F_SKETCHKEY) && cand.sketch_key != src.sketch_key) return false;
  return true;
}

// Generic (semantics-unaware) reducer, same catalogue as aeio/codec.py.
inline AEIO reduce(const AEIO& a, uint8_t level) {
  AEIO r = a; if (level <= a.fidelity) return r;
  r.fidelity = level; r.evidence_len = 0;
  if (level >= 2) { r.fields &= ~F_LATLON; r.lat_e5 = r.lon_e5 = 0; }
  if (level >= 3) { r.fields &= ~(F_TRAPPED | F_MED | F_URGENCY | F_RULE); r.fields |= F_SKETCHKEY; r.observed_at = (a.observed_at / 300) * 300; }
  if (level >= 4) { r.fields &= ~F_CELL; strcpy(r.geo_cell, "R0"); }
  return r;
}

// Commit only if permitted; otherwise clamp to the most-reduced permitted level.
inline AEIO splTransition(const AEIO& a, uint8_t target, bool* rejected) {
  *rejected = false;
  for (int lvl = target; lvl > a.fidelity; --lvl) {
    AEIO c = reduce(a, (uint8_t)lvl);
    if (permit(a, c)) return c;
    *rejected = true;
  }
  return a;
}

// Bounded HyperLogLog, p=8 (256 B). Duplicate-insensitive; merge = register max.
struct HLL {
  static const int P = 8, M = 1 << P;
  uint8_t reg[M];
  HLL() { memset(reg, 0, M); }
  bool add(uint64_t x) {
    uint32_t idx = (uint32_t)(x >> (64 - P)); uint64_t w = x << P; uint8_t rank = 1;
    while (rank <= 64 - P && !(w & 0x8000000000000000ULL)) { rank++; w <<= 1; }
    if (rank > reg[idx]) { reg[idx] = rank; return true; } return false;
  }
  void merge(const HLL& o) { for (int i = 0; i < M; i++) if (o.reg[i] > reg[i]) reg[i] = o.reg[i]; }
  double estimate() const {
    double z = 0; int zeros = 0;
    for (int i = 0; i < M; i++) { z += ldexp(1.0, -reg[i]); zeros += reg[i] == 0; }
    double e = (0.7213 / (1 + 1.079 / M)) * M * M / z;
    if (e <= 2.5 * M && zeros) e = M * log((double)M / zeros);
    return e;
  }
};

// Fixed-capacity ring buffer of raw samples (int16, scaled x100).
template <int N> struct Ring {
  int16_t v[N]; int head = 0, count = 0;
  void push(float x) { long q = lroundf(x * 100); if (q > 32767) q = 32767; if (q < -32768) q = -32768; v[head] = (int16_t)q; head = (head + 1) % N; if (count < N) count++; }
  int freeze(int16_t* out) const { for (int i = 0; i < count; i++) out[i] = v[(head - count + i + N) % N]; return count; }
};

inline uint8_t waterBucket(float cm) { return (cm >= 50) + (cm >= 100) + (cm >= 150) + (cm >= 200); }
inline uint8_t smokeBucket(float ppm) { return (ppm >= 50) + (ppm >= 150) + (ppm >= 300) + (ppm >= 600); }
inline uint8_t riskState(float g) { g = fabsf(g); return g >= 0.2f ? RISK_HIGH : (g >= 0.05f ? RISK_ELEVATED : RISK_LOW); }

inline void cellOf(int32_t lat_e5, int32_t lon_e5, char* out) {
  // 500 m grid around the deployment origin (26.1 N, 91.7 E), matching core/geo.py.
  double y = (lat_e5 / 1e5 - 26.1) * 111320.0, x = (lon_e5 / 1e5 - 91.7) * 111320.0 * cos(26.1 * M_PI / 180);
  int cx = (int)floor(x / 500.0), cy = (int)floor(y / 500.0);
  int n = 0; out[n++] = 'C';
  char tmp[24]; int k = 0; long a = cx; bool neg = a < 0; if (neg) a = -a; do { tmp[k++] = '0' + a % 10; a /= 10; } while (a);
  if (neg) { out[n++] = '-'; }
  while (k) { out[n++] = tmp[--k]; }
  out[n++] = '_';
  a = cy; neg = a < 0; if (neg) a = -a; do { tmp[k++] = '0' + a % 10; a /= 10; } while (a);
  if (neg) { out[n++] = '-'; }
  while (k) { out[n++] = tmp[--k]; }
  out[n] = 0;
}

// Utility-driven candidate fidelity: floor(5 * P * (1 - min(1, U/0.5))), as utility/engine.py.
inline uint8_t proposeFidelity(float U, float P) {
  float un = U / 0.5f; if (un > 1) un = 1; int l = (int)floorf(5 * P * (1 - un)); return l > 4 ? 4 : (l < 0 ? 0 : l);
}

}  // namespace sage
