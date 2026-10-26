// SAGE-DTN RESPONDER NODE (ESP32 + SSD1306 OLED): ingests AEIO lines from peers,
// deterministically merges protected records (max (ts, fidelity)) and aggregate
// sketches (register max), displays protected events and aggregate estimates,
// and issues evidence-recovery requests for reduced records with commitments.
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "sage_core.h"
#include "radio_adapter.h"
using namespace sage;

Adafruit_SSD1306 oled(128, 64, &Wire, -1);
const int PIN_REQ_BTN = 4;
struct Entry { uint64_t id; char type[24]; char cell[12]; uint32_t ts; uint8_t fid; bool hasCommit; bool recovered; };
const int CAP = 128; Entry prot[CAP]; int nProt = 0;
HLL water, safe;

// tiny field extractor for flat JSON lines produced by SAGE nodes
bool field(const char* line, const char* key, char* out, int n) {
  char pat[32]; snprintf(pat, sizeof pat, "\"%s\":", key); const char* p = strstr(line, pat); if (!p) return false;
  p += strlen(pat); bool q = *p == '"'; if (q) p++; int i = 0;
  while (*p && i < n - 1 && (q ? *p != '"' : (*p != ',' && *p != '}'))) out[i++] = *p++; out[i] = 0; return true;
}

void ingest(const char* line) {
  char id[20], type[24], cell[12], ts[16], fid[4], note[16], commit[66] = "";
  if (!field(line, "event_id", id, sizeof id) || !field(line, "event_type", type, sizeof type)) return;
  field(line, "geo_cell", cell, sizeof cell); field(line, "observed_at", ts, sizeof ts); field(line, "fidelity_level", fid, sizeof fid);
  field(line, "integrity_commitment", commit, sizeof commit);
  uint64_t eid = strtoull(id, nullptr, 16);
  if (field(line, "note", note, sizeof note) && !strcmp(note, "aggregated")) {   // aggregate contribution
    if (!strcmp(type, "WATER_REQUEST")) water.add(eid); else if (!strcmp(type, "SAFE_STATUS")) safe.add(eid);
    return;
  }
  for (int i = 0; i < nProt; i++) if (prot[i].id == eid) {                       // deterministic merge
    uint32_t t = atol(ts); uint8_t f = atoi(fid);
    if (t > prot[i].ts || (t == prot[i].ts && f < prot[i].fid)) { prot[i].ts = t; prot[i].fid = f; }
    return;
  }
  if (nProt < CAP) { Entry& e = prot[nProt++]; e.id = eid; strncpy(e.type, type, 23); strncpy(e.cell, cell, 11);
    e.ts = atol(ts); e.fid = atoi(fid); e.hasCommit = strlen(commit) == 64; e.recovered = false; }
}

void requestEvidence() {
  for (int i = 0; i < nProt; i++) if (prot[i].fid > 0 && prot[i].hasCommit && !prot[i].recovered) {
    char line[160];
    snprintf(line, sizeof line, "{\"schema\":\"sage.recovery_request.v1\",\"event_id\":\"%016llx\",\"requester\":\"R0\",\"role\":\"RESPONDER\",\"token\":\"<capability-token>\"}",
             (unsigned long long)prot[i].id);
    Serial.println(line); radioSend(line);
  }
}

void draw() {
  oled.clearDisplay(); oled.setTextSize(1); oled.setTextColor(SSD1306_WHITE); oled.setCursor(0, 0);
  int trapped = 0, other = 0; for (int i = 0; i < nProt; i++) (strstr(prot[i].type, "TRAPPED") ? trapped : other)++;
  oled.printf("PROTECTED %d\nTRAPPED %d other %d\nWATER~%.0f SAFE~%.0f\n", nProt, trapped, other, water.estimate(), safe.estimate());
  for (int i = max(0, nProt - 3); i < nProt; i++) oled.printf("%.10s %s F%u\n", prot[i].type, prot[i].cell, prot[i].fid);
  oled.display();
}

void setup() {
  Serial.begin(115200); pinMode(PIN_REQ_BTN, INPUT_PULLUP);
  oled.begin(SSD1306_SWITCHCAPVCC, 0x3C); radioBegin("R0"); radioOnReceive(ingest);
}

void loop() {
  radioPoll();
  static uint32_t last = 0; if (millis() - last > 1000) { last = millis(); draw(); }
  if (!digitalRead(PIN_REQ_BTN)) { requestEvidence(); delay(300); }
}
