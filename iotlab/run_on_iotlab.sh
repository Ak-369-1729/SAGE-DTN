#!/usr/bin/env bash
# One command to run the SAGE-DTN hardware experiments on FIT IoT-LAB.
# Run it ON the IoT-LAB SSH frontend (e.g. ssh <login>@grenoble.iot-lab.info), from the repo folder:
#
#   ./iotlab/run_on_iotlab.sh                         # quick plan: 16 M3 nodes, Grenoble, 90 minutes
#   ./iotlab/run_on_iotlab.sh --plan full --duration 240
#   ./iotlab/run_on_iotlab.sh --nodes-list grenoble,m3,100-115   # choose physical nodes
#   ./iotlab/run_on_iotlab.sh --exp-id 412345         # reuse an experiment that is already running
#
# It builds (or uses the prebuilt) firmware, reserves nodes, flashes them, turns on power monitoring,
# runs the plan, stops the experiment, analyses the log and packs everything into one .tar.gz.
set -euo pipefail

SITE=grenoble; NODES=16; DURATION=90; PLAN=quick; EXP_ID=""; NODES_LIST=""; BOARD=iotlab-m3
PREBUILT=0; KEEP=0; PHASE_S=12; SEED=1
while [ $# -gt 0 ]; do
  case "$1" in
    --site) SITE=$2; shift ;;
    --nodes) NODES=$2; shift ;;
    --duration) DURATION=$2; shift ;;
    --plan) PLAN=$2; shift ;;
    --exp-id) EXP_ID=$2; shift ;;
    --nodes-list) NODES_LIST=$2; shift ;;
    --board) BOARD=$2; shift ;;
    --prebuilt) PREBUILT=1 ;;
    --keep-running) KEEP=1 ;;
    --phase-s) PHASE_S=$2; shift ;;
    --seed) SEED=$2; shift ;;
    -h|--help) sed -n 2,12p "$0"; exit 0 ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
  shift
done

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
say() { printf '\n==> %s\n' "$*"; }

[ -f "$HOME/.iotlabrc" ] || { echo "Not logged in to the IoT-LAB API. Run:  iotlab-auth -u <your_login>   then run this script again."; exit 1; }
command -v iotlab-experiment >/dev/null || { echo "iotlab-experiment not found: run this script on the IoT-LAB SSH frontend."; exit 1; }

case "$BOARD" in
  iotlab-m3) ARCHI="m3:at86rf231" ;;
  nrf52840dk) ARCHI=${ARCHI:-nrf52840dk:multi} ;;   # check the exact name with: iotlab-status --nodes --site <site>
  *) echo "unsupported board $BOARD (use iotlab-m3 or nrf52840dk)"; exit 2 ;;
esac

# ---- 1. firmware --------------------------------------------------------------------------
FW="$HERE/riot/bin/$BOARD/sage-node.elf"
if [ "$PREBUILT" = 0 ]; then
  say "Building firmware for $BOARD"
  [ -f /opt/riot.source ] && source /opt/riot.source || true
  if [ ! -d "$HOME/RIOT" ]; then git clone --depth 1 --branch 2025.07 https://github.com/RIOT-OS/RIOT.git "$HOME/RIOT"; fi
  if ! make -C "$HERE/riot" BOARD="$BOARD" RIOTBASE="$HOME/RIOT" -j4 >"$HERE/riot/build.log" 2>&1; then
    echo "Build failed (see iotlab/riot/build.log); using the prebuilt firmware instead."
    PREBUILT=1
  fi
fi
if [ "$PREBUILT" = 1 ]; then FW="$HERE/prebuilt/sage-node-$BOARD.elf"; fi
[ -f "$FW" ] || { echo "firmware $FW not found"; exit 1; }
echo "firmware: $FW"

# ---- 2. power monitoring profile (M3 only) ---------------------------------------------------
PROFILE=""
if [ "$BOARD" = iotlab-m3 ]; then
  iotlab-profile addm3 -n sage_power -p dc -current -voltage -power -period 8244 -avg 4 >/dev/null 2>&1 || true
  PROFILE=sage_power
fi

# ---- 3. reserve nodes ------------------------------------------------------------------------
if [ -z "$EXP_ID" ]; then
  say "Reserving nodes ($DURATION minutes)"
  if [ -n "$NODES_LIST" ]; then LIST="$NODES_LIST"; else LIST="$NODES,archi=$ARCHI+site=$SITE"; fi
  OUT=$(iotlab-experiment submit -n sage_dtn -d "$DURATION" -l "$LIST")
  echo "$OUT"
  EXP_ID=$(echo "$OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
fi
echo "experiment id: $EXP_ID"
say "Waiting for the experiment to start (this can take a few minutes if the testbed is busy)"
iotlab-experiment wait -i "$EXP_ID"

# ---- 4. flash and monitor --------------------------------------------------------------------
say "Flashing all nodes"
iotlab-node --flash "$FW" -i "$EXP_ID" >/dev/null
if [ -n "$PROFILE" ]; then iotlab-node --update-profile "$PROFILE" -i "$EXP_ID" >/dev/null || echo "(power monitoring not enabled)"; fi
sleep 5

# ---- 5. run the plan -------------------------------------------------------------------------
RES="$HOME/sage_results/$EXP_ID"
mkdir -p "$RES"
cp "$FW" "$RES/firmware.elf"
(cd "$REPO" && git rev-parse HEAD 2>/dev/null || echo unknown) > "$RES/code_version.txt"
sha256sum "$FW" >> "$RES/code_version.txt"
say "Running plan '$PLAN' (log: $RES/run.log)"
python3 "$HERE/tools/controller.py" iotlab --exp-id "$EXP_ID" --plan "$PLAN" --out "$RES" --phase-s "$PHASE_S" --seed "$SEED" | tee "$RES/controller.out"

# ---- 6. collect --------------------------------------------------------------------------------
if [ "$KEEP" = 0 ]; then say "Stopping the experiment (frees the nodes)"; iotlab-experiment stop -i "$EXP_ID" || true; sleep 5; fi
CONS="$HOME/.iot-lab/$EXP_ID/consumption"
if [ -d "$CONS" ]; then cp -r "$CONS" "$RES/consumption"; fi
say "Analysing"
python3 "$HERE/tools/analyze.py" "$RES" $( [ -d "$RES/consumption" ] && echo --consumption "$RES/consumption" )
tar -czf "$HOME/sage_results/sage_$EXP_ID.tar.gz" -C "$HOME/sage_results" "$EXP_ID"
say "Done"
echo "Results:  $RES/HW_RESULTS.md"
echo "Download to your computer with:"
echo "  scp $(whoami)@$SITE.iot-lab.info:sage_results/sage_$EXP_ID.tar.gz ."
