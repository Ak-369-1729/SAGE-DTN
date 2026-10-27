#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for d in firmware/field-node firmware/sensor-node firmware/responder-node wokwi/sensor-node; do
  cp firmware/common/sage_core.h firmware/common/radio_adapter.h "$d/"
done
cp firmware/sensor-node/sensor-node.ino wokwi/sensor-node/sketch.ino
cp firmware/common/sage_core.h iotlab/sage_app/
echo synced
