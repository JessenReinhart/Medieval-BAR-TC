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
    # The headless sim runs at roughly 28 frames/s. Phase 4 Slice 3 stages land at
    # frames 620 (spawn), 860 (craft verdicts) and 880 (recruit-gate verdict); the
    # Slice 4 upgrade stages then run at 920 (tech-gate baseline), 950 (chivalry
    # unlock), 990 (recruit-gate verdict) and 1030 (damage-multiplier verdict), so
    # ~42s of wall clock is needed. The timeout leaves generous headroom because
    # the 720:quitforce debugcommand does not terminate this engine build.
    try:
        proc = subprocess.run(cmd, timeout=200, capture_output=True, text=True)
        print(f"Engine exited {proc.returncode}")
    except subprocess.TimeoutExpired:
        print("Engine timed out (expected for headless run)")
    infolog = RUNTIME / "infolog.txt"
    if infolog.exists():
        text = infolog.read_text(encoding="utf-8", errors="replace")
        # Filter relevant phase probe lines (Phase 2 recruitment, Phase 3, Phase 4
        # probe/damage-matrix verdicts, the Phase 4 Slice 3 crafting verdicts and
        # the Phase 4 Slice 4 military-upgrade verdicts).
        relevant = [l for l in text.splitlines()
                    if "PHASE2 PROBE" in l or "PHASE3 PROBE" in l
                    or "PHASE4 PROBE" in l or "PHASE4 DMATRIX" in l
                    or "PHASE4 CRAFT" in l or "PHASE4 UPGRADE" in l]
        for line in relevant:
            print(line)
        print(f"[{len(relevant)} relevant probe lines]")
    else:
        print("No infolog generated")


if __name__ == "__main__":
    run_probe()
