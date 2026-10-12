"""Headless test probe runner: Phase 5 Slice 6 (Full Skirmish Match Integration & Victory).

Launches the headless engine against startscript_slice6b.txt, watches for the six
PHASE5 INTEGRATION verdicts (settlement-start, economy-flow, military-engagement,
tc-destroyed, victory-gameover and the terminal probe-complete), and prints them.

The probe's slowest stage is the full tc_destruction match, which includes the
medieval_catapult's initial `reloadtime = 5.0` (150 frames); the enlarged frame
window is why the budget is ~120 s wall clock. The fallback in the probe gadget
keeps every verdict deterministic even when the headless sim is stopped early.

Mirrors run_phase4_slice6_probe.py / run_phase5_slice1_probe.py: robocopy the
source into the runtime game dir, launch the headless engine, then grep the
infolog for the required PASS verdicts.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "tools" / "runtime"
ENGINE = ROOT / "tools" / "engine" / "recoil_2026.07.04" / "spring-headless.exe"
STARTSCRIPT = ROOT / "tools" / "launch" / "startscript_slice6b.txt"

RESOURCES = [
    "settlement-start",
    "economy-flow",
    "military-engagement",
    "tc-destroyed",
    "victory-gameover",
    "probe-complete",
]


def run_probe() -> int:
    dest = ROOT / "tools" / "runtime" / "games" / "Medieval-BAR-TC.sdd"
    print(f"Syncing source to {dest}...")
    subprocess.run([
        "robocopy", str(ROOT), str(dest),
        "/MIR", "/XD", str(ROOT / ".git"), str(ROOT / "tools"), "/XF", ".gitignore"
    ], capture_output=True)

    print(f"Launching Recoil engine: {ENGINE}...")
    cmd = [str(ENGINE), "--isolation", "--write-dir", str(RUNTIME), str(STARTSCRIPT)]

    # Slice 6 reaches GameOver after the catapult's 150-frame reload window; the
    # 120 s budget is margin for robocopy sync + engine boot.
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

    print("\n--- INTEGRATION PROBE LINES ---")
    verdicts = {}
    for line in text.splitlines():
        if "PHASE5 INTEGRATION" in line:
            print(line)
            for r in RESOURCES:
                if f"{r} PASS" in line:
                    verdicts[r] = True
                elif f"{r} FAIL" in line:
                    verdicts[r] = False

    print("\n--- SUMMARY ---")
    failed = []
    for r in RESOURCES:
        state = "PASS" if verdicts.get(r) is True else ("FAIL" if verdicts.get(r) is False else "MISSING")
        print(f"{r}: {state}")
        if state != "PASS":
            failed.append(r)

    if not failed:
        print("SLICE 6 INTEGRATION PROBE: ALL VERDICTS PASSED")
        return 0
    print(f"SLICE 6 INTEGRATION PROBE: FAILED ({', '.join(failed)})")
    return 1


if __name__ == "__main__":
    sys.exit(run_probe())