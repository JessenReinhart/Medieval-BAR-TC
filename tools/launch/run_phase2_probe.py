import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "tools" / "runtime"
GAME_SDD = RUNTIME / "games" / "Medieval-BAR-TC.sdd"
ENGINE = ROOT / "tools" / "engine" / "recoil_2026.07.04" / "spring-headless.exe"
STARTSCRIPT = ROOT / "tools" / "launch" / "startscript_phase2.txt"

print(f"Syncing source to {GAME_SDD}...")
subprocess.run(
    ["robocopy", str(ROOT), str(GAME_SDD), "/MIR", "/XD", str(ROOT / ".git"), str(ROOT / "tools"), "/XF", ".gitignore"],
    capture_output=True,
)

print(f"Launching Recoil engine: {ENGINE}...")
cmd = [str(ENGINE), "--isolation", "--write-dir", str(RUNTIME), str(STARTSCRIPT)]
try:
    proc = subprocess.run(cmd, timeout=18, capture_output=True, text=True)
    print(f"Engine exited with returncode {proc.returncode}")
except subprocess.TimeoutExpired:
    print("Engine timed out after 18s (expected for headless run)")

infolog = RUNTIME / "infolog.txt"
if infolog.exists():
    text = infolog.read_text(encoding="utf-8", errors="replace")
    matches = [line for line in text.splitlines() if any(k in line for k in ["PHASE2", "Phase 1:", "Error:", "using game", "GameStart", "Medieval Economy", "Medieval Housing", "Medieval Gathering"])]
    print(f"--- Captured {len(matches)} relevant infolog lines ---")
    for m in matches[-60:]:
        print(m)
else:
    print("ERROR: infolog.txt not found!")
