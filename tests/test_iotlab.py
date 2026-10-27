"""IoT-LAB port: the host build of the node exchanges a record and the analyzer's hash matches the firmware's."""
import importlib.util
import pathlib
import shutil
import subprocess
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
IOT = ROOT / "iotlab"


def _analyze():
    spec = importlib.util.spec_from_file_location("sage_iotlab_analyze", IOT / "tools" / "analyze.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(shutil.which("g++") is None, reason="needs g++")
def test_host_nodes_deliver_and_hash_matches(tmp_path):
    exe = tmp_path / "host_node"
    subprocess.run(["g++", "-std=c++17", "-O2", "-I", str(IOT / "sage_app"), str(IOT / "sage_app" / "sage_app.cpp"),
                    str(IOT / "host" / "host_main.cpp"), "-o", str(exe)], check=True)
    procs = [subprocess.Popen([str(exe), str(i), "2", "47600"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) for i in range(2)]
    try:
        cfgs = ["cfg id=0 role=F grp=1 mode=H trial=3", "cfg id=1 role=R grp=0 mode=H trial=3"]
        for p, c in zip(procs, cfgs):
            p.stdin.write(c + "\nph -1 0\n")
            p.stdin.flush()
        procs[0].stdin.write("r TRAPPED_PERSON T3:V1:7 2\nselftest 5000\n")
        procs[0].stdin.flush()
        time.sleep(2.0)
    finally:
        for p in procs:
            p.stdin.close()
        outs = [p.communicate(timeout=10)[0] for p in procs]
    sink = [line for line in outs[1].splitlines() if line.startswith("@dl ")]
    assert sink, outs[1]
    eid, typ, fid, usable = sink[0].split()[1:5]
    assert eid == _analyze().hash_str("T3:V1:7")
    assert (typ, fid, usable) == ("TRAPPED_PERSON", "0", "1")
    e1 = [line for line in outs[0].splitlines() if line.startswith("@e1 ")][0]
    assert "committed_forbidden=0" in e1


def test_pending_report(tmp_path):
    _analyze().write_report(str(tmp_path), None, [], [], False)
    text = (tmp_path / "HW_RESULTS.md").read_text()
    assert "PENDING" in text and "| " not in text.split("## E1")[1].split("##")[0]
