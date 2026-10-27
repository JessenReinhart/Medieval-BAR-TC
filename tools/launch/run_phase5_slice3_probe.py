"""Headless test probe runner: Phase 5 Slice 3 (Market & Trade Exchange).

Launches the headless engine against startscript_phase5_slice3.txt, watches for
the PHASE5 MARKET verdicts (rate, barter, probe-complete), and prints them.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "tools" / "runtime"
ENGINE = ROOT / "tools" / "engine" / "recoil_2026.07.04" / "spring-headless.exe"
STARTSCRIPT = ROOT / "tools" / "launch" / "startscript_phase5_slice3.txt"

RESOURCES = ["rate", "barter"]


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

    # Slice 3 verdicts complete by f=90 (~3s of sim at 28 fps). The 90s budget is
    # mostly margin for robocopy sync and engine boot.
    try:
        proc = subprocess.run(cmd, timeout=90, capture_output=True, text=True)
        print(f"Engine exited {proc.returncode}")
    except subprocess.TimeoutExpired:
        print("Engine timed out after budget (expected; headless quitforce does not terminate this build)")

    infolog = RUNTIME / "infolog.txt"
    if not infolog.exists():
        print("ERROR: No infolog generated")
        return 1

    text = infolog.read_text(encoding="utf-8", errors="replace")

    print("\n--- MARKET PROBE LINES ---")
    verdicts = {}
    complete = False
    for line in text.splitlines():
        if "PHASE5 MARKET" in line:
            print(line)
            if "probe-complete PASS" in line:
                complete = True
            for r in RESOURCES:
                if f"{r}-verdict PASS" in line:
                    verdicts[r] = True
                elif f"{r}-verdict FAIL" in line:
                    verdicts[r] = False

    print("\n--- SUMMARY ---")
    failed = []
    for r in RESOURCES:
        state = "PASS" if verdicts.get(r) is True else ("FAIL" if verdicts.get(r) is False else "MISSING")
        print(f"{r}: {state}")
        if state != "PASS":
            failed.append(r)
    print(f"probe-complete: {'PASS' if complete else 'MISSING'}")
    if not complete:
        failed.append("probe-complete")

    if not failed:
        print("SLICE 3 MARKET PROBE: ALL VERDICTS PASSED")
        return 0
    print(f"SLICE 3 MARKET PROBE: FAILED ({', '.join(failed)})")
    return 1


if __name__ == "__main__":
    sys.exit(run_probe())
