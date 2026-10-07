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
    try:
        proc = subprocess.run(cmd, timeout=22, capture_output=True, text=True)
        print(f"Engine exited {proc.returncode}")
    except subprocess.TimeoutExpired:
        print("Engine timed out (expected for headless run)")
    infolog = RUNTIME / "infolog.txt"
    if infolog.exists():
        text = infolog.read_text(encoding="utf-8", errors="replace")
        # Filter relevant Phase2 lines for recruitment events.
        relevant = [l for l in text.splitlines() if "PHASE2" in l]
        for line in relevant[:50]:
            print(line)
    else:
        print("No infolog generated")

if __name__ == "__main__":
    run_probe()
