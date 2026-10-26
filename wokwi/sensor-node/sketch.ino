// SAGE-DTN SENSOR NODE (ESP32, Arduino core)
// Acquires flood / smoke / vibration, keeps a raw ring buffer, emits sensor AEIOs
// as JSON lines on Serial (and over the radio adapter when one is fitted).
// Event-triggered evidence: on bucket rise / HIGH collapse risk the ring buffer is
// frozen, committed with SHA-256 and kept for transfer to a higher-capacity node.
#include <Arduino.h>
#include "mbedtls/sha256.h"
#include "sage_core.h"
#include "radio_adapter.h"

using namespace sage;

// ---- pin map (see firmware/PINMAP.md) ----
const int PIN_WATER = 34;    // ADC1_CH6: ultrasonic/pressure level sensor (0-3.3 V -> 0-250 cm)
const int PIN_SMOKE = 35;    // ADC1_CH7: MQ-2 analog out via divider
const int PIN_LED   = 2;
// MPU-6050 on I2C SDA=21 SCL=22 (optional; analog fallback on PIN_VIB)
const int PIN_VIB   = 32;    // ADC1_CH4: vibration (piezo/accelerometer analog) fallback

const float SAMPLE_HZ = 10.0f;
uint32_t publishPeriodMs = 60000;     // adapted by INCREASE_SENSOR_AGGREGATION commands
const char* NODE_ID = "S0_0";
const int32_t LAT_E5 = 2611000, LON_E5 = 9171000;

Ring<300> ringWater, ringSmoke, ringVib;    // 30 s @ 10 Hz each
uint8_t lastWB = 255, lastSB = 255, lastRisk = 255;
uint32_t seq = 0, lastPublish = 0, lastSample = 0;
float energyUsedJ = 0;                       // battery/resource budget proxy
const float ENERGY_BUDGET_J = 5000, E_SAMPLE = 2e-4f, E_PUBLISH = 0.05f;

float readWaterCm() { return analogRead(PIN_WATER) * (250.0f / 4095.0f); }
float readSmokePpm() { return analogRead(PIN_SMOKE) * (1000.0f / 4095.0f); }
float readVibG() { return (analogRead(PIN_VIB) - 2048) * (1.0f / 2048.0f); }

void commit(const int16_t* buf, int n, uint8_t* out) {
  mbedtls_sha256((const unsigned char*)buf, n * sizeof(int16_t), out, 0);
}

void emit(const char* type, float value, uint8_t bucket, bool trig, Ring<300>& ring) {
  AEIO a{};
  char key[48]; snprintf(key, sizeof key, "%s:%s:%lu", NODE_ID, type, (unsigned long)++seq);
  a.event_id = hashStr(key); a.observed_at = millis() / 1000; a.lat_e5 = LAT_E5; a.lon_e5 = LON_E5;
  cellOf(LAT_E5, LON_E5, a.geo_cell); a.bucket = bucket;
  static int16_t frozen[300]; int n = 0;
  if (trig) { n = ring.freeze(frozen); commit(frozen, n, a.commitment); a.evidence_len = n * 2; }
  char hex[65] = {0}; for (int i = 0; i < 32 && trig; i++) sprintf(hex + 2 * i, "%02x", a.commitment[i]);
  char line[512];
  snprintf(line, sizeof line,
    "{\"schema\":\"sage.aeio.v1\",\"event_id\":\"%016llx\",\"event_type\":\"%s\",\"source_class\":\"%s\","
    "\"fidelity_level\":0,\"geo_cell\":\"%s\",\"lat\":%.5f,\"lon\":%.5f,\"observed_at\":%lu,\"value\":%.2f,"
    "\"bucket\":%u,\"observation_key\":\"%s\",\"origin_node\":\"%s\",\"triggered\":%s,\"evidence_len\":%lu,"
    "\"integrity_commitment\":\"%s\",\"policy_version\":\"%s\"}",
    (unsigned long long)a.event_id, type, strcmp(type, "COLLAPSE_RISK") ? "ENV_SENSOR" : "STRUCT_SENSOR",
    a.geo_cell, LAT_E5 / 1e5, LON_E5 / 1e5, (unsigned long)a.observed_at, value, bucket, key, NODE_ID,
    trig ? "true" : "false", (unsigned long)a.evidence_len, hex, POLICY_VERSION);
  Serial.println(line);
  radioSend(line);
  energyUsedJ += E_PUBLISH;
  if (trig) digitalWrite(PIN_LED, HIGH);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  analogReadResolution(12);
  radioBegin(NODE_ID);
  Serial.println("{\"schema\":\"sage.boot.v1\",\"role\":\"SENSOR\",\"node\":\"S0_0\"}");
}

void loop() {
  if (energyUsedJ >= ENERGY_BUDGET_J) { delay(1000); return; }           // budget exhausted: sensor failed
  uint32_t now = millis();
  if (now - lastSample >= (uint32_t)(1000 / SAMPLE_HZ)) {
    lastSample = now;
    ringWater.push(readWaterCm()); ringSmoke.push(readSmokePpm()); ringVib.push(readVibG());
    energyUsedJ += 3 * E_SAMPLE;
  }
  // adaptation command from a peer/utility node: "AGG <multiplier>"
  if (Serial.available()) { String c = Serial.readStringUntil('\n'); if (c.startsWith("AGG ")) publishPeriodMs = 60000UL * c.substring(4).toInt(); }
  float w = readWaterCm(), s = readSmokePpm(), v = readVibG();
  uint8_t wb = waterBucket(w), sb = smokeBucket(s), rk = riskState(v);
  bool due = now - lastPublish >= publishPeriodMs;
  // threshold-adjacent changes are always published immediately (sensor-rate adaptation never hides them)
  if (due || wb != lastWB) { emit("WATER_LEVEL", w, wb, lastWB != 255 && wb > lastWB, ringWater); lastWB = wb; }
  if (due || sb != lastSB) { emit("SMOKE_DENSITY", s, sb, lastSB != 255 && sb > lastSB && sb >= 2, ringSmoke); lastSB = sb; }
  if (due || rk != lastRisk) { emit("COLLAPSE_RISK", v, rk, rk == RISK_HIGH && lastRisk != RISK_HIGH, ringVib); lastRisk = rk; }
  if (due) lastPublish = now;
  radioPoll();
}
