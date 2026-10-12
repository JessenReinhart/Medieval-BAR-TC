"""Headless test probe runner: Phase 4 Slice 6 (Basic Medieval Skirmish AI).

Launches the headless engine against startscript_slice6.txt, watches for the five
PHASE4 SKIRMISH verdicts (harvest, road, house, recruit, attack), and prints them.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "tools" / "runtime"
ENGINE = ROOT / "tools" / "engine" / "recoil_2026.07.04" / "spring-headless.exe"
STARTSCRIPT = ROOT / "tools" / "launch" / "startscript_slice6.txt"

RESOURCES = ["harvest", "road", "house", "recruit", "attack"]


def run_probe() -> int:
    dest = ROOT / "tools" / "runtime" / "games" / "Medieval-BAR-TC.sdd"
    print(f"Syncing source to {dest}...")
    subprocess.run([
        "robocopy", str(ROOT), str(dest),
        "/MIR", "/XD", str(ROOT / ".git"), str(ROOT / "tools"), "/XF", ".gitignore"
    ], capture_output=True)

    print(f"Launching Recoil engine: {ENGINE}...")
    cmd = [str(ENGINE), "--isolation", "--write-dir", str(RUNTIME), str(STARTSCRIPT)]

    # Slice 6 verdicts complete by f=180 (~7s of sim at 28 fps). The 90s budget is
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

    print("\n--- SKIRMISH PROBE LINES ---")
    verdicts = {}
    for line in text.splitlines():
        if "PHASE4 SKIRMISH" in line:
            print(line)
            if "verdict PASS" in line:
                for r in RESOURCES:
                    if f"{r}-verdict PASS" in line:
                        verdicts[r] = True
            elif "verdict FAIL" in line:
                for r in RESOURCES:
                    if f"{r}-verdict FAIL" in line:
                        verdicts[r] = False

    print("\n--- SUMMARY ---")
    failed = []
    for r in RESOURCES:
        state = "PASS" if verdicts.get(r) is True else ("FAIL" if verdicts.get(r) is False else "MISSING")
        print(f"{r}: {state}")
        if state != "PASS":
            failed.append(r)

    if not failed:
        print("SLICE 6 SKIRMISH AI PROBE: ALL VERDICTS PASSED")
        return 0
    print(f"SLICE 6 SKIRMISH AI PROBE: FAILED ({', '.join(failed)})")
    return 1


if __name__ == "__main__":
    sys.exit(run_probe())
