"""Headless test probe runner: Phase 5 Slice 1 (Match Objectives & Victory Engine).

Launches the headless engine against startscript_slice1.txt, watches for the
PHASE5 VICTORY verdicts (baseline, tc, conquest, regicide, surrender, gameover
and the terminal probe-complete), and prints them.

The probe's slowest stage lands at f=120 (~5-8s of sim at the observed 16-28 f/s),
so the wall-clock budget is mostly margin for the robocopy sync and engine boot.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "tools" / "runtime"
ENGINE = ROOT / "tools" / "engine" / "recoil_2026.07.04" / "spring-headless.exe"
STARTSCRIPT = ROOT / "tools" / "launch" / "startscript_slice1.txt"

RESOURCES = ["baseline", "tc", "conquest", "regicide", "surrender", "gameover", "probe-complete"]


def run_probe() -> int:
    dest = ROOT / "tools" / "runtime" / "games" / "Medieval-BAR-TC.sdd"
    print(f"Syncing source to {dest}...")
    res = subprocess.run([
        "robocopy", str(ROOT), str(dest),
        "/MIR", "/XD", str(ROOT / ".git"), str(ROOT / "tools"), "/XF", ".gitignore"
    ], capture_output=True)
    if res.returncode >= 8:
        raise RuntimeError(f"robocopy failed: {res.returncode}")

    infolog = RUNTIME / "infolog.txt"
    if infolog.exists():
        infolog.unlink()
    print(f"Launching Recoil engine: {ENGINE}...")
    cmd = [str(ENGINE), "--isolation", "--write-dir", str(RUNTIME), str(STARTSCRIPT)]

    try:
        proc = subprocess.run(cmd, timeout=120, capture_output=True, text=True)
        print(f"Engine exited {proc.returncode}")
    except subprocess.TimeoutExpired:
        print("Engine timed out after budget (expected; headless quitforce does not terminate this build)")

    infolog = RUNTIME / "infolog.txt"
    if not infolog.exists():
        print("ERROR: No infolog generated")
        return 1

    text = infolog.read_text(encoding="utf-8", errors="replace")

    print("\n--- VICTORY PROBE LINES ---")
    verdicts = {}
    for line in text.splitlines():
        if "PHASE5 VICTORY" in line:
            print(line)
            for r in RESOURCES:
                if f"{r}-verdict PASS" in line or f"{r} PASS" in line:
                    verdicts[r] = True
                elif f"{r}-verdict FAIL" in line or f"{r} FAIL" in line:
                    verdicts[r] = False

    print("\n--- SUMMARY ---")
    failed = []
    for r in RESOURCES:
        state = "PASS" if verdicts.get(r) is True else ("FAIL" if verdicts.get(r) is False else "MISSING")
        print(f"{r}: {state}")
        if state != "PASS":
            failed.append(r)

    if not failed:
        print("SLICE 1 VICTORY PROBE: ALL VERDICTS PASSED")
        return 0
    print(f"SLICE 1 VICTORY PROBE: FAILED ({', '.join(failed)})")
    return 1


if __name__ == "__main__":
    sys.exit(run_probe())
