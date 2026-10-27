// SAGE-DTN testbed node. One binary, role set at run time by the controller ("cfg ...").
//
// Roles: F field node, S sensor node, X ferry (data mule), R responder (sink).
// Modes (same letters as the simulator baselines):
//   A flooding: records only, no reduction, tail drop when full, no priority
//   E adaptive fidelity WITHOUT SPL: utility-proposed reduction committed unchecked
//   F utility + SPL: records, SPL-gated reduction, critical records never evicted
//   H full deterministic core: F + bounded sketches (HLL) for aggregatable reports,
//     sensor last-writer-wins state, on-node ECP promotion
//   I H + evidence replicas on ferries and SHA-256-verified recovery
//
// Disruption: IoT-LAB nodes are static and usually in radio range of each other, so the
// contact plan is applied in software from the phase number the controller broadcasts.
// Ferry k is at location (phase + k) mod (V + 1); location 0 is the responder base and
// 1..V are villages. Packets from nodes not at the receiver's location are ignored. Real
// radio loss, collisions and serial timing come from the hardware.
//
// All output lines start with '@' so the analysis ignores RIOT shell noise.
#include "sage_app.h"
#include "sage_core.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

using namespace sage;

namespace {

const int MAXREC = 160, MAXV = 4, MAXEV = 8, MAXJOB = 6, MAXWANT = 6, MAXNODES = 64;
const int EV_SAMPLES = 64, EV_BYTES = EV_SAMPLES * 2, EV_CHUNK = 32, EV_NCHUNK = EV_BYTES / EV_CHUNK;
const uint8_t MAGIC = 0x53, VER = 1;
enum MsgType : uint8_t { MSG_REC = 1, MSG_HLL = 2, MSG_SENS = 3, MSG_EVC = 4, MSG_EVREQ = 5, MSG_EVACK = 6, MSG_BEACON = 7 };
enum HllKind { K_WATER = 0, K_SAFE = 1, K_SMOKE = 2, N_KIND = 3 };
const int HDR = 8;

struct Cfg {
  int id = -1; char role = 'F'; int grp = 0; char mode = 'H'; int trial = 0;
  int cap = 40, rcap = MAXREC, bud = 150, V = 3, nf = 3, R = 0, ecpw = 6, ecps = 2;
  int corrupt_pm = 0;     // replica corruption probability, per mille
  int tau = 120;          // utility age constant (s)
} cfg;

struct Rec {
  bool used; bool has_commit; bool ev_ok; bool lost_reported; AEIO a;
  uint32_t seq; uint32_t tx_epoch; uint32_t req_epoch;
};
struct Ev { bool used; bool own; uint64_t eid; uint8_t data[EV_BYTES]; uint8_t have; uint64_t acked; uint32_t place_epoch; };
struct Job { bool used; uint64_t eid; uint8_t dest; uint8_t next; };
struct Want { bool used; uint64_t eid; uint32_t epoch; };
struct Sens { uint32_t ts; uint8_t bucket; int16_t val; uint32_t tx_epoch; bool set; };
struct Stats { uint32_t tx_b, tx_p, rx_b, rx_p, tx_sensor_b, red, rej, evict, drop, pdrop, loss, peak_b; } st;

Rec recs[MAXREC]; uint32_t recSeq = 0;
HLL hll[N_KIND][MAXV + 1];
struct HllTx { uint32_t epoch; int cursor; } hllTx[N_KIND][MAXV + 1];   // sparse pages sent once per contact epoch
const int HLL_PAIRS = 36;
Sens sens[MAXV + 1][3];
Ev evs[MAXEV]; Job jobs[MAXJOB]; Want wants[MAXWANT];
uint32_t ferryHeard[MAXNODES];
bool ecpDone[2][MAXV + 1];
uint32_t waterRaw[MAXV + 1];               // responder: raw WATER_REQUEST record messages received
int phase = 0; uint32_t pepoch = 1; uint32_t tAtPh = 0, msAtPh = 0;
float tokens = 0; uint32_t lastTickMs = 0, lastSlowMs = 0;
uint8_t pend[128]; size_t pendLen = 0; bool pendSensor = false;
uint64_t rng = 1; uint32_t beaconEpoch = 0;
bool dead = false;          // source destroyed (E4): silent until the next reset
char villageCell[MAXV + 1][12];
// sensor node local state
Ring<EV_SAMPLES> sring[3]; uint8_t sLast[3] = {255, 255, 255}; uint32_t sSeq = 0;
char out[256];

uint32_t rnd() { rng = rng * 6364136223846793005ULL + 1442695040888963407ULL; return (uint32_t)(rng >> 33); }
void hex64(uint64_t v, char* o) { static const char* H = "0123456789abcdef"; for (int i = 15; i >= 0; i--) { o[i] = H[v & 15]; v >>= 4; } o[16] = 0; }
uint32_t nowS() { return tAtPh + (plat_ms() - msAtPh) / 1000; }
bool isSink() { return cfg.role == 'R'; }
bool modeHasSketch() { return cfg.mode == 'H' || cfg.mode == 'I'; }
bool modeHasSpl() { return cfg.mode == 'F' || cfg.mode == 'H' || cfg.mode == 'I'; }

void villageCenter(int v, int32_t* lat, int32_t* lon) { *lat = 2610000 + 2250 * v; *lon = 9170000 + 2250 * v; }
int villageOfCell(const char* c) { for (int v = 0; v <= cfg.V; v++) if (!strcmp(c, villageCell[v])) return v; return -1; }

int locOf(char role, int grp) { return role == 'X' ? (phase + grp) % (cfg.V + 1) : grp; }
bool inContact(char role, int grp) { return phase < 0 || locOf(role, grp) == locOf(cfg.role, cfg.grp); }
bool ferryAtMyLoc() {
  if (phase < 0 || cfg.role == 'X') return true;
  for (int k = 0; k < cfg.nf; k++) if (locOf('X', k) == locOf(cfg.role, cfg.grp)) return true;
  return false;
}
bool ferryHeardNow() { for (int i = 0; i < MAXNODES; i++) if (ferryHeard[i] == pepoch) return true; return false; }

bool isCriticalType(const AEIO& a) {
  return a.type == TRAPPED_PERSON || a.type == MEDICATION_NEED || a.type == WATER_SHORTAGE || a.type == POTENTIAL_FIRE_CLUSTER ||
         (a.type == COLLAPSE_RISK && a.bucket >= RISK_ELEVATED);
}
bool usable(const AEIO& a) { uint16_t req = REGISTRY[a.type].required; return (a.fields & req) == req && a.fidelity <= minFidelity(a); }

float utility(const AEIO& a) {
  static const float CRIT[N_TYPES] = {0.8f, 0.6f, 0.05f, 0.03f, 0.1f, 0.1f, 0.1f, 0.5f, 0.5f};
  float c = CRIT[a.type]; if (a.type == COLLAPSE_RISK && a.bucket >= RISK_HIGH) c = 0.4f;
  float age = (float)nowS() - (float)a.observed_at; if (age < 0) age = 0;
  float urg = a.urgency ? 0.5f + 0.25f * a.urgency : 1.0f;
  return c * urg * expf(-age / (float)cfg.tau);
}

// ---- wire encoding (little endian) ----
struct W { uint8_t* p; size_t n; void u8(uint8_t v) { p[n++] = v; } void u16(uint16_t v) { u8(v); u8(v >> 8); }
  void u32(uint32_t v) { u16(v); u16(v >> 16); } void u64(uint64_t v) { u32((uint32_t)v); u32((uint32_t)(v >> 32)); }
  void raw(const void* d, size_t k) { memcpy(p + n, d, k); n += k; } };
struct Rd { const uint8_t* p; size_t n, i; bool ok = true;
  bool need(size_t k) { if (i + k > n) ok = false; return ok; }
  uint8_t u8() { return need(1) ? p[i++] : 0; } uint16_t u16() { uint16_t a = u8(); return a | (uint16_t)u8() << 8; }
  uint32_t u32() { uint32_t a = u16(); return a | (uint32_t)u16() << 16; } uint64_t u64() { uint64_t a = u32(); return a | (uint64_t)u32() << 32; }
  void raw(void* d, size_t k) { if (need(k)) { memcpy(d, p + i, k); i += k; } } };

void header(W& w, uint8_t type) { w.u8(MAGIC); w.u8(VER); w.u8(type); w.u8((uint8_t)cfg.trial); w.u8((uint8_t)cfg.id); w.u8((uint8_t)cfg.role); w.u8((uint8_t)cfg.grp); w.u8(0); }

size_t encodeRec(uint8_t* buf, const Rec& r) {
  W w{buf, 0}; header(w, MSG_REC); const AEIO& a = r.a;
  w.u64(a.event_id); w.u8(a.type); w.u8(a.fidelity); w.u16(a.fields); w.u32(a.observed_at); w.u8(a.bucket); w.u8(a.urgency);
  size_t cl = strlen(a.geo_cell); w.u8((uint8_t)cl); w.raw(a.geo_cell, cl);
  uint8_t flags = r.has_commit ? 1 : 0; w.u8(flags);
  if (a.fields & F_LATLON) { w.u32((uint32_t)a.lat_e5); w.u32((uint32_t)a.lon_e5); }
  if (a.fields & (F_MED | F_RULE)) { char l[8] = {0}; memcpy(l, a.label, strnlen(a.label, 8)); w.raw(l, 8); }
  if (a.fields & F_SKETCHKEY) w.u64(a.sketch_key);
  if (r.has_commit) w.raw(a.commitment, 32);
  return w.n;
}
size_t recBytes(const Rec& r) { static uint8_t tmp[128]; return encodeRec(tmp, r); }

uint32_t storeBytes() { uint32_t b = 0; for (auto& r : recs) if (r.used) b += recBytes(r); return b; }
int storeCount() { int n = 0; for (auto& r : recs) if (r.used) n++; return n; }
int capacity() { int c = isSink() ? cfg.rcap : cfg.cap; return c > MAXREC ? MAXREC : c; }
int findRec(uint64_t eid) { for (int i = 0; i < MAXREC; i++) if (recs[i].used && recs[i].a.event_id == eid) return i; return -1; }

void sinkLog(const char* tag, const Rec& r) {
  char h[17]; hex64(r.a.event_id, h);
  snprintf(out, sizeof out, "@%s %s %s %u %d %lu", tag, h, TYPE_NAMES[r.a.type], r.a.fidelity, usable(r.a) ? 1 : 0, (unsigned long)nowS());
  plat_out(out);
}

void checkLoss(Rec& r) {   // critical information destroyed by a committed reduction
  if (isCriticalType(r.a) && !usable(r.a) && !r.lost_reported) {
    r.lost_reported = true; st.loss++; char h[17]; hex64(r.a.event_id, h);
    snprintf(out, sizeof out, "@loss %s %s %u", h, TYPE_NAMES[r.a.type], r.a.fidelity); plat_out(out);
  }
}

// returns slot index or -1 when the record was not stored
int insertRec(const AEIO& a, bool hasCommit) {
  int i = findRec(a.event_id);
  if (i >= 0) {          // deterministic merge: max (observed_at, then higher fidelity = lower level)
    Rec& r = recs[i]; bool better = a.observed_at > r.a.observed_at || (a.observed_at == r.a.observed_at && a.fidelity < r.a.fidelity);
    if (hasCommit && !r.has_commit) { memcpy(r.a.commitment, a.commitment, 32); r.has_commit = true; }
    if (better) {
      uint8_t c[32]; memcpy(c, r.a.commitment, 32); r.a = a; memcpy(r.a.commitment, c, 32);
      if (isSink()) sinkLog("up", r);
      r.lost_reported = false; checkLoss(r);
    }
    return i;
  }
  int n = storeCount(), cap = capacity(), slot = -1;
  if (n < cap) { for (int k = 0; k < MAXREC; k++) if (!recs[k].used) { slot = k; break; } }
  else if (cfg.mode == 'A' || isSink()) { st.drop++; return -1; }
  else {
    float uin = utility(a); int victim = -1; float vu = 1e9f;
    for (int k = 0; k < MAXREC; k++) {
      if (!recs[k].used) continue;
      if (modeHasSpl() && isCriticalType(recs[k].a)) continue;   // protected records are never evicted
      float u = utility(recs[k].a); if (u < vu) { vu = u; victim = k; }
    }
    if (victim < 0 || vu > uin) { if (isCriticalType(a)) st.pdrop++; else st.drop++; return -1; }
    recs[victim].used = false; st.evict++; slot = victim;
  }
  Rec& r = recs[slot]; memset(&r, 0, sizeof r); r.used = true; r.a = a; r.has_commit = hasCommit; r.seq = ++recSeq;
  if (isSink()) sinkLog("dl", r);
  checkLoss(r);
  uint32_t b = storeBytes(); if (b > st.peak_b) st.peak_b = b;
  return slot;
}

void reductionPass() {
  if (cfg.mode == 'A' || isSink() || phase < 0) return;   // no new reductions during the E6 all-contact sync
  float P = (float)storeCount() / (float)capacity(); if (P > 1) P = 1;
  for (auto& r : recs) {
    if (!r.used) continue;
    uint8_t target = proposeFidelity(utility(r.a), P);   // UTILITY PROPOSES
    if (target <= r.a.fidelity) continue;
    if (cfg.mode == 'E') { r.a = reduce(r.a, target); st.red++; checkLoss(r); continue; }   // committed unchecked
    bool rej = false; AEIO c = splTransition(r.a, target, &rej);                             // SPL DISPOSES
    if (rej) st.rej++;
    if (c.fidelity != r.a.fidelity) { r.a = c; st.red++; }
    checkLoss(r);
  }
}

void promote(EventType t, int v) {
  AEIO a{}; char key[24]; snprintf(key, sizeof key, "ECP:%s:%d", t == WATER_SHORTAGE ? "WS" : "FC", v);
  a.event_id = hashStr(key); a.type = t; a.fidelity = 0; a.fields = F_RULE | F_CELL | F_FRESH; a.observed_at = nowS();
  strcpy(a.geo_cell, villageCell[v]); strcpy(a.label, t == WATER_SHORTAGE ? "R-WS1" : "R-FC1");
  int k = findRec(a.event_id); if (k >= 0) return;
  snprintf(out, sizeof out, "@ecpnode %s %d", TYPE_NAMES[t], v); plat_out(out);
  insertRec(a, false);
}

void ecpPass() {
  if (modeHasSketch()) {
    for (int v = 1; v <= cfg.V; v++) {
      if (hll[K_WATER][v].estimate() >= cfg.ecpw - 0.5) promote(WATER_SHORTAGE, v);
      if (hll[K_SMOKE][v].estimate() >= cfg.ecps - 0.5) promote(POTENTIAL_FIRE_CLUSTER, v);
    }
  } else if (isSink()) {   // record modes: exact central detector at the responder
    for (int v = 1; v <= cfg.V; v++) {
      int nw = 0; uint64_t smk[8]; int ns = 0;
      for (auto& r : recs) {
        if (!r.used || villageOfCell(r.a.geo_cell) != v) continue;
        if (r.a.type == WATER_REQUEST) nw++;
        if (r.a.type == SMOKE_DENSITY && r.a.bucket >= 2) { bool seen = false; for (int j = 0; j < ns; j++) seen |= smk[j] == r.a.sketch_key; if (!seen && ns < 8) smk[ns++] = r.a.sketch_key; }
      }
      if (nw >= cfg.ecpw) promote(WATER_SHORTAGE, v);
      if (ns >= cfg.ecps) promote(POTENTIAL_FIRE_CLUSTER, v);
    }
  }
  if (isSink()) for (auto& r : recs) {
    if (!r.used || (r.a.type != WATER_SHORTAGE && r.a.type != POTENTIAL_FIRE_CLUSTER)) continue;
    int v = villageOfCell(r.a.geo_cell); int t = r.a.type == WATER_SHORTAGE ? 0 : 1;
    if (v >= 0 && !ecpDone[t][v]) { ecpDone[t][v] = true; snprintf(out, sizeof out, "@ecp %s %d %lu", TYPE_NAMES[r.a.type], v, (unsigned long)nowS()); plat_out(out); }
  }
}

// ---- evidence ----
int findEv(uint64_t eid) { for (int i = 0; i < MAXEV; i++) if (evs[i].used && evs[i].eid == eid) return i; return -1; }
int allocEv(uint64_t eid) {
  int i = findEv(eid); if (i >= 0) return i;
  for (int k = 0; k < MAXEV; k++) if (!evs[k].used) { memset(&evs[k], 0, sizeof evs[k]); evs[k].used = true; evs[k].eid = eid; return k; }
  return -1;
}
void addJob(uint64_t eid, uint8_t dest) {
  for (auto& j : jobs) if (j.used && j.eid == eid && j.dest == dest) return;
  for (auto& j : jobs) if (!j.used) { j.used = true; j.eid = eid; j.dest = dest; j.next = 0; return; }
}
void addWant(uint64_t eid) {
  for (auto& w : wants) if (w.used && w.eid == eid) return;
  for (auto& w : wants) if (!w.used) { w.used = true; w.eid = eid; w.epoch = 0; return; }
}
void dropWant(uint64_t eid) { for (auto& w : wants) if (w.used && w.eid == eid) w.used = false; }

// ---- transmit scheduling: build the next message for this contact epoch ----
size_t buildNext(uint8_t* buf, bool* sensorBytes) {
  *sensorBytes = false;
  W w{buf, 0};
  // 1. evidence chunks owed to someone
  for (auto& j : jobs) {
    if (!j.used) continue;
    int e = findEv(j.eid); if (e < 0 || evs[e].have != (1 << EV_NCHUNK) - 1) { j.used = false; continue; }
    header(w, MSG_EVC); w.u8(j.dest); w.u64(j.eid); w.u8(j.next); w.raw(evs[e].data + j.next * EV_CHUNK, EV_CHUNK);
    if (++j.next >= EV_NCHUNK) j.used = false;
    return w.n;
  }
  if (cfg.mode == 'I') {
    // 2. responder asks for evidence of committed records it has not verified
    if (isSink() && ferryHeardNow()) for (auto& r : recs) if (r.used && r.has_commit && !r.ev_ok && r.req_epoch != pepoch) {
      r.req_epoch = pepoch; header(w, MSG_EVREQ); w.u8((uint8_t)cfg.id); w.u64(r.a.event_id); return w.n;
    }
    // 3. ferries relay requests they could not serve
    if (cfg.role == 'X') for (auto& q : wants) if (q.used && q.epoch != pepoch) {
      q.epoch = pepoch; header(w, MSG_EVREQ); w.u8((uint8_t)cfg.id); w.u64(q.eid); return w.n;
    }
    // 4. sensor places replicas of its own evidence on up to R distinct ferries
    if (cfg.role == 'S') for (auto& e : evs) if (e.used && e.own && __builtin_popcountll(e.acked) < cfg.R && e.place_epoch != pepoch) {
      for (int f = 0; f < MAXNODES; f++) if (ferryHeard[f] == pepoch && !(e.acked >> f & 1)) {
        e.place_epoch = pepoch; addJob(e.eid, (uint8_t)f); return buildNext(buf, sensorBytes);
      }
    }
  }
  if (isSink() && phase >= 0) return 0;   // the responder is a sink outside the all-contact phase
  // 5. records, highest utility first (mode A: arrival order)
  int best = -1; float bu = -1; uint32_t bseq = 0xFFFFFFFF;
  for (int i = 0; i < MAXREC; i++) {
    Rec& r = recs[i]; if (!r.used || r.tx_epoch == pepoch) continue;
    if (cfg.mode == 'A') { if (r.seq < bseq) { bseq = r.seq; best = i; } }
    else { float u = utility(r.a); if (u > bu) { bu = u; best = i; } }
  }
  bool sketchFirst = modeHasSketch() && (best < 0 || bu < 0.2f);   // CPMM: bounded state before low-utility records
  if (best >= 0 && !sketchFirst) {
    recs[best].tx_epoch = pepoch; uint8_t t = recs[best].a.type;
    *sensorBytes = t == WATER_LEVEL || t == SMOKE_DENSITY || t == COLLAPSE_RISK;
    return encodeRec(buf, recs[best]);
  }
  // 6. bounded aggregate state: non-zero HLL registers as (index, rank) pairs, plus sensor LWW state
  if (modeHasSketch()) {
    for (int k = 0; k < N_KIND; k++) for (int v = 0; v <= cfg.V; v++) {
      HllTx& tx = hllTx[k][v]; if (tx.epoch == pepoch) continue;
      int i = tx.cursor, n = 0; uint8_t pairs[2 * HLL_PAIRS];
      for (; i < HLL::M && n < HLL_PAIRS; i++) if (hll[k][v].reg[i]) { pairs[2 * n] = (uint8_t)i; pairs[2 * n + 1] = hll[k][v].reg[i]; n++; }
      if (i >= HLL::M) { tx.epoch = pepoch; tx.cursor = 0; } else tx.cursor = i;
      if (!n) continue;
      header(w, MSG_HLL); w.u8((uint8_t)k); w.u8((uint8_t)v); w.u8((uint8_t)n); w.raw(pairs, 2 * n);
      *sensorBytes = k == K_SMOKE; return w.n;
    }
    for (int v = 0; v <= cfg.V; v++) for (int t = 0; t < 3; t++) if (sens[v][t].set && sens[v][t].tx_epoch != pepoch) {
      Sens& s = sens[v][t]; s.tx_epoch = pepoch; header(w, MSG_SENS); w.u8((uint8_t)v); w.u8((uint8_t)t); w.u32(s.ts); w.u8(s.bucket); w.u16((uint16_t)s.val);
      *sensorBytes = true; return w.n;
    }
  }
  if (best >= 0) {
    recs[best].tx_epoch = pepoch; uint8_t t = recs[best].a.type;
    *sensorBytes = t == WATER_LEVEL || t == SMOKE_DENSITY || t == COLLAPSE_RISK;
    return encodeRec(buf, recs[best]);
  }
  if (cfg.role == 'X' && beaconEpoch != pepoch) { beaconEpoch = pepoch; header(w, MSG_BEACON); return w.n; }   // lets peers see the ferry
  return 0;
}

void mergeSens(int v, int t, uint32_t ts, uint8_t b, int16_t val) {
  if (v < 0 || v > cfg.V || t < 0 || t > 2) return;
  Sens& s = sens[v][t];
  if (!s.set || ts > s.ts || (ts == s.ts && b > s.bucket)) { s.set = true; s.ts = ts; s.bucket = b; s.val = val; s.tx_epoch = 0; }
}

void handleRx(const uint8_t* buf, size_t len) {
  Rd r{buf, len, 0};
  if (len < HDR || buf[0] != MAGIC || buf[1] != VER) return;
  uint8_t type = buf[2], trial = buf[3], src = buf[4]; char srole = (char)buf[5]; int sgrp = buf[6]; r.i = HDR;
  if (cfg.id < 0 || trial != (uint8_t)cfg.trial || src == cfg.id) return;
  if (!inContact(srole, sgrp)) return;                      // software contact plan
  st.rx_b += len; st.rx_p++;
  if (srole == 'X' && src < MAXNODES) ferryHeard[src] = pepoch;
  if (type == MSG_REC) {
    bool accept = phase < 0 || isSink() || (cfg.role == 'X' && srole != 'R');
    AEIO a{}; a.event_id = r.u64(); a.type = (EventType)r.u8(); a.fidelity = r.u8(); a.fields = r.u16(); a.observed_at = r.u32();
    a.bucket = r.u8(); a.urgency = r.u8(); uint8_t cl = r.u8(); if (cl > 11) return; r.raw(a.geo_cell, cl); a.geo_cell[cl] = 0;
    uint8_t flags = r.u8();
    if (a.fields & F_LATLON) { a.lat_e5 = (int32_t)r.u32(); a.lon_e5 = (int32_t)r.u32(); }
    if (a.fields & (F_MED | F_RULE)) { r.raw(a.label, 8); a.label[8] = 0; }
    if (a.fields & F_SKETCHKEY) a.sketch_key = r.u64();
    if (flags & 1) r.raw(a.commitment, 32);
    if (!r.ok || a.type >= N_TYPES || a.fidelity > 4) return;
    if (isSink() && a.type == WATER_REQUEST) { int v = villageOfCell(a.geo_cell); if (v >= 0) waterRaw[v]++; }
    if (accept) insertRec(a, flags & 1);
  } else if (type == MSG_HLL) {
    uint8_t k = r.u8(), v = r.u8(), n = r.u8(); uint8_t pairs[2 * HLL_PAIRS];
    if (!r.ok || k >= N_KIND || v > cfg.V || n > HLL_PAIRS) return;
    r.raw(pairs, 2 * n); if (!r.ok) return;
    for (int j = 0; j < n; j++) { uint8_t i = pairs[2 * j], rank = pairs[2 * j + 1]; if (rank > hll[k][v].reg[i]) hll[k][v].reg[i] = rank; }   // merge = register max
  } else if (type == MSG_SENS) {
    uint8_t v = r.u8(), t = r.u8(); uint32_t ts = r.u32(); uint8_t b = r.u8(); int16_t val = (int16_t)r.u16();
    if (r.ok) mergeSens(v, t, ts, b, val);
  } else if (type == MSG_EVREQ) {
    uint8_t req = r.u8(); uint64_t eid = r.u64(); if (!r.ok) return;
    int e = findEv(eid);
    if (e >= 0 && evs[e].have == (1 << EV_NCHUNK) - 1) addJob(eid, req);
    else if (cfg.role == 'X') addWant(eid);
  } else if (type == MSG_EVC) {
    uint8_t dest = r.u8(); uint64_t eid = r.u64(); uint8_t idx = r.u8(); uint8_t chunk[EV_CHUNK]; r.raw(chunk, EV_CHUNK);
    if (!r.ok || dest != cfg.id || idx >= EV_NCHUNK) return;
    int e = allocEv(eid); if (e < 0 || evs[e].own) return;
    if (!isSink() && cfg.corrupt_pm && (int)(rnd() % 1000) < cfg.corrupt_pm) chunk[rnd() % EV_CHUNK] ^= 0x5A;   // injected replica fault
    memcpy(evs[e].data + idx * EV_CHUNK, chunk, EV_CHUNK); evs[e].have |= 1 << idx;
    if (evs[e].have != (1 << EV_NCHUNK) - 1) return;
    char h[17]; hex64(eid, h);
    if (isSink()) {
      int k = findRec(eid); uint8_t d[32]; plat_sha256(evs[e].data, EV_BYTES, d);
      bool ok = k >= 0 && recs[k].has_commit && !memcmp(d, recs[k].a.commitment, 32);
      snprintf(out, sizeof out, "@%s %s %u %lu", ok ? "evok" : "evbad", h, src, (unsigned long)nowS()); plat_out(out);
      if (ok && k >= 0) recs[k].ev_ok = true;
      evs[e].used = false;     // a bad copy is discarded and requested again next contact
    } else {
      dropWant(eid); W w{pend, 0};
      snprintf(out, sizeof out, "@evhold %s", h); plat_out(out);
      if (pendLen == 0) { header(w, MSG_EVACK); w.u64(eid); pendLen = w.n; pendSensor = false; }
    }
  } else if (type == MSG_EVACK) {
    uint64_t eid = r.u64(); if (!r.ok) return;
    int e = findEv(eid); if (e >= 0 && evs[e].own && src < MAXNODES) evs[e].acked |= 1ULL << src;
  }
}

// ---- commands from the controller ----
int typeOf(const char* s) { for (int i = 0; i < N_TYPES; i++) if (!strcmp(s, TYPE_NAMES[i])) return i; return -1; }

void resetState() {
  memset(recs, 0, sizeof recs); memset(hll, 0, sizeof hll); memset(hllTx, 0, sizeof hllTx); memset(sens, 0, sizeof sens);
  memset(evs, 0, sizeof evs); memset(jobs, 0, sizeof jobs); memset(wants, 0, sizeof wants); memset(ferryHeard, 0, sizeof ferryHeard);
  memset(ecpDone, 0, sizeof ecpDone); memset(waterRaw, 0, sizeof waterRaw); memset(&st, 0, sizeof st);
  for (auto& s : sring) s = Ring<EV_SAMPLES>();
  memset(sLast, 255, sizeof sLast);
  recSeq = 0; sSeq = 0; phase = 0; pepoch++; pendLen = 0; tokens = 0; dead = false;
}

void cmdCfg(char* args) {
  for (char* tok = strtok(args, " "); tok; tok = strtok(nullptr, " ")) {
    char* eq = strchr(tok, '='); if (!eq) continue; *eq = 0; const char* k = tok; const char* v = eq + 1;
    if (!strcmp(k, "id")) cfg.id = atoi(v); else if (!strcmp(k, "role")) cfg.role = v[0]; else if (!strcmp(k, "grp")) cfg.grp = atoi(v);
    else if (!strcmp(k, "mode")) cfg.mode = v[0]; else if (!strcmp(k, "trial")) cfg.trial = atoi(v); else if (!strcmp(k, "cap")) cfg.cap = atoi(v);
    else if (!strcmp(k, "rcap")) cfg.rcap = atoi(v); else if (!strcmp(k, "bud")) cfg.bud = atoi(v); else if (!strcmp(k, "V")) cfg.V = atoi(v);
    else if (!strcmp(k, "nf")) cfg.nf = atoi(v); else if (!strcmp(k, "R")) cfg.R = atoi(v); else if (!strcmp(k, "ecpw")) cfg.ecpw = atoi(v);
    else if (!strcmp(k, "ecps")) cfg.ecps = atoi(v); else if (!strcmp(k, "corrupt")) cfg.corrupt_pm = atoi(v); else if (!strcmp(k, "tau")) cfg.tau = atoi(v);
  }
  if (cfg.V > MAXV) cfg.V = MAXV;
  if (cfg.id >= MAXNODES) cfg.id = MAXNODES - 1;
  rng = 0x9E3779B97F4A7C15ULL ^ ((uint64_t)cfg.id << 32) ^ (uint64_t)cfg.trial;
  for (int v = 0; v <= cfg.V; v++) { int32_t la, lo; villageCenter(v, &la, &lo); cellOf(la, lo, villageCell[v]); }
  snprintf(out, sizeof out, "@cfg id=%d role=%c grp=%d mode=%c trial=%d cap=%d bud=%d R=%d", cfg.id, cfg.role, cfg.grp, cfg.mode, cfg.trial, cfg.cap, cfg.bud, cfg.R);
  plat_out(out);
}

void cmdReport(int type, const char* key, int urg) {      // human report at a field node
  AEIO a{}; a.event_id = hashStr(key); a.type = (EventType)type; a.observed_at = nowS(); a.urgency = (uint8_t)urg;
  villageCenter(cfg.grp, &a.lat_e5, &a.lon_e5); strcpy(a.geo_cell, villageCell[cfg.grp]);
  a.fields = F_LATLON | F_FRESH | F_CELL | F_SKETCHKEY; a.sketch_key = a.event_id;
  if (type == TRAPPED_PERSON) a.fields |= F_TRAPPED;
  if (type == MEDICATION_NEED) { a.fields |= F_MED | F_URGENCY; strcpy(a.label, "INSULIN"); }
  if (modeHasSketch() && (type == WATER_REQUEST || type == SAFE_STATUS)) {   // CPMM: bounded aggregate state
    hll[type == WATER_REQUEST ? K_WATER : K_SAFE][cfg.grp].add(a.sketch_key);
    return;
  }
  insertRec(a, false);
}

void cmdSensor(int type, int valx100) {                   // one sensor sample/publication
  int t = type == WATER_LEVEL ? 0 : type == SMOKE_DENSITY ? 1 : type == COLLAPSE_RISK ? 2 : -1; if (t < 0) return;
  float v = valx100 / 100.0f; sring[t].push(v);
  uint8_t b = t == 0 ? waterBucket(v) : t == 1 ? smokeBucket(v) : riskState(v);
  bool trig = (t == 0 && sLast[0] != 255 && b > sLast[0]) || (t == 1 && sLast[1] != 255 && b > sLast[1] && b >= 2) ||
              (t == 2 && b == RISK_HIGH && sLast[2] != RISK_HIGH);
  bool changed = b != sLast[t]; sLast[t] = b;
  uint32_t ts = nowS();
  char skey[24]; snprintf(skey, sizeof skey, "smk:%d", cfg.id);
  if (t == 1 && b >= 2 && modeHasSketch()) { hll[K_SMOKE][cfg.grp].add(hashStr(skey)); }
  if (modeHasSketch()) mergeSens(cfg.grp, t, ts, b, (int16_t)(valx100 > 32767 ? 32767 : valx100));
  if (modeHasSketch() && !changed && !trig) return;    // sensor state already carries it; only bucket changes become records
  AEIO a{}; char key[40]; snprintf(key, sizeof key, "S%d:%d:%lu", cfg.id, t, (unsigned long)++sSeq);
  a.event_id = hashStr(key); a.type = (EventType)type; a.observed_at = ts; a.bucket = b;
  villageCenter(cfg.grp, &a.lat_e5, &a.lon_e5); strcpy(a.geo_cell, villageCell[cfg.grp]);
  a.fields = F_CELL | F_FRESH | F_SKETCHKEY | (t == 0 ? F_LEVELB : t == 1 ? F_SMOKEB : F_RISK); a.sketch_key = hashStr(skey);
  bool commit = false;
  if (trig) {
    int16_t frozen[EV_SAMPLES] = {0}; sring[t].freeze(frozen);
    plat_sha256(frozen, EV_BYTES, a.commitment); a.evidence_len = EV_BYTES; commit = true;
    int e = allocEv(a.event_id);
    if (e >= 0) { evs[e].own = true; memcpy(evs[e].data, frozen, EV_BYTES); evs[e].have = (1 << EV_NCHUNK) - 1; }
    char h[17]; hex64(a.event_id, h); snprintf(out, sizeof out, "@trig %s %s %u", h, TYPE_NAMES[type], b); plat_out(out);
  }
  insertRec(a, commit);
}

void cmdDump() {
  // order-independent digest of the replicated state (records + sketches + sensor state)
  static uint64_t ids[MAXREC]; static uint8_t fid[MAXREC]; int n = 0;
  for (auto& r : recs) if (r.used) { ids[n] = r.a.event_id; fid[n] = r.a.fidelity; n++; }
  for (int i = 1; i < n; i++) for (int j = i; j > 0 && ids[j] < ids[j - 1]; j--) { uint64_t t = ids[j]; ids[j] = ids[j - 1]; ids[j - 1] = t; uint8_t f = fid[j]; fid[j] = fid[j - 1]; fid[j - 1] = f; }
  uint64_t h = 1469598103934665603ULL;
  auto mix = [&](const void* d, size_t k) { const uint8_t* p = (const uint8_t*)d; for (size_t i = 0; i < k; i++) { h ^= p[i]; h *= 1099511628211ULL; } };
  for (int i = 0; i < n; i++) { mix(&ids[i], 8); mix(&fid[i], 1); }
  for (int k = 0; k < N_KIND; k++) for (int v = 0; v <= cfg.V; v++) mix(hll[k][v].reg, HLL::M);
  for (int v = 0; v <= cfg.V; v++) for (int t = 0; t < 3; t++) { mix(&sens[v][t].ts, 4); mix(&sens[v][t].bucket, 1); }
  char hx[17]; hex64(h, hx);
  snprintf(out, sizeof out, "@dg %s n=%d", hx, n); plat_out(out);
  if (isSink()) for (int v = 1; v <= cfg.V; v++) {
    int exact = 0; for (auto& r : recs) if (r.used && r.a.type == WATER_REQUEST && villageOfCell(r.a.geo_cell) == v) exact++;
    snprintf(out, sizeof out, "@agg %d raw=%lu exact=%d hll_x10=%ld safe_hll_x10=%ld", v, (unsigned long)waterRaw[v], exact,
             lround(hll[K_WATER][v].estimate() * 10), lround(hll[K_SAFE][v].estimate() * 10));
    plat_out(out);
  }
}

void cmdStats() {
  snprintf(out, sizeof out, "@st tx_b=%lu tx_p=%lu rx_b=%lu rx_p=%lu txs_b=%lu n=%d store_b=%lu peak_b=%lu red=%lu rej=%lu evict=%lu drop=%lu pdrop=%lu loss=%lu",
           (unsigned long)st.tx_b, (unsigned long)st.tx_p, (unsigned long)st.rx_b, (unsigned long)st.rx_p, (unsigned long)st.tx_sensor_b, storeCount(),
           (unsigned long)storeBytes(), (unsigned long)st.peak_b, (unsigned long)st.red, (unsigned long)st.rej, (unsigned long)st.evict,
           (unsigned long)st.drop, (unsigned long)st.pdrop, (unsigned long)st.loss);
  plat_out(out);
}

// E1 on the device: the firmware SPL check against random forbidden mutations (as test_sage_core.cpp),
// plus the measured cost of one permit() call on this CPU.
void cmdSelftest(long iters) {
  AEIO t{}; t.type = TRAPPED_PERSON; t.fidelity = 0; t.fields = F_TRAPPED | F_LATLON | F_FRESH | F_CELL;
  t.lat_e5 = 2611234; t.lon_e5 = 9171234; t.observed_at = 1234; cellOf(t.lat_e5, t.lon_e5, t.geo_cell);
  uint64_t save = rng; rng = 7;
  long forb = 0, committed = 0, legal = 0, legalOk = 0; uint32_t us = 0;
  for (long i = 0; i < iters; i++) {
    AEIO m = reduce(t, (uint8_t)(rnd() % 5)); int k = rnd() % 4;
    if (k == 0) m.lat_e5 += 100; else if (k == 1) m.observed_at += 3600; else if (k == 2) m.fields &= ~F_TRAPPED; else m.fidelity = 0;
    bool ok = m.fidelity <= 1 && m.fidelity >= t.fidelity && (m.fields & (F_TRAPPED | F_LATLON | F_FRESH)) == (F_TRAPPED | F_LATLON | F_FRESH) &&
              m.lat_e5 / 10 == t.lat_e5 / 10 && m.lon_e5 / 10 == t.lon_e5 / 10 && m.observed_at / 300 == t.observed_at / 300;
    uint32_t t0 = plat_us(); bool p = permit(t, m); us += plat_us() - t0;
    if (ok) { legal++; legalOk += p; } else { forb++; committed += p; }
  }
  bool rej; AEIO c = splTransition(t, proposeFidelity(0.0f, 1.0f), &rej);
  rng = save;
  snprintf(out, sizeof out, "@e1 iters=%ld forbidden=%ld committed_forbidden=%ld legal=%ld committed_legal=%ld permit_ns=%lu clamp_fid=%u",
           iters, forb, committed, legal, legalOk, (unsigned long)(iters ? (uint64_t)us * 1000 / (uint64_t)iters : 0), c.fidelity);
  plat_out(out);
}

}  // namespace

extern "C" void app_init(void) {
  resetState();
  plat_out("@boot sage-node v1 SPL-1.0.0");
}

extern "C" void app_cmd(const char* line) {
  char buf[160]; strncpy(buf, line, sizeof buf - 1); buf[sizeof buf - 1] = 0;
  size_t L = strlen(buf); while (L && (buf[L - 1] == '\r' || buf[L - 1] == '\n' || buf[L - 1] == ' ')) buf[--L] = 0;
  char* sp = strchr(buf, ' '); char* args = sp ? sp + 1 : buf + L; if (sp) *sp = 0;
  const char* c = buf;
  if (dead && strcmp(c, "reset") && strcmp(c, "ping")) return;
  if (!strcmp(c, "cfg")) cmdCfg(args);
  else if (!strcmp(c, "die")) { resetState(); dead = true; plat_out("@dead"); }
  else if (!strcmp(c, "reset")) { resetState(); plat_out("@reset"); }
  else if (!strcmp(c, "ph")) {
    int p = 0; long t = 0; sscanf(args, "%d %ld", &p, &t); phase = p; tAtPh = (uint32_t)t; msAtPh = plat_ms(); pepoch++;
  }
  else if (!strcmp(c, "r")) { char ty[24], key[48]; int u = 1; if (sscanf(args, "%23s %47s %d", ty, key, &u) >= 2 && typeOf(ty) >= 0) cmdReport(typeOf(ty), key, u); }
  else if (!strcmp(c, "s")) { char ty[24]; int v = 0; if (sscanf(args, "%23s %d", ty, &v) == 2 && typeOf(ty) >= 0) cmdSensor(typeOf(ty), v); }
  else if (!strcmp(c, "st")) cmdStats();
  else if (!strcmp(c, "dump")) cmdDump();
  else if (!strcmp(c, "selftest")) cmdSelftest(*args ? atol(args) : 20000);
  else if (!strcmp(c, "ping")) { snprintf(out, sizeof out, "@pong id=%d role=%c", cfg.id, cfg.role); plat_out(out); }
}

extern "C" void app_rx(const uint8_t* buf, size_t len) { if (!dead) handleRx(buf, len); }

extern "C" void app_tick(void) {
  uint32_t now = plat_ms();
  uint32_t dt = now - lastTickMs; lastTickMs = now; if (dt > 1000) dt = 1000;
  if (cfg.id < 0 || dead) return;
  if (now - lastSlowMs >= 1000) { lastSlowMs = now; reductionPass(); ecpPass(); }
  tokens += cfg.bud * dt / 1000.0f; float maxTok = cfg.bud * 2.0f < 256 ? 256 : cfg.bud * 2.0f; if (tokens > maxTok) tokens = maxTok;
  bool active = ferryAtMyLoc();
  if (!active) return;
  if (pendLen == 0) pendLen = buildNext(pend, &pendSensor);
  if (pendLen && tokens >= pendLen) {
    plat_send(pend, pendLen); tokens -= pendLen; st.tx_b += pendLen; st.tx_p++; if (pendSensor) st.tx_sensor_b += pendLen; pendLen = 0;
  }
}
