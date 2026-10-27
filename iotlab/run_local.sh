#!/usr/bin/env bash
# Test the whole IoT-LAB pipeline on your own computer, without hardware or an account.
#   ./iotlab/run_local.sh            # host build, 16 local processes, 'smoke' plan (~4 min)
#   ./iotlab/run_local.sh riot       # RIOT native64 build over an emulated 802.15.4 radio (needs ~/RIOT)
#   PLAN=quick ./iotlab/run_local.sh # same plan as the hardware run (shortened phases)
# Results go to /tmp/sage_local/HW_RESULTS.md and are labelled LOCAL EMULATION, never hardware.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
KIND=${1:-host}; PLAN=${PLAN:-smoke}; OUT=${OUT:-/tmp/sage_local}
rm -rf "$OUT"
if [ "$KIND" = riot ]; then
  RIOTBASE=${RIOTBASE:-$HOME/RIOT}
  make -C "$HERE/riot" BOARD=native64 RIOTBASE="$RIOTBASE" >/dev/null
  make -C "$RIOTBASE/dist/tools/zep_dispatch" >/dev/null
  EXE="$HERE/riot/bin/native64/sage-node.elf"
else
  EXE=/tmp/sage_host_node
  g++ -std=c++17 -O2 -I "$HERE/sage_app" "$HERE/sage_app/sage_app.cpp" "$HERE/host/host_main.cpp" -o "$EXE"
fi
RIOTBASE=${RIOTBASE:-$HOME/RIOT} python3 "$HERE/tools/controller.py" local --kind "$KIND" --exe "$EXE" --nodes 16 --plan "$PLAN" \
  --out "$OUT" --phase-s 6 --phases 10 --drain 4
python3 "$HERE/tools/analyze.py" "$OUT"
echo "see $OUT/HW_RESULTS.md"
