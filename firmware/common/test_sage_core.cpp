// Host-side unit test for the firmware core: g++ -std=c++17 -O2 test_sage_core.cpp && ./a.out
#include <cstdio>
#include <cstdlib>
#include "sage_core.h"
using namespace sage;
static int fails = 0;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); fails++; } } while (0)

int main() {
  AEIO t{}; t.type = TRAPPED_PERSON; t.fidelity = 0; t.fields = F_TRAPPED | F_LATLON | F_FRESH | F_CELL;
  t.lat_e5 = 2611234; t.lon_e5 = 9171234; t.observed_at = 1234; cellOf(t.lat_e5, t.lon_e5, t.geo_cell);
  bool rej;
  AEIO r = splTransition(t, proposeFidelity(0.0f, 1.0f), &rej);   // max pressure, zero utility asks for F4
  CHECK(proposeFidelity(0.0f, 1.0f) == 4);
  CHECK(r.fidelity == 1 && rej && r.lat_e5 == t.lat_e5);            // SPL clamps to F1, keeps location
  CHECK(!permit(t, reduce(t, 2)) && !permit(t, reduce(t, 3)) && permit(t, reduce(t, 1)));

  AEIO s{}; s.type = SAFE_STATUS; s.fields = F_CELL | F_SKETCHKEY; strcpy(s.geo_cell, "C3_4"); s.sketch_key = 42;
  CHECK(permit(s, reduce(s, 3)) && !permit(s, reduce(s, 4)));

  AEIO c{}; c.type = COLLAPSE_RISK; c.fields = F_RISK | F_CELL | F_FRESH; c.bucket = RISK_HIGH; strcpy(c.geo_cell, "C1_1");
  CHECK(!permit(c, reduce(c, 3)) && permit(c, reduce(c, 2)));
  c.bucket = RISK_LOW; CHECK(permit(c, reduce(c, 3)));

  // random illegal mutations are never permitted
  srand(7); int forb = 0, committed = 0;
  for (int i = 0; i < 100000; i++) {
    AEIO m = reduce(t, rand() % 5);
    int k = rand() % 4;
    if (k == 0) m.lat_e5 += 100; else if (k == 1) m.observed_at += 3600; else if (k == 2) m.fields &= ~F_TRAPPED; else m.fidelity = 0;
    bool legal = m.fidelity <= 1 && m.fidelity >= t.fidelity && (m.fields & (F_TRAPPED | F_LATLON | F_FRESH)) == (F_TRAPPED | F_LATLON | F_FRESH)
                 && m.lat_e5 / 10 == t.lat_e5 / 10 && m.lon_e5 / 10 == t.lon_e5 / 10 && m.observed_at / 300 == t.observed_at / 300;
    if (!legal) { forb++; committed += permit(t, m); }
  }
  CHECK(forb > 0 && committed == 0);

  HLL h, h2; char key[32];
  for (int rep = 0; rep < 20; rep++) for (int i = 0; i < 500; i++) { snprintf(key, 32, "obs%d", i); h.add(hashStr(key)); }
  double e = h.estimate(); CHECK(fabs(e - 500) / 500 < 0.2);
  for (int i = 250; i < 750; i++) { snprintf(key, 32, "obs%d", i); h2.add(hashStr(key)); }
  HLL a = h; a.merge(h2); HLL b = h2; b.merge(h); CHECK(memcmp(a.reg, b.reg, HLL::M) == 0);
  HLL aa = a; aa.merge(a); CHECK(memcmp(aa.reg, a.reg, HLL::M) == 0);
  CHECK(fabs(a.estimate() - 750) / 750 < 0.2);

  Ring<8> ring; for (int i = 0; i < 20; i++) ring.push(i * 0.5f); int16_t out[8]; CHECK(ring.freeze(out) == 8 && out[0] == 600 && out[7] == 950);
  CHECK(waterBucket(49) == 0 && waterBucket(160) == 3 && smokeBucket(700) == 4 && riskState(0.3f) == RISK_HIGH);
  char cell[12]; cellOf(2610000, 9170000, cell); CHECK(strcmp(cell, "C0_0") == 0);
  printf("forbidden=%d committed=%d hll500=%.1f hll750=%.1f\n", forb, committed, e, a.estimate());
  printf(fails ? "FIRMWARE CORE TESTS FAILED (%d)\n" : "FIRMWARE CORE TESTS PASSED\n", fails);
  return fails ? 1 : 0;
}
