#!/usr/bin/env python3
"""SAGE-DTN testbed controller (Python 3 standard library only, runs on the IoT-LAB SSH frontend).

It assigns roles, drives the contact phases, injects the seeded workload (human reports, sensor
samples, replays) and records every node line plus the ground truth in one log:

    <unix_time>;<node>;<line>        node lines (from serial_aggregator or local processes)
    <unix_time>;ctl;<event>          controller ground truth

Backends:
    iotlab  real nodes of a running IoT-LAB experiment, via serial_aggregator
    local   N local processes (RIOT native64 over a ZEP 802.15.4 emulator, or the host build)

Examples:
    controller.py iotlab --exp-id 412345 --plan quick --out ~/sage_results/412345
    controller.py local --kind riot --exe riot/bin/native64/sage-node.elf --nodes 16 --plan smoke --out /tmp/sage
"""
import argparse
import json
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time

CRITICAL = ("TRAPPED_PERSON", "MEDICATION_NEED")
MIX = (("TRAPPED_PERSON", 0.15), ("MEDICATION_NEED", 0.10), ("WATER_REQUEST", 0.45), ("SAFE_STATUS", 0.30))


# ----------------------------------------------------------------------------- backends
class Backend:
    def __init__(self, log_path):
        self.q = queue.Queue()
        self.log = open(log_path, "a", buffering=1)
        self.lock = threading.Lock()

    def record(self, node, text):
        with self.lock:
            self.log.write("%.6f;%s;%s\n" % (time.time(), node, text))

    def ctl(self, text):
        self.record("ctl", text)


class IotlabBackend(Backend):
    def __init__(self, log_path, exp_id):
        super().__init__(log_path)
        self.exp_id = str(exp_id)
        out = subprocess.run(["iotlab-experiment", "get", "-i", self.exp_id, "-n"], capture_output=True, text=True, check=True).stdout
        found = sorted(set(re.findall(r"([a-z0-9]+-\d+)\.([a-z]+)\.iot-lab\.info", out)), key=lambda t: (t[0].split("-")[0], int(t[0].split("-")[1])))
        if not found:
            sys.exit("no nodes found for experiment %s:\n%s" % (self.exp_id, out))
        self.nodes = [n for n, _ in found]
        self.site = {n: s for n, s in found}
        self.proc = subprocess.Popen(["serial_aggregator", "-i", self.exp_id], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1)
        threading.Thread(target=self._reader, daemon=True).start()
        time.sleep(3)

    def _reader(self):
        for line in self.proc.stdout:
            line = line.rstrip("\n")
            parts = line.split(";", 2)
            if len(parts) == 3:
                with self.lock:
                    self.log.write(line + "\n")
                self.q.put((parts[1], parts[2]))

    def send(self, node, cmd):
        self.proc.stdin.write("%s;%s\n" % (node if node else "-", cmd))
        self.proc.stdin.flush()

    def close(self):
        try:
            self.proc.terminate()
        except OSError:
            pass


class LocalBackend(Backend):
    def __init__(self, log_path, kind, exe, n, loss):
        super().__init__(log_path)
        self.nodes = ["m3-%d" % (i + 1) for i in range(n)]
        self.procs = {}
        self.zep = None
        if kind == "riot":
            zep = os.environ.get("ZEP_DISPATCH") or os.path.join(os.environ.get("RIOTBASE", os.path.expanduser("~/RIOT")), "dist/tools/zep_dispatch/bin/zep_dispatch")
            self.zep = subprocess.Popen([zep, "127.0.0.1", "17754"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
        for i, name in enumerate(self.nodes):
            if kind == "riot":
                argv = [exe, "-z", "127.0.0.1:%d,127.0.0.1:17754" % (17800 + i)]
            else:
                argv = [exe, str(i), str(n), "47000", str(loss)]
            p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            self.procs[name] = p
            threading.Thread(target=self._reader, args=(name, p), daemon=True).start()
        time.sleep(3)

    def _reader(self, name, p):
        for line in p.stdout:
            line = line.rstrip("\n")
            self.record(name, line)
            self.q.put((name, line))

    def send(self, node, cmd):
        for name in ([node] if node else self.nodes):
            p = self.procs[name]
            try:
                p.stdin.write(cmd + "\n")
                p.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
        time.sleep(0.002)

    def close(self):
        for p in self.procs.values():
            p.kill()
        if self.zep:
            self.zep.kill()


# ----------------------------------------------------------------------------- layout
def layout(nodes):
    """Assign roles: V villages x (field + sensor nodes), ferries, one responder. Extra nodes stay idle."""
    for V, nfield, nsens, nf in ((3, 2, 2, 3), (3, 2, 1, 3), (3, 1, 1, 3), (2, 1, 1, 2)):
        need = V * (nfield + nsens) + nf + 1
        if len(nodes) >= need:
            break
    else:
        sys.exit("need at least 7 nodes, got %d" % len(nodes))
    roles, it = [], iter(nodes)
    roles.append((next(it), "R", 0))
    for k in range(nf):
        roles.append((next(it), "X", k))
    for v in range(1, V + 1):
        for _ in range(nfield):
            roles.append((next(it), "F", v))
        for _ in range(nsens):
            roles.append((next(it), "S", v))
    return {"V": V, "nf": nf, "roles": [{"node": n, "role": r, "grp": g, "id": i} for i, (n, r, g) in enumerate(roles)]}


# ----------------------------------------------------------------------------- plans
def trial(exp, mode, **kw):
    t = {"exp": exp, "mode": mode, "load": 1.0, "dup": 1, "srate": 6, "R": 0, "corrupt": 0, "kill_phase": -1, "conv": False, "rep": 0}
    t.update(kw)
    return t


def make_plan(name):
    plans = {
        "smoke": [trial("E3", "H", load=1.0), trial("E3", "E", load=4.0)],
        "e3": [trial("E3", m, load=l, rep=r) for r in (0, 1) for l in (0.5, 1, 2, 4, 8) for m in "AEFH"],
        "e2": [trial("E2", m, dup=d) for d in (1, 5, 20) for m in "FH"],
        "e5": [trial("E5", m, srate=s) for s in (1, 4, 12) for m in "FH"],
        "e4": [trial("E4", "I", R=R, corrupt=c, kill_phase=6) for c in (0, 100) for R in (0, 1, 3)],
        "e6": [trial("E6", "H", conv=True, rep=r) for r in range(3)],
    }
    plans["quick"] = ([trial("E3", m, load=l) for l in (1, 4) for m in "AEFH"] + [trial("E2", m, dup=5) for m in "FH"] +
                      [trial("E4", "I", R=R, kill_phase=6) for R in (0, 1)] + [trial("E6", "H", conv=True)])
    plans["full"] = plans["e3"] + plans["e2"] + plans["e5"] + plans["e4"] + plans["e6"]
    if name not in plans:
        sys.exit("unknown plan %s (choose from %s)" % (name, ", ".join(sorted(plans))))
    return plans[name]


# ----------------------------------------------------------------------------- scenario
def sensor_value(kind, village, phase, rng, early):
    """Deterministic sensor scenario: flood in village 1, smoke in village 2, tremor in village 3."""
    if kind == "WATER_LEVEL":
        base = 30 + (max(0, min(phase - 2, 6)) * 24 if village == 1 else 0)
        return base + rng.gauss(0, 3)
    if kind == "SMOKE_DENSITY":
        start = 1 if early else 4
        base = 20 + (min(max(phase - start, 0), 3) * 130 if village == 2 else 0)
        return max(0.0, base + rng.gauss(0, 5))
    g = 0.3 if (village == 3 and phase in (6, 7)) else 0.01
    return g + rng.gauss(0, 0.005)


def run_trial(be, lay, idx, t, args, seed):
    rng = random.Random(seed * 1000 + idx)
    ph_s, P, D = args.phase_s, args.phases, args.drain
    roles = lay["roles"]
    field = {v: [r for r in roles if r["role"] == "F" and r["grp"] == v] for v in range(1, lay["V"] + 1)}
    sensors = [r for r in roles if r["role"] == "S"]
    be.ctl("trial_start " + json.dumps(dict(t, trial=idx, unix=time.time(), phase_s=ph_s, phases=P, drain=D, ecpw=args.ecpw, ecps=2,
                                            cap=args.cap, bud=args.bud, V=lay["V"], nf=lay["nf"], seed=seed)))
    be.send(None, "reset")
    time.sleep(1.0)
    for r in roles:
        be.send(r["node"], "cfg id=%d role=%s grp=%d mode=%s trial=%d cap=%d rcap=160 bud=%d V=%d nf=%d R=%d ecpw=%d ecps=2 corrupt=%d tau=%d" % (
            r["id"], r["role"], r["grp"], t["mode"], idx % 250 + 1, args.cap, args.bud, lay["V"], lay["nf"], t["R"], args.ecpw, t["corrupt"], args.tau))
        time.sleep(0.05)
    time.sleep(1.0)
    seq = 0
    killed = set()
    t0 = time.time()
    total = P + D
    for ph in range(total):
        tnow = int(time.time() - t0)
        be.send(None, "ph %d %d" % (ph, tnow))
        be.ctl("phase %d %d" % (ph, tnow))
        if t["kill_phase"] == ph:   # E4: destroy the evidence sources (village-2 sensors)
            for r in sensors:
                if r["grp"] == 2:
                    be.send(r["node"], "die")
                    killed.add(r["node"])
                    be.ctl("kill %s" % r["node"])
        events = []
        if ph < P:
            for v, fnodes in field.items():
                lam = 0.1 * t["load"] * ph_s
                n = poisson(rng, lam)
                for _ in range(n):
                    seq += 1
                    typ = weighted(rng, MIX)
                    key = "T%d:V%d:%d" % (idx, v, seq)
                    node = rng.choice(fnodes)
                    at = rng.uniform(0, ph_s * 0.8)
                    events.append((at, "inj", node["node"], typ, key, v, rng.randint(1, 3)))
                    reps = (t["dup"] - 1) if typ == "WATER_REQUEST" else 0
                    reps += 1 if rng.random() < 0.2 else 0
                    for _ in range(reps):
                        other = rng.choice(fnodes)
                        events.append((min(ph_s * 0.95, at + rng.uniform(0.5, ph_s * 0.5)), "rep", other["node"], typ, key, v, 1))
            period = 60.0 / max(t["srate"], 0.01)
            for s in sensors:
                k = 0
                while k * period < ph_s:
                    for kind in ("WATER_LEVEL", "SMOKE_DENSITY", "COLLAPSE_RISK"):
                        val = sensor_value(kind, s["grp"], ph, rng, t["exp"] == "E4")
                        events.append((k * period + rng.uniform(0, 0.5), "sens", s["node"], kind, int(round(val * 100)), s["grp"], 0))
                    k += 1
        events.sort(key=lambda e: e[0])
        start = time.time()
        for at, kind, node, typ, key, v, urg in events:
            delay = start + at - time.time()
            if delay > 0:
                time.sleep(delay)
            if node in killed:
                continue
            if kind == "sens":
                be.send(node, "s %s %d" % (typ, key))
                be.ctl("sens %s %s %d %d" % (node, typ, key, v))
            else:
                be.send(node, "r %s %s %d" % (typ, key, urg))
                be.ctl("%s %s %s %d %s" % (kind, key, typ, v, node))
        rest = start + ph_s - time.time()
        if rest > 0:
            time.sleep(rest)
    if t["conv"]:   # E6: everyone in contact, then compare state digests
        for k in range(3):
            be.send(None, "ph -1 %d" % int(time.time() - t0))
            be.ctl("phase -1")
            time.sleep(ph_s)
    be.send(None, "st")
    time.sleep(1.5)
    be.send(None, "dump")
    time.sleep(2.5)
    be.ctl("trial_end %d %.3f" % (idx, time.time()))


def poisson(rng, lam):
    L, k, p = pow(2.718281828459045, -lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def weighted(rng, items):
    x, acc = rng.random(), 0.0
    for name, w in items:
        acc += w
        if x <= acc:
            return name
    return items[-1][0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backend", choices=("iotlab", "local"))
    ap.add_argument("--exp-id", help="IoT-LAB experiment id (iotlab backend)")
    ap.add_argument("--kind", choices=("riot", "host"), default="riot", help="local backend: RIOT native64 or host build")
    ap.add_argument("--exe", help="local backend: node executable")
    ap.add_argument("--nodes", type=int, default=16, help="local backend: number of nodes")
    ap.add_argument("--loss", type=float, default=0.0, help="local host backend: packet loss probability")
    ap.add_argument("--plan", default="quick")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--phase-s", type=float, default=12.0)
    ap.add_argument("--phases", type=int, default=12)
    ap.add_argument("--drain", type=int, default=4)
    ap.add_argument("--cap", type=int, default=40)
    ap.add_argument("--bud", type=int, default=150, help="bytes/s per node radio budget")
    ap.add_argument("--ecpw", type=int, default=6)
    ap.add_argument("--tau", type=int, default=120)
    ap.add_argument("--selftest-iters", type=int, default=20000)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    log = os.path.join(args.out, "run.log")
    if args.backend == "iotlab":
        if not args.exp_id:
            sys.exit("--exp-id is required")
        be = IotlabBackend(log, args.exp_id)
    else:
        if not args.exe:
            sys.exit("--exe is required")
        be = LocalBackend(log, args.kind, args.exe, args.nodes, args.loss)
    plan = make_plan(args.plan)
    lay = layout(be.nodes)
    meta = {"backend": args.backend, "exp_id": args.exp_id, "kind": args.kind if args.backend == "local" else "iotlab",
            "nodes": be.nodes, "layout": lay, "plan": args.plan, "args": vars(args), "start_unix": time.time()}
    be.ctl("meta " + json.dumps(meta))
    with open(os.path.join(args.out, "layout.json"), "w") as f:
        json.dump(meta, f, indent=1)
    minutes = len(plan) * ((args.phases + args.drain) * args.phase_s + 9) / 60.0
    print("plan %s: %d trials, about %.0f minutes, %d nodes (%d villages, %d ferries)" % (args.plan, len(plan), minutes, len(be.nodes), lay["V"], lay["nf"]))
    try:
        be.send(None, "ping")
        time.sleep(2)
        # E1 on every node
        be.ctl("e1_start %.3f" % time.time())
        be.send(None, "selftest %d" % args.selftest_iters)
        time.sleep(max(5, args.selftest_iters / 2000))
        for i, t in enumerate(plan, 1):
            print("[%s] trial %d/%d %s mode=%s load=%s dup=%s srate=%s R=%s" % (time.strftime("%H:%M:%S"), i, len(plan), t["exp"], t["mode"], t["load"], t["dup"], t["srate"], t["R"]), flush=True)
            run_trial(be, lay, i, t, args, args.seed + t["rep"])
        be.ctl("done %.3f" % time.time())
    finally:
        be.close()
    print("log written to", log)


if __name__ == "__main__":
    main()
