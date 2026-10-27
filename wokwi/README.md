# Wokwi sensor-node emulation

What Wokwi is used for here: emulating the **ESP32 sensor-node firmware and its analog sensors**
(potentiometer = water-level probe, `wokwi-gas-sensor` = MQ-2 smoke sensor, second potentiometer =
vibration channel, LED = evidence-trigger indicator). The firmware prints `sage.aeio.v1` JSON lines on
the serial monitor.

What Wokwi is **not** used for: the opportunistic DTN radio/contact behaviour. Multi-node ESP-NOW/LoRa
contacts are not emulated here; they run in the Python simulator. This project does not claim otherwise.

## Run
1. Web: create a new ESP32 Arduino project at https://wokwi.com, replace `sketch.ino` and `diagram.json`
   with the files in this folder and add `sage_core.h` and `radio_adapter.h` as extra files. Press play.
   Turn the potentiometers / gas-sensor slider and watch AEIO lines (bucket changes publish immediately,
   rising buckets freeze the ring buffer and print a SHA-256 commitment).
2. VS Code / CLI: compile with arduino-cli (see `wokwi.toml`) and run `wokwi-cli` in this folder.

## Connect to the simulator
Copy the serial output to a file (or pipe `wokwi-cli` output) and feed it to the bridge:

    python scripts/wokwi_bridge.py --input serial_log.txt

The bridge converts every line into an AEIO, applies SPL, inserts it into a CPMM `NodeState`, and prints
aggregate estimates and any ECP promotions. Without Wokwi, `python scripts/virtual_sensor_demo.py | python scripts/wokwi_bridge.py`
produces the same line format from the Python virtual sensors.

Status: these Wokwi files were **not executed in the build environment** (no Wokwi access); the shared
core header was compiled and unit-tested on the host (`firmware/common/test_sage_core.cpp`).
