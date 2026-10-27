# SAGE-DTN on FIT IoT-LAB (real radios)

This folder ports the SAGE-DTN node to RIOT OS so it runs on FIT IoT-LAB testbed nodes (default: IoT-LAB M3,
STM32F103 + AT86RF231 IEEE 802.15.4 radio; nRF52840-DK also builds). It reuses the firmware SPL core
(`firmware/common/sage_core.h`, copied here by `scripts/sync_firmware_common.sh`) and adds the network
behaviour of the simulator modes A, E, F, H and I on a real radio.

**Status: no hardware results yet.** `results/HW_RESULTS.md` says PENDING until someone with an IoT-LAB
account runs `run_on_iotlab.sh`. Do not quote numbers from a local run as hardware results.

## One command (on the IoT-LAB SSH frontend)
```bash
iotlab-auth -u <login>                      # once
./iotlab/run_on_iotlab.sh                   # quick plan, 16 M3 nodes in Grenoble, 90-minute reservation
./iotlab/run_on_iotlab.sh --plan full --duration 240
```
The script builds the firmware (or falls back to `prebuilt/`), reserves nodes, flashes them, enables power
monitoring, runs the plan, stops the experiment, analyses the log and writes
`~/sage_results/<exp_id>/HW_RESULTS.md` plus `~/sage_results/sage_<exp_id>.tar.gz`.

## Test locally first (no account needed)
```bash
./iotlab/run_local.sh          # host build, 16 processes, ~4 min
./iotlab/run_local.sh riot     # the RIOT build itself (BOARD=native64) over RIOT's ZEP 802.15.4 emulator
```

## What runs on the hardware
| Sim experiment | Hardware version | Notes |
|---|---|---|
| E1 SPL property | `selftest` on every node: random forbidden mutations, measured ns per `permit()` on the MCU | same test as `firmware/common/test_sage_core.cpp` |
| E2 duplicate replay | water requests replayed ×5 (×1/×5/×20 in `--plan e2`); responder reports raw messages, exact distinct, HLL estimate | real loss and retransmissions |
| E3 network load | modes A, E, F, H at load 1× and 4× (0.5×–8× in `--plan e3`): CDR, critical information loss, latency, bytes, peak storage, ECP | |
| E4 source loss | mode I, replicas R=0/1 on ferries, village-2 sensors destroyed at phase 6, SHA-256-verified recovery | source loss is a firmware `die` command, not a power cut |
| E5 sensor rate | `--plan e5`: 1/4/12 sensor publications per minute, modes F and H | |
| E6 convergence | mode H, then all nodes in contact, then order-independent state digests compared | |
| Energy | IoT-LAB M3 power monitor (`.oml`), mean node power and energy per trial | idle listening dominates, see caveats |
| E7, E8 | not ported | ML models are not on the node |

## How disruption is emulated
IoT-LAB nodes are fixed and mostly within radio range of each other. The controller broadcasts a phase number;
ferry *k* is at location `(phase + k) mod (V+1)` (0 = responder base, 1..V = villages). A node ignores packets
from nodes that are not at its location in the current phase. Everything else is real: radio loss,
collisions, CSMA back-off, serial timing, MCU speed, RAM limits and power draw. Report this clearly in any
paper or patent text: *the contact plan is scheduled in software; the radio links are physical.*

## Files
| Path | Content |
|---|---|
| `sage_app/` | platform-independent node logic (`sage_app.cpp`), wire format, modes, ECP, evidence; `sage_core.h` copy |
| `riot/` | RIOT application (`main.c`: shell commands, link-local multicast UDP, tick thread), `Makefile` |
| `host/` | host build for local tests (UDP on localhost, built-in SHA-256) |
| `tools/controller.py` | role assignment, contact phases, seeded workload, ground-truth log (stdlib only) |
| `tools/analyze.py` | `run.log` → `hw_trials.csv`, `hw_e1_spl.csv`, `HW_RESULTS.md` (PENDING where empty) |
| `prebuilt/` | firmware built from this commit with RIOT 2025.07 and arm-none-eabi-gcc 13.2 |
| `results/` | where hardware results are copied once they exist |

## Serial protocol (one line per command)
`cfg id=<n> role=F|S|X|R grp=<g> mode=A|E|F|H|I trial=<t> cap=<records> bud=<bytes/s> R=<replicas> ...`,
`reset`, `ph <phase> <t_s>`, `r <TYPE> <key> <urgency>`, `s <TYPE> <value×100>`, `st`, `dump`,
`selftest <iters>`, `die`, `ping`. Node output lines start with `@` (`@dl`, `@loss`, `@ecp`, `@st`, `@dg`,
`@agg`, `@trig`, `@evok`, `@evbad`, `@e1`).

## Caveats
* 16 nodes and short trials: treat differences inside run-to-run spread as not established; run `--plan e3`
  (2 repetitions) or repeat with `--seed` for more runs.
* `spl_clamps` counts every once-per-second check where SPL refused the proposed level, so it is a rate, not
  a count of distinct records.
* Power on M3 nodes is dominated by the radio listening continuously; modes may show small energy differences.
* The ESP32 firmware in `firmware/` was not built here; this folder is the hardware path that was compiled
  (`iotlab-m3`, `nrf52840dk`) and executed (`native64` and host).
