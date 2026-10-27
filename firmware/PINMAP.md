# Pin map and wiring table

| Node | Signal | ESP32 pin | Notes |
|---|---|---|---|
| all | Battery sense | GPIO36 (ADC1_CH0) | 100k/100k divider from cell + |
| all | LoRa SCK/MISO/MOSI | GPIO18/19/23 | when `SAGE_RADIO_LORA` |
| all | LoRa NSS/RST/DIO0 | GPIO5/14/26 | `LoRa.setPins(5,14,26)` |
| field | SOS button | GPIO4 | INPUT_PULLUP, to GND |
| field | Water-request button | GPIO16 | INPUT_PULLUP |
| field | Safe-status button | GPIO17 | INPUT_PULLUP |
| field | OK LED / SOS LED | GPIO2 / GPIO15 | 220 Ω to GND |
| sensor | Water level (analog) | GPIO34 (ADC1_CH6) | 0–3.3 V ⇒ 0–250 cm |
| sensor | Smoke MQ-2 AO | GPIO35 (ADC1_CH7) | MQ-2 is 5 V: use divider to ≤3.3 V |
| sensor | Vibration (analog fallback) | GPIO32 (ADC1_CH4) | centred at 1.65 V |
| sensor | MPU-6050 SDA/SCL | GPIO21/22 | optional I2C accelerometer |
| sensor | Trigger LED | GPIO2 | 220 Ω |
| responder | OLED SDA/SCL | GPIO21/22 | I2C addr 0x3C |
| responder | Recovery-request button | GPIO4 | INPUT_PULLUP |

ADC2 pins are avoided because ADC2 is unavailable while Wi-Fi is active on the ESP32.
