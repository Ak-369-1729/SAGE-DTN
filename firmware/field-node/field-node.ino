// SAGE-DTN FIELD NODE (ESP32): SOS / report input, local AEIO store under SPL,
// utility/pressure-driven fidelity, communication adapter, battery state.
#include <Arduino.h>
#include "sage_core.h"
#include "radio_adapter.h"
using namespace sage;

const int PIN_SOS = 4, PIN_WATER_BTN = 16, PIN_SAFE_BTN = 17, PIN_LED_OK = 2, PIN_LED_SOS = 15, PIN_VBAT = 36;
const char* NODE_ID = "F0_0";
const int32_t LAT_E5 = 2611010, LON_E5 = 9171020;
const int CAP = 64;                       // local protected store (individually addressable)
AEIO store[CAP]; int nStore = 0;
HLL waterSketch, safeSketch;              // bounded aggregate state for aggregatable reports
uint32_t seq = 0, rejectedSPL = 0;

float batteryFrac() { float v = analogRead(PIN_VBAT) * (3.3f / 4095.0f) * 2.0f; return constrain((v - 3.3f) / (4.2f - 3.3f), 0.0f, 1.0f); }
float pressure() {   // subset of utility/engine.py pressure: storage + energy
  float s = (float)nStore / CAP, e = 1.0f - batteryFrac();
  float p = 0.2f * s + 0.15f * e; return max(p, s);
}

void publish(const AEIO& a, const char* note) {
  char line[320];
  snprintf(line, sizeof line, "{\"schema\":\"sage.aeio.v1\",\"event_id\":\"%016llx\",\"event_type\":\"%s\","
           "\"source_class\":\"SURVIVOR\",\"fidelity_level\":%u,\"geo_cell\":\"%s\",\"lat\":%.5f,\"lon\":%.5f,"
           "\"observed_at\":%lu,\"origin_node\":\"%s\",\"pressure\":%.2f,\"spl_rejected\":%lu,\"note\":\"%s\","
           "\"policy_version\":\"%s\"}", (unsigned long long)a.event_id, TYPE_NAMES[a.type], a.fidelity, a.geo_cell,
           a.lat_e5 / 1e5, a.lon_e5 / 1e5, (unsigned long)a.observed_at, NODE_ID, pressure(), (unsigned long)rejectedSPL,
           note, POLICY_VERSION);
  Serial.println(line); radioSend(line);
}

void report(EventType t) {
  AEIO a{}; char key[40]; snprintf(key, sizeof key, "%s:%u:%lu", NODE_ID, t, (unsigned long)++seq);
  a.event_id = hashStr(key); a.type = t; a.observed_at = millis() / 1000; a.lat_e5 = LAT_E5; a.lon_e5 = LON_E5;
  cellOf(LAT_E5, LON_E5, a.geo_cell);
  a.fields = F_LATLON | F_FRESH | F_CELL | F_SKETCHKEY; a.sketch_key = a.event_id;
  if (t == TRAPPED_PERSON) a.fields |= F_TRAPPED;
  float U = t == TRAPPED_PERSON ? 0.7f : 0.03f;              // utility from criticality (simplified)
  bool rej = false;
  AEIO r = splTransition(a, proposeFidelity(U, pressure()), &rej);   // UTILITY PROPOSES, SPL DISPOSES
  rejectedSPL += rej;
  if (t == WATER_REQUEST && r.fidelity >= 3) { waterSketch.add(r.sketch_key); publish(r, "aggregated"); return; }
  if (t == SAFE_STATUS && r.fidelity >= 3) { safeSketch.add(r.sketch_key); publish(r, "aggregated"); return; }
  if (nStore < CAP) store[nStore++] = r;                      // protected records are never evicted
  publish(r, "protected");
  digitalWrite(PIN_LED_SOS, t == TRAPPED_PERSON);
}

void onPeer(const char* line) { Serial.print("{\"rx\":"); Serial.print(line); Serial.println("}"); }

void setup() {
  Serial.begin(115200);
  pinMode(PIN_SOS, INPUT_PULLUP); pinMode(PIN_WATER_BTN, INPUT_PULLUP); pinMode(PIN_SAFE_BTN, INPUT_PULLUP);
  pinMode(PIN_LED_OK, OUTPUT); pinMode(PIN_LED_SOS, OUTPUT);
  radioBegin(NODE_ID); radioOnReceive(onPeer);
  digitalWrite(PIN_LED_OK, HIGH);
}

void loop() {
  static uint32_t last = 0;
  if (millis() - last > 250) {          // simple debounce
    if (!digitalRead(PIN_SOS)) { report(TRAPPED_PERSON); last = millis(); }
    else if (!digitalRead(PIN_WATER_BTN)) { report(WATER_REQUEST); last = millis(); }
    else if (!digitalRead(PIN_SAFE_BTN)) { report(SAFE_STATUS); last = millis(); }
  }
  static uint32_t lastHb = 0;
  if (millis() - lastHb > 30000) {
    lastHb = millis();
    Serial.printf("{\"schema\":\"sage.status.v1\",\"node\":\"%s\",\"battery\":%.2f,\"protected\":%d,\"water_est\":%.1f,\"safe_est\":%.1f}\n",
                  NODE_ID, batteryFrac(), nStore, waterSketch.estimate(), safeSketch.estimate());
  }
  radioPoll();
}
