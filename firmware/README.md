# SAGE-DTN reference firmware (ESP32, Arduino core)

Three node roles share one portable core (`common/sage_core.h`: AEIO struct, SPL-1.0.0 registry and
`permit()`, semantics-unaware reducer, SPL-gated `splTransition()`, bounded HyperLogLog, ring buffer,
sensor bucketing, 500 m geo-cell) and one communication adapter (`common/radio_adapter.h`: Serial JSON
lines by default, `-DSAGE_RADIO_ESPNOW` or `-DSAGE_RADIO_LORA`).

| Folder | Role | Implements |
|---|---|---|
| `field-node/` | Field/survivor node | SOS / water / safe buttons, local protected store, SPL-gated reduction under utility/pressure, HLL aggregates, battery state, adapter |
| `sensor-node/` | Sensor node | flood / smoke / vibration acquisition at 10 Hz, 30 s ring buffers, AEIO generation, bucket-change immediate publish, triggered evidence freeze + SHA-256 commitment, publish-period adaptation command `AGG <k>`, energy budget |
| `responder-node/` | Responder node | ingestion, deterministic merge (max (ts, fidelity)), aggregate sketches, OLED display, evidence-recovery request button |

Each sketch folder contains a copy of the two shared headers so it opens directly in the Arduino IDE.
After editing `common/`, run `scripts/sync_firmware_common.sh`.

## Verification status (honest)
* `common/test_sage_core.cpp` — compiled with g++ and **executed** in the build environment: SPL clamps a
  max-pressure TRAPPED_PERSON reduction to F1, 0 of ~90 000 random forbidden mutations permitted, HLL
  estimate/merge laws, ring buffer, buckets, geo-cell.
* `host_stub/compile_check.sh` — field and sensor sketches **compiled and run on the host** against a stub
  Arduino API (logic/syntax only).
* **Not done here:** ESP32 toolchain build, flashing, radio range tests, power measurement. No Arduino/ESP32
  toolchain or hardware was available. Build with `arduino-cli compile --fqbn esp32:esp32:esp32 <folder>`.

## Build & flash
```bash
arduino-cli core install esp32:esp32
arduino-cli lib install "Adafruit SSD1306" "Adafruit GFX Library" "LoRa"
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/sensor-node
arduino-cli upload  --fqbn esp32:esp32:esp32 -p /dev/ttyUSB0 firmware/sensor-node
# ESP-NOW between boards: add --build-property "build.extra_flags=-DSAGE_RADIO_ESPNOW"
```
See `BOM.md`, `PINMAP.md` (wiring table) and `schemas/` (message schemas).
