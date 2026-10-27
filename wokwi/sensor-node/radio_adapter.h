// Communication adapter. Default: Serial JSON lines (works on bare ESP32 and in Wokwi).
// Define SAGE_RADIO_ESPNOW to use ESP-NOW broadcast between physical ESP32 nodes,
// or SAGE_RADIO_LORA (SX127x via the 'LoRa' library) for long-range contacts.
#pragma once
#include <Arduino.h>
#if defined(SAGE_RADIO_ESPNOW)
#include <WiFi.h>
#include <esp_now.h>
static uint8_t BCAST[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
typedef void (*RxHandler)(const char* line);
static RxHandler g_rx = nullptr;
static void onRecv(const esp_now_recv_info_t*, const uint8_t* data, int len) {
  static char buf[251]; int n = len < 250 ? len : 250; memcpy(buf, data, n); buf[n] = 0; if (g_rx) g_rx(buf);
}
inline void radioBegin(const char*) {
  WiFi.mode(WIFI_STA); esp_now_init(); esp_now_peer_info_t p{}; memcpy(p.peer_addr, BCAST, 6); esp_now_add_peer(&p);
  esp_now_register_recv_cb(onRecv);
}
inline void radioOnReceive(RxHandler h) { g_rx = h; }
inline void radioSend(const char* line) {  // ESP-NOW payload limit 250 B: send in chunks prefixed by sequence
  size_t n = strlen(line); for (size_t off = 0; off < n; off += 240) esp_now_send(BCAST, (const uint8_t*)line + off, min((size_t)240, n - off));
}
inline void radioPoll() {}
#elif defined(SAGE_RADIO_LORA)
#include <LoRa.h>
typedef void (*RxHandler)(const char* line);
static RxHandler g_rx = nullptr;
inline void radioBegin(const char*) { LoRa.setPins(5, 14, 26); LoRa.begin(865E6); }  // IN865 band; check local regulations
inline void radioOnReceive(RxHandler h) { g_rx = h; }
inline void radioSend(const char* line) { LoRa.beginPacket(); LoRa.print(line); LoRa.endPacket(); }
inline void radioPoll() {
  int sz = LoRa.parsePacket(); if (!sz) return; static char buf[256]; int n = 0;
  while (LoRa.available() && n < 255) buf[n++] = (char)LoRa.read(); buf[n] = 0; if (g_rx) g_rx(buf);
}
#else
typedef void (*RxHandler)(const char* line);
static RxHandler g_rx = nullptr;
inline void radioBegin(const char*) {}
inline void radioOnReceive(RxHandler h) { g_rx = h; }
inline void radioSend(const char*) {}          // Serial already carries the line
inline void radioPoll() {
  static String acc;
  while (Serial.available()) { char c = (char)Serial.read(); if (c == '\n') { if (g_rx && acc.startsWith("{")) g_rx(acc.c_str()); acc = ""; } else acc += c; }
}
#endif
