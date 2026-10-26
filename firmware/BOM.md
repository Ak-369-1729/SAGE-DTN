# Bill of materials (reference prototype, per node role)

Part numbers are examples; the invention is independent of any particular board or sensor. Prices are
deliberately omitted (not verified).

| Role | Qty | Part | Purpose |
|---|---|---|---|
| all | 1 | ESP32 DevKitC (ESP32-WROOM-32) | MCU, Wi-Fi/BLE/ESP-NOW |
| all | 1 | 18650 Li-ion cell + holder, TP4056 charger w/ protection | battery |
| all | 1 | 5 V/1 A solar panel (optional) | recharge |
| all | 1 | 100 k + 100 k resistor divider | battery voltage sense (GPIO36) |
| all (optional) | 1 | SX1276/RFM95W LoRa module, 865–867 MHz (India) + antenna | long-range contacts |
| all (optional) | 1 | microSD breakout (SPI) | evidence store / larger buffers |
| field | 3 | 12 mm momentary push buttons | SOS / water / safe |
| field | 2 | LEDs (green, red) + 220 Ω | status / SOS ack |
| sensor | 1 | water-level probe: JSN-SR04T ultrasonic or 0–5 m pressure transducer (via divider to 3.3 V) | WATER_LEVEL |
| sensor | 1 | MQ-2 gas/smoke module (analog out via 2:3 divider) | SMOKE_DENSITY |
| sensor | 1 | MPU-6050 accelerometer (I2C) or analog vibration sensor | COLLAPSE_RISK |
| sensor | 1 | LED + 220 Ω | evidence-trigger indicator |
| responder | 1 | SSD1306 128×64 I2C OLED | protected/aggregate display |
| responder | 1 | push button | evidence-recovery request |
| optional | 1 | GPS/NavIC module (e.g. u-blox NEO-M8N; NavIC-capable module where available) | location |
