#!/usr/bin/env bash
# Compile-checks the field and sensor sketches on the host with stubbed Arduino APIs (logic/syntax only;
# it does not prove ESP32 toolchain compatibility). Responder needs Adafruit libs and is checked with arduino-cli.
set -euo pipefail
cd "$(dirname "$0")/.."
for s in sensor-node field-node; do
  printf '#include "%s.ino"\nint main(){setup(); for(int i=0;i<2000;i++) loop(); return 0;}\n' "$s" > /tmp/sage_${s}_main.cpp
  g++ -std=c++17 -Wall -Wno-unused-variable -I host_stub -I "$s" -x c++ /tmp/sage_${s}_main.cpp -o /tmp/sage_${s}_bin
  /tmp/sage_${s}_bin | head -3
  echo "OK host compile+run: $s"
done
