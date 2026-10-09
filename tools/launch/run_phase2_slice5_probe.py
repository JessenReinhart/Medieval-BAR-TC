import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "tools" / "runtime"
ENGINE = ROOT / "tools" / "engine" / "recoil_2026.07.04" / "spring-headless.exe"
STARTSCRIPT = ROOT / "tools" / "launch" / "startscript_phase2.txt"


def run_probe():
    print(f"Syncing source to {ROOT / 'tools' / 'runtime' / 'games' / 'Medieval-BAR-TC.sdd'}...")
    subprocess.run([
        "robocopy", str(ROOT), str(ROOT / 'tools' / 'runtime' / 'games' / 'Medieval-BAR-TC.sdd'),
        "/MIR", "/XD", str(ROOT / '.git'), str(ROOT / 'tools'), "/XF", ".gitignore"
    ], capture_output=True)
    print(f"Launching Recoil engine: {ENGINE}...")
    cmd = [str(ENGINE), "--isolation", "--write-dir", str(RUNTIME), str(STARTSCRIPT)]
    # The headless sim runs at roughly 28 frames/s. Slice 5's hauler stages run at
    # 1060 (hubs + cart spawned), 1094/1124 (off-road and on-road speed legs),
    # 1128 (deficit trigger + route verdict) and 1158..1200 (delivery verdict), so
    # the full stage completes around f=1200 (~43s of wall clock). The timeout
    # leaves generous headroom because the 720:quitforce debugcommand does not
    # terminate this engine build.
    try:
        proc = subprocess.run(cmd, timeout=220, capture_output=True, text=True)
        print(f"Engine exited {proc.returncode}")
    except subprocess.TimeoutExpired:
        print("Engine timed out (expected for headless run)")
    infolog = RUNTIME / "infolog.txt"
    if infolog.exists():
        text = infolog.read_text(encoding="utf-8", errors="replace")
        # Filter relevant phase probe lines (Phase 2 recruitment, Phase 3, Phase 4
        # probe/damage-matrix verdicts, the Slice 3 crafting verdicts, the Slice 4
        # military-upgrade verdicts and the Slice 5 hauler verdicts).
        relevant = [l for l in text.splitlines()
                    if "PHASE2 PROBE" in l or "PHASE3 PROBE" in l
                    or "PHASE4 PROBE" in l or "PHASE4 DMATRIX" in l
                    or "PHASE4 CRAFT" in l or "PHASE4 UPGRADE" in l
                    or "PHASE4 HAUL" in l]
        for line in relevant:
            print(line)
        print(f"[{len(relevant)} relevant probe lines]")
    else:
        print("No infolog generated")


if __name__ == "__main__":
    run_probe()
